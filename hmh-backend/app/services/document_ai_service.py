"""
Document AI service — PDF and image text extraction with graceful fallbacks.

Library priority:
  PDF  : PyMuPDF (fitz) → pdfplumber → pypdf → PyPDF2 → OCR fallback
  Image: pytesseract + Pillow → OCR_NOT_AVAILABLE

Never crashes. Always returns a structured result dict.

Output shape:
{
  "status": "EXTRACTED" | "OCR_REQUIRED" | "OCR_NOT_AVAILABLE" | "FAILED" | "NEEDS_REVIEW",
  "document_type": "INVOICE" | "DELIVERY_NOTE" | "QUOTE" | "OTHER",
  "raw_text": "...",
  "fields": { po_number, invoice_number, delivery_note_number, supplier_name,
               supplier_email, date, total_amount },
  "items": [ { description, unit, quantity, unit_price, line_total, confidence } ],
  "warnings": []
}
"""

import logging
import os
import re
from typing import Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)

# OCR_PROVIDER is read lazily on first use so that import order doesn't matter.
def _ocr_provider() -> str:
    from app.core.config import settings
    return (settings.OCR_PROVIDER or "local").lower()


def _resolve_credentials_path(raw: str) -> str:
    """
    Resolve GOOGLE_APPLICATION_CREDENTIALS to an absolute path.
    Relative paths are resolved relative to the hmh-backend/ project root
    (3 directories above this file: services/ → app/ → hmh-backend/).
    Inline JSON strings (starting with '{') are returned unchanged.
    """
    if not raw or raw.strip().startswith("{"):
        return raw
    if os.path.isabs(raw):
        return raw
    import pathlib
    base_dir = pathlib.Path(__file__).resolve().parent.parent.parent
    return str(base_dir / raw)


# Module-level cache for inline-JSON temp credential file (written once per process).
_cred_temp_path: Optional[str] = None


def _prepare_credentials() -> None:
    """
    Resolve Google Vision credentials and set GOOGLE_APPLICATION_CREDENTIALS env var.
    Priority:
      1. GOOGLE_CREDENTIALS_JSON  — full service-account JSON (recommended for Render)
      2. GOOGLE_APPLICATION_CREDENTIALS — file path (relative or absolute) or inline JSON
    Inline JSON is written to a temp file once per process and cached.
    """
    global _cred_temp_path
    from app.core.config import settings

    # Priority 1: GOOGLE_CREDENTIALS_JSON (explicit JSON string for cloud deployments)
    raw = settings.GOOGLE_CREDENTIALS_JSON or settings.GOOGLE_APPLICATION_CREDENTIALS
    if not raw:
        return

    if raw.strip().startswith("{"):
        # Inline JSON: write to a fixed path so redeploys overwrite rather than
        # accumulate orphaned files. Validated on every call but written only once.
        import json, pathlib
        if not _cred_temp_path:
            try:
                json.loads(raw)  # validate JSON before writing
            except json.JSONDecodeError as exc:
                logger.warning("Google credentials inline JSON is invalid: %s", exc)
                return
            fixed_path = str(pathlib.Path(__file__).resolve().parent.parent.parent / "hmh_gcp_creds.json")
            with open(fixed_path, "w") as f:
                f.write(raw)
            globals()["_cred_temp_path"] = fixed_path
            logger.info("vision credentials written to %s", fixed_path)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _cred_temp_path
    else:
        abs_path = _resolve_credentials_path(raw)
        if not os.path.exists(abs_path):
            logger.warning(
                "GOOGLE_APPLICATION_CREDENTIALS file not found: %s — "
                "on Render, set GOOGLE_CREDENTIALS_JSON to the full JSON content instead.",
                abs_path,
            )
            return
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path


def extract_text_via_google_vision(file_path: str) -> str:
    """
    Extract text from an image or PDF using Google Cloud Vision DOCUMENT_TEXT_DETECTION.
    Returns empty string on any error — never raises.
    OCR_PROVIDER must be "google_vision" and GOOGLE_APPLICATION_CREDENTIALS must point
    to a valid service-account JSON file (or inline JSON string).
    """
    try:
        from google.cloud import vision  # type: ignore

        _prepare_credentials()

        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            logger.warning(
                "Google Vision credentials not available for %s — "
                "set GOOGLE_CREDENTIALS_JSON (Render) or GOOGLE_APPLICATION_CREDENTIALS (local).",
                os.path.basename(file_path),
            )
            return ""

        client_v = vision.ImageAnnotatorClient()

        with open(file_path, "rb") as f:
            content = f.read()

        image    = vision.Image(content=content)
        response = client_v.document_text_detection(image=image)

        if response.error.message:
            logger.warning("Vision API error for %s: %s", file_path, response.error.message)
            return ""

        text = response.full_text_annotation.text or ""
        logger.info("vision extracted chars=%d file=%s", len(text), os.path.basename(file_path))
        return text

    except ImportError:
        logger.debug("google-cloud-vision not installed — falling back to local OCR")
        return ""
    except Exception as exc:
        logger.warning("Google Vision extraction failed for %s: %s", file_path, exc)
        return ""


