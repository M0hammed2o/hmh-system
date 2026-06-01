"""
Gmail procurement inbox endpoints.

POST /gmail/fetch                          — trigger IMAP fetch
GET  /gmail/incoming                       — list fetched emails
GET  /gmail/incoming/{id}                  — single email + attachments
POST /gmail/incoming/{id}/process          — extract + classify + match all attachments
POST /gmail/incoming/{id}/suggest          — OCR → PO matching → reconciliation suggestions
GET  /gmail/attachments/{id}               — single attachment metadata

POST /invoices/from-gmail/{att_id}         — create Invoice from Gmail attachment
POST /delivery-notes/from-gmail/{att_id}   — link Gmail attachment to a Delivery
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.logging_config import get_logger
from app.dependencies import OFFICE_AND_ABOVE, CurrentUser, DbSession
from app.schemas.common import ApiSuccess

logger = get_logger(__name__)

gmail_router      = APIRouter(prefix="/gmail",          tags=["gmail"])
gmail_docs_router = APIRouter(prefix="",                tags=["gmail"])   # for /invoices/from-gmail etc.


# ── Email config status ───────────────────────────────────────────────────────

@gmail_router.get("/email-config", dependencies=[OFFICE_AND_ABOVE])
def get_email_config():
    """Return whether SMTP and IMAP are configured."""
    from app.core.config import settings
    return ApiSuccess(data={
        "smtp_enabled": bool(getattr(settings, "SMTP_ENABLED", False)),
        "imap_enabled": bool(getattr(settings, "IMAP_ENABLED", False)),
    })


# ── Fetch trigger ─────────────────────────────────────────────────────────────

@gmail_router.post("/fetch", dependencies=[OFFICE_AND_ABOVE])
def fetch_emails(db: DbSession, limit: int = 20):
    """Trigger an IMAP fetch of unread procurement emails."""
    from app.services.gmail_reader_service import fetch_procurement_emails
    result = fetch_procurement_emails(db, limit=limit)
    return ApiSuccess(data=result, message="Fetch complete.")


# ── Incoming email list ───────────────────────────────────────────────────────

@gmail_router.get("/incoming", dependencies=[OFFICE_AND_ABOVE])
def list_incoming(
    db: DbSession,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List incoming emails, newest first."""
    from app.models.incoming_email import IncomingEmail

    q = db.query(IncomingEmail).order_by(IncomingEmail.received_at.desc())
    if status:
        q = q.filter(IncomingEmail.processed_status == status.upper())
    total = q.count()
    emails = q.offset(offset).limit(limit).all()

    return ApiSuccess(data={
        "total": total,
        "items": [_email_summary(e) for e in emails],
    })


