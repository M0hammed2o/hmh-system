"""Purchase Order routes."""

import uuid

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