def validate_ocr_setup() -> dict:
    """
    Check OCR configuration at startup.
    Returns dict: { provider, ready, message }
    Never raises — intended for diagnostic logging only.
    """
    provider = _ocr_provider()

    if provider == "disabled":
        return {"provider": "disabled", "ready": True, "message": "OCR disabled by config"}

    if provider == "google_vision":
        from app.core.config import settings
        cred = settings.GOOGLE_CREDENTIALS_JSON or settings.GOOGLE_APPLICATION_CREDENTIALS
        if not cred:
            return {
                "provider": "google_vision", "ready": False,
                "message": (
                    "No credentials set. On Render: set GOOGLE_CREDENTIALS_JSON to the full "
                    "service-account JSON. Locally: set GOOGLE_APPLICATION_CREDENTIALS to the "
                    "file path or inline JSON."
                ),
            }
        if cred.strip().startswith("{"):
            try:
                import json
                json.loads(cred)
                src = "GOOGLE_CREDENTIALS_JSON" if settings.GOOGLE_CREDENTIALS_JSON else "GOOGLE_APPLICATION_CREDENTIALS"
                label = f"inline JSON ({src})"
            except Exception:
                return {"provider": "google_vision", "ready": False, "message": "inline JSON is invalid"}
        else:
            abs_path = _resolve_credentials_path(cred)
            if not os.path.exists(abs_path):
                return {
                    "provider": "google_vision", "ready": False,
                    "message": (
                        f"credentials file not found: {abs_path}. "
                        "On Render, use GOOGLE_CREDENTIALS_JSON with the full JSON content."
                    ),
                }
            label = os.path.basename(abs_path)
        try:
            from google.cloud import vision  # type: ignore  # noqa: F401
            return {"provider": "google_vision", "ready": True, "message": f"credentials: {label}"}
        except ImportError:
            return {
                "provider": "google_vision", "ready": False,
                "message": "google-cloud-vision package not installed (run: pip install google-cloud-vision)",
            }

    # local tesseract
    try:
        import pytesseract  # type: ignore  # noqa: F401
        return {"provider": "local", "ready": True, "message": "pytesseract available"}
    except ImportError:
        return {
            "provider": "local", "ready": False,
            "message": "pytesseract not installed (OCR unavailable on Render without build config)",
        }

# ── Regex patterns ────────────────────────────────────────────────────────────

_PO_RE = re.compile(
    # (?!\w) guards on short abbreviations prevent mid-word false matches (e.g. "POLICY" via p\.?o\.?)
    # Mandatory separator in fallback alt prevents bare "PO" prefix from matching mid-word tokens
    r"(?:purchase[ \t]+order(?:[ \t]+(?:no\.?|number|#))?|po[ \t]+(?:no\.?|number|#)|p\.?o\.?(?!\w))[ \t]*[:\-]?[ \t]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(PO[-/ \t][A-Z0-9][A-Z0-9\-]{1,19})(?!\w)",
    re.IGNORECASE,
)
_INV_RE = re.compile(
    # inv\.?(?!\w) prevents "INVOICE" from being consumed by the inv abbreviation sub-alt
    # Mandatory separator [-/ \t] in fallback alt prevents "INVOICE" from matching as "INV" + "OICE"
    r"(?:invoice[ \t]+(?:no\.?|number|#)|tax[ \t]+invoice(?:[ \t]+(?:no\.?|number|#))?|inv\.?(?!\w)(?:[ \t]+(?:no\.?|number|#))?)[ \t]*[:\-]?[ \t]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(INV[-/ \t][A-Z0-9][A-Z0-9\-]{1,19})(?!\w)",
    re.IGNORECASE,
)
_DN_RE = re.compile(
    # d\.?n\.?(?!\w) prevents false matches on "DNA" etc.
    # Mandatory separator in fallback alt prevents bare "DN" prefix from matching mid-word tokens
    r"(?:delivery[ \t]+(?:note|no\.?)(?!\w)(?:[ \t]+(?:no\.?|number|#))?|d\.?n\.?(?!\w)|d/n)[ \t]*[:\-]?[ \t]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(DN[-/ \t][A-Z0-9][A-Z0-9\-]{1,19})(?!\w)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Supplier name: look for common label lines, capture text on the SAME line only (no newline)
# Patterns: "From:", "Supplier:", "Sold By:", "Vendor:", "Billed From:", "Company Name:"
_SUPPLIER_LABEL_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:from|supplier|sold\s+by|vendor|billed\s+from|company\s+name)"
    r"[ \t]*[:\-]?[ \t]*([A-Z][A-Za-z0-9&.,\t ()/]{2,60})",
    re.IGNORECASE | re.MULTILINE,
)
# Also match standalone header-style company names: two or more title-case words at line start
# (used as a last resort — only if label-based extraction found nothing)
_COMPANY_HEADER_RE = re.compile(
    r"^([A-Z][a-zA-Z]{1,30}(?:\s+[A-Z][a-zA-Z]{1,30}){1,4})\s*(?:\(PTY\)|\(Pty\)|Ltd|CC|Inc)?\s*$",
    re.MULTILINE,
)

# VAT amount (South African context: "VAT", "Tax Amount")
_VAT_RE = re.compile(
    r"(?:vat|tax\s+amount)\s*(?:@?\s*\d{1,2}%\s*)?\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Due date (separate from invoice date — look for "due", "payment due", "pay by")
_DUE_DATE_RE = re.compile(
    r"(?:due\s+date|payment\s+due|pay\s+by)\s*[:\-]?\s*"
    r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
    re.IGNORECASE,
)

_DATE_RE  = re.compile(
    r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
# ── Amount patterns ───────────────────────────────────────────────────────────
#
# _AMT_STRICT — used in total/subtotal patterns where the captured text is the
#   LAST or ONLY number on that section of line (no backtracking concern).
#   Handles: "12 200" (SA space-thousands), "12,200.00" (standard),
#            "12 200,50" (SA space+comma-decimal), "12200" (no separator).
_AMT = r"[\d][\d ,]*(?:[,.]\s*\d{1,2})?"

# _COL_SEP — two-or-more spaces / tab used as the separator BETWEEN table
#   columns.  A single space inside "12 200" (SA thousands) is NOT a column
#   separator, so requiring 2+ spaces here prevents the regex engine from
#   backtracking and splitting "12 200" into price="12" / total="200".
_COL_SEP = r"(?:[ \t]{2,}|\t)"

_TOTAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"total\s+due\s*[:\s]\s*R?\s*(" + _AMT + r")",      re.IGNORECASE), "Total Due"),
    (re.compile(r"amount\s+due\s*[:\s]\s*R?\s*(" + _AMT + r")",     re.IGNORECASE), "Amount Due"),
    (re.compile(r"invoice\s+total\s*[:\s]\s*R?\s*(" + _AMT + r")",  re.IGNORECASE), "Invoice Total"),
    (re.compile(r"grand\s+total\s*[:\s]\s*R?\s*(" + _AMT + r")",    re.IGNORECASE), "Grand Total"),
    (re.compile(r"net\s+total\s*[:\s]\s*R?\s*(" + _AMT + r")",      re.IGNORECASE), "Net Total"),
    # Generic "Total:" only when NOT part of "Subtotal" (negative lookbehind)
    (re.compile(r"(?<!\w)total\s*[:\s]\s*R?\s*(" + _AMT + r")",     re.IGNORECASE | re.MULTILINE), "Total"),
    # Subtotal only as a last resort
    (re.compile(r"subtotal\s*[:\s]\s*R?\s*(" + _AMT + r")",         re.IGNORECASE), "Subtotal"),
]