@gmail_router.get("/incoming/{email_id}", dependencies=[OFFICE_AND_ABOVE])
def get_incoming(email_id: uuid.UUID, db: DbSession):
    """Get a single incoming email with its attachments."""
    from app.models.incoming_email import IncomingEmail
    from sqlalchemy.orm import joinedload

    e = (
        db.query(IncomingEmail)
        .options(joinedload(IncomingEmail.attachments))
        .filter(IncomingEmail.id == email_id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="Email not found.")

    return ApiSuccess(data={
        **_email_summary(e),
        "body_snippet": e.body_snippet,
        "attachments": [_att_summary(a) for a in e.attachments],
    })


@gmail_router.post("/incoming/{email_id}/process", dependencies=[OFFICE_AND_ABOVE])
def process_email(email_id: uuid.UUID, db: DbSession):
    """
    Process all attachments in an incoming email:
    extract text → classify → match to MR → create alerts on mismatch.
    Updates email processed_status to PROCESSED or PROCESSING_FAILED.
    """
    import json
    from datetime import datetime, timezone
    from sqlalchemy.orm import joinedload
    from app.models.incoming_email import IncomingEmail
    from app.models.document_extraction import DocumentExtraction
    from app.services.document_ai_service import extract_document_data

    logger.info("gmail_process email_id=%s", email_id)

    email = (
        db.query(IncomingEmail)
        .options(joinedload(IncomingEmail.attachments))
        .filter(IncomingEmail.id == email_id)
        .first()
    )
    if not email:
        raise HTTPException(status_code=404, detail="Email not found.")

    if not email.attachments:
        return ApiSuccess(data={"results": [], "processed_status": "UNPROCESSED"},
                          message="No attachments to process.")

    now      = datetime.now(timezone.utc)
    results  = []
    any_done = False

    for att in email.attachments:
        logger.debug("gmail_att filename=%s type=%s", att.filename, att.detected_type)

        # ── Extract ──────────────────────────────────────────────────────────
        ext_result = extract_document_data(att.file_path, att.detected_type)
        raw_text   = ext_result.get("raw_text", "")
        fields     = ext_result.get("fields", {})
        items      = ext_result.get("items", [])

        logger.info("gmail_extract status=%s chars=%d", ext_result['status'], len(raw_text))

        # ── Match MR ─────────────────────────────────────────────────────────
        mr_match = _match_mr_from_text(db, raw_text, fields, items)
        logger.debug("gmail_mr_match status=%s ref=%s", mr_match['status'], mr_match.get('mr_number'))

        # ── Store/update DocumentExtraction ───────────────────────────────────
        payload = {**ext_result, "mr_match": mr_match}
        existing = (
            db.query(DocumentExtraction)
            .filter(
                DocumentExtraction.source_type == "GMAIL_ATTACHMENT",
                DocumentExtraction.source_id   == att.id,
            )
            .first()
        )
        if existing:
            existing.status        = ext_result["status"]
            existing.raw_text      = raw_text
            existing.extracted_json = json.dumps(payload)
        else:
            db.add(DocumentExtraction(
                source_type   = "GMAIL_ATTACHMENT",
                source_id     = att.id,
                file_path     = att.file_path,
                document_type = att.detected_type,
                status        = ext_result["status"],
                raw_text      = raw_text,
                extracted_json = json.dumps(payload),
                created_at    = now,
            ))

        if ext_result["status"] in ("EXTRACTED", "NEEDS_REVIEW"):
            any_done = True

        # ── Alerts ───────────────────────────────────────────────────────────
        if mr_match["status"] == "MISMATCH":
            _gmail_alert(
                db, email,
                f"Invoice quantity mismatch — {mr_match.get('mr_number')}",
                mr_match.get("mismatch_detail", "Quantity on document differs from MR."),
                "HIGH", now,
            )
        elif mr_match["status"] == "NOT_FOUND":
            _gmail_alert(
                db, email,
                f"MR not found — {mr_match.get('mr_number') or att.filename}",
                "Could not match this document to any Material Request.",
                "MEDIUM", now,
            )

        results.append({
            "attachment_id":    str(att.id),
            "filename":         att.filename,
            "detected_type":    att.detected_type,
            "extraction_status": ext_result["status"],
            "fields":           fields,
            "items":            items,
            "mr_match":         mr_match,
            "warnings":         ext_result.get("warnings", []),
        })

    # ── Update email status ───────────────────────────────────────────────────
    email.processed_status = "PROCESSED" if any_done else "PROCESSING_FAILED"
    db.commit()

    logger.info("gmail_process done status=%s attachments=%d", email.processed_status, len(results))
    return ApiSuccess(data={
        "email_id":        str(email_id),
        "processed_status": email.processed_status,
        "results":         results,
    })


@gmail_router.post("/incoming/{email_id}/suggest", dependencies=[OFFICE_AND_ABOVE])
def suggest_reconciliation(email_id: uuid.UUID, db: DbSession):
    """
    Run the OCR → PO matching pipeline for every attachment on an incoming email
    and return reconciliation suggestions for human review.

    NEVER creates Invoice, Delivery, Payment, or any business record.
    Every suggestion includes requires_review=True — human approval is always required.
    """
    from sqlalchemy.orm import joinedload
    from app.models.incoming_email import IncomingEmail
    from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion

    email = (
        db.query(IncomingEmail)
        .options(joinedload(IncomingEmail.attachments))
        .filter(IncomingEmail.id == email_id)
        .first()
    )
    if not email:
        raise HTTPException(status_code=404, detail="Email not found.")

    if not email.attachments:
        return ApiSuccess(
            data={"email_id": str(email_id), "suggestions": []},
            message="No attachments to process.",
        )

    suggestions = []
    for att in email.attachments:
        suggestion = build_reconciliation_suggestion(db, att.id)
        suggestions.append(suggestion)

    db.commit()

    logger.info(
        "gmail_suggest email_id=%s attachments=%d suggestions=%d",
        email_id, len(email.attachments), len(suggestions),
    )
    return ApiSuccess(data={
        "email_id":    str(email_id),
        "from_email":  email.from_email,
        "subject":     email.subject,
        "suggestions": suggestions,
    })


# ── Processing helpers ────────────────────────────────────────────────────────

def _match_mr_from_text(db, raw_text: str, fields: dict, items: list) -> dict:
    """
    Try to find a MaterialRequest matching the extracted document.

    Search order:
      1. po_number field from extraction (often holds MR reference)
      2. Regex scan of raw text for MR-XXXXX pattern
    """
    import re
    from app.models.material_request import MaterialRequest
    from sqlalchemy.orm import joinedload

    # 1. Check extracted po_number field (parsers put MR refs here)
    mr_ref = None
    po_field = (fields.get("po_number") or "").strip()
    if po_field and re.search(r"\bMR\b", po_field, re.IGNORECASE):
        mr_ref = po_field.upper()

    # 2. Scan raw text — require explicit hyphen to avoid matching "MR number", "MR report" etc.
    if not mr_ref:
        m = re.search(r"\bMR-([A-Z0-9]+(?:-[A-Z0-9]+)*)\b", raw_text or "", re.IGNORECASE)
        if m:
            mr_ref = "MR-" + m.group(1).upper()

    if not mr_ref:
        return {"status": "NO_REFERENCE", "mr_number": None, "mr_id": None}

    # Strip prefix for flexible DB match
    suffix = re.sub(r"^MR[-]?", "", mr_ref, flags=re.IGNORECASE).strip("-")
    mr = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.request_number.ilike(f"%{suffix}%"))
        .first()
    )

    if not mr:
        return {"status": "NOT_FOUND", "mr_number": mr_ref, "mr_id": None}

    # Quantity comparison (best-effort: compare first extracted item vs first MR item)
    mismatch_detail = None
    match_status    = "MATCHED"

    if items and mr.items:
        ext_item = items[0]
        mr_item  = mr.items[0]
        ext_qty  = float(ext_item.get("quantity") or 0)
        mr_qty   = float(mr_item.requested_quantity or 0)
        if ext_qty > 0 and mr_qty > 0:
            ratio = abs(ext_qty - mr_qty) / mr_qty
            if ratio > 0.05:   # >5% difference = mismatch
                match_status   = "MISMATCH"
                mismatch_detail = (
                    f"Document qty {ext_qty:.1f} vs MR qty {mr_qty:.1f} "
                    f"({ratio * 100:.0f}% difference)"
                )

    return {
        "status":          match_status,
        "mr_number":       mr.request_number,
        "mr_id":           str(mr.id),
        "mr_status":       mr.status.value if mr.status else None,
        "mismatch_detail": mismatch_detail,
    }


