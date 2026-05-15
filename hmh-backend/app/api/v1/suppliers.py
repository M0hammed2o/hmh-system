"""Supplier routes."""

import uuid

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import ALL_ROLES, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "/",
    response_model=ApiSuccess[list[SupplierRead]],
    dependencies=[ALL_ROLES],
)
def list_suppliers(
    db: DbSession,
    include_inactive: bool = Query(False),
):
    suppliers = supplier_service.list_suppliers(db, include_inactive)
    return ApiSuccess(data=[SupplierRead.model_validate(s) for s in suppliers])


@router.get(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[ALL_ROLES],
)
def get_supplier(supplier_id: uuid.UUID, db: DbSession):
    s = supplier_service.get_supplier(db, supplier_id)
    return ApiSuccess(data=SupplierRead.model_validate(s))


@router.post(
    "/",
    response_model=ApiSuccess[SupplierRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_supplier(body: SupplierCreate, db: DbSession):
    s = supplier_service.create_supplier(db, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier created.")


@router.patch(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession):
    s = supplier_service.update_supplier(db, supplier_id, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier updated.")


@router.get("/{supplier_id}/outstanding", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def supplier_outstanding(supplier_id: uuid.UUID, db: DbSession):
    """
    Return per-supplier financial summary: PO total, invoiced, paid, outstanding.
    """
    from datetime import date
    from sqlalchemy import func
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.enums import RecordStatus, PaymentStatus

    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")

    po_total = float(
        db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
        .filter(PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status.notin_([RecordStatus.CANCELLED, RecordStatus.REJECTED]))
        .scalar() or 0
    )
    invoice_total = float(
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
        .filter(Invoice.supplier_id == supplier_id,
                Invoice.status.notin_([RecordStatus.CANCELLED, RecordStatus.REJECTED]))
        .scalar() or 0
    )
    paid_total = float(
        db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
        .filter(Payment.supplier_id == supplier_id, Payment.status == PaymentStatus.PAID)
        .scalar() or 0
    )
    today = date.today()
    overdue = float(
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
        .filter(Invoice.supplier_id == supplier_id,
                Invoice.due_date < today,
                Invoice.status.notin_([RecordStatus.PAID, RecordStatus.CANCELLED]))
        .scalar() or 0
    )

    return ApiSuccess(data={
        "supplier_id":      str(supplier_id),
        "supplier_name":    s.name,
        "po_total":         po_total,
        "invoice_total":    invoice_total,
        "paid_total":       paid_total,
        "outstanding":      max(0.0, invoice_total - paid_total),
        "overdue_amount":   overdue,
    })


@router.delete(
    "/{supplier_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_supplier(supplier_id: uuid.UUID, db: DbSession):
    """Soft-delete a supplier (set is_active=False). Historical records are preserved."""
    from app.models.supplier import Supplier
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")
    s.is_active = False
    db.commit()
    return ApiSuccess(data={"supplier_id": str(supplier_id), "name": s.name},
                      message=f"Supplier '{s.name}' deactivated.")