# ── Line-item patterns ─────────────────────────────────────────────────────────
#
# All patterns use _COL_SEP (2+ spaces / tab) between the price and total
# columns so a single-space SA thousands separator inside "12 200" is never
# mistaken for a column boundary.
#
# Pattern priority in _parse_line_items:
#   1. _LINE_RE      — 5-col: desc | qty | unit | price | total
#   2. _LINE_RE_SIMPLE — 4-col: desc | qty | price | total  (no unit column)
#   3. _LINE_RE_3COL — 3-col: desc | qty | [unit] | price  (no total column)
#      → The price is the LAST group so _AMT is fully greedy with no backtrack.
#      → Handles quotations and SA invoices that omit the line-total column.

_LINE_RE = re.compile(
    r"^(.{3,60}?)\s+(\d[\d,]*(?:\.\d+)?)\s+([a-zA-Z]{1,10})\s+R?\s*(" + _AMT + r")"
    + _COL_SEP + r"R?\s*(" + _AMT + r")\s*$",
    re.MULTILINE,
)
_LINE_RE_SIMPLE = re.compile(
    r"^(.{3,70}?)\s+(\d[\d,]*(?:\.\d+)?)\s+R?\s*(" + _AMT + r")"
    + _COL_SEP + r"R?\s*(" + _AMT + r")\s*$",
    re.MULTILINE,
)
# 3-col: no total column — price is last, greedy, no backtracking.
# Uses _COL_SEP between all columns so metadata / date lines (single-spaced)
# are not accidentally matched.
_LINE_RE_3COL = re.compile(
    r"^(.{3,70}?)" + _COL_SEP + r"(\d[\d,]*(?:\.\d+)?)(?:" + _COL_SEP
    + r"[a-zA-Z]{1,10})?" + _COL_SEP + r"R?\s*(" + _AMT + r")\s*$",
    re.MULTILINE,
)

