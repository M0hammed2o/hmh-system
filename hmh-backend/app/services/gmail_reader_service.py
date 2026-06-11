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
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ── Classification keywords ───────────────────────────────────────────────────

_INVOICE_KEYWORDS  = {"invoice", "inv", "tax invoice", "tax_invoice", "proforma"}
_DELIVERY_KEYWORDS = {"delivery note", "delivery_note", "dn-", "dn_", "dn ", " dn", "delivery", "receipt note"}
_QUOTE_KEYWORDS    = {"quote", "quotation", "pricing", "proposal"}
_PO_KEYWORDS       = {"purchase order", "purchase_order", "po-doc", "po_document"}
_FUEL_KEYWORDS     = {"fuel slip", "fuel_slip", "fuel receipt", "fuel_receipt", "petrol slip",
                      "diesel slip", "forecourt", "fuel log"}
_PAYMENT_KEYWORDS  = {"proof of payment", "proof_of_payment", "payment proof", "payment_proof",
                      "eft confirmation", "eft_confirmation", "bank confirmation", "payment confirmation",
                      "remittance advice", "remittance"}

# PO number pattern: PO-XXX, PO XXX, PO/XXX
_PO_RE = re.compile(r"\bPO[-/\s]?([A-Z0-9\-]+)\b", re.IGNORECASE)

# Attachment allowlist — unsupported MIME types are logged and skipped
_ALLOWED_MIMES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
})
# Accept by extension when the mail client sends a generic MIME type (e.g. application/octet-stream)
_ALLOWED_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


def _is_allowed_attachment(content_type: str, size_bytes: int, filename: str = "") -> bool:
    """Return True when the attachment is safe to save.

    Accepts by MIME type first; falls back to file extension because many mail
    clients (including Gmail forwarding) send PDFs as application/octet-stream.
    """
    if size_bytes > _MAX_ATTACHMENT_BYTES:
        return False
    ct = content_type.lower().split(";")[0].strip()
    if ct in _ALLOWED_MIMES:
        return True
    if filename:
        ext = os.path.splitext(filename.lower())[1]
        return ext in _ALLOWED_EXTENSIONS
    return False


def classify_document(filename: str, subject: str = "") -> str:
    """
    Return INVOICE, DELIVERY_NOTE, PURCHASE_ORDER, FUEL_SLIP, PAYMENT_PROOF,
    QUOTE, or OTHER based on filename + subject keywords.
    Pure function — no DB or I/O.

    Priority order: PAYMENT_PROOF > FUEL_SLIP > PURCHASE_ORDER >
                    INVOICE > DELIVERY_NOTE > QUOTE > OTHER
    """
    text = f"{filename} {subject}".lower()
    if any(k in text for k in _PAYMENT_KEYWORDS):
        return "PAYMENT_PROOF"
    if any(k in text for k in _FUEL_KEYWORDS):
        return "FUEL_SLIP"
    if any(k in text for k in _PO_KEYWORDS):
        return "PURCHASE_ORDER"
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
    "INVOICE":        "invoices",
    "DELIVERY_NOTE":  "delivery_notes",
    "QUOTE":          "quotes",
    "PURCHASE_ORDER": "purchase_orders",
    "FUEL_SLIP":      "fuel_slips",
    "PAYMENT_PROOF":  "payment_proofs",
    "OTHER":          "other",
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
    logger.info("gmail_attachment saved filename=%s path=%s exists=%s size=%d",
                filename, full_path, exists, len(payload))
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
    if _in_test:
        logger.info("[MOCK IMAP] Test env — skipping real IMAP fetch.")
        return {"fetched": 0, "saved": 0, "skipped": 0, "mock": True}
    if not settings.IMAP_ENABLED:
        logger.info("IMAP disabled (IMAP_ENABLED=false) — no emails fetched.")
        return {"fetched": 0, "saved": 0, "skipped": 0, "enabled": False, "message": "IMAP is disabled in this environment. Set IMAP_ENABLED=true to activate."}

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
                # Skip fully duplicate emails — but check for missing attachment files
                if message_id and db.query(IncomingEmail).filter(
                    IncomingEmail.message_id == message_id
                ).first():
                    existing_email = db.query(IncomingEmail).filter(
                        IncomingEmail.message_id == message_id
                    ).first()
                    _refetch_missing_attachments(db, existing_email, msg)
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
                seen_filenames: set = set()  # duplicate detection within same email
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

                    # Duplicate attachment guard (same filename within one email)
                    if filename in seen_filenames:
                        logger.info("gmail_att_skip filename=%s reason=duplicate_within_email", filename)
                        continue
                    seen_filenames.add(filename)

                    # MIME allowlist + size cap
                    content_type = part.get_content_type().lower()
                    if not _is_allowed_attachment(content_type, len(payload_bytes), filename):
                        logger.info(
                            "gmail_att_skip filename=%s content_type=%s size=%d reason=blocked",
                            filename, content_type, len(payload_bytes),
                        )
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


