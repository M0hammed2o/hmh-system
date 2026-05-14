"""
Lot material allocation routes.

GET  /lots/{lot_id}/allocations        — all items allocated to a lot
GET  /lots/{lot_id}/allocations/{item_id} — one item
POST /lots/{lot_id}/transfer           — transfer stock into a lot (with overrun guard)
POST /sites/transfer                   — transfer between two sites
"""

import uuid

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession
from app.schemas.common import ApiSuccess
from app.services import allocation_service, transfer_service
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["allocation"])


# ── Response schema ───────────────────────────────────────────────────────────

class LotAllocationRead(BaseModel):
    lot_id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    item_unit: Optional[str]
    allocated_quantity: float
    used_quantity: float
    remaining_quantity: float
    over_quantity: float
    is_over: bool


class LotTransferCreate(BaseModel):
    item_id: uuid.UUID
    quantity: float
    site_id: uuid.UUID
    notes: Optional[str] = None
    overrun_reason: Optional[str] = None
    boq_item_id: Optional[uuid.UUID] = None
    unit_cost: Optional[float] = None


class SiteTransferCreate(BaseModel):
    from_site_id: uuid.UUID
    to_site_id: uuid.UUID
    item_id: uuid.UUID
    quantity: float
    notes: Optional[str] = None
    unit_cost: Optional[float] = None


class StockLedgerRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID]
    item_id: uuid.UUID
    quantity_in: float
    quantity_out: float


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/lots/{lot_id}/allocations",
    response_model=ApiSuccess[list[LotAllocationRead]],
    dependencies=[ALL_ROLES],
)
def get_lot_allocations(lot_id: uuid.UUID, db: DbSession):
    allocations = allocation_service.get_all_lot_allocations(db, lot_id)
    return ApiSuccess(data=[LotAllocationRead(**vars(a)) for a in allocations])


@router.get(
    "/lots/{lot_id}/allocations/{item_id}",
    response_model=ApiSuccess[LotAllocationRead],
    dependencies=[ALL_ROLES],
)
def get_lot_allocation(lot_id: uuid.UUID, item_id: uuid.UUID, db: DbSession):
    alloc = allocation_service.get_lot_allocation(db, lot_id, item_id)
    return ApiSuccess(data=LotAllocationRead(**vars(alloc)))


@router.post(
    "/projects/{project_id}/lots/{lot_id}/transfer",
    response_model=ApiSuccess[StockLedgerRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def transfer_to_lot(
    project_id: uuid.UUID,
    lot_id: uuid.UUID,
    body: LotTransferCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    entry = transfer_service.transfer_to_lot(
        db,
        project_id=project_id,
        site_id=body.site_id,
        lot_id=lot_id,
        item_id=body.item_id,
        quantity=body.quantity,
        entered_by=current_user.id,
        notes=body.notes,
        overrun_reason=body.overrun_reason,
        boq_item_id=body.boq_item_id,
        unit_cost=body.unit_cost,
    )
    return ApiSuccess(
        data=StockLedgerRead(
            id=entry.id,
            project_id=entry.project_id,
            site_id=entry.site_id,
            lot_id=entry.lot_id,
            item_id=entry.item_id,
            quantity_in=float(entry.quantity_in),
            quantity_out=float(entry.quantity_out),
        ),
        message="Stock transferred to lot.",
    )


@router.post(
    "/projects/{project_id}/site-transfer",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def transfer_between_sites(
    project_id: uuid.UUID,
    body: SiteTransferCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    out_entry, in_entry = transfer_service.transfer_to_site(
        db,
        project_id=project_id,
        from_site_id=body.from_site_id,
        to_site_id=body.to_site_id,
        item_id=body.item_id,
        quantity=body.quantity,
        entered_by=current_user.id,
        notes=body.notes,
        unit_cost=body.unit_cost,
    )
    return ApiSuccess(
        data={"out_ledger_id": str(out_entry.id), "in_ledger_id": str(in_entry.id)},
        message="Stock transferred between sites.",
    )