# Subtotal (distinct from total — extracted separately for invoices)
_SUBTOTAL_RE = re.compile(
    r"subtotal\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Received / signed by — delivery notes
_RECEIVED_BY_RE = re.compile(
    r"(?:received\s+by|signed\s+by|collected\s+by|delivered\s+to)\s*[:\-]?\s*([A-Za-z][A-Za-z\s\.]{1,40})",
    re.IGNORECASE,
)

# Delivery note simple items: description  qty  unit
# Uses \s+ (not \s{2,}) because OCR from table images typically outputs a single
# tab or space between cells, not multiple spaces.  The non-greedy description
# match still prevents the separator from being swallowed into the description.
_DELIVERY_ITEM_RE = re.compile(
    r"^[ \t]*([A-Za-z][A-Za-z0-9 ,./\-]{2,50}?)\s+(\d[\d,]*(?:\.\d+)?)\s+([A-Za-z]{1,15})\s*$",
    re.MULTILINE,
)

# ── Fuel slip patterns ────────────────────────────────────────────────────────
_STATION_RE = re.compile(
    r"(?:station(?:\s+name)?|forecourt)\s*[:\-]?\s*([A-Za-z][A-Za-z0-9&.,\s\-]{2,50})",
    re.IGNORECASE,
)
_LITRES_RE = re.compile(
    r"(?:litres?|liters?|fuel\s+qty|qty|volume)\s*[:\-]?\s*([\d,]+\.?\d*)\s*(?:l|litres?|liters?)?",
    re.IGNORECASE,
)
_VEHICLE_REG_RE = re.compile(
    r"(?:vehicle|registration|reg\.?\s*no\.?|fleet\s*no\.?|rego|plate\s*no\.?)\s*[:\-]?\s*([A-Z]{1,3}\s*\d{1,4}\s*[A-Z0-9]{0,3}(?:\s*[A-Z]{0,2})?)",
    re.IGNORECASE,
)
_ODOMETER_RE = re.compile(
    r"(?:odometer|odo|mileage|km\s+reading|current\s+km|kms?)\s*[:\-]?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# ── Payment proof patterns ────────────────────────────────────────────────────
_PAID_AMOUNT_RE = re.compile(
    r"(?:amount\s+paid|paid\s+amount|payment\s+amount|amount\s+transferred|total\s+payment|debit\s+amount)\s*[:\-]?\s*R?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)
_PAYMENT_REF_RE = re.compile(
    r"(?:reference\s*(?:no\.?|number)?|ref\s*(?:no\.?|#)?|transaction\s*(?:id|ref|reference|number)?|payment\s*ref)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{1,30})",
    re.IGNORECASE,
)
_BENEFICIARY_RE = re.compile(
    r"(?:beneficiary|pay\s+to|payee|recipient|credit(?:ed)?\s+to|transferred\s+to|account\s+name)\s*[:\-]?\s*([A-Za-z][A-Za-z0-9&.,\s]{2,50})",
    re.IGNORECASE,
)


# ── PDF text extraction ───────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract selectable text from a PDF.
    Tries each library in turn; returns the first non-empty result.

    Priority: PyMuPDF (fitz) → pdfplumber → pypdf → PyPDF2
    """
    logger.debug("pdf text extraction starting file=%s", os.path.basename(file_path))

    # 1. PyMuPDF (fitz) — best quality
    try:
        import fitz  # type: ignore
        doc  = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            logger.debug("pdf fitz extracted chars=%d", len(text))
            return text
        logger.debug("pdf fitz no text found (scanned PDF?)")
    except ImportError:
        logger.debug("pdf fitz not installed")
    except Exception as exc:
        logger.warning("fitz PDF extraction failed: %s", exc)

    # 2. pdfplumber
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(file_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            logger.debug("pdf pdfplumber extracted chars=%d", len(text))
            return text
        logger.debug("pdf pdfplumber no text found")
    except ImportError:
        logger.debug("pdf pdfplumber not installed")
    except Exception as exc:
        logger.warning("pdfplumber PDF extraction failed: %s", exc)

    # 3. pypdf (pure Python, no binary dependencies)
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(file_path)
        pages  = [page.extract_text() or "" for page in reader.pages]
        text   = "\n".join(pages)
        if text.strip():
            logger.debug("pdf pypdf extracted chars=%d", len(text))
            return text
        logger.debug("pdf pypdf no text found")
    except ImportError:
        logger.debug("pdf pypdf not installed")
    except Exception as exc:
        logger.warning("pypdf PDF extraction failed: %s", exc)

    # 4. PyPDF2 (older API, same logic)
    try:
        import PyPDF2  # type: ignore
        with open(file_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            pages  = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        if text.strip():
            logger.debug("pdf PyPDF2 extracted chars=%d", len(text))
            return text
        logger.debug("pdf PyPDF2 no text found")
    except ImportError:
        logger.debug("pdf PyPDF2 not installed")
    except Exception as exc:
        logger.warning("PyPDF2 PDF extraction failed: %s", exc)

    logger.warning("pdf all extraction libraries exhausted file=%s", os.path.basename(file_path))
    return ""


# ── Image text extraction ─────────────────────────────────────────────────────

def extract_text_from_image(file_path: str) -> str:
    """Extract text from image via pytesseract. Returns empty if unavailable."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract     # type: ignore
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)
    except ImportError:
        return ""
    except Exception as exc:
        logger.warning("pytesseract extraction failed for %s: %s", file_path, exc)
        return ""


# ── Unified text extractor ────────────────────────────────────────────────────

def extract_document_text(file_path: str) -> tuple[str, str]:
    """
    Return (raw_text, status).
    status: EXTRACTED | OCR_REQUIRED | OCR_NOT_AVAILABLE | FAILED
    """
    if not os.path.exists(file_path):
        return ("", "FAILED")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        text = extract_text_from_pdf(file_path)
        logger.debug("pdf extracted chars=%d", len(text))
        if text.strip():
            return (text, "EXTRACTED")

        # No text found — PDF is scanned (or empty); try OCR
        logger.info("pdf ocr_fallback=required file=%s", os.path.basename(file_path))
        if _ocr_provider() == "disabled":
            return ("", "OCR_NOT_AVAILABLE")
        vision_attempted = False
        if _ocr_provider() == "google_vision":
            vision_attempted = True
            text = extract_text_via_google_vision(file_path)
            if text.strip():
                return (text, "OCR_EXTRACTED")
            # Vision failed — fall through to local tesseract
        try:
            from PIL import Image   # type: ignore
            import pytesseract      # type: ignore
            try:
                import fitz         # type: ignore
                import io
                doc    = fitz.open(file_path)
                texts  = []
                for page in doc:
                    pix      = page.get_pixmap(dpi=200)
                    img      = Image.open(io.BytesIO(pix.tobytes("png")))
                    texts.append(pytesseract.image_to_string(img))
                doc.close()
                combined = "\n".join(texts)
                logger.info("pdf ocr extracted chars=%d via fitz+tesseract", len(combined))
                return (combined, "OCR_EXTRACTED") if combined.strip() else ("", "EXTRACTION_FAILED")
            except ImportError:
                logger.debug("pdf fitz not available for OCR rendering")
        except ImportError:
            logger.debug("pdf pytesseract/Pillow not installed — OCR unavailable")
            return ("", "OCR_FAILED" if vision_attempted else "OCR_NOT_AVAILABLE")
        return ("", "OCR_REQUIRED")

    elif ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}:
        # Google Vision first (if configured)
        if _ocr_provider() == "google_vision":
            text = extract_text_via_google_vision(file_path)
            if text.strip():
                return (text, "OCR_EXTRACTED")
            # Vision configured but returned empty — try local tesseract as fallback
            text = extract_text_from_image(file_path)
            if text.strip():
                return (text, "OCR_EXTRACTED")
            # Both Vision and local OCR returned nothing
            return ("", "OCR_FAILED")
        elif _ocr_provider() == "disabled":
            return ("", "OCR_NOT_AVAILABLE")

        text = extract_text_from_image(file_path)
        if text.strip():
            return (text, "OCR_EXTRACTED")
        # Check if pytesseract is importable
        try:
            import pytesseract  # type: ignore  # noqa
            return ("", "EXTRACTION_FAILED")
        except ImportError:
            return ("", "OCR_NOT_AVAILABLE")

    else:
        # Try reading as plain text (e.g. .txt files in tests)
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            return (text, "EXTRACTED") if text.strip() else ("", "FAILED")
        except Exception:
            return ("", "FAILED")


# ── Field parsers ─────────────────────────────────────────────────────────────

def _extract_supplier_name(text: str) -> Optional[str]:
    """
    Extract supplier name using label-first strategy:
      1. Look for lines with explicit labels (From:, Supplier:, Vendor:, etc.)
      2. Fall back to header-style title-case company name near the top of the document
    Returns None if no confident match found.
    """
    # Strategy 1: labelled lines
    m = _SUPPLIER_LABEL_RE.search(text)
    if m:
        name = m.group(1).strip().rstrip(".,")
        if len(name) >= 3:
            return name

    # Strategy 2: title-case company header in the first 600 characters (letterhead area)
    header_region = text[:600]
    for m in _COMPANY_HEADER_RE.finditer(header_region):
        name = m.group(1).strip()
        # Skip common false positives
        if name.lower() in {"tax invoice", "purchase order", "delivery note", "invoice", "credit note", "receipt"}:
            continue
        if len(name) >= 4:
            return name

    return None


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    if not m:
        return None
    # Return first non-None capture group, or full match if no groups
    for g in m.groups():
        if g:
            return g.strip()
    return m.group(0).strip() or None


def _parse_amount(raw: Optional[str]) -> Optional[float]:
    """
    Parse a monetary string into a float, handling all common formats:

      Standard    "8,625.00"   "8 625.00"   comma/space=thousands, dot=decimal
      SA          "12 200,00"  "12 200,50"  space=thousands, comma=decimal
      European    "12.200,50"              dot=thousands, comma=decimal
      No-sep      "12200"      "12200.50"   plain digits

    Strategy:
      1. Strip R/ZAR prefix and leading/trailing whitespace.
      2. If both ',' and '.' present: whichever appears LAST is the decimal.
      3. If only ',': decimal if ≤2 digits follow it, thousands otherwise.
      4. If only '.': standard decimal.
      5. Remove space (SA/standard thousands separator) then parse.
    """
    if not raw:
        return None
    import re as _re
    s = raw.strip()
    # Strip currency prefix (R, ZAR) — e.g. "R 12 200" → "12 200"
    s = _re.sub(r'^(?:R|ZAR)\s*', '', s, flags=_re.IGNORECASE).strip()
    if not s:
        return None

    has_comma = ',' in s
    has_dot   = '.' in s

    try:
        if has_comma and has_dot:
            # Both separators present — last one is the decimal point
            if s.rfind('.') > s.rfind(','):
                # Standard: 1,234.56 or 1 234.56
                cleaned = s.replace(' ', '').replace(',', '')
            else:
                # European: 1.234,56 or 1 234,56
                cleaned = s.replace(' ', '').replace('.', '').replace(',', '.')
        elif has_comma:
            # Only comma — decimal if ≤2 digits follow last comma, else thousands
            after_last_comma = s.rsplit(',', 1)[-1].strip()
            if len(after_last_comma) <= 2:
                # SA/European decimal: "12 200,50" → 12200.50
                cleaned = s.replace(' ', '').replace(',', '.')
            else:
                # Comma thousands: "12,200" → 12200
                cleaned = s.replace(' ', '').replace(',', '')
        else:
            # Dot decimal or plain digits; remove spaces (SA/standard thousands)
            cleaned = s.replace(' ', '')

        return float(cleaned)
    except (ValueError, IndexError):
        return None


def _extract_total(text: str) -> Optional[float]:
    """
    Extract invoice total using strict priority order.
    Tries "Total Due" before "Total" so Subtotal is never returned
    when a real final total exists.
    """
    for pattern, label in _TOTAL_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_amount(m.group(1))
            if val is not None and val > 0:
                logger.debug("Total matched by '%s': %s", label, val)
                return val
    return None


def _parse_line_items(text: str) -> list[dict]:
    """
    Parse table rows into line items.

    Tries patterns in priority order:
      1. 5-col: desc | qty | unit | price | total
      2. 4-col: desc | qty | price | total  (no unit column)
      3. 3-col: desc | qty | [unit] | price  (no total column — SA quotations)

    All patterns use _COL_SEP (2+ spaces/tab) between price and total so a
    single space inside SA numbers like "12 200" is never split by backtracking.
    Pattern 3 is last-resort: the price group is final on the line, so _AMT
    is fully greedy and always captures "12 200" = 12 200 correctly.
    """
    items = []

    # 1. 5-col (desc | qty | unit | price | total)
    for m in _LINE_RE.finditer(text):
        desc, qty_s, unit, price_s, total_s = m.groups()
        qty   = _parse_amount(qty_s)
        price = _parse_amount(price_s)
        total = _parse_amount(total_s)
        if qty is None or price is None:
            continue
        items.append({
            "description": desc.strip(),
            "unit":        unit.strip(),
            "quantity":    qty,
            "unit_price":  price,
            "line_total":  total if total is not None else round(qty * price, 2),
            "confidence":  0.6,
        })

    if items:
        return items

    # 2. 4-col (desc | qty | price | total — no unit column)
    for m in _LINE_RE_SIMPLE.finditer(text):
        desc, qty_s, price_s, total_s = m.groups()
        qty   = _parse_amount(qty_s)
        price = _parse_amount(price_s)
        total = _parse_amount(total_s)
        if qty is None or price is None:
            continue
        items.append({
            "description": desc.strip(),
            "unit":        None,
            "quantity":    qty,
            "unit_price":  price,
            "line_total":  total if total is not None else round(qty * price, 2),
            "confidence":  0.5,
        })

    if items:
        return items

    # 3. 3-col (desc | qty | [unit] | price — no total column)
    # Handles SA quotations and any doc where the total is on a separate summary line.
    # Because price is the last capture group, _AMT is fully greedy and correctly
    # matches "12 200" (SA thousands) without being split by regex backtracking.
    for m in _LINE_RE_3COL.finditer(text):
        desc, qty_s, price_s = m.groups()
        qty   = _parse_amount(qty_s)
        price = _parse_amount(price_s)
        if qty is None or price is None or price < 0.01:
            continue
        items.append({
            "description": desc.strip(),
            "unit":        None,
            "quantity":    qty,
            "unit_price":  price,
            "line_total":  round(qty * price, 2),
            "confidence":  0.45,
        })

    return items


def _extract_subtotal(text: str) -> Optional[float]:
    m = _SUBTOTAL_RE.search(text)
    return _parse_amount(m.group(1)) if m else None


def _extract_received_by(text: str) -> Optional[str]:
    m = _RECEIVED_BY_RE.search(text)
    if m:
        name = m.group(1).strip().rstrip(".,")
        if 2 <= len(name) <= 40:
            return name
    return None


def _parse_delivery_items(text: str) -> list[dict]:
    """Parse simple 2-3 column delivery item rows (description, qty, unit)."""
    items = []
    for m in _DELIVERY_ITEM_RE.finditer(text):
        desc, qty_s, unit = m.group(1), m.group(2), m.group(3)
        qty = _parse_amount(qty_s)
        if qty is None:
            continue
        items.append({
            "description": desc.strip(),
            "unit":        unit.strip(),
            "quantity":    qty,
            "unit_price":  None,
            "line_total":  None,
            "confidence":  0.5,
        })
    return items


def parse_invoice_text(text: str) -> dict:
    """Extract structured fields from invoice text."""
    due_date   = _first_match(_DUE_DATE_RE, text)
    inv_date   = _first_match(_DATE_RE, text)
    vat_raw    = _first_match(_VAT_RE, text)
    vat_amount = _parse_amount(vat_raw) if vat_raw else None

    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       _first_match(_INV_RE,   text),
        "delivery_note_number": None,
        "supplier_name":        _extract_supplier_name(text),
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 inv_date,
        "due_date":             due_date,
        "total_amount":         _extract_total(text),
        "subtotal":             _extract_subtotal(text),
        "vat_amount":           vat_amount,
    }


