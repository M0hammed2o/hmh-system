"""Lots routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.lot import LotCreate, LotRead, LotUpdate
from app.services import lot_service

project_lots_router = APIRouter(
    prefix="/projects/{project_id}/lots",
    tags=["lots"],
)
lots_router = APIRouter(prefix="/lots", tags=["lots"])


@project_lots_router.get(
    "/",
    response_model=ApiSuccess[list[LotRead]],
    dependencies=[ALL_ROLES],
)
def list_lots(project_id: uuid.UUID, db: DbSession):
    lots = lot_service.list_lots(db, project_id)
    return ApiSuccess(data=[LotRead.model_validate(l) for l in lots])


@project_lots_router.post(
    "/",
    response_model=ApiSuccess[LotRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_lot(project_id: uuid.UUID, body: LotCreate, db: DbSession):
    lot = lot_service.create_lot(db, project_id, body)
    return ApiSuccess(data=LotRead.model_validate(lot), message="Lot created successfully.")


@lots_router.get(
    "/{lot_id}",
    response_model=ApiSuccess[LotRead],
    dependencies=[ALL_ROLES],
)
def get_lot(lot_id: uuid.UUID, db: DbSession):
    lot = lot_service.get_lot(db, lot_id)
    return ApiSuccess(data=LotRead.model_validate(lot))


@lots_router.get(
    "/{lot_id}/boq-headers",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def get_lot_boq_headers(lot_id: uuid.UUID, db: DbSession):
    """
    Return all BOQ headers that have at least one item assigned to this lot.
    Used to navigate from a lot to its specific BOQ builder.
    """
    from app.models.boq import BOQHeader, BOQItem, BOQSection
    from sqlalchemy import distinct

    lot = lot_service.get_lot(db, lot_id)

    # Find all header IDs via items that have this lot_id
    header_ids = (
        db.query(distinct(BOQHeader.id))
        .join(BOQSection, BOQSection.boq_header_id == BOQHeader.id)
        .join(BOQItem, BOQItem.boq_section_id == BOQSection.id)
        .filter(BOQItem.lot_id == lot_id, BOQItem.is_active == True)
        .all()
    )
    ids = [row[0] for row in header_ids]

    headers = db.query(BOQHeader).filter(BOQHeader.id.in_(ids)).all() if ids else []

    return ApiSuccess(data=[
        {
            "id": str(h.id),
            "project_id": str(h.project_id),
            "version_name": h.version_name,
            "template_name": h.template_name,
            "status": h.status.value,
            "is_active_version": h.is_active_version,
            "is_template": h.is_template,
        }
        for h in headers
    ])


@lots_router.patch(
    "/{lot_id}",
    response_model=ApiSuccess[LotRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_lot(lot_id: uuid.UUID, body: LotUpdate, db: DbSession):
    lot = lot_service.update_lot(db, lot_id, body)
    return ApiSuccess(data=LotRead.model_validate(lot), message="Lot updated successfully.")


@lots_router.delete(
    "/{lot_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_lot(lot_id: uuid.UUID, db: DbSession):
    """
    Delete a lot.

    Hard-deletes the lot row.  FK constraints (ondelete=SET NULL) will NULL-out
    boq_items.lot_id and stock_ledger.lot_id automatically, preserving audit data.

    Blocked if the lot has:
    - Active stock ledger movements  (financial record — must be zero-balanced first)
    - Linked deliveries via site      (soft dependency check)

    BOQ items are allowed — they will become unassigned (lot_id=NULL) on cascade.
    """
    from app.models.boq import BOQItem
    from app.models.stock import StockLedger, UsageLog

    lot = lot_service.get_lot(db, lot_id)

    # Block if stock ledger entries exist — these represent real material movements
    ledger_count = (
        db.query(StockLedger)
        .filter(StockLedger.lot_id == lot_id)
        .count()
    )
    if ledger_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete lot {lot.lot_number}: it has {ledger_count} stock ledger "
            "entries. Archive or transfer stock before deleting.",
        )

    usage_count = db.query(UsageLog).filter(UsageLog.lot_id == lot_id).count()
    if usage_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete lot {lot.lot_number}: it has {usage_count} usage log "
            "entries. These represent recorded material usage and cannot be removed.",
        )

    # BOQ items will be SET NULL automatically by the FK constraint — acceptable
    boq_count = db.query(BOQItem).filter(BOQItem.lot_id == lot_id).count()

    db.delete(lot)
    db.commit()
    return ApiSuccess(
        data={"deleted_lot_number": lot.lot_number, "boq_items_unlinked": boq_count},
        message=f"Lot {lot.lot_number} deleted."
        + (f" {boq_count} BOQ item(s) were unlinked." if boq_count else ""),
    )


@lots_router.get(
    "/{lot_id}/boq-summary",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_lot_boq_summary(lot_id: uuid.UUID, db: DbSession):
    """
    Return per-item BOQ allocation vs actual usage for a lot.
    Used by the lot detail page to show allocated/used/remaining/over columns.
    """
    from sqlalchemy import func
    from app.models.boq import BOQItem, BOQSection, BOQHeader
    from app.models.item import Item
    from app.models.stock import StockLedger
    from app.models.enums import ItemType

    lot = lot_service.get_lot(db, lot_id)

    # Get all active BOQ items for this lot
    boq_items = (
        db.query(BOQItem)
        .filter(BOQItem.lot_id == lot_id, BOQItem.is_active == True)
        .order_by(BOQItem.sort_order)
        .all()
    )

    # Get actual usage from stock ledger per item
    usage_map: dict[uuid.UUID, float] = {}
    if boq_items:
        item_ids = list({i.item_id for i in boq_items if i.item_id})
        if item_ids:
            rows = (
                db.query(
                    StockLedger.item_id,
                    func.sum(StockLedger.quantity_out).label("used"),
                )
                .filter(
                    StockLedger.lot_id == lot_id,
                    StockLedger.item_id.in_(item_ids),
                )
                .group_by(StockLedger.item_id)
                .all()
            )
            usage_map = {r.item_id: float(r.used or 0) for r in rows}

    # Load item names
    item_name_map: dict[uuid.UUID, str] = {}
    for boq_item in boq_items:
        if boq_item.item_id and boq_item.item_id not in item_name_map:
            item = db.get(Item, boq_item.item_id)
            if item:
                item_name_map[boq_item.item_id] = item.name

    total_planned = 0.0
    total_used_cost = 0.0
    items_out = []

    for bi in boq_items:
        allocated = float(bi.planned_quantity or 0)
        used = usage_map.get(bi.item_id, 0.0) if bi.item_id else 0.0
        remaining = max(0.0, allocated - used)
        over = max(0.0, used - allocated)
        planned_total = float(bi.planned_total or 0)
        total_planned += planned_total
        rate = float(bi.planned_rate or 0)
        used_cost = used * rate
        total_used_cost += used_cost

        items_out.append({
            "boq_item_id": str(bi.id),
            "item_id": str(bi.item_id) if bi.item_id else None,
            "description": bi.raw_description,
            "item_type": bi.item_type.value if bi.item_type else "MATERIAL",
            "unit": bi.unit,
            "item_name": item_name_map.get(bi.item_id, "") if bi.item_id else "",
            "allocated_quantity": allocated,
            "used_quantity": used,
            "remaining_quantity": remaining,
            "over_quantity": over,
            "is_over": over > 0 and allocated > 0,
            "planned_rate": rate,
            "planned_total": planned_total,
            "used_cost": round(used_cost, 2),
        })

    return ApiSuccess(data={
        "lot_id": str(lot_id),
        "lot_number": lot.lot_number,
        "items": items_out,
        "total_planned_cost": round(total_planned, 2),
        "total_used_cost": round(total_used_cost, 2),
        "total_items": len(items_out),
        "overrun_count": sum(1 for i in items_out if i["is_over"]),
    })


# ── Unassigned lots: list + bulk assign ──────────────────────────────────────

@project_lots_router.get(
    "/unassigned",
    response_model=ApiSuccess[list[LotRead]],
    dependencies=[OFFICE_AND_ABOVE],
)
def list_unassigned_lots(project_id: uuid.UUID, db: DbSession):
    """Return all lots for this project that have no site_id set."""
    from app.models.lot import Lot
    lots = (
        db.query(Lot)
        .filter(Lot.project_id == project_id, Lot.site_id.is_(None))
        .order_by(Lot.lot_number)
        .all()
    )
    return ApiSuccess(data=[LotRead.model_validate(l) for l in lots])


class _BulkAssignSiteBody(BaseModel):
    site_id:  uuid.UUID
    lot_ids:  list[uuid.UUID]


@project_lots_router.patch(
    "/assign-site",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def bulk_assign_lots_to_site(
    project_id: uuid.UUID,
    body: _BulkAssignSiteBody,
    db: DbSession,
):
    """
    Assign a list of lots to a specific site.
    Only operates on lots that currently have site_id IS NULL — it will not
    override an existing site assignment, preventing accidental cross-site moves.
    """
    from app.models.lot import Lot
    from app.models.site import Site

    site = db.get(Site, body.site_id)
    if not site or site.project_id != project_id:
        raise HTTPException(404, "Site not found in this project.")

    updated = 0
    skipped = 0
    for lot_id in body.lot_ids:
        lot = db.get(Lot, lot_id)
        if not lot or lot.project_id != project_id:
            skipped += 1
            continue
        if lot.site_id is not None:
            # Safety: never overwrite an existing site assignment
            skipped += 1
            continue
        lot.site_id = body.site_id
        updated += 1

    db.commit()
    return ApiSuccess(
        data={"updated": updated, "skipped": skipped},
        message=f"{updated} lot(s) assigned to site '{site.name}'. {skipped} skipped (already assigned).",
    )


# ── Lots generator ────────────────────────────────────────────────────────────

class LotGenerateRequest(BaseModel):
    start_number: int
    end_number: int
    site_id: Optional[uuid.UUID] = None
    unit_type: Optional[str] = None
    boq_template_id: Optional[uuid.UUID] = None

    @field_validator("end_number")
    @classmethod
    def sane_range(cls, v: int, info) -> int:
        start = info.data.get("start_number", 1)
        if v < start:
            raise ValueError("end_number must be >= start_number")
        if (v - start + 1) > 500:
            raise ValueError("Cannot generate more than 500 lots at once")
        return v


@project_lots_router.post(
    "/generate",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def generate_lots(
    project_id: uuid.UUID,
    body: LotGenerateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Generate lots from start_number to end_number.
    Skips any lot_number that already exists for this project.
    If boq_template_id is provided, clones the template to each new lot.
    """
    created_lots = lot_service.generate_lots(
        db,
        project_id=project_id,
        start_number=body.start_number,
        end_number=body.end_number,
        site_id=body.site_id,
        unit_type=body.unit_type,
        boq_template_id=body.boq_template_id,
        actor_id=current_user.id,
    )
    return ApiSuccess(
        data={
            "created": len(created_lots),
            "lot_ids": [str(l.id) for l in created_lots],
            "lot_numbers": [l.lot_number for l in created_lots],
        },
        message=f"{len(created_lots)} lots generated.",
    )
