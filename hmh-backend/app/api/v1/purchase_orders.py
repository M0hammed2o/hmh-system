"""Purchase Order routes."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.purchase_order import (
    POItemCreate, POItemRead,
    PurchaseOrderCreate, PurchaseOrderRead, PurchaseOrderUpdate,
)
from app.services import po_service

project_po_router = APIRouter(
    prefix="/projects/{project_id}/purchase-orders",
    tags=["purchase-orders"],
)
po_router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@project_po_router.get(
    "/",
    response_model=ApiSuccess[list[PurchaseOrderRead]],
    dependencies=[ALL_ROLES],
)
def list_purchase_orders(project_id: uuid.UUID, db: DbSession):
    pos = po_service.list_pos(db, project_id)
    return ApiSuccess(data=[PurchaseOrderRead.model_validate(p) for p in pos])


@project_po_router.post(
    "/",
    response_model=ApiSuccess[PurchaseOrderRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_purchase_order(
    project_id: uuid.UUID,
    body: PurchaseOrderCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    po = po_service.create_po(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=PurchaseOrderRead.model_validate(po),
        message="Purchase order created.",
    )


@po_router.get(
    "/{po_id}",
    response_model=ApiSuccess[PurchaseOrderRead],
    dependencies=[ALL_ROLES],
)
def get_purchase_order(po_id: uuid.UUID, db: DbSession):
    po = po_service.get_po(db, po_id)
    return ApiSuccess(data=PurchaseOrderRead.model_validate(po))


@po_router.patch(
    "/{po_id}",
    response_model=ApiSuccess[PurchaseOrderRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_purchase_order(po_id: uuid.UUID, body: PurchaseOrderUpdate, db: DbSession):
    po = po_service.update_po(db, po_id, body)
    return ApiSuccess(data=PurchaseOrderRead.model_validate(po), message="PO updated.")


@po_router.post(
    "/{po_id}/items",
    response_model=ApiSuccess[POItemRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def add_po_item(po_id: uuid.UUID, body: POItemCreate, db: DbSession):
    item = po_service.add_po_item(db, po_id, body)
    return ApiSuccess(data=POItemRead.model_validate(item), message="Item added to PO.")


@po_router.post("/{po_id}/approve", response_model=ApiSuccess[PurchaseOrderRead], dependencies=[OFFICE_AND_ABOVE])
def approve_po(po_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    po = po_service.approve_po(db, po_id, current_user.id)
    return ApiSuccess(data=PurchaseOrderRead.model_validate(po), message="PO approved.")


@po_router.post("/{po_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def prepare_po_email_draft(po_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Generate the PO confirmation email body and store it as a draft (status=queued)
    in po_email_logs WITHOUT sending.  Office staff can then view, edit, and send.
    """
    from app.models.purchase_order import PurchaseOrder, PoEmailLog
    from app.models.enums import EmailStatus
    from app.models.supplier import Supplier
    from app.services.email_service import build_po_email_body
    from datetime import datetime, timezone
    from fastapi import HTTPException

    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(404, "PO not found.")

    supplier = db.get(Supplier, po.supplier_id) if po.supplier_id else None
    to_email = supplier.email if supplier else ""
    subject, body_html = build_po_email_body(po)
    now = datetime.now(timezone.utc)

    # Remove any existing unsent draft to avoid duplicates
    db.query(PoEmailLog).filter(
        PoEmailLog.purchase_order_id == po_id,
        PoEmailLog.status == EmailStatus.queued,
    ).delete(synchronize_session=False)

    draft = PoEmailLog(
        purchase_order_id   = po_id,
        sent_to_email       = to_email or "(no email on supplier)",
        sent_by             = current_user.id,
        email_subject       = subject,
        email_body          = body_html,
        status              = EmailStatus.queued,
        material_request_id = po.material_request_id,
        created_at          = now,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    return ApiSuccess(data={
        "draft_id":   str(draft.id),
        "to_email":   to_email,
        "subject":    subject,
        "body_html":  body_html,
        "status":     "queued",
    }, message="Email draft prepared. Review and edit before sending.")


@po_router.patch("/{po_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def update_po_email_draft(po_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
                          subject: str | None = None, body_html: str | None = None,
                          to_email: str | None = None):
    """Update the unsent draft body/subject/recipient before sending."""
    from app.models.purchase_order import PoEmailLog
    from app.models.enums import EmailStatus
    from fastapi import HTTPException
    from pydantic import BaseModel

    draft = (
        db.query(PoEmailLog)
        .filter(PoEmailLog.purchase_order_id == po_id, PoEmailLog.status == EmailStatus.queued)
        .first()
    )
    if not draft:
        raise HTTPException(404, "No draft found. Call POST /prepare-email first.")
    if subject:    draft.email_subject = subject
    if body_html:  draft.email_body    = body_html
    if to_email:   draft.sent_to_email = to_email
    db.commit()
    return ApiSuccess(data={"draft_id": str(draft.id), "status": "queued"}, message="Draft updated.")


@po_router.get("/{po_id}/prepare-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def get_po_email_draft(po_id: uuid.UUID, db: DbSession):
    """Return the current unsent draft for the PO email."""
    from app.models.purchase_order import PoEmailLog
    from app.models.enums import EmailStatus

    draft = (
        db.query(PoEmailLog)
        .filter(PoEmailLog.purchase_order_id == po_id, PoEmailLog.status == EmailStatus.queued)
        .first()
    )
    if not draft:
        return ApiSuccess(data={"exists": False}, message="No draft.")
    return ApiSuccess(data={
        "exists":    True,
        "draft_id":  str(draft.id),
        "to_email":  draft.sent_to_email,
        "subject":   draft.email_subject,
        "body_html": draft.email_body,
        "status":    "queued",
    })


@po_router.post("/{po_id}/send-email", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def send_po_email(po_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    po, log = po_service.send_po_email(db, po_id, current_user.id)
    return ApiSuccess(
        data={
            "po_number": po.po_number,
            "sent_to": log.sent_to_email,
            "status": log.status.value,
            "error": log.error_message,
            "is_mock": not __import__("os").getenv("SMTP_ENABLED", "false").lower() == "true",
        },
        message=f"Email {'mock-sent' if log.status.value == 'sent' and not __import__('os').getenv('SMTP_ENABLED','false').lower() == 'true' else log.status.value}.",
    )


@po_router.post(
    "/{po_id}/mark-sent",
    response_model=ApiSuccess[PurchaseOrderRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def mark_po_sent(po_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Manually mark a PO as sent to the supplier (for non-email channels)."""
    from app.models.purchase_order import PurchaseOrder
    from app.models.enums import RecordStatus
    from fastapi import HTTPException

    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(404, "PO not found.")
    if po.status not in (RecordStatus.APPROVED, RecordStatus.SENT):
        raise HTTPException(422, "Only APPROVED or SENT POs can be marked as sent.")
    po.status   = RecordStatus.SENT
    po.sent_at  = datetime.now(timezone.utc)
    db.commit()
    db.refresh(po)
    return ApiSuccess(data=PurchaseOrderRead.model_validate(po), message="PO marked as sent to supplier.")


@po_router.get("/{po_id}/outstanding", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_po_outstanding(po_id: uuid.UUID, db: DbSession):
    from app.services.delivery_service import get_po_outstanding as _get
    result = _get(db, po_id)
    return ApiSuccess(data=result)


@po_router.get("/{po_id}/email-log", response_model=ApiSuccess[list[dict]], dependencies=[OFFICE_AND_ABOVE])
def get_email_log(po_id: uuid.UUID, db: DbSession):
    from app.models.purchase_order import PoEmailLog
    logs = db.query(PoEmailLog).filter(PoEmailLog.purchase_order_id == po_id).order_by(PoEmailLog.created_at.desc()).all()
    return ApiSuccess(data=[
        {
            "id": str(l.id),
            "sent_to": l.sent_to_email,
            "subject": l.email_subject,
            "status": l.status.value,
            "sent_at": l.sent_at.isoformat() if l.sent_at else None,
            "error": l.error_message,
            "has_body": bool(l.email_body),
        }
        for l in logs
    ])
