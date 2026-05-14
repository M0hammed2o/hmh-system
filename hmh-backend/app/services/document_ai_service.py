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

logger = logging.getLogger(__name__)

# OCR_PROVIDER is read lazily on first use so that import order doesn't matter.
def _ocr_provider() -> str:
    from app.core.config import settings
    return (settings.OCR_PROVIDER or "local").lower()


def extract_text_via_google_vision(file_path: str) -> str:
    """
    Extract text from an image or PDF using Google Cloud Vision DOCUMENT_TEXT_DETECTION.
    Returns empty string on any error — never raises.
    OCR_PROVIDER must be "google_vision" and GOOGLE_APPLICATION_CREDENTIALS must point
    to a valid service-account JSON file.
    """
    try:
        from google.cloud import vision  # type: ignore
        from app.core.config import settings

        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ.setdefault(
                "GOOGLE_APPLICATION_CREDENTIALS", settings.GOOGLE_APPLICATION_CREDENTIALS
            )

        client_v = vision.ImageAnnotatorClient()
        with open(file_path, "rb") as f:
            content = f.read()

        image   = vision.Image(content=content)
        response = client_v.document_text_detection(image=image)

        if response.error.message:
            logger.warning("Vision API error for %s: %s", file_path, response.error.message)
            return ""

        text = response.full_text_annotation.text or ""
        print(f"[VISION] Extracted {len(text)} chars from {os.path.basename(file_path)}", flush=True)
        return text

    except ImportError:
        print("[VISION] google-cloud-vision not installed — falling back to local OCR", flush=True)
        return ""
    except Exception as exc:
        logger.warning("Google Vision extraction failed for %s: %s", file_path, exc)
        return ""

# ── Regex patterns ────────────────────────────────────────────────────────────

_PO_RE = re.compile(
    r"(?:purchase\s+order|p\.?o\.?)[:\s#-]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(PO[-/\s]?[A-Z0-9\-]{2,20})(?!\w)",
    re.IGNORECASE,
)
_INV_RE = re.compile(
    r"(?:invoice\s+(?:no|number|#)|tax\s+invoice|inv)[:\s#-]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(INV[-/\s]?[A-Z0-9\-]{2,20})(?!\w)",
    re.IGNORECASE,
)
_DN_RE = re.compile(
    r"(?:delivery\s+(?:note|no|number|#)|d\.?n\.?)[:\s#-]*([A-Z0-9][A-Z0-9\-]{1,20})"
    r"|(?<!\w)(DN[-/\s]?[A-Z0-9\-]{2,20})(?!\w)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_DATE_RE  = re.compile(
    r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    re.IGNORECASE,
)
# Invoice total patterns in strict priority order.
# (?<!\w) prevents matching "subtotal" when looking for "total".
# Each tuple: (regex, label)
_TOTAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"total\s+due\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",      re.IGNORECASE), "Total Due"),
    (re.compile(r"amount\s+due\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",     re.IGNORECASE), "Amount Due"),
    (re.compile(r"invoice\s+total\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",  re.IGNORECASE), "Invoice Total"),
    (re.compile(r"grand\s+total\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",    re.IGNORECASE), "Grand Total"),
    (re.compile(r"net\s+total\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",      re.IGNORECASE), "Net Total"),
    # Generic "Total:" only when NOT part of "Subtotal" (negative lookbehind)
    (re.compile(r"(?<!\w)total\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",     re.IGNORECASE | re.MULTILINE), "Total"),
    # Subtotal only as a last resort
    (re.compile(r"subtotal\s*[:\s]\s*R?\s*([\d,]+\.?\d*)",         re.IGNORECASE), "Subtotal"),
]

# Line-item pattern: handles comma-formatted numbers like 2,500.00
# Cols: description | qty | unit | unit_price | line_total
_LINE_RE = re.compile(
    r"^(.{3,60}?)\s+(\d[\d,]*(?:\.\d+)?)\s+([a-zA-Z]{1,10})\s+(\d[\d,]*(?:\.\d+)?)\s+(\d[\d,]*(?:\.\d+)?)\s*$",
    re.MULTILINE,
)


