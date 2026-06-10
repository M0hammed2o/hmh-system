"""Procurement Reconciliation routes — Phase 4."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, OFFICE_AND_ABOVE, CurrentUser, DbSession
from app.models.enums import ReconciliationStatus
from app.schemas.common import ApiSuccess
from app.schemas.procurement_reconciliation import (
    ProcurementReconciliationCreate,
    ProcurementReconciliationUpdate,
)
from app.services import procurement_reconciliation_service as svc

router = APIRouter(prefix="/reconciliations", tags=["reconciliations"])


@router.get("/dashboard", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_dashboard(db: DbSession):
    """Return status counts for the reconciliation dashboard."""
    return ApiSuccess(data=svc.get_dashboard_stats(db))


@router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def list_reconciliations(
    db: DbSession,
    status: Optional[ReconciliationStatus] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    records = svc.list_reconciliations(db, status, supplier_id, project_id, limit, offset)
    return ApiSuccess(data=[svc.build_detail(db, r) for r in records])


@router.get("/{recon_id}", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_reconciliation(recon_id: uuid.UUID, db: DbSession):
    r = svc.get_reconciliation(db, recon_id)
    return ApiSuccess(data=svc.build_detail(db, r))


@router.post("/", response_model=ApiSuccess[dict], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_reconciliation(body: ProcurementReconciliationCreate, db: DbSession, current_user: CurrentUser):
    r = svc.create_reconciliation(db, body, created_by=current_user.id)
    return ApiSuccess(data=svc.build_detail(db, r), message="Reconciliation record created.")


@router.patch("/{recon_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def update_reconciliation(recon_id: uuid.UUID, body: ProcurementReconciliationUpdate, db: DbSession, current_user: CurrentUser):
    r = svc.update_reconciliation(db, recon_id, body, reviewed_by=current_user.id)
    return ApiSuccess(data=svc.build_detail(db, r), message="Reconciliation updated.")


@router.post("/{recon_id}/recompute", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def recompute_variances(recon_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Re-fetch linked documents and recompute variance data."""
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder
    from app.models.quotation import Quotation

    r = svc.get_reconciliation(db, recon_id)
    po       = db.get(PurchaseOrder, r.purchase_order_id) if r.purchase_order_id else None
    invoice  = db.get(Invoice,       r.invoice_id)        if r.invoice_id        else None
    delivery = db.get(Delivery,      r.delivery_id)       if r.delivery_id       else None
    quotation = db.get(Quotation,    r.quotation_id)      if r.quotation_id      else None

    if not po:
        from fastapi import HTTPException
        raise HTTPException(404, "Linked purchase order not found.")

    r.variance_data = svc.compute_variances(po, invoice, quotation, delivery)

    if invoice is None:
        r.status = ReconciliationStatus.PENDING
    elif r.variance_data["has_variance"]:
        r.status = ReconciliationStatus.VARIANCE_DETECTED
    else:
        r.status = ReconciliationStatus.MATCHED

    db.commit()
    db.refresh(r)
    return ApiSuccess(data=svc.build_detail(db, r), message="Variances recomputed.")


@router.delete("/{recon_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_reconciliation(recon_id: uuid.UUID, db: DbSession):
    svc.delete_reconciliation(db, recon_id)
    return ApiSuccess(data={"deleted": str(recon_id)}, message="Reconciliation deleted.")