def parse_delivery_note_text(text: str) -> dict:
    """Extract structured fields from delivery note text."""
    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       None,
        "delivery_note_number": _first_match(_DN_RE,    text),
        "supplier_name":        _extract_supplier_name(text),
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         None,
        "received_by":          _extract_received_by(text),
    }


def parse_quote_text(text: str) -> dict:
    """Extract structured fields from quote/quotation text, including line items."""
    line_items = _parse_quote_line_items(text)
    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       None,
        "delivery_note_number": None,
        "supplier_name":        _extract_supplier_name(text),
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         _extract_total(text),
        "subtotal":             _extract_subtotal(text),
        "line_items":           line_items,
    }


def _parse_quote_line_items(text: str) -> list[dict]:
    """
    Extract individual line items from a quotation document.

    Strategy (in order):
      1. Shared _parse_line_items (5-col → 4-col → 3-col with _COL_SEP separators).
      2. Quote-specific wide pattern (2+ space separator between all cols, R optional).
      3. Quote-specific SA-loose pattern: R is MANDATORY before price, single-space
         separators allowed.  The mandatory R eliminates false matches on date/metadata
         lines like "Approved by Admin  17 Jun 2026" where no R prefix is present.

    Returns [] when nothing parseable is found — callers must show a fallback.
    """
    import re as _re

    # 1. Shared invoice/delivery parser (includes 3-col SA fallback)
    items = _parse_line_items(text)
    if items:
        return items

    # 2. Wide-separator quotation pattern (desc 2+ spaces qty [unit] R price)
    _QUOTE_WIDE = _re.compile(
        r"^(.{3,60}?)\s{2,}(\d+(?:[.,]\d+)?)\s{1,}(?:[a-zA-Z]{1,6}\s{1,})?R?\s*([\d][\d ,]*(?:[,.]\s*\d{1,2})?)\s*$",
        _re.MULTILINE | _re.IGNORECASE,
    )
    wide: list[dict] = []
    for m in _QUOTE_WIDE.finditer(text):
        desc, qty_s, price_s = m.groups()
        qty   = _parse_amount(qty_s)
        price = _parse_amount(price_s)
        if qty is None or price is None or price < 0.01:
            continue
        wide.append({
            "description": desc.strip(),
            "unit":        None,
            "quantity":    qty,
            "unit_price":  price,
            "line_total":  round(qty * price, 2),
            "confidence":  0.4,
        })
    if wide:
        return wide

    # 3. SA loose pattern: single-space separators, R is MANDATORY before price.
    # Mandatory R prevents false matches on date lines, signature lines, etc.
    # The price group is last → _AMT greedily captures "12 200" without split.
    _QUOTE_SA_LOOSE = _re.compile(
        r"^([A-Za-z][A-Za-z0-9 ,.\-\/]{2,59}?)\s+(\d+(?:[.,]\d+)?)\s+(?:[a-zA-Z]{1,6}\s+)?R\s*([\d][\d ,]*(?:[,.]\s*\d{1,2})?)\s*$",
        _re.MULTILINE,
    )
    loose: list[dict] = []
    for m in _QUOTE_SA_LOOSE.finditer(text):
        desc, qty_s, price_s = m.groups()
        qty   = _parse_amount(qty_s)
        price = _parse_amount(price_s)
        if qty is None or price is None or price < 0.01:
            continue
        loose.append({
            "description": desc.strip(),
            "unit":        None,
            "quantity":    qty,
            "unit_price":  price,
            "line_total":  round(qty * price, 2),
            "confidence":  0.35,
        })
    return loose


