"""
Gmail IMAP reader — fetches unread procurement emails, saves attachments locally,
and stores metadata in the incoming_emails / incoming_email_attachments tables.

Config read from settings:
    IMAP_ENABLED   — false = mock/skip (no connection attempted)
    IMAP_HOST      — imap.gmail.com
    IMAP_PORT      — 993
    IMAP_USERNAME  — Gmail address
    IMAP_PASSWORD  — App password

Attachments are saved to:
    uploads/gmail/invoices/
    uploads/gmail/delivery_notes/
    uploads/gmail/quotes/
    uploads/gmail/other/
"""

import email
import imaplib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Classification keywords ───────────────────────────────────────────────────

_INVOICE_KEYWORDS = {"invoice", "inv", "tax invoice", "tax_invoice", "proforma"}
_DELIVERY_KEYWORDS = {"delivery note", "delivery_note", "dn-", "dn_", "dn ", " dn", "delivery", "receipt note"}
_QUOTE_KEYWORDS = {"quote", "quotation", "pricing", "proposal"}

# PO number pattern: PO-XXX, PO XXX, PO/XXX
_PO_RE = re.compile(r"\bPO[-/\s]?([A-Z0-9\-]+)\b", re.IGNORECASE)


def classify_document(filename: str, subject: str = "") -> str:
    """
    Return INVOICE, DELIVERY_NOTE, QUOTE, or OTHER based on filename + subject keywords.
    Pure function — no DB or I/O.
    """
    text = f"{filename} {subject}".lower()
    if any(k in text for k in _INVOICE_KEYWORDS):
        return "INVOICE"
    if any(k in text for k in _DELIVERY_KEYWORDS):
        return "DELIVERY_NOTE"
    if any(k in text for k in _QUOTE_KEYWORDS):
        return "QUOTE"
    return "OTHER"


def extract_po_number(text: str) -> Optional[str]:
    """Return the first PO reference found in text, or None."""
    m = _PO_RE.search(text or "")
    return m.group(0).upper().replace(" ", "-").replace("/", "-") if m else None


# ── Subfolder mapping ─────────────────────────────────────────────────────────

_TYPE_DIR = {
    "INVOICE":       "invoices",
    "DELIVERY_NOTE": "delivery_notes",
    "QUOTE":         "quotes",
    "OTHER":         "other",
}


def _save_attachment(payload: bytes, filename: str, doc_type: str) -> str:
    """
    Save bytes to disk and return the ABSOLUTE file path.

    Storing the absolute path in the DB ensures the download endpoint can
    locate the file regardless of the process working directory.
    """
    subdir = _TYPE_DIR.get(doc_type, "other")
    save_dir = os.path.join(settings.UPLOAD_DIR, "gmail", subdir)
    os.makedirs(save_dir, exist_ok=True)

    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    full_path = os.path.abspath(os.path.join(save_dir, unique_name))

    with open(full_path, "wb") as f:
        f.write(payload)

    exists = os.path.isfile(full_path)
    logger.info("[GMAIL-SAVE-ATTACHMENT] filename=%s saved_path=%s exists=%s size=%d",
                filename, full_path, exists, len(payload))
    print(
        f"[GMAIL-SAVE-ATTACHMENT] filename={filename!r}"
        f" saved_path={full_path!r}"
        f" exists={exists}"
        f" size={len(payload)}",
        flush=True,
    )
    return full_path


def _decode_header_value(raw: str) -> str:
    parts = decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


# ── Mock mode ─────────────────────────────────────────────────────────────────

def fetch_procurement_emails(db: Session, limit: int = 20) -> dict:
    """
    Fetch unread emails from the procurement Gmail inbox via IMAP.

    Returns:
        {"fetched": int, "saved": int, "skipped": int, "mock": bool}
    """
    # Never hit live Gmail in pytest — same guard as email_service SMTP
    import os as _os
    _in_test = bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"
    if not settings.IMAP_ENABLED or _in_test:
        logger.info("[MOCK IMAP] IMAP disabled or test env — returning empty result.")
        return {"fetched": 0, "saved": 0, "skipped": 0, "mock": True}

    if not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
        logger.warning("IMAP credentials not set. Set IMAP_USERNAME and IMAP_PASSWORD in .env.")
        return {"fetched": 0, "saved": 0, "skipped": 0, "mock": False, "error": "Credentials missing"}

    return _fetch_via_imap(db, limit)


# ── Real IMAP fetch ───────────────────────────────────────────────────────────