# ── PDF text extraction ───────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract selectable text from a PDF.
    Tries each library in turn; returns the first non-empty result.

    Priority: PyMuPDF (fitz) → pdfplumber → pypdf → PyPDF2
    """
    print(f"[PDF] Trying normal text extraction: {os.path.basename(file_path)}", flush=True)

    # 1. PyMuPDF (fitz) — best quality
    try:
        import fitz  # type: ignore
        doc  = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            print(f"[PDF] fitz: extracted {len(text)} chars", flush=True)
            return text
        print("[PDF] fitz: no text found (scanned PDF?)", flush=True)
    except ImportError:
        print("[PDF] fitz: not installed", flush=True)
    except Exception as exc:
        logger.warning("fitz PDF extraction failed: %s", exc)
        print(f"[PDF] fitz: error — {exc}", flush=True)

    # 2. pdfplumber
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(file_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            print(f"[PDF] pdfplumber: extracted {len(text)} chars", flush=True)
            return text
        print("[PDF] pdfplumber: no text found", flush=True)
    except ImportError:
        print("[PDF] pdfplumber: not installed", flush=True)
    except Exception as exc:
        logger.warning("pdfplumber PDF extraction failed: %s", exc)
        print(f"[PDF] pdfplumber: error — {exc}", flush=True)

    # 3. pypdf (pure Python, no binary dependencies)
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(file_path)
        pages  = [page.extract_text() or "" for page in reader.pages]
        text   = "\n".join(pages)
        if text.strip():
            print(f"[PDF] pypdf: extracted {len(text)} chars", flush=True)
            return text
        print("[PDF] pypdf: no text found", flush=True)
    except ImportError:
        print("[PDF] pypdf: not installed", flush=True)
    except Exception as exc:
        logger.warning("pypdf PDF extraction failed: %s", exc)
        print(f"[PDF] pypdf: error — {exc}", flush=True)

    # 4. PyPDF2 (older API, same logic)
    try:
        import PyPDF2  # type: ignore
        with open(file_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            pages  = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        if text.strip():
            print(f"[PDF] PyPDF2: extracted {len(text)} chars", flush=True)
            return text
        print("[PDF] PyPDF2: no text found", flush=True)
    except ImportError:
        print("[PDF] PyPDF2: not installed", flush=True)
    except Exception as exc:
        logger.warning("PyPDF2 PDF extraction failed: %s", exc)
        print(f"[PDF] PyPDF2: error — {exc}", flush=True)

    print("[PDF] All PDF text-extraction libraries exhausted", flush=True)
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
        print(f"[PDF] Extracted text length: {len(text)}", flush=True)
        if text.strip():
            print("[PDF] OCR fallback required: False", flush=True)
            return (text, "EXTRACTED")

        # No text found — PDF is scanned (or empty); try OCR
        print("[PDF] OCR fallback required: True", flush=True)
        if _ocr_provider() == "disabled":
            return ("", "OCR_NOT_AVAILABLE")
        if _ocr_provider() == "google_vision":
            text = extract_text_via_google_vision(file_path)
            if text.strip():
                return (text, "EXTRACTED")
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
                print(f"[PDF] OCR extracted {len(combined)} chars via fitz+tesseract", flush=True)
                return (combined, "EXTRACTED") if combined.strip() else ("", "FAILED")
            except ImportError:
                print("[PDF] fitz not available for OCR rendering", flush=True)
        except ImportError:
            print("[PDF] pytesseract/Pillow not installed — OCR_NOT_AVAILABLE", flush=True)
            return ("", "OCR_NOT_AVAILABLE")
        return ("", "OCR_REQUIRED")

    elif ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}:
        # Google Vision first (if configured)
        if _ocr_provider() == "google_vision":
            text = extract_text_via_google_vision(file_path)
            if text.strip():
                return (text, "EXTRACTED")
            # Vision failed — fall through to local
        elif _ocr_provider() == "disabled":
            return ("", "OCR_NOT_AVAILABLE")

        text = extract_text_from_image(file_path)
        if text.strip():
            return (text, "EXTRACTED")
        # Check if pytesseract is importable
        try:
            import pytesseract  # type: ignore  # noqa
            return ("", "FAILED")
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
    """Parse a string like '8,625.00' or '8 625.00' into a float."""
    if not raw:
        return None
    cleaned = raw.replace(" ", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
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
    Handles comma-formatted numbers (e.g. 2,500.00) in all numeric columns.
    """
    items = []
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
    return items


def parse_invoice_text(text: str) -> dict:
    """Extract structured fields from invoice text."""
    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       _first_match(_INV_RE,   text),
        "delivery_note_number": None,
        "supplier_name":        None,
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         _extract_total(text),
    }


def parse_delivery_note_text(text: str) -> dict:
    """Extract structured fields from delivery note text."""
    return {
        "po_number":            _first_match(_PO_RE,  text),
        "invoice_number":       None,
        "delivery_note_number": _first_match(_DN_RE,  text),
        "supplier_name":        None,
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE, text),
        "total_amount":         None,
    }


def parse_quote_text(text: str) -> dict:
    """Extract structured fields from quote/quotation text."""
    return {
        "po_number":            _first_match(_PO_RE,    text),
        "invoice_number":       None,
        "delivery_note_number": None,
        "supplier_name":        None,
        "supplier_email":       _first_match(_EMAIL_RE, text),
        "date":                 _first_match(_DATE_RE,  text),
        "total_amount":         _extract_total(text),
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
            "po_number":            None,
            "invoice_number":       None,
            "delivery_note_number": None,
            "supplier_name":        None,
            "supplier_email":       None,
            "date":                 None,
            "total_amount":         None,
        },
        "items":    [],
        "warnings": [],
    }

    try:
        raw_text, status = extract_document_text(file_path)
        result["raw_text"] = raw_text
        result["status"]   = status

        if status == "EXTRACTED" and raw_text.strip():
            doc_type = document_type.upper()
            if doc_type == "INVOICE":
                result["fields"] = parse_invoice_text(raw_text)
            elif doc_type == "DELIVERY_NOTE":
                result["fields"] = parse_delivery_note_text(raw_text)
            elif doc_type == "QUOTE":
                result["fields"] = parse_quote_text(raw_text)
            else:
                result["fields"] = parse_invoice_text(raw_text)

            result["items"] = _parse_line_items(raw_text)

            # Downgrade to NEEDS_REVIEW if key fields missing
            key = (
                result["fields"].get("invoice_number") if doc_type == "INVOICE"
                else result["fields"].get("delivery_note_number") if doc_type == "DELIVERY_NOTE"
                else None
            )
            if not key:
                result["status"] = "NEEDS_REVIEW"
                result["warnings"].append("Key reference number could not be extracted — manual review required.")

        elif status in {"OCR_REQUIRED", "OCR_NOT_AVAILABLE"}:
            result["warnings"].append(f"Text extraction not available ({status}) — manual data entry required.")

        elif status == "FAILED":
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


def _similar(a: str, b: str) -> bool:
    """Rough string similarity — first 10 chars match."""
    a, b = a.lower().strip()[:10], b.lower().strip()[:10]
    return a and b and a == b


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