def parse_purchase_order_text(text: str) -> dict:
    """Extract structured fields from a purchase order document."""
    vat_raw    = _first_match(_VAT_RE, text)
    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       None,
        "delivery_note_number": None,
        "supplier_name":        _extract_supplier_name(text),
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         _extract_total(text),
        "subtotal":             _extract_subtotal(text),
        "vat_amount":           _parse_amount(vat_raw) if vat_raw else None,
    }


def parse_fuel_slip_text(text: str) -> dict:
    """
    Extract structured fields from a fuel slip / petrol station receipt.

    Supports SA stations: BP, Shell, Sasol, Engen, Total, Caltex, Astron Energy.
    All extracted values are suggestions — NEVER auto-approved.
    """
    station = _first_match(_STATION_RE, text) or _extract_supplier_name(text)
    litres_raw = _first_match(_LITRES_RE, text)
    odo_raw    = _first_match(_ODOMETER_RE, text)

    return {
        "po_number":            None,
        "invoice_number":       None,
        "delivery_note_number": None,
        "supplier_name":        station,
        "supplier_email":       None,
        "date":                 _first_match(_DATE_RE, text),
        "total_amount":         _extract_total(text),
        "station_name":         station,
        "litres":               _parse_amount(litres_raw),
        "vehicle_registration": _first_match(_VEHICLE_REG_RE, text),
        "odometer":             _parse_amount(odo_raw),
    }


