"""
Site Warehouse routes.

A Site Warehouse is the stock held at a site level (site_id = X, lot_id = NULL)
before being allocated/transferred to individual lots.

Stock flow:
  Delivery / Main Warehouse → Site Warehouse → Lot

GET  /sites/{site_id}/warehouse          — current on-hand stock per item
POST /sites/{site_id}/warehouse/transfer  — move items from site warehouse to lot
GET  /sites/{site_id}/warehouse/history   — recent movements through this warehouse
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.models.enums import MovementType
from app.models.item import Item
from app.models.lot import Lot
from app.models.site import Site
from app.models.stock import StockLedger
from app.schemas.common import ApiSuccess
from app.services import audit_service
from app.models.enums import AuditAction

router = APIRouter(prefix="/sites/{site_id}/warehouse", tags=["warehouse"])


# ── On-hand stock ─────────────────────────────────────────────────────────────

@router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_warehouse_stock(site_id: uuid.UUID, db: DbSession):
    """
    Returns current on-hand stock for the Site Warehouse.

    On-hand = items received at site level (lot_id IS NULL) minus transfers out.
    This includes stock received from deliveries and transfers from Main Warehouse.
    """
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")

    # Aggregate: net balance per item at site level (lot_id IS NULL)
    rows = db.execute(text("""
        SELECT
            sl.item_id,
            i.name                              AS item_name,
            i.default_unit                      AS unit,
            SUM(sl.quantity_in)                 AS total_in,
            SUM(sl.quantity_out)                AS total_out,
            SUM(sl.quantity_in) - SUM(sl.quantity_out) AS on_hand,
            MAX(sl.movement_date)               AS last_movement
        FROM stock_ledger sl
        JOIN items i ON i.id = sl.item_id
        WHERE sl.site_id   = :site_id
          AND sl.lot_id IS NULL
        GROUP BY sl.item_id, i.name, i.default_unit
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY i.name
    """), {"site_id": str(site_id)}).mappings().all()

    result = []
    for r in rows:
        result.append({
            "item_id":       str(r["item_id"]),
            "item_name":     r["item_name"],
            "unit":          r["unit"],
            "on_hand":       float(r["on_hand"]),
            "total_in":      float(r["total_in"]),
            "total_out":     float(r["total_out"]),
            "last_movement": r["last_movement"].isoformat() if r["last_movement"] else None,
        })

    return ApiSuccess(data=result, message=f"{len(result)} item(s) in site warehouse.")


# ── Transfer to lot ───────────────────────────────────────────────────────────

class TransferToLotRequest(BaseModel):
    item_id:  uuid.UUID
    lot_id:   uuid.UUID
    quantity: float
    notes:    Optional[str] = None


@router.post("/transfer", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def transfer_to_lot(
    site_id: uuid.UUID,
    body: TransferToLotRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Transfer stock from the Site Warehouse to a specific lot.

    Creates two immutable StockLedger entries:
      TRANSFER_OUT  — stock leaves the site warehouse  (site, lot=NULL)
      TRANSFER_IN   — stock enters the lot             (site, lot=Y)
    """
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")

    lot = db.get(Lot, body.lot_id)
    if not lot or lot.site_id != site_id:
        raise HTTPException(404, "Lot not found in this site.")

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Transfer quantity must be greater than zero.")

    # Check available balance
    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE site_id = :site_id AND lot_id IS NULL AND item_id = :item_id
    """), {"site_id": str(site_id), "item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient stock. Site warehouse has {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    # 1. TRANSFER_OUT from site warehouse (lot_id = NULL)
    db.add(StockLedger(
        project_id     = site.project_id,
        site_id        = site_id,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "warehouse_transfer",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Transferred to Lot {lot.lot_number}",
        created_at     = now,
    ))

    # 2. TRANSFER_IN to lot (lot_id = Y)
    db.add(StockLedger(
        project_id     = site.project_id,
        site_id        = site_id,
        lot_id         = body.lot_id,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "warehouse_transfer",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Received from Site Warehouse",
        created_at     = now,
    ))

    # Audit trail
    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="site_warehouse",
        actor_id=current_user.id,
        entity_id=site_id,
        after_value={
            "item": item.name,
            "quantity": body.quantity,
            "unit": item.default_unit,
            "lot_number": lot.lot_number,
            "transfer_ref": str(transfer_ref),
        },
    )

    db.commit()

    # Refresh materialized view
    import os as _os
    _in_test = bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"
    if not _in_test:
        try:
            db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
            db.commit()
        except Exception:
            db.rollback()

    print(
        f"[WAREHOUSE] Transferred {body.quantity} {item.default_unit or ''} of {item.name}"
        f" from site={site_id} to lot={lot.lot_number} (ref={transfer_ref})",
        flush=True,
    )

    return ApiSuccess(
        data={
            "transfer_ref":  str(transfer_ref),
            "item_id":       str(body.item_id),
            "item_name":     item.name,
            "quantity":      body.quantity,
            "unit":          item.default_unit,
            "lot_number":    lot.lot_number,
            "new_balance":   available - body.quantity,
        },
        message=f"Transferred {body.quantity} {item.default_unit or ''} of {item.name} to Lot {lot.lot_number}.",
    )


# ── Movement history ──────────────────────────────────────────────────────────

@router.get("/history", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_warehouse_history(
    site_id: uuid.UUID,
    db: DbSession,
    limit: int = Query(50, le=200),
):
    """Recent stock movements through this site warehouse (lot_id IS NULL)."""
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")

    rows = db.execute(text("""
        SELECT
            sl.id,
            sl.movement_type,
            sl.quantity_in,
            sl.quantity_out,
            sl.unit,
            sl.movement_date,
            sl.notes,
            sl.reference_type,
            i.name AS item_name,
            u.full_name AS entered_by_name
        FROM stock_ledger sl
        JOIN items i ON i.id = sl.item_id
        LEFT JOIN users u ON u.id = sl.entered_by
        WHERE sl.site_id   = :site_id
          AND sl.lot_id IS NULL
        ORDER BY sl.movement_date DESC
        LIMIT :limit
    """), {"site_id": str(site_id), "limit": limit}).mappings().all()

    return ApiSuccess(data=[
        {
            "id":             str(r["id"]),
            "movement_type":  r["movement_type"],
            "item_name":      r["item_name"],
            "quantity_in":    float(r["quantity_in"] or 0),
            "quantity_out":   float(r["quantity_out"] or 0),
            "unit":           r["unit"],
            "movement_date":  r["movement_date"].isoformat() if r["movement_date"] else None,
            "notes":          r["notes"],
            "reference_type": r["reference_type"],
            "entered_by":     r["entered_by_name"],
        }
        for r in rows
    ])