def _fetch_via_imap(db: Session, limit: int) -> dict:
    from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment

    counts = {"fetched": 0, "saved": 0, "skipped": 0, "mock": False}

    try:
        imap = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        imap.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        imap.select("INBOX")

        _, data = imap.search(None, "UNSEEN")
        msg_ids = (data[0].split() if data[0] else [])[-limit:]  # newest last

        for msg_num in msg_ids:
            counts["fetched"] += 1
            try:
                _, raw = imap.fetch(msg_num, "(RFC822)")
                raw_email = raw[0][1] if raw and raw[0] else b""
                msg = email.message_from_bytes(raw_email)

                message_id = msg.get("Message-ID", "").strip()
                # Skip duplicates
                if message_id and db.query(IncomingEmail).filter(
                    IncomingEmail.message_id == message_id
                ).first():
                    counts["skipped"] += 1
                    continue

                subject   = _decode_header_value(msg.get("Subject", ""))
                from_raw  = _decode_header_value(msg.get("From", ""))
                date_str  = msg.get("Date", "")

                # Extract plain email address
                from_email = re.search(r"<([^>]+)>", from_raw)
                from_email = from_email.group(1) if from_email else from_raw.strip()

                received_at: Optional[datetime] = None
                try:
                    received_at = parsedate_to_datetime(date_str) if date_str else None
                except Exception:
                    pass

                # Build body snippet from text part
                body_snippet = ""
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and not body_snippet:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_snippet = payload.decode("utf-8", errors="replace")[:500]

                # Detect PO number in subject/body
                matched_po = extract_po_number(subject) or extract_po_number(body_snippet)

                now = datetime.now(timezone.utc)
                incoming = IncomingEmail(
                    id=uuid.uuid4(),
                    message_id=message_id or None,
                    from_email=from_email,
                    subject=subject,
                    body_snippet=body_snippet,
                    received_at=received_at or now,
                    has_attachments=False,
                    processed_status="UNPROCESSED",
                    matched_po_number=matched_po,
                    created_at=now,
                )
                db.add(incoming)
                db.flush()

                # Process attachments
                att_count = 0
                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if part.get("Content-Disposition") is None:
                        continue

                    filename = part.get_filename()
                    if not filename:
                        continue
                    filename = _decode_header_value(filename)

                    payload_bytes = part.get_payload(decode=True)
                    if not payload_bytes:
                        continue

                    doc_type  = classify_document(filename, subject)
                    file_path = _save_attachment(payload_bytes, filename, doc_type)

                    att = IncomingEmailAttachment(
                        id=uuid.uuid4(),
                        incoming_email_id=incoming.id,
                        filename=filename,
                        file_path=file_path,
                        content_type=part.get_content_type(),
                        detected_type=doc_type,
                        created_at=now,
                    )
                    db.add(att)
                    db.flush()
                    att_count += 1

                    # Trigger Document AI extraction (best-effort, never fails fetch)
                    _trigger_extraction(db, file_path, doc_type, str(att.id), now)

                if att_count > 0:
                    incoming.has_attachments = True

                db.commit()
                counts["saved"] += 1

                # Mark as read only after successful save
                imap.store(msg_num, "+FLAGS", "\\Seen")

            except Exception:
                logger.exception("Error processing email %s", msg_num)
                try:
                    db.rollback()
                except Exception:
                    pass

        imap.logout()

    except imaplib.IMAP4.error as exc:
        logger.error("IMAP connection error: %s", exc)
        counts["error"] = str(exc)

    return counts


# ── Document AI extraction (triggered after attachment save) ──────────────────

def _trigger_extraction(db, file_path: str, doc_type: str, source_id: str, now) -> None:
    """
    Run document AI extraction on a saved Gmail attachment.
    Stores result in DocumentExtraction. Never raises — Gmail fetch must not fail
    because of an OCR error.
    """
    import json
    try:
        from app.models.document_extraction import DocumentExtraction
        from app.services.document_ai_service import extract_document_data

        result = extract_document_data(file_path, doc_type)

        extraction = DocumentExtraction(
            source_type="GMAIL_ATTACHMENT",
            source_id=None,          # attachment UUID stored as string source_id isn't UUID FK
            file_path=file_path,
            document_type=doc_type,
            status=result["status"],
            raw_text=result.get("raw_text", ""),
            extracted_json=json.dumps(result),
            created_at=now,
        )
        db.add(extraction)
        db.flush()

        # If extracted OK, try auto-match to a PO
        if result["status"] in ("EXTRACTED", "NEEDS_REVIEW"):
            fields = result.get("fields", {})
            po_num = fields.get("po_number")
            if po_num and doc_type == "INVOICE":
                from app.services.procurement_matching_service import _find_po_by_number
                po = _find_po_by_number(db, po_num)
                if po:
                    logger.info("[GMAIL] Auto-matched %s to %s", doc_type, po.po_number)

    except Exception:
        logger.exception("_trigger_extraction failed for %s — fetch continues", file_path)