def parse_payment_proof_text(text: str) -> dict:
    """
    Extract structured fields from a payment proof / EFT confirmation.

    All extracted values are suggestions requiring human review.
    NEVER auto-approves payments.
    """
    paid_raw   = _first_match(_PAID_AMOUNT_RE, text)
    paid_amount = _parse_amount(paid_raw)

    return {
        "po_number":            None,
        "invoice_number":       None,
        "delivery_note_number": None,
        "supplier_name":        None,
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         paid_amount or _extract_total(text),
        "payment_date":         _first_match(_DATE_RE,  text),
        "paid_amount":          paid_amount,
        "reference_number":     _first_match(_PAYMENT_REF_RE, text),
        "beneficiary":          _first_match(_BENEFICIARY_RE, text),
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_document_data(file_path: str, document_type: str = "OTHER") -> dict:
    """
    Full pipeline: extract text → parse fields → return structured result.
    Never raises. Always returns the output shape.
    """
    result: dict = {
        "status":        "FAILED",
        "document_type": document_type,
        "raw_text":      "",
        "fields":        {
            # Core fields (all document types)
            "po_number":            None,
            "invoice_number":       None,
            "delivery_note_number": None,
            "supplier_name":        None,
            "supplier_email":       None,
            "date":                 None,
            "total_amount":         None,
            # Invoice-specific
            "subtotal":             None,
            "vat_amount":           None,
            "due_date":             None,
            # Delivery note-specific
            "received_by":          None,
            # Fuel slip-specific
            "station_name":         None,
            "litres":               None,
            "vehicle_registration": None,
            "odometer":             None,
            # Payment proof-specific
            "payment_date":         None,
            "paid_amount":          None,
            "reference_number":     None,
            "beneficiary":          None,
        },
        "items":    [],
        "warnings": [],
    }

    try:
        raw_text, status = extract_document_text(file_path)
        result["raw_text"] = raw_text
        result["status"]   = status

        if status in ("EXTRACTED", "OCR_EXTRACTED") and raw_text.strip():
            # EXTRACTION_FAILED if text is too short to contain useful data
            if len(raw_text.strip()) < 20:
                result["status"] = "EXTRACTION_FAILED"
                result["warnings"].append("Extracted text too short — document may be blank or unreadable.")
            else:
                doc_type = document_type.upper()
                if doc_type == "INVOICE":
                    parsed = parse_invoice_text(raw_text)
                    items  = _parse_line_items(raw_text)
                elif doc_type == "DELIVERY_NOTE":
                    parsed = parse_delivery_note_text(raw_text)
                    items  = _parse_delivery_items(raw_text) or _parse_line_items(raw_text)
                elif doc_type == "QUOTE":
                    parsed = parse_quote_text(raw_text)
                    items  = _parse_line_items(raw_text)
                elif doc_type == "PURCHASE_ORDER":
                    parsed = parse_purchase_order_text(raw_text)
                    items  = _parse_line_items(raw_text)
                elif doc_type == "FUEL_SLIP":
                    parsed = parse_fuel_slip_text(raw_text)
                    items  = []
                elif doc_type == "PAYMENT_PROOF":
                    parsed = parse_payment_proof_text(raw_text)
                    items  = []
                else:
                    parsed = parse_invoice_text(raw_text)
                    items  = _parse_line_items(raw_text)

                # Merge parsed fields into the full-schema default (additive — new keys win)
                result["fields"].update(parsed)
                result["items"] = items

                # Determine key reference field per document type
                key = (
                    result["fields"].get("invoice_number")       if doc_type == "INVOICE"
                    else result["fields"].get("delivery_note_number") if doc_type == "DELIVERY_NOTE"
                    else result["fields"].get("po_number")       if doc_type in ("PURCHASE_ORDER", "QUOTE")
                    else result["fields"].get("reference_number") if doc_type == "PAYMENT_PROOF"
                    else None
                )
                if not key:
                    result["status"] = "NEEDS_REVIEW"
                    result["warnings"].append(
                        "Key reference number could not be extracted — manual review required."
                    )

        elif status == "OCR_FAILED":
            result["warnings"].append(
                "Google Vision is configured but returned no text. "
                "Verify GOOGLE_CREDENTIALS_JSON is set correctly on Render, "
                "or check API quota and service account permissions."
            )
        elif status in {"OCR_REQUIRED", "OCR_NOT_AVAILABLE"}:
            result["warnings"].append(f"Text extraction not available ({status}) — manual data entry required.")

        elif status in ("FAILED", "EXTRACTION_FAILED"):
            result["warnings"].append("Could not read file — check file format and integrity.")

    except Exception as exc:
        logger.exception("extract_document_data failed for %s: %s", file_path, exc)
        result["status"] = "FAILED"
        result["warnings"].append(f"Unexpected error: {exc}")

    return result


# ── PO vs Invoice vs Delivery comparison ─────────────────────────────────────

def compare_po_invoice_delivery(
    po_id: str,
    invoice_id: Optional[str],
    delivery_note_id: Optional[str],
    db,
) -> dict:
    """
    Compare PO, invoice, and delivery note.
    Returns structured comparison result with per-item checks.
    """
    import uuid as _uuid

    checks = []
    alerts_created = []
    warnings = []
    overall = "MATCHED"

    try:
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
        from app.models.invoice import Invoice
        from app.models.delivery import Delivery, DeliveryItem

        po = db.get(PurchaseOrder, _uuid.UUID(str(po_id)))
        if not po:
            return {"status": "FAILED", "summary": "PO not found", "checks": [], "alerts_created": []}

        po_items = (
            db.query(PurchaseOrderItem)
            .filter(PurchaseOrderItem.purchase_order_id == po.id)
            .all()
        )

        invoice = db.get(Invoice, _uuid.UUID(str(invoice_id))) if invoice_id else None
        delivery = db.get(Delivery, _uuid.UUID(str(delivery_note_id))) if delivery_note_id else None
        delivery_items = (
            db.query(DeliveryItem).filter(DeliveryItem.delivery_id == delivery.id).all()
            if delivery else []
        )

        po_total = float(po.total_amount or 0)

        # ── Amount check
        if invoice:
            inv_total = float(invoice.total_amount or 0)
            amount_ok = abs(po_total - inv_total) < 0.05
            if not amount_ok:
                overall = "MISMATCH"
                checks.append({
                    "type": "AMOUNT",
                    "item": "Total",
                    "po_qty": po_total,
                    "invoice_qty": inv_total,
                    "delivery_qty": None,
                    "actual_received_qty": None,
                    "status": "MISMATCH",
                    "message": f"Invoice R{inv_total:,.2f} ≠ PO R{po_total:,.2f}",
                })
            else:
                checks.append({"type": "AMOUNT", "item": "Total", "status": "MATCHED",
                                "message": f"Amount matches R{po_total:,.2f}"})

        # ── Quantity checks per PO item
        for poi in po_items:
            ordered = float(poi.quantity_ordered or 0)
            received = float(poi.quantity_received or 0)
            outstanding = max(0.0, ordered - received)

            # Find matching delivery item by description similarity
            del_item = next(
                (d for d in delivery_items if _similar(d.description, poi.description)),
                None,
            )
            del_qty = float(del_item.quantity_received) if del_item else None

            if del_qty is not None and abs(del_qty - ordered) > 0.01:
                status_str = "MISMATCH"
                if overall == "MATCHED":
                    overall = "MISMATCH"
                msg = f"Delivered {del_qty} but PO ordered {ordered}"
            elif outstanding > 0:
                status_str = "MISMATCH"
                if overall == "MATCHED":
                    overall = "MISMATCH"
                msg = f"Only {received} received of {ordered} ordered — {outstanding} outstanding"
            else:
                status_str = "MATCHED"
                msg = f"Quantity matches: {ordered}"

            checks.append({
                "type":                 "QUANTITY",
                "item":                 poi.description,
                "po_qty":               ordered,
                "invoice_qty":          None,
                "delivery_qty":         del_qty,
                "actual_received_qty":  received,
                "status":               status_str,
                "message":              msg,
            })

        # ── Create alerts for mismatches
        if overall == "MISMATCH":
            _create_comparison_alert(db, po, "Procurement mismatch detected", checks)
            alerts_created.append("MISMATCH_ALERT")

        if not delivery:
            warnings.append("No delivery note linked — quantities unverified.")
        if not invoice:
            warnings.append("No invoice linked — amount check skipped.")

    except Exception as exc:
        logger.exception("compare_po_invoice_delivery error: %s", exc)
        return {"status": "FAILED", "summary": str(exc), "checks": [], "alerts_created": []}

    return {
        "status":         overall,
        "summary":        f"{len([c for c in checks if c['status'] == 'MATCHED'])} matched, "
                          f"{len([c for c in checks if c['status'] == 'MISMATCH'])} mismatched",
        "checks":         checks,
        "alerts_created": alerts_created,
        "warnings":       warnings,
    }


def _similar(a: str, b: str, threshold: float = 0.70) -> bool:
    """
    Return True if two strings are similar enough to be the same item.
    Uses exact match after normalization, then prefix check, then difflib ratio.
    """
    if not a or not b:
        return False
    a_c = re.sub(r"\W+", " ", a.lower()).strip()
    b_c = re.sub(r"\W+", " ", b.lower()).strip()
    if a_c == b_c:
        return True
    if len(a_c) >= 4 and a_c[:10] == b_c[:10]:
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a_c, b_c).ratio() >= threshold


