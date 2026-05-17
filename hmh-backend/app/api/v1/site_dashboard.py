"""
Site Dashboard API — real-time BOQ allocation vs delivery vs usage tracking per lot.

GET  /site-dashboard/{site_id}/lots/{lot_id}/material-summary
GET  /site-dashboard/{site_id}/lots/{lot_id}/activity
"""

import uuid

from fastapi import APIRouter
from sqlalchemy import func

from app.dependencies import ALL_ROLES, DbSession
from app.models.boq import BOQItem
from app.models.enums import MovementType
from app.models.stock import StockLedger
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/site-dashboard", tags=["site-dashboard"])


# ── Material summary ──────────────────────────────────────────────────────────

@router.get("/{site_id}/lots/{lot_id}/material-summary", dependencies=[ALL_ROLES])
def lot_material_summary(site_id: uuid.UUID, lot_id: uuid.UUID, db: DbSession):
    """
    Per-item BOQ summary: allocated vs delivered vs used vs remaining.

    Data source priority:
      1. BOQItem rows where lot_id = <lot_id>   (lot-specific BOQ)
      2. BOQItem rows where site_id = <site_id> and lot_id IS NULL  (site template)

    Unlike allocation_service.get_all_lot_allocations(), this endpoint
    does NOT filter by item_id IS NOT NULL — so template items without
    a catalog link (item_id = NULL) are included correctly.

    Stock matching:
      - If item_id is set  → match StockLedger by item_id + lot_id
      - If item_id is NULL → match StockLedger by boq_item_id + lot_id
    """
    from app.models.lot import Lot
    from app.models.item import Item

    # ── 1. Fetch BOQ items ────────────────────────────────────────────────────
    boq_items = (
        db.query(BOQItem)
        .filter(BOQItem.lot_id == lot_id, BOQItem.is_active == True)
        .all()
    )

    # ── 2. Fall back to site-level template if lot has no BOQ items ───────────
    fallback = False
    if not boq_items:
        lot = db.get(Lot, lot_id)
        if lot and lot.site_id:
            boq_items = (
                db.query(BOQItem)
                .filter(
                    BOQItem.site_id   == lot.site_id,
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active == True,
                )
                .all()
            )
            fallback = bool(boq_items)

    # ── 3. De-duplicate by (raw_description, item_type, unit) ────────────────
    # Duplicates arise when a template is applied to lots AND generate_lot_boqs
    # is also called, inserting two copies of each item for the same lot.
    # Keep only the first occurrence (highest planned_quantity wins on tie).
    seen_keys: set = set()
    unique_boq_items = []
    for bi in sorted(boq_items, key=lambda x: float(x.planned_quantity or 0), reverse=True):
        key = (
            (bi.raw_description or "").lower().strip(),
            bi.unit or "",
        )
        if key not in seen_keys:
            seen_keys.add(key)
            unique_boq_items.append(bi)
    boq_items = unique_boq_items

    # ── 4. Build summary rows ─────────────────────────────────────────────────
    result = []
    for bi in boq_items:
        allocated = float(bi.planned_quantity or 0)

        # Stock filter strategy: prefer item_id (catalog), fall back to boq_item_id
        if bi.item_id:
            delivered = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_in), 0))
                .filter(
                    StockLedger.lot_id        == lot_id,
                    StockLedger.item_id       == bi.item_id,
                    StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
                )
                .scalar() or 0
            )
            used = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_out), 0))
                .filter(
                    StockLedger.lot_id   == lot_id,
                    StockLedger.item_id  == bi.item_id,
                )
                .scalar() or 0
            )
        else:
            delivered = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_in), 0))
                .filter(
                    StockLedger.lot_id        == lot_id,
                    StockLedger.boq_item_id   == bi.id,
                    StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
                )
                .scalar() or 0
            )
            used = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_out), 0))
                .filter(
                    StockLedger.lot_id        == lot_id,
                    StockLedger.boq_item_id   == bi.id,
                )
                .scalar() or 0
            )

        remaining = max(0.0, allocated - used)
        over      = max(0.0, used - allocated)
        is_over   = allocated > 0 and used > allocated

        if is_over:
            status = "OVER_BOQ"
        elif allocated > 0 and remaining < allocated * 0.15:
            status = "LOW"
        elif used > 0 and delivered > 0 and used > delivered:
            status = "STOCK_ISSUE"
        else:
            status = "OK"

        # Prefer linked catalog item name/unit; fall back to BOQ raw description
        description = bi.raw_description
        unit        = bi.unit
        if bi.item_id:
            cat_item = db.get(Item, bi.item_id)
            if cat_item:
                description = cat_item.name
                unit        = cat_item.default_unit or bi.unit

        result.append({
            "boq_item_id":       str(bi.id),
            "item_id":           str(bi.item_id) if bi.item_id else None,
            "description":       description,
            "unit":              unit,
            "boq_allocated_qty": round(allocated, 3),
            "delivered_qty":     round(delivered, 3),
            "used_qty":          round(used, 3),
            "remaining_qty":     round(remaining, 3),
            "over_qty":          round(over, 3),
            "status":            status,
            "from_site_template": fallback,
        })

    return ApiSuccess(data=result)