# ── Re-fetch missing attachment files ────────────────────────────────────────

def _refetch_missing_attachments(db, incoming_email, msg) -> None:
    """
    Called when an email already exists in DB (skip duplicate path).

    Two actions:
    1. For existing IncomingEmailAttachment records with missing files, re-download them.
    2. For attachment parts that were never imported (e.g. skipped due to old MIME filter),
       save them now so they are available for OCR.

    Never raises — skipping an existing email must not fail.
    """
    from app.models.incoming_email import IncomingEmailAttachment
    try:
        existing_atts = (
            db.query(IncomingEmailAttachment)
            .filter(IncomingEmailAttachment.incoming_email_id == incoming_email.id)
            .all()
        )
        existing_filenames = {a.filename for a in existing_atts}
        now = datetime.now(timezone.utc)

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            raw_fname = part.get_filename()
            if not raw_fname:
                continue
            filename = _decode_header_value(raw_fname)

            payload_bytes = part.get_payload(decode=True)
            if not payload_bytes:
                continue

            content_type = part.get_content_type().lower()

            if filename in existing_filenames:
                # Already has a DB record — check if file is missing on disk
                att = next((a for a in existing_atts if a.filename == filename), None)
                if att:
                    resolved, _ = _resolve_path(att.file_path)
                    if not resolved:
                        doc_type = att.detected_type or classify_document(filename, "")
                        new_path = _save_attachment(payload_bytes, filename, doc_type)
                        att.file_path = new_path
                        db.commit()
                        logger.info("gmail_refetch_att att_id=%s path=%s size=%d",
                                    att.id, new_path, len(payload_bytes))
            else:
                # New attachment — was never imported (e.g. old MIME filter blocked it)
                if not _is_allowed_attachment(content_type, len(payload_bytes), filename):
                    continue
                doc_type = classify_document(filename, incoming_email.subject or "")
                try:
                    file_path = _save_attachment(payload_bytes, filename, doc_type)
                    att = IncomingEmailAttachment(
                        id=uuid.uuid4(),
                        incoming_email_id=incoming_email.id,
                        filename=filename,
                        file_path=file_path,
                        content_type=content_type,
                        detected_type=doc_type,
                        created_at=now,
                    )
                    db.add(att)
                    db.flush()
                    _trigger_extraction(db, file_path, doc_type, str(att.id), now)
                    existing_filenames.add(filename)
                    logger.info("gmail_new_att_imported filename=%s email_id=%s",
                                filename, incoming_email.id)
                except Exception:
                    logger.exception("_refetch_missing_attachments new-att failed filename=%s", filename)

        # Update has_attachments flag
        updated_count = (
            db.query(IncomingEmailAttachment)
            .filter(IncomingEmailAttachment.incoming_email_id == incoming_email.id)
            .count()
        )
        if updated_count > 0 and not incoming_email.has_attachments:
            incoming_email.has_attachments = True
            db.commit()

    except Exception:
        logger.exception("_refetch_missing_attachments failed for email %s", incoming_email.id)