def fuzzy_match_supplier(extracted_name: str, db) -> Optional[object]:
    """
    Find the best-matching Supplier record for an OCR-extracted name.
    Returns the Supplier with similarity ≥ 0.60, or None.
    Never raises — all exceptions are swallowed gracefully.
    """
    if not extracted_name:
        return None
    try:
        from app.models.supplier import Supplier
        from difflib import SequenceMatcher

        name_c = re.sub(r"\W+", " ", extracted_name.lower()).strip()
        suppliers = db.query(Supplier).filter(Supplier.name.isnot(None)).all()

        best, best_score = None, 0.0
        for s in suppliers:
            s_c = re.sub(r"\W+", " ", (s.name or "").lower()).strip()
            score = SequenceMatcher(None, name_c, s_c).ratio()
            if score > best_score:
                best_score = score
                best = s

        if best_score >= 0.60:
            logger.debug("fuzzy supplier match '%s' → '%s' score=%.2f", extracted_name, best.name, best_score)
            return best
        return None
    except Exception as exc:
        logger.debug("fuzzy_match_supplier failed for '%s': %s", extracted_name, exc)
        return None


def _create_comparison_alert(db, po, message: str, checks: list) -> None:
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        mismatches = [c for c in checks if c["status"] == "MISMATCH"]
        detail = "; ".join(c["message"] for c in mismatches[:3])
        db.add(SystemAlert(
            alert_type=AlertType.DELIVERY_MISMATCH,
            severity=AlertSeverity.HIGH,
            title=f"Mismatch — {po.po_number}",
            message=f"{message}: {detail}",
            status=AlertStatus.OPEN,
            project_id=po.project_id,
            notification_channel="whatsapp",
            created_at=now,
            sent_at=now,
        ))
        db.flush()
    except Exception:
        logger.exception("Failed to create comparison alert")