# ── Activity feed ─────────────────────────────────────────────────────────────

@router.get("/{site_id}/lots/{lot_id}/activity", dependencies=[ALL_ROLES])
def lot_activity(site_id: uuid.UUID, lot_id: uuid.UUID, db: DbSession, limit: int = 20):
    """
    Recent activity for a site/lot — deliveries, usage, alerts, stage updates.
    Returns a unified list sorted newest-first.
    """
    from app.models.delivery import Delivery
    from app.models.alert import SystemAlert
    from app.models.item import Item
    from app.models.stage import ProjectStageStatus

    activities = []

    # Deliveries
    for d in (
        db.query(Delivery)
        .filter(Delivery.site_id == site_id)
        .order_by(Delivery.delivery_date.desc())
        .limit(8)
        .all()
    ):
        activities.append({
            "type":   "delivery",
            "title":  f"Delivery: {d.delivery_number or str(d.id)[:8]}",
            "date":   d.delivery_date.isoformat() if d.delivery_date else None,
            "status": d.delivery_status.value if d.delivery_status else None,
        })

    # Usage ledger entries for this lot
    for row in (
        db.query(StockLedger)
        .filter(
            StockLedger.site_id        == site_id,
            StockLedger.lot_id         == lot_id,
            StockLedger.movement_type  == MovementType.USAGE,
        )
        .order_by(StockLedger.movement_date.desc())
        .limit(8)
        .all()
    ):
        item = db.get(Item, row.item_id)
        activities.append({
            "type":   "usage",
            "title":  f"Usage: {item.name if item else 'Unknown'} — {row.quantity_out:.1f} {row.unit or ''}",
            "date":   row.movement_date.isoformat() if row.movement_date else None,
            "status": None,
        })

    # Alerts for this site
    for a in (
        db.query(SystemAlert)
        .filter(SystemAlert.site_id == site_id)
        .order_by(SystemAlert.created_at.desc())
        .limit(8)
        .all()
    ):
        activities.append({
            "type":     "alert",
            "title":    a.title,
            "date":     a.created_at.isoformat(),
            "status":   a.severity.value if a.severity else None,
            "severity": a.severity.value if a.severity else None,
        })

    # Stage updates for this lot
    for s in (
        db.query(ProjectStageStatus)
        .filter(ProjectStageStatus.lot_id == lot_id)
        .order_by(ProjectStageStatus.updated_at.desc())
        .limit(4)
        .all()
    ):
        activities.append({
            "type":   "stage",
            "title":  f"Stage: {s.stage_name or 'Unknown'} → {s.status.value if s.status else '?'}",
            "date":   s.updated_at.isoformat() if s.updated_at else None,
            "status": s.status.value if s.status else None,
        })

    activities.sort(key=lambda x: x.get("date") or "", reverse=True)
    return ApiSuccess(data=activities[:limit])