def _gmail_alert(db, email, title: str, message: str, severity: str, now) -> None:
    """Create a SystemAlert for a Gmail processing issue."""
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        sev = getattr(AlertSeverity, severity, AlertSeverity.MEDIUM)
        db.add(SystemAlert(
            alert_type          = AlertType.INVOICE_MISMATCH,
            severity            = sev,
            title               = title,
            message             = message,
            status              = AlertStatus.OPEN,
            notification_channel = "in_app",
            created_at          = now,
        ))
        db.flush()
    except Exception:
        logger.exception("_gmail_alert failed — alert not created for: %s", title)


@gmail_router.post("/incoming/{email_id}/reimport-attachments", dependencies=[OFFICE_AND_ABOVE])
def reimport_email_attachments(email_id: uuid.UUID, db: DbSession):
    """
    Connect to IMAP and import any attachments for this email that were previously
    skipped (e.g. because they had a generic MIME type like application/octet-stream).

    Safe to call multiple times — already-imported attachments are not duplicated.
    Returns {"imported": N, "already_present": N, "skipped": N}.
    """
    from app.services.gmail_reader_service import reimport_email_attachments as _reimport
    try:
        result = _reimport(db, email_id)
        msg = f"Imported {result['imported']} new attachment(s)."
        return ApiSuccess(data=result, message=msg)
    except ValueError as exc:
        logger.warning("reimport_email_attachments failed email_id=%s: %s", email_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))


