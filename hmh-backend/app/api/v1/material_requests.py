"""Material Request routes."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.logging_config import get_logger

logger = get_logger(__name__)

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.enums import RecordStatus
from app.models.material_request import MaterialRequest
from app.schemas.common import ApiSuccess
from app.schemas.material_request import (
    MaterialRequestCreate, MaterialRequestRead, MaterialRequestUpdate,
)
from app.services import mr_service

project_mr_router = APIRouter(
    prefix="/projects/{project_id}/material-requests",
    tags=["material-requests"],
)
mr_router = APIRouter(prefix="/material-requests", tags=["material-requests"])


@project_mr_router.get("/", response_model=ApiSuccess[list[MaterialRequestRead]], dependencies=[ALL_ROLES])
def list_material_requests(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    status:  Optional[RecordStatus] = Query(None),
    site_id: Optional[uuid.UUID]    = Query(None),
):
    check_project_access(db, current_user, project_id)
    mrs = mr_service.list_requests(db, project_id, site_id=site_id, status=status)
    return ApiSuccess(data=[MaterialRequestRead.model_validate(m) for m in mrs])


@project_mr_router.post("/", response_model=ApiSuccess[MaterialRequestRead], status_code=201, dependencies=[WRITE_ROLES])
def create_material_request(project_id: uuid.UUID, body: MaterialRequestCreate, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    import json as _json
    try:
        mr = mr_service.create_request(db, project_id, body, current_user.id)
        logger.info("mr_created project_id=%s user=%s mr_id=%s number=%s", project_id, current_user.id, mr.id, mr.request_number)
        return ApiSuccess(data=MaterialRequestRead.model_validate(mr), message="Material request created.")
    except Exception as exc:
        logger.exception("mr_create_failed project_id=%s error=%s", project_id, exc)
        raise


@mr_router.get("/{mr_id}", response_model=ApiSuccess[MaterialRequestRead], dependencies=[ALL_ROLES])
def get_material_request(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    mr = mr_service.get_request(db, mr_id)
    check_project_access(db, current_user, mr.project_id)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr))


@mr_router.patch("/{mr_id}", response_model=ApiSuccess[MaterialRequestRead], dependencies=[OFFICE_AND_ABOVE])
def update_material_request(mr_id: uuid.UUID, body: MaterialRequestUpdate, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    mr = mr_service.update_request(db, mr_id, body, current_user.id)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr), message="Material request updated.")


# ── Workflow actions ──────────────────────────────────────────────────────────

@mr_router.post("/{mr_id}/submit", response_model=ApiSuccess[MaterialRequestRead], dependencies=[ALL_ROLES])
def submit_request(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    mr = mr_service.submit_request(db, mr_id, current_user.id)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr), message="Request submitted.")


class ApproveBody(BaseModel):
    over_boq_reason: Optional[str] = None


@mr_router.post("/{mr_id}/approve", response_model=ApiSuccess[MaterialRequestRead], dependencies=[OFFICE_AND_ABOVE])
def approve_request(mr_id: uuid.UUID, body: ApproveBody, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    logger.info("mr_approve mr_id=%s user=%s role=%s", mr_id, current_user.id, current_user.role.value)
    mr = mr_service.approve_request(db, mr_id, current_user.id, body.over_boq_reason)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr), message="Request approved.")


class RejectBody(BaseModel):
    reason: str


@mr_router.post("/{mr_id}/send-email", dependencies=[OFFICE_AND_ABOVE])
def send_mr_email(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """(Re)send the approval email to the preferred supplier. Always creates a new send attempt."""
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    log = mr_service.resend_mr_email(db, mr_id, sent_by_id=current_user.id)
    return ApiSuccess(
        data={
            "status":        log.status,
            "sent_to_email": log.sent_to_email,
            "sent_at":       log.sent_at.isoformat() if log.sent_at else None,
            "error":         log.error_message,
        },
        message=f"Email {log.status.lower().replace('_', ' ')}.",
    )


@mr_router.get("/{mr_id}/email-log", dependencies=[OFFICE_AND_ABOVE])
def get_mr_email_log(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Return all email send attempts for a material request."""
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from app.models.mr_email_log import MREmailLog
    logs = (
        db.query(MREmailLog)
        .filter(MREmailLog.material_request_id == mr_id)
        .order_by(MREmailLog.created_at.desc())
        .all()
    )
    return ApiSuccess(data=[{
        "id":            str(l.id),
        "status":        l.status,
        "sent_to_email": l.sent_to_email,
        "sent_at":       l.sent_at.isoformat() if l.sent_at else None,
        "error_message": l.error_message,
        "created_at":    l.created_at.isoformat(),
    } for l in logs])


