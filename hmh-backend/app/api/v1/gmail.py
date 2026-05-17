"""
Gmail procurement inbox endpoints.

POST /gmail/fetch                     — trigger IMAP fetch
GET  /gmail/incoming                  — list fetched emails
GET  /gmail/incoming/{id}             — single email + attachments
GET  /gmail/attachments/{id}          — single attachment metadata

POST /invoices/from-gmail/{att_id}    — create Invoice from Gmail attachment
POST /delivery-notes/from-gmail/{att_id} — link Gmail attachment to a Delivery
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies import OFFICE_AND_ABOVE, CurrentUser, DbSession
from app.schemas.common import ApiSuccess

gmail_router      = APIRouter(prefix="/gmail",          tags=["gmail"])
gmail_docs_router = APIRouter(prefix="",                tags=["gmail"])   # for /invoices/from-gmail etc.


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

    print(f"[GMAIL-PROCESS] Processing email {email_id}", flush=True)

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
        print(f"[GMAIL-PROCESS] Attachment: {att.filename} ({att.detected_type})", flush=True)

        # ── Extract ──────────────────────────────────────────────────────────
        ext_result = extract_document_data(att.file_path, att.detected_type)
        raw_text   = ext_result.get("raw_text", "")
        fields     = ext_result.get("fields", {})
        items      = ext_result.get("items", [])

        print(f"[GMAIL-PROCESS] Extraction status: {ext_result['status']}", flush=True)
        if raw_text:
            print(f"[GMAIL-PROCESS] Extracted text ({len(raw_text)} chars)", flush=True)

        # ── Match MR ─────────────────────────────────────────────────────────
        mr_match = _match_mr_from_text(db, raw_text, fields, items)
        print(f"[GMAIL-PROCESS] MR match: status={mr_match['status']} ref={mr_match.get('mr_number')}", flush=True)

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

    print(f"[GMAIL-PROCESS] Done — status={email.processed_status}, {len(results)} attachment(s)", flush=True)
    return ApiSuccess(data={
        "email_id":        str(email_id),
        "processed_status": email.processed_status,
        "results":         results,
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
        pass


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

    print(
        f"[GMAIL-DOWNLOAD] att_id={att_id}"
        f" | stored={stored!r}"
        f" | UPLOAD_DIR={upload_dir!r}"
        f" | resolved={resolved!r}",
        flush=True,
    )

    if not resolved:
        tried = " | ".join(repr(c) for c in candidates if c)
        raise HTTPException(
            status_code=404,
            detail=(
                "Attachment record exists but the file is no longer on disk. "
                "Render's ephemeral filesystem is wiped on every redeploy — "
                "re-fetch the email via POST /api/v1/gmail/fetch to restore it. "
                f"Tried paths: {tried}. "
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

    # Mark email attachment as processed
    att.email.processed_status = "PROCESSED"
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
    db.commit()

    match_result = match_delivery_note_to_po(delivery.id, db)
    return ApiSuccess(
        data={"delivery_id": str(delivery.id), "match": match_result},
        message="Delivery note linked.",
    )


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