@gmail_router.post("/reimport-all-attachments", dependencies=[OFFICE_AND_ABOVE])
def reimport_all_attachments(db: DbSession):
    """
    For every email with has_attachments=False or status=UNPROCESSED,
    reconnect to IMAP and import any missed attachments.

    Use this after enabling OCR to backfill attachments that were silently
    skipped during an earlier IMAP fetch (generic MIME type on the PDF).
    Returns {"processed": N, "total_imported": N}.
    """
    from app.services.gmail_reader_service import reimport_all_unprocessed
    result = reimport_all_unprocessed(db)
    msg = f"Processed {result['processed']} email(s), imported {result['total_imported']} attachment(s)."
    return ApiSuccess(data=result, message=msg)


@gmail_router.post("/attachments/{att_id}/refetch", dependencies=[OFFICE_AND_ABOVE])
def refetch_attachment(att_id: uuid.UUID, db: DbSession):
    """
    Re-connect to Gmail IMAP, find the original email by Message-ID, and
    re-download the missing attachment file to UPLOAD_DIR.

    Use this when an attachment record exists in the database but the file
    is missing from disk (e.g. after a Render redeploy wipes the filesystem).
    """
    from app.services.gmail_reader_service import refetch_attachment_from_imap
    try:
        result = refetch_attachment_from_imap(db, att_id)
        return ApiSuccess(data=result, message="Attachment re-fetched successfully.")
    except ValueError as exc:
        logger.warning("refetch_attachment failed att_id=%s: %s", att_id, exc)
        raise HTTPException(status_code=422, detail="Attachment re-fetch failed. Check server logs for details.")


class ReviewStatusBody(BaseModel):
    status: str  # PENDING_REVIEW | INVOICE_CREATED | DELIVERY_LINKED | DISMISSED


_VALID_REVIEW_STATUSES = {"PENDING_REVIEW", "INVOICE_CREATED", "DELIVERY_LINKED", "DISMISSED"}


@gmail_router.patch("/attachments/{att_id}/review-status", dependencies=[OFFICE_AND_ABOVE])
def update_review_status(att_id: uuid.UUID, body: ReviewStatusBody, db: DbSession):
    """Update the review_status of the DocumentExtraction linked to this attachment."""
    from app.models.document_extraction import DocumentExtraction

    if body.status not in _VALID_REVIEW_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid review status. Must be one of: {', '.join(sorted(_VALID_REVIEW_STATUSES))}",
        )

    extraction = (
        db.query(DocumentExtraction)
        .filter(
            DocumentExtraction.source_type == "GMAIL_ATTACHMENT",
            DocumentExtraction.source_id   == att_id,
        )
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )
    if not extraction:
        raise HTTPException(status_code=404, detail="No extraction found for this attachment.")

    extraction.review_status = body.status
    db.commit()

    return ApiSuccess(data={"att_id": str(att_id), "review_status": extraction.review_status})