def _resolve_path(stored: str) -> tuple:
    """Return (resolved_absolute_path | None, candidates_tried)."""
    from app.core.config import settings as _s
    abs_upload = os.path.abspath(_s.UPLOAD_DIR)
    parent_dir = os.path.dirname(abs_upload)
    basename   = os.path.basename(stored) if stored else ""
    candidates = [
        stored,
        os.path.join(parent_dir, stored),
        os.path.join(abs_upload, stored),
        os.path.join(abs_upload, "gmail", basename),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c, candidates
    return None, candidates


def reimport_email_attachments(db: Session, email_id: uuid.UUID) -> dict:
    """
    Connect to IMAP, locate the email by Message-ID (works on already-SEEN messages),
    and import any attachments that were never saved (e.g. silently skipped by old MIME filter).

    Returns {"imported": N, "already_present": N, "skipped": N, "errors": list}.
    Raises ValueError with a human-readable message on fatal errors.
    """
    from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment

    incoming = db.get(IncomingEmail, email_id)
    if not incoming:
        raise ValueError(f"Email {email_id} not found.")
    if not incoming.message_id:
        raise ValueError("Email has no Message-ID — cannot locate in IMAP.")
    if not settings.IMAP_ENABLED:
        raise ValueError("IMAP is disabled. Set IMAP_ENABLED=true to reimport attachments.")
    if not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
        raise ValueError("IMAP credentials missing. Set IMAP_USERNAME and IMAP_PASSWORD.")

    existing_atts = (
        db.query(IncomingEmailAttachment)
        .filter(IncomingEmailAttachment.incoming_email_id == email_id)
        .all()
    )
    existing_filenames = {a.filename for a in existing_atts}

    try:
        imap = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        imap.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        imap.select("INBOX")

        mid = incoming.message_id.strip()
        _, data = imap.search(None, f'HEADER "Message-ID" "{mid}"')
        msg_ids = data[0].split() if data[0] else []

        if not msg_ids:
            for folder in ('"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "All Mail"):
                try:
                    rv, _ = imap.select(folder)
                    if rv != "OK":
                        continue
                    _, data = imap.search(None, f'HEADER "Message-ID" "{mid}"')
                    msg_ids = data[0].split() if data[0] else []
                    if msg_ids:
                        logger.debug("gmail_reimport found msg in folder=%s", folder)
                        break
                except Exception as fe:
                    logger.debug("IMAP folder=%s search failed: %s", folder, fe)

        if not msg_ids:
            raise ValueError(
                f"Email Message-ID={mid!r} not found in Gmail INBOX or All Mail. "
                "It may have been deleted or moved to an unlisted folder."
            )

        _, raw = imap.fetch(msg_ids[0], "(RFC822)")
        raw_bytes = raw[0][1] if raw and raw[0] else b""
        msg = email.message_from_bytes(raw_bytes)
        imap.logout()

    except (imaplib.IMAP4.error, OSError) as exc:
        raise ValueError(f"IMAP error: {exc}") from exc

    imported = 0
    already_present = 0
    skipped = 0
    errors: list = []
    now = datetime.now(timezone.utc)

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue
        raw_fname = part.get_filename()
        if not raw_fname:
            continue
        filename = _decode_header_value(raw_fname)

        payload_bytes = part.get_payload(decode=True)
        if not payload_bytes:
            continue

        content_type = part.get_content_type().lower()

        if filename in existing_filenames:
            already_present += 1
            continue

        if not _is_allowed_attachment(content_type, len(payload_bytes), filename):
            logger.info("gmail_reimport_skip filename=%s content_type=%s", filename, content_type)
            skipped += 1
            continue

        doc_type = classify_document(filename, incoming.subject or "")
        try:
            file_path = _save_attachment(payload_bytes, filename, doc_type)
            att = IncomingEmailAttachment(
                id=uuid.uuid4(),
                incoming_email_id=incoming.id,
                filename=filename,
                file_path=file_path,
                content_type=content_type,
                detected_type=doc_type,
                created_at=now,
            )
            db.add(att)
            db.flush()
            _trigger_extraction(db, file_path, doc_type, str(att.id), now)
            existing_filenames.add(filename)
            imported += 1
            logger.info("gmail_reimport_imported filename=%s email_id=%s", filename, email_id)
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
            logger.exception("reimport_email_attachments failed filename=%s", filename)

    if imported > 0 and not incoming.has_attachments:
        incoming.has_attachments = True
    db.commit()

    return {
        "email_id":       str(email_id),
        "imported":       imported,
        "already_present": already_present,
        "skipped":        skipped,
        "errors":         errors,
    }


def reimport_all_unprocessed(db: Session) -> dict:
    """
    For every email in the DB with has_attachments=False or processed_status=UNPROCESSED,
    reconnect to IMAP and import any missed attachments.

    Returns summary {"processed": N, "total_imported": N, "errors": list}.
    """
    from app.models.incoming_email import IncomingEmail

    emails = (
        db.query(IncomingEmail)
        .filter(
            (IncomingEmail.has_attachments == False) |  # noqa: E712
            (IncomingEmail.processed_status == "UNPROCESSED")
        )
        .all()
    )

    total_imported = 0
    processed = 0
    errors: list = []

    for e in emails:
        if not e.message_id:
            continue
        try:
            result = reimport_email_attachments(db, e.id)
            total_imported += result["imported"]
            processed += 1
        except Exception as exc:
            errors.append(f"email_id={e.id}: {exc}")
            logger.warning("reimport_all_unprocessed failed email_id=%s: %s", e.id, exc)

    return {"processed": processed, "total_imported": total_imported, "errors": errors}


def refetch_attachment_from_imap(db, att_id: uuid.UUID) -> dict:
    """
    Re-connect to IMAP, search for the parent email by Message-ID,
    find the attachment by original filename, save it, update file_path in DB.

    Returns {"att_id", "saved_path", "exists", "size"}.
    Raises ValueError with a human-readable message on any failure.
    """
    from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment

    att = db.get(IncomingEmailAttachment, att_id)
    if not att:
        raise ValueError(f"Attachment {att_id} not found.")

    parent = db.get(IncomingEmail, att.incoming_email_id)
    if not parent or not parent.message_id:
        raise ValueError("Cannot refetch: parent email has no Message-ID stored.")

    if not settings.IMAP_ENABLED:
        raise ValueError("IMAP is disabled. Set IMAP_ENABLED=true to refetch attachments.")

    if not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
        raise ValueError("IMAP credentials missing. Set IMAP_USERNAME and IMAP_PASSWORD.")

    try:
        imap = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        imap.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        imap.select("INBOX")

        # Search by Message-ID header — works for read AND unread messages.
        # Try INBOX first, then common Gmail All-Mail folder names as fallback.
        mid = parent.message_id.strip()
        _, data = imap.search(None, f'HEADER "Message-ID" "{mid}"')
        msg_ids = data[0].split() if data[0] else []

        if not msg_ids:
            for folder in ('"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "All Mail"):
                try:
                    rv, _ = imap.select(folder)
                    if rv != "OK":
                        continue
                    _, data = imap.search(None, f'HEADER "Message-ID" "{mid}"')
                    msg_ids = data[0].split() if data[0] else []
                    if msg_ids:
                        logger.debug("gmail_refetch found msg in folder=%s", folder)
                        break
                except Exception as fe:
                    logger.debug("IMAP folder=%s search failed: %s", folder, fe)

        if not msg_ids:
            raise ValueError(
                f"Email with Message-ID={mid!r} not found in Gmail INBOX or All Mail. "
                "The email may have been permanently deleted or archived in an unlisted folder. "
                "Re-fetch emails via the Gmail sync button to re-import it."
            )

        _, raw = imap.fetch(msg_ids[0], "(RFC822)")
        raw_bytes = raw[0][1] if raw and raw[0] else b""
        msg = email.message_from_bytes(raw_bytes)
        imap.logout()

        # Find the attachment part matching att.filename
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            raw_fname = part.get_filename()
            if not raw_fname:
                continue
            original_fname = _decode_header_value(raw_fname)
            if original_fname != att.filename:
                continue

            payload_bytes = part.get_payload(decode=True)
            if not payload_bytes:
                raise ValueError(f"Attachment '{att.filename}' has empty payload in Gmail.")

            doc_type = att.detected_type or classify_document(att.filename, "")
            new_path = _save_attachment(payload_bytes, att.filename, doc_type)
            att.file_path = new_path
            db.commit()

            exists = os.path.isfile(new_path)
            logger.info("gmail_refetch_attachment att_id=%s path=%s exists=%s size=%d",
                        att_id, new_path, exists, len(payload_bytes))
            return {"att_id": str(att_id), "saved_path": new_path, "exists": exists, "size": len(payload_bytes)}

        raise ValueError(
            f"Attachment '{att.filename}' was not found in the original email. "
            "The email may have been modified or the attachment removed."
        )

    except (imaplib.IMAP4.error, OSError) as exc:
        raise ValueError(f"IMAP error: {exc}") from exc


# ── Document AI extraction (triggered after attachment save) ──────────────────

def _trigger_extraction(db, file_path: str, doc_type: str, source_id: str, now) -> None:
    """
    Run document AI extraction on a saved Gmail attachment.
    Stores result in DocumentExtraction. Never raises — Gmail fetch must not fail
    because of an OCR error.

    On success: logs the best PO candidate (suggestion only — no records created).
    On failure: creates an OCR_EXTRACTION_FAILED alert for human follow-up.
    """
    import json
    try:
        from app.models.document_extraction import DocumentExtraction
        from app.services.document_ai_service import extract_document_data

        result = extract_document_data(file_path, doc_type)
        status = result["status"]

        extraction = DocumentExtraction(
            source_type="GMAIL_ATTACHMENT",
            source_id=uuid.UUID(source_id) if source_id else None,
            file_path=file_path,
            document_type=doc_type,
            status=status,
            raw_text=result.get("raw_text", ""),
            extracted_json=json.dumps(result),
            created_at=now,
        )
        db.add(extraction)
        db.flush()

        # Log PO candidate when extraction succeeded (suggestion only)
        if status in ("EXTRACTED", "OCR_EXTRACTED", "NEEDS_REVIEW"):
            fields = result.get("fields", {})
            po_num = fields.get("po_number")
            if po_num:
                try:
                    from app.services.procurement_matching_service import _find_po_by_number
                    po = _find_po_by_number(db, po_num)
                    if po:
                        logger.info("[GMAIL] PO candidate found: %s → %s (human review required)",
                                    doc_type, po.po_number)
                except Exception:
                    pass

        # Alert when OCR could not extract usable text
        elif status in ("EXTRACTION_FAILED", "OCR_NOT_AVAILABLE", "FAILED"):
            try:
                from app.models.alert import SystemAlert
                from app.models.enums import AlertType, AlertSeverity, AlertStatus
                import os as _os
                db.add(SystemAlert(
                    alert_type=AlertType.OCR_EXTRACTION_FAILED,
                    severity=AlertSeverity.LOW,
                    title=f"OCR extraction failed — {_os.path.basename(file_path)}",
                    message=(
                        f"Could not extract text from attachment '{_os.path.basename(file_path)}' "
                        f"(type: {doc_type}, status: {status}). Manual data entry required."
                    ),
                    status=AlertStatus.OPEN,
                    notification_channel="in_app",
                    created_at=now,
                ))
                db.flush()
            except Exception:
                logger.exception("OCR failure alert creation failed for %s", file_path)

    except Exception:
        logger.exception("_trigger_extraction failed for %s — fetch continues", file_path)
