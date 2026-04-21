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