@mr_router.post("/{mr_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def prepare_mr_email_draft(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Generate the MR supplier enquiry email and store it as a draft (status=queued).
    Allows office staff to review/edit before sending.
    """
    from app.models.mr_email_log import MREmailLog
    from app.services.email_service import build_mr_email_body
    from datetime import datetime, timezone

    mr = mr_service.get_request(db, mr_id)
    check_project_access(db, current_user, mr.project_id)
    subject, body_html = build_mr_email_body(db, mr)
    now = datetime.now(timezone.utc)

    to_email = ""
    if mr.preferred_supplier_id:
        from app.models.supplier import Supplier
        s = db.get(Supplier, mr.preferred_supplier_id)
        to_email = s.email or "" if s else ""

    # Remove existing unsent draft if any
    db.query(MREmailLog).filter(
        MREmailLog.material_request_id == mr_id,
        MREmailLog.status == "queued",
    ).delete(synchronize_session=False)

    draft = MREmailLog(
        material_request_id=mr_id,
        supplier_id=mr.preferred_supplier_id,
        sent_to_email=to_email or "(no email)",
        email_subject=subject,
        email_body=body_html,
        status="queued",
        sent_by=current_user.id,
        created_at=now,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    return ApiSuccess(data={
        "draft_id":  str(draft.id),
        "to_email":  to_email,
        "subject":   subject,
        "body_html": body_html,
        "status":    "queued",
    }, message="MR email draft prepared. Review and edit before sending.")


@mr_router.get("/{mr_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def get_mr_email_draft(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Return the current unsent draft for the MR email."""
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from app.models.mr_email_log import MREmailLog
    draft = (
        db.query(MREmailLog)
        .filter(MREmailLog.material_request_id == mr_id, MREmailLog.status == "queued")
        .first()
    )
    if not draft:
        return ApiSuccess(data={"exists": False})
    return ApiSuccess(data={
        "exists":    True,
        "draft_id":  str(draft.id),
        "to_email":  draft.sent_to_email,
        "subject":   draft.email_subject,
        "body_html": draft.email_body,
        "status":    draft.status,
    })


@mr_router.patch("/{mr_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def update_mr_email_draft(
    mr_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    subject: str | None = None,
    body_html: str | None = None,
    to_email: str | None = None,
):
    """Update the unsent MR email draft body/subject/recipient."""
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from app.models.mr_email_log import MREmailLog
    draft = (
        db.query(MREmailLog)
        .filter(MREmailLog.material_request_id == mr_id, MREmailLog.status == "queued")
        .first()
    )
    if not draft:
        raise HTTPException(404, "No draft found. Call POST /prepare-email first.")
    if subject:   draft.email_subject = subject
    if body_html: draft.email_body    = body_html
    if to_email:  draft.sent_to_email = to_email
    db.commit()
    return ApiSuccess(data={"draft_id": str(draft.id)}, message="Draft updated.")


@mr_router.post("/{mr_id}/mark-sent", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def mark_mr_email_sent(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Mark the MR enquiry email as manually sent (e.g., via WhatsApp or phone)."""
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from app.models.mr_email_log import MREmailLog
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    draft = (
        db.query(MREmailLog)
        .filter(MREmailLog.material_request_id == mr_id, MREmailLog.status == "queued")
        .first()
    )
    if draft:
        draft.status    = "MANUAL_SENT"
        draft.sent_at   = now
        draft.sent_by   = current_user.id
        db.commit()
        return ApiSuccess(data={"status": "MANUAL_SENT", "sent_at": now.isoformat()},
                          message="MR email marked as manually sent.")
    return ApiSuccess(data={"status": "no_draft"}, message="No draft to mark sent.")


@mr_router.post("/{mr_id}/reject", response_model=ApiSuccess[MaterialRequestRead], dependencies=[OFFICE_AND_ABOVE])
def reject_request(mr_id: uuid.UUID, body: RejectBody, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    mr = mr_service.reject_request(db, mr_id, current_user.id, body.reason)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr), message="Request rejected.")


class ConvertToPOBody(BaseModel):
    supplier_id: uuid.UUID
    expected_delivery_date: Optional[str] = None
    notes: Optional[str] = None
    items: list[dict]


@mr_router.post("/{mr_id}/convert-to-po", response_model=ApiSuccess[dict], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def convert_to_po(mr_id: uuid.UUID, body: ConvertToPOBody, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from datetime import date
    exp_date = date.fromisoformat(body.expected_delivery_date) if body.expected_delivery_date else None
    po = mr_service.convert_to_po(
        db, mr_id, current_user.id, body.supplier_id, body.items,
        expected_delivery_date=exp_date, notes=body.notes,
    )
    return ApiSuccess(data={"po_id": str(po.id), "po_number": po.po_number}, message=f"PO {po.po_number} created.")


# ── Quotes ────────────────────────────────────────────────────────────────────

class QuoteCreate(BaseModel):
    supplier_id: uuid.UUID
    description: str
    quoted_quantity: float
    unit_price: float
    unit: Optional[str] = None
    delivery_date: Optional[str] = None
    notes: Optional[str] = None
    item_id: Optional[uuid.UUID] = None


class QuoteRead(BaseModel):
    id: uuid.UUID
    material_request_id: uuid.UUID
    supplier_id: uuid.UUID
    item_id: Optional[uuid.UUID] = None
    description: str
    quoted_quantity: float
    unit: Optional[str] = None
    unit_price: float
    total_price: Optional[float] = None
    delivery_date: Optional[str] = None
    notes: Optional[str] = None
    is_selected: bool

    class Config:
        from_attributes = True


@mr_router.get("/{mr_id}/quotes", response_model=ApiSuccess[list[QuoteRead]], dependencies=[ALL_ROLES])
def list_quotes(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    quotes = mr_service.list_quotes(db, mr_id)
    return ApiSuccess(data=[QuoteRead.model_validate(q) for q in quotes])


@mr_router.post("/{mr_id}/quotes", response_model=ApiSuccess[QuoteRead], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def add_quote(mr_id: uuid.UUID, body: QuoteCreate, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    from datetime import date
    delivery_date = date.fromisoformat(body.delivery_date) if body.delivery_date else None
    quote = mr_service.add_quote(
        db, mr_id, body.supplier_id, body.description,
        body.quoted_quantity, body.unit_price,
        unit=body.unit, delivery_date=delivery_date,
        notes=body.notes, item_id=body.item_id, actor_id=current_user.id,
    )
    return ApiSuccess(data=QuoteRead.model_validate(quote), message="Quote added.")


@mr_router.post("/{mr_id}/quotes/{quote_id}/select", response_model=ApiSuccess[QuoteRead], dependencies=[OFFICE_AND_ABOVE])
def select_quote(mr_id: uuid.UUID, quote_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _mr = db.get(MaterialRequest, mr_id)
    if not _mr:
        raise HTTPException(404, "Material request not found.")
    check_project_access(db, current_user, _mr.project_id)
    quote = mr_service.select_quote(db, mr_id, quote_id, current_user.id)
    return ApiSuccess(data=QuoteRead.model_validate(quote), message="Quote selected.")


@mr_router.get("/{mr_id}/activity", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_mr_activity(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser, limit: int = Query(30, le=100)):
    """Return a human-readable activity timeline for this material request."""
    from app.models.audit import AuditEvent
    from app.models.attachment import Attachment
    from app.models.enums import AttachmentEntity
    from app.core.storage import public_url as _pub

    mr = mr_service.get_request(db, mr_id)  # 404 if not found
    check_project_access(db, current_user, mr.project_id)

    audit_rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_id == mr_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    attachments = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == AttachmentEntity.MATERIAL_REQUEST,
            Attachment.entity_id   == mr_id,
        )
        .order_by(Attachment.uploaded_at.desc())
        .all()
    )

    activity = []
    for a in audit_rows:
        actor = None
        if a.actor_id:
            from app.models.user import User
            u = db.get(User, a.actor_id)
            actor = u.full_name if u else None
        after = a.after_value or {}
        status = after.get("status", "")
        if status:
            desc = f"Status changed to {status.replace('_', ' ').title()}"
        elif a.action == "CREATE":
            desc = "Material request created"
        elif a.action == "APPROVE":
            desc = "Request approved"
        elif a.action == "REJECT":
            desc = f"Request rejected: {after.get('reason', '')}"
        else:
            desc = a.action.replace("_", " ").title()
        activity.append({
            "type": "status", "timestamp": a.created_at.isoformat(),
            "actor": actor or "System", "description": desc,
        })
    for att in attachments:
        activity.append({
            "type": "document", "timestamp": att.uploaded_at.isoformat(),
            "actor": None, "description": f"Document: {att.file_name}",
            "url": _pub(att.stored_path), "attachment_id": str(att.id),
            "is_image": att.mime_type.startswith("image/") if att.mime_type else False,
        })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return ApiSuccess(data=activity[:limit])