@gmail_router.get("/attachments/{att_id}", dependencies=[OFFICE_AND_ABOVE])
def get_attachment(att_id: uuid.UUID, db: DbSession):
    from app.models.incoming_email import IncomingEmailAttachment

    att = db.query(IncomingEmailAttachment).filter(
        IncomingEmailAttachment.id == att_id
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return ApiSuccess(data=_att_summary(att))


def _resolve_attachment_path(stored: str, upload_dir: str) -> tuple[str | None, list[str]]:
    """
    Resolve an attachment file path using four fallback strategies.

    Problem: old records store relative paths like "uploads/gmail/other/file.pdf"
    while UPLOAD_DIR is an absolute path like "/opt/render/project/src/uploads".
    Naively joining them produces a doubled prefix:
        /opt/render/project/src/uploads/uploads/gmail/...  ← WRONG

    Correct approach: join the *parent* of UPLOAD_DIR with the stored relative path:
        parent = /opt/render/project/src
        path   = uploads/gmail/other/file.pdf
        result = /opt/render/project/src/uploads/gmail/other/file.pdf  ← CORRECT

    Strategy order
    -------------
    1. stored as-is          → absolute paths (new records saved after the fix)
    2. parent(UPLOAD_DIR) / stored  → "uploads/..." relative paths (old records)
    3. UPLOAD_DIR / stored   → "gmail/..." relative paths (even older records)
    4. UPLOAD_DIR / "gmail" / basename  → filename-only fallback
    """
    import os
    abs_upload  = os.path.abspath(upload_dir)
    parent_dir  = os.path.dirname(abs_upload)   # /opt/render/project/src
    basename    = os.path.basename(stored)

    candidates = [
        stored,                                                  # (1) absolute
        os.path.join(parent_dir, stored),                        # (2) parent + relative
        os.path.join(abs_upload, stored),                        # (3) UPLOAD_DIR + relative
        os.path.join(abs_upload, "gmail", basename),             # (4) filename only
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c, candidates
    return None, candidates


@gmail_router.get("/attachments/{att_id}/download", dependencies=[OFFICE_AND_ABOVE])
def download_attachment(att_id: uuid.UUID, db: DbSession, inline: bool = False):
    """
    Serve the saved attachment file for viewing or download.

    ?inline=true  → Content-Disposition: inline  (browser opens PDF/image in tab)
    ?inline=false → Content-Disposition: attachment (browser saves the file)
    """
    import os
    from fastapi.responses import FileResponse
    from app.core.config import settings
    from app.models.incoming_email import IncomingEmailAttachment

    att = db.query(IncomingEmailAttachment).filter(
        IncomingEmailAttachment.id == att_id
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found in database.")

    stored     = att.file_path or ""
    upload_dir = settings.UPLOAD_DIR
    resolved, candidates = _resolve_attachment_path(stored, upload_dir)

    logger.debug("gmail_download att_id=%s stored=%s resolved=%s", att_id, stored, resolved)

    if not resolved:
        tried = " | ".join(repr(c) for c in candidates if c)
        raise HTTPException(
            status_code=404,
            detail=(
                f"Attachment file is missing from disk. "
                f"Use POST /api/v1/gmail/attachments/{att_id}/refetch to restore it from Gmail. "
                f"Tried: {tried}. "
                f"UPLOAD_DIR={upload_dir!r}."
            ),
        )

    media_type  = att.content_type or _guess_mime(att.filename)
    disposition = "inline" if inline else "attachment"

    return FileResponse(
        path=resolved,
        media_type=media_type,
        filename=att.filename,
        headers={"Content-Disposition": f'{disposition}; filename="{att.filename}"'},
    )


def _guess_mime(filename: str) -> str:
    """Best-effort MIME type from file extension."""
    import mimetypes
    mime, _ = mimetypes.guess_type(filename or "")
    return mime or "application/octet-stream"


# ── Create invoice from Gmail attachment ──────────────────────────────────────

class InvoiceFromGmailBody(BaseModel):
    invoice_number:   Optional[str]   = None
    supplier_id:      Optional[uuid.UUID] = None
    project_id:       uuid.UUID
    site_id:          Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None
    total_amount:     float = 0.0
    notes:            Optional[str]   = None


@gmail_docs_router.post(
    "/invoices/from-gmail/{att_id}",
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_invoice_from_gmail(
    att_id: uuid.UUID,
    body: InvoiceFromGmailBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create an Invoice record linked to a Gmail attachment."""
    from app.models.incoming_email import IncomingEmailAttachment
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    from datetime import datetime, timezone

    att = db.query(IncomingEmailAttachment).filter(
        IncomingEmailAttachment.id == att_id
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    now = datetime.now(timezone.utc)
    invoice = Invoice(
        invoice_number=body.invoice_number or att.filename,
        supplier_id=body.supplier_id,
        project_id=body.project_id,
        site_id=body.site_id,
        purchase_order_id=body.purchase_order_id,
        total_amount=body.total_amount,
        status=RecordStatus.SUBMITTED,
        captured_by=current_user.id,
        captured_at=now,
        notes=body.notes or f"Created from Gmail attachment: {att.filename}",
    )
    db.add(invoice)
    db.flush()

    # Mark email attachment as processed and update extraction review_status
    att.email.processed_status = "PROCESSED"
    from app.models.document_extraction import DocumentExtraction as _DE
    _ext = (
        db.query(_DE)
        .filter(_DE.source_type == "GMAIL_ATTACHMENT", _DE.source_id == att.id)
        .order_by(_DE.created_at.desc()).first()
    )
    if _ext:
        _ext.review_status = "INVOICE_CREATED"
    db.commit()

    # Auto-match to PO
    from app.services.procurement_matching_service import match_invoice_to_po
    match_result = match_invoice_to_po(invoice.id, db)

    return ApiSuccess(
        data={"invoice_id": str(invoice.id), "match": match_result},
        message="Invoice created and matching attempted.",
    )


# ── Create delivery note from Gmail attachment ────────────────────────────────

class DeliveryNoteFromGmailBody(BaseModel):
    delivery_id: uuid.UUID


@gmail_docs_router.post(
    "/delivery-notes/from-gmail/{att_id}",
    dependencies=[OFFICE_AND_ABOVE],
)
def link_delivery_note_from_gmail(
    att_id: uuid.UUID,
    body: DeliveryNoteFromGmailBody,
    db: DbSession,
):
    """Link a Gmail attachment to an existing Delivery as its delivery note image."""
    from app.models.incoming_email import IncomingEmailAttachment
    from app.models.delivery import Delivery
    from app.services.procurement_matching_service import match_delivery_note_to_po

    att = db.query(IncomingEmailAttachment).filter(
        IncomingEmailAttachment.id == att_id
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    delivery = db.get(Delivery, body.delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found.")

    delivery.delivery_note_image_url = att.file_path
    att.email.processed_status = "PROCESSED"
    from app.models.document_extraction import DocumentExtraction as _DE2
    _ext2 = (
        db.query(_DE2)
        .filter(_DE2.source_type == "GMAIL_ATTACHMENT", _DE2.source_id == att.id)
        .order_by(_DE2.created_at.desc()).first()
    )
    if _ext2:
        _ext2.review_status = "DELIVERY_LINKED"
    db.commit()

    match_result = match_delivery_note_to_po(delivery.id, db)
    return ApiSuccess(
        data={"delivery_id": str(delivery.id), "match": match_result},
        message="Delivery note linked.",
    )


# ── Compose + send with optional file attachments ────────────────────────────

ALLOWED_COMPOSE_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
}
ALLOWED_COMPOSE_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".xls", ".xlsx", ".csv"}
_MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB per file


@gmail_router.post("/compose-send", dependencies=[OFFICE_AND_ABOVE])
async def compose_send(
    to_email:  str = Form(...),
    subject:   str = Form(...),
    body_html: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
):
    """
    Send a free-form email with optional file attachments.

    Accepted attachment MIME types: PDF, JPEG, PNG, GIF, XLS, XLSX, CSV.
    Max 10 MB per file. Up to 5 attachments.

    Returns {"status": "SENT"|"MOCK_SENT"|"FAILED", "attachment_count": N}.
    """
    import os
    from app.services.email_service import send_email

    if len(attachments) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 attachments per email.")

    att_data: list[tuple[str, bytes, str]] = []
    for f in attachments:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_COMPOSE_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not allowed. Accepted: PDF, JPEG, PNG, GIF, XLS, XLSX, CSV."
            )
        data = await f.read()
        if len(data) > _MAX_ATTACHMENT_SIZE:
            raise HTTPException(status_code=400, detail=f"File '{f.filename}' exceeds 10 MB limit.")
        mime = f.content_type or "application/octet-stream"
        if mime not in ALLOWED_COMPOSE_MIME:
            # Derive from extension as fallback
            ext_to_mime = {
                ".pdf": "application/pdf",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".xls": "application/vnd.ms-excel",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".csv": "text/csv",
            }
            mime = ext_to_mime.get(ext, "application/octet-stream")
        att_data.append((f.filename, data, mime))

    result = send_email(
        to_email=to_email,
        subject=subject,
        body=body_html,
        attachments=att_data or None,
    )
    return ApiSuccess(data={**result, "attachment_count": len(att_data)})


# ── Serialisers ───────────────────────────────────────────────────────────────

def _email_summary(e) -> dict:
    return {
        "id":               str(e.id),
        "from_email":       e.from_email,
        "subject":          e.subject,
        "received_at":      e.received_at.isoformat() if e.received_at else None,
        "has_attachments":  e.has_attachments,
        "processed_status": e.processed_status,
        "matched_po_number": e.matched_po_number,
    }


def _att_summary(a) -> dict:
    from app.core.config import settings

    stored = a.file_path or ""
    resolved, _ = _resolve_attachment_path(stored, settings.UPLOAD_DIR)

    return {
        "id":            str(a.id),
        "filename":      a.filename,
        "file_path":     a.file_path,
        "content_type":  a.content_type,
        "detected_type": a.detected_type,
        "created_at":    a.created_at.isoformat(),
        "file_exists":   resolved is not None,
    }
