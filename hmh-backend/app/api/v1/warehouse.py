"""
Warehouse routes — three levels:

  Global Main Warehouse  (GET /warehouse/main/)            — company-wide, no project filter
  Project Warehouse      (GET /projects/{id}/warehouse/)   — per-project, site_id IS NULL
  Site Warehouse         (GET /sites/{id}/warehouse/)      — per-site, lot_id IS NULL

Stock flow:
  Supplier Delivery → Project Warehouse → Site Warehouse → Lot
"""

import uuid

from app.core.logging_config import get_logger as _get_logger
_wh_log = _get_logger(__name__)
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.enums import MovementType
from app.models.item import Item
from app.models.lot import Lot
from app.models.site import Site
from app.models.stock import StockLedger
from app.schemas.common import ApiSuccess
from app.services import audit_service
from app.models.enums import AuditAction

router = APIRouter(prefix="/sites/{site_id}/warehouse", tags=["warehouse"])
project_warehouse_router = APIRouter(prefix="/projects/{project_id}/warehouse", tags=["warehouse"])
global_warehouse_router  = APIRouter(prefix="/warehouse", tags=["warehouse"])


# ── On-hand stock ─────────────────────────────────────────────────────────────

@router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_warehouse_stock(site_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Returns current on-hand stock for the Site Warehouse.

    On-hand = items received at site level (lot_id IS NULL) minus transfers out.
    This includes stock received from deliveries and transfers from Main Warehouse.
    """
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")
    check_project_access(db, current_user, site.project_id)

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


@router.post("/transfer", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
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
    check_project_access(db, current_user, site.project_id)

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

    _wh_log.info("warehouse transfer qty=%s item=%s site=%s lot=%s ref=%s",
                 body.quantity, item.name, site_id, lot.lot_number, transfer_ref)

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
    current_user: CurrentUser,
    limit: int = Query(50, le=200),
):
    """Recent stock movements through this site warehouse (lot_id IS NULL)."""
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")
    check_project_access(db, current_user, site.project_id)

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


# ── Site warehouse: TOOL items ────────────────────────────────────────────────

@router.get("/tools", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_site_tools(site_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """List TOOL items currently in this site warehouse (lot_id IS NULL, item_type = TOOL)."""
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")
    check_project_access(db, current_user, site.project_id)

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
        WHERE sl.site_id = :site_id
          AND sl.lot_id IS NULL
          AND i.item_type = 'TOOL'
        GROUP BY sl.item_id, i.name, i.default_unit
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY i.name
    """), {"site_id": str(site_id)}).mappings().all()

    return ApiSuccess(data=[{
        "item_id":       str(r["item_id"]),
        "item_name":     r["item_name"],
        "unit":          r["unit"],
        "on_hand":       float(r["on_hand"]),
        "total_in":      float(r["total_in"]),
        "total_out":     float(r["total_out"]),
        "last_movement": r["last_movement"].isoformat() if r["last_movement"] else None,
    } for r in rows], message=f"{len(rows)} tool(s) at site.")


class ReturnToolsRequest(BaseModel):
    item_id:  uuid.UUID
    quantity: float
    notes:    Optional[str] = None


@router.post("/return-tools", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def return_tools_to_main(
    site_id: uuid.UUID,
    body: ReturnToolsRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Return tools from a site warehouse back to the global main warehouse (project_id=NULL).

    TRANSFER_OUT — leaves site   (project_id=site.project_id, site_id=X, lot_id=NULL)
    TRANSFER_IN  — enters global (project_id=NULL, site_id=NULL, lot_id=NULL)
    """
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")
    check_project_access(db, current_user, site.project_id)

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Return quantity must be greater than zero.")

    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE site_id = :site_id
          AND lot_id IS NULL
          AND item_id = :item_id
    """), {"site_id": str(site_id), "item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient tools at site. "
            f"Available: {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    db.add(StockLedger(
        project_id     = site.project_id,
        site_id        = site_id,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "site_to_global_tool_return",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or "Tool returned to Main Warehouse",
        created_at     = now,
    ))

    db.add(StockLedger(
        project_id     = None,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "site_to_global_tool_return",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Tool returned from {site.name}",
        created_at     = now,
    ))

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="site_warehouse",
        actor_id=current_user.id,
        entity_id=site_id,
        after_value={
            "direction":    "site_to_global",
            "item":         item.name,
            "quantity":     body.quantity,
            "unit":         item.default_unit,
            "site":         site.name,
            "transfer_ref": str(transfer_ref),
        },
    )

    db.commit()
    return ApiSuccess(
        data={
            "transfer_ref": str(transfer_ref),
            "item_id":      str(body.item_id),
            "item_name":    item.name,
            "quantity":     body.quantity,
            "unit":         item.default_unit,
            "site_name":    site.name,
            "new_balance":  available - body.quantity,
        },
        message=f"Returned {body.quantity} {item.default_unit or ''} of {item.name} to Main Warehouse.",
    )


# ── Main Warehouse (project-level stock: site_id IS NULL, lot_id IS NULL) ─────

@project_warehouse_router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_main_warehouse_stock(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Returns current on-hand stock in the Main (Project) Warehouse.

    Main Warehouse = StockLedger rows where site_id IS NULL and lot_id IS NULL.
    Stock arrives when deliveries are set to MAIN_WAREHOUSE destination.
    """
    from app.models.project import Project
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

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
        WHERE sl.project_id  = :project_id
          AND sl.site_id  IS NULL
          AND sl.lot_id   IS NULL
        GROUP BY sl.item_id, i.name, i.default_unit
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY i.name
    """), {"project_id": str(project_id)}).mappings().all()

    result = [{
        "item_id":       str(r["item_id"]),
        "item_name":     r["item_name"],
        "unit":          r["unit"],
        "on_hand":       float(r["on_hand"]),
        "total_in":      float(r["total_in"]),
        "total_out":     float(r["total_out"]),
        "last_movement": r["last_movement"].isoformat() if r["last_movement"] else None,
    } for r in rows]

    return ApiSuccess(data=result, message=f"{len(result)} item(s) in main warehouse.")


@project_warehouse_router.get("/boq-summary", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_warehouse_boq_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Aggregate MATERIAL BOQ items across all lots in the project.
    Compares planned qty vs on-hand stock in the Project Warehouse.
    Used by the Project Warehouse dashboard Outstanding Materials panel.
    """
    from app.models.project import Project as _Proj
    from app.models.boq import BOQItem
    from app.models.enums import ItemType
    from collections import defaultdict

    project = db.get(_Proj, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    # All MATERIAL BOQ items attached to a specific lot in this project
    boq_rows = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.is_active  == True,
            BOQItem.item_type  == ItemType.MATERIAL,
            BOQItem.lot_id.isnot(None),
        )
        .all()
    )

    # Aggregate by item_id (when linked) or normalised description+unit
    groups: dict = defaultdict(lambda: {
        "total_planned": 0.0, "lots": set(),
        "description": "", "unit": None, "item_id": None,
    })
    for bi in boq_rows:
        if bi.item_id:
            key = str(bi.item_id)
            groups[key]["item_id"] = str(bi.item_id)
        else:
            key = f"_:{(bi.raw_description or '').lower().strip()}:{bi.unit or ''}"

        groups[key]["total_planned"] += float(bi.planned_quantity or 0)
        groups[key]["description"]    = bi.raw_description or groups[key]["description"]
        groups[key]["unit"]           = bi.unit
        if bi.lot_id:
            groups[key]["lots"].add(str(bi.lot_id))

    # On-hand stock in the Project Warehouse (site_id IS NULL, lot_id IS NULL)
    stock_rows = db.execute(text("""
        SELECT sl.item_id,
               SUM(sl.quantity_in) - SUM(sl.quantity_out) AS on_hand
        FROM stock_ledger sl
        WHERE sl.project_id = :pid
          AND sl.site_id IS NULL
          AND sl.lot_id  IS NULL
        GROUP BY sl.item_id
    """), {"pid": str(project_id)}).mappings().all()
    on_hand_by_item: dict = {str(r["item_id"]): float(r["on_hand"] or 0) for r in stock_rows}

    result = []
    for g in sorted(groups.values(), key=lambda x: (x["description"] or "").lower()):
        on_hand = on_hand_by_item.get(g["item_id"] or "", 0.0) if g["item_id"] else 0.0
        total   = g["total_planned"]
        result.append({
            "item_id":       g["item_id"],
            "description":   g["description"],
            "unit":          g["unit"],
            "total_boq_qty": round(total, 3),
            "on_hand_qty":   round(on_hand, 3),
            "shortfall_qty": round(max(0.0, total - on_hand), 3),
            "lots_count":    len(g["lots"]),
        })

    return ApiSuccess(data=result)


@project_warehouse_router.get("/material-summary", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_warehouse_material_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    BOQ items aggregated across ALL lots in the project, returned in the same
    MaterialSummaryItem shape as the lot-level material-summary endpoint.

    Used by the Receive Delivery modal when operating at project warehouse level
    (no specific lot selected) so the BOQ picker shows every material the project
    needs, regardless of which lot it came from.

    Aggregation key: item_id (catalog-linked) or description+unit (non-catalog).
    boq_item_id = the representative BOQ item ID (first created for that key).
    Stock quantities reflect the project warehouse (site_id IS NULL, lot_id IS NULL).
    """
    from collections import defaultdict
    from app.models.project import Project as _Proj
    from app.models.boq import BOQItem
    from app.models.enums import ItemType
    from app.models.supplier import Supplier as _Sup

    project = db.get(_Proj, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    boq_rows = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.is_active  == True,
            BOQItem.item_type  == ItemType.MATERIAL,
            BOQItem.lot_id.isnot(None),
        )
        .order_by(BOQItem.created_at)
        .all()
    )

    groups: dict = defaultdict(lambda: {
        "boq_item_id":  None,
        "item_id":      None,
        "description":  "",
        "unit":         None,
        "supplier_id":  None,
        "total_planned": 0.0,
    })
    for bi in boq_rows:
        key = str(bi.item_id) if bi.item_id else f"_:{(bi.raw_description or '').lower().strip()}:{bi.unit or ''}"
        g = groups[key]
        if g["boq_item_id"] is None:
            g["boq_item_id"] = str(bi.id)
            g["item_id"]     = str(bi.item_id) if bi.item_id else None
            g["description"] = bi.raw_description or ""
            g["unit"]        = bi.unit
            g["supplier_id"] = str(bi.supplier_id) if bi.supplier_id else None
        g["total_planned"] += float(bi.planned_quantity or 0)

    if not groups:
        return ApiSuccess(data=[])

    item_ids = [uuid.UUID(g["item_id"]) for g in groups.values() if g["item_id"]]
    items_map = {str(i.id): i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()} if item_ids else {}
    supplier_ids = [uuid.UUID(g["supplier_id"]) for g in groups.values() if g["supplier_id"]]
    suppliers_map = {str(s.id): s for s in db.query(_Sup).filter(_Sup.id.in_(supplier_ids)).all()} if supplier_ids else {}

    in_rows = db.execute(text("""
        SELECT item_id, COALESCE(SUM(quantity_in), 0) AS total_in
        FROM stock_ledger
        WHERE project_id = :pid AND site_id IS NULL AND lot_id IS NULL
          AND movement_type = 'DELIVERY_RECEIVED'
        GROUP BY item_id
    """), {"pid": str(project_id)}).mappings().all()
    delivered_by_item = {str(r["item_id"]): float(r["total_in"]) for r in in_rows}

    out_rows = db.execute(text("""
        SELECT item_id, COALESCE(SUM(quantity_out), 0) AS total_out
        FROM stock_ledger
        WHERE project_id = :pid AND site_id IS NULL AND lot_id IS NULL
        GROUP BY item_id
    """), {"pid": str(project_id)}).mappings().all()
    used_by_item = {str(r["item_id"]): float(r["total_out"]) for r in out_rows}

    result = []
    for g in sorted(groups.values(), key=lambda x: (x["description"] or "").lower()):
        item_id  = g["item_id"]
        cat_item = items_map.get(item_id) if item_id else None

        description  = cat_item.name if cat_item else g["description"]
        unit         = (cat_item.default_unit if cat_item else None) or g["unit"]
        supplier_id  = g["supplier_id"]
        supplier_name = suppliers_map[supplier_id].name if supplier_id and supplier_id in suppliers_map else None

        allocated = g["total_planned"]
        delivered = delivered_by_item.get(item_id, 0.0) if item_id else 0.0
        used      = used_by_item.get(item_id, 0.0)      if item_id else 0.0
        remaining = max(0.0, allocated - used)
        over      = max(0.0, used - allocated)

        if used > allocated > 0:
            status = "OVER_BOQ"
        elif allocated > 0 and remaining < allocated * 0.15:
            status = "LOW"
        elif used > 0 and delivered > 0 and used > delivered:
            status = "STOCK_ISSUE"
        else:
            status = "OK"

        result.append({
            "boq_item_id":       g["boq_item_id"],
            "item_id":           item_id,
            "description":       description,
            "unit":              unit,
            "boq_allocated_qty": round(allocated, 3),
            "delivered_qty":     round(delivered, 3),
            "used_qty":          round(used, 3),
            "remaining_qty":     round(remaining, 3),
            "over_qty":          round(over, 3),
            "status":            status,
            "from_site_template": False,
            "supplier_id":       supplier_id,
            "supplier_name":     supplier_name,
        })

    return ApiSuccess(data=result)


class TransferToSiteRequest(BaseModel):
    item_id:  uuid.UUID
    site_id:  uuid.UUID
    quantity: float
    notes:    Optional[str] = None


@project_warehouse_router.post("/transfer", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def transfer_main_to_site(
    project_id: uuid.UUID,
    body: TransferToSiteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Transfer stock from Main Warehouse to a Site Warehouse.

    Creates two StockLedger entries:
      TRANSFER_OUT — stock leaves main warehouse  (site=NULL, lot=NULL)
      TRANSFER_IN  — stock enters site warehouse   (site=X,   lot=NULL)
    """
    from app.models.project import Project
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    site = db.get(Site, body.site_id)
    if not site or site.project_id != project_id:
        raise HTTPException(404, "Site not found in this project.")

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Transfer quantity must be greater than zero.")

    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE project_id = :project_id
          AND site_id  IS NULL
          AND lot_id   IS NULL
          AND item_id  = :item_id
    """), {"project_id": str(project_id), "item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient main warehouse stock. "
            f"Available: {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    db.add(StockLedger(
        project_id     = project_id,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "main_to_site_transfer",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Transferred to {site.name}",
        created_at     = now,
    ))

    db.add(StockLedger(
        project_id     = project_id,
        site_id        = body.site_id,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "main_to_site_transfer",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Received from Main Warehouse",
        created_at     = now,
    ))

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="main_warehouse",
        actor_id=current_user.id,
        entity_id=project_id,
        after_value={
            "item": item.name,
            "quantity": body.quantity,
            "unit": item.default_unit,
            "site": site.name,
            "transfer_ref": str(transfer_ref),
        },
    )

    db.commit()
    return ApiSuccess(
        data={
            "transfer_ref": str(transfer_ref),
            "item_id":      str(body.item_id),
            "item_name":    item.name,
            "quantity":     body.quantity,
            "unit":         item.default_unit,
            "site_name":    site.name,
            "new_balance":  available - body.quantity,
        },
        message=f"Transferred {body.quantity} {item.default_unit or ''} of {item.name} to {site.name}.",
    )


# ── Return from Site to Main Warehouse ────────────────────────────────────────

class ReturnFromSiteRequest(BaseModel):
    item_id:  uuid.UUID
    site_id:  uuid.UUID
    quantity: float
    notes:    Optional[str] = None


@project_warehouse_router.post("/return", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def return_from_site_to_main(
    project_id: uuid.UUID,
    body: ReturnFromSiteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Receive stock returned from a Site Warehouse back to the Main Warehouse.

    Creates two StockLedger entries:
      TRANSFER_OUT — stock leaves site warehouse  (site=X,    lot=NULL)
      TRANSFER_IN  — stock enters main warehouse  (site=NULL, lot=NULL)
    """
    from app.models.project import Project
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    site = db.get(Site, body.site_id)
    if not site or site.project_id != project_id:
        raise HTTPException(404, "Site not found in this project.")

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Return quantity must be greater than zero.")

    # Verify site warehouse has sufficient stock
    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE project_id = :project_id
          AND site_id    = :site_id
          AND lot_id  IS NULL
          AND item_id    = :item_id
    """), {"project_id": str(project_id), "site_id": str(body.site_id), "item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient stock at {site.name}. "
            f"Site warehouse has {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested return of {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    # TRANSFER_OUT from site warehouse
    db.add(StockLedger(
        project_id     = project_id,
        site_id        = body.site_id,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "site_to_main_return",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Returned to Main Warehouse",
        created_at     = now,
    ))

    # TRANSFER_IN to main warehouse
    db.add(StockLedger(
        project_id     = project_id,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "site_to_main_return",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Received back from {site.name}",
        created_at     = now,
    ))

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="main_warehouse",
        actor_id=current_user.id,
        entity_id=project_id,
        after_value={
            "direction":    "site_to_main",
            "item":         item.name,
            "quantity":     body.quantity,
            "unit":         item.default_unit,
            "site":         site.name,
            "transfer_ref": str(transfer_ref),
        },
    )

    db.commit()
    return ApiSuccess(
        data={
            "transfer_ref":  str(transfer_ref),
            "item_id":       str(body.item_id),
            "item_name":     item.name,
            "quantity":      body.quantity,
            "unit":          item.default_unit,
            "site_name":     site.name,
            "new_main_balance": available,       # will be recalculated on next fetch
        },
        message=f"Received {body.quantity} {item.default_unit or ''} of {item.name} back from {site.name}.",
    )


# ── Transfer between project warehouses ──────────────────────────────────────

class TransferToProjectRequest(BaseModel):
    to_project_id: uuid.UUID
    item_id:       uuid.UUID
    quantity:      float
    notes:         Optional[str] = None


@project_warehouse_router.post("/transfer-to-project", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def transfer_project_to_project(
    project_id: uuid.UUID,
    body: TransferToProjectRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Transfer stock from one project's main warehouse to another project's main
    warehouse.  Both projects must be accessible to the current user.

    Creates two StockLedger entries:
      TRANSFER_OUT — stock leaves source project  (site=NULL, lot=NULL)
      TRANSFER_IN  — stock enters target project   (site=NULL, lot=NULL)
    """
    from app.models.project import Project

    if project_id == body.to_project_id:
        raise HTTPException(422, "Source and destination projects must be different.")

    src_project = db.get(Project, project_id)
    if not src_project:
        raise HTTPException(404, "Source project not found.")
    check_project_access(db, current_user, project_id)

    dst_project = db.get(Project, body.to_project_id)
    if not dst_project:
        raise HTTPException(404, "Destination project not found.")
    check_project_access(db, current_user, body.to_project_id)

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Transfer quantity must be greater than zero.")

    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE project_id = :project_id
          AND site_id  IS NULL
          AND lot_id   IS NULL
          AND item_id  = :item_id
    """), {"project_id": str(project_id), "item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient stock in {src_project.name}. "
            f"Available: {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    db.add(StockLedger(
        project_id     = project_id,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "project_to_project_transfer",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Transferred to {dst_project.name}",
        created_at     = now,
    ))

    db.add(StockLedger(
        project_id     = body.to_project_id,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "project_to_project_transfer",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Received from {src_project.name}",
        created_at     = now,
    ))

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="main_warehouse",
        actor_id=current_user.id,
        entity_id=project_id,
        after_value={
            "direction":      "project_to_project",
            "item":           item.name,
            "quantity":       body.quantity,
            "unit":           item.default_unit,
            "from_project":   src_project.name,
            "to_project":     dst_project.name,
            "transfer_ref":   str(transfer_ref),
        },
    )

    db.commit()
    return ApiSuccess(
        data={
            "transfer_ref":   str(transfer_ref),
            "item_id":        str(body.item_id),
            "item_name":      item.name,
            "quantity":       body.quantity,
            "unit":           item.default_unit,
            "from_project":   src_project.name,
            "to_project":     dst_project.name,
            "new_balance":    available - body.quantity,
        },
        message=(
            f"Transferred {body.quantity} {item.default_unit or ''} of {item.name} "
            f"from {src_project.name} to {dst_project.name}."
        ),
    )


# ── Main Warehouse movement history ───────────────────────────────────────────

@project_warehouse_router.get("/history", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_main_warehouse_history(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(100, le=500),
):
    """Recent movements through the Main (Project) Warehouse (site_id IS NULL, lot_id IS NULL)."""
    from app.models.project import Project
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

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
            i.name          AS item_name,
            u.full_name     AS entered_by_name
        FROM stock_ledger sl
        JOIN items i ON i.id = sl.item_id
        LEFT JOIN users u ON u.id = sl.entered_by
        WHERE sl.project_id = :project_id
          AND sl.site_id  IS NULL
          AND sl.lot_id   IS NULL
        ORDER BY sl.movement_date DESC
        LIMIT :limit
    """), {"project_id": str(project_id), "limit": limit}).mappings().all()

    return ApiSuccess(data=[{
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
    } for r in rows])


# ── Project Warehouse: add ad-hoc material ────────────────────────────────────

class AddProjectMaterialBody(BaseModel):
    name:     str
    quantity: float
    unit:     Optional[str] = None
    notes:    Optional[str] = None


@project_warehouse_router.post(
    "/add-material",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def add_project_warehouse_material(
    project_id: uuid.UUID,
    body: AddProjectMaterialBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Add an ad-hoc material to the project warehouse (not in BOQ / PO).
    If a catalog Item with the same normalized name already exists it is
    reused (no duplicate).  Otherwise a new MATERIAL Item is auto-created.
    """
    from app.models.project import Project
    from app.models.enums import ItemType

    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Material name is required.")
    if body.quantity <= 0:
        raise HTTPException(422, "Quantity must be greater than zero.")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    normalized = name.lower()

    # Find or auto-create catalog item
    item = db.query(Item).filter(Item.normalized_name == normalized).first()
    created_item = False
    if not item:
        now_dt = datetime.now(timezone.utc)
        item = Item(
            name=name,
            normalized_name=normalized,
            item_type=ItemType.MATERIAL,
            default_unit=body.unit or None,
            is_active=True,
            created_at=now_dt,
            updated_at=now_dt,
        )
        db.add(item)
        db.flush()
        created_item = True
        _wh_log.info("add_project_material: created catalog item '%s' id=%s", name, item.id)

    now = datetime.now(timezone.utc)
    entry = StockLedger(
        project_id=project_id,
        site_id=None,
        lot_id=None,
        item_id=item.id,
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="PROJECT_WAREHOUSE_ADD",
        quantity_in=body.quantity,
        quantity_out=0,
        unit=body.unit or item.default_unit,
        movement_date=now,
        entered_by=current_user.id,
        notes=body.notes or None,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="stock_ledger",
        actor_id=current_user.id,
        entity_id=entry.id,
        after_value={"movement": "PROJECT_WAREHOUSE_ADD", "item": item.name,
                     "qty": body.quantity, "project_id": str(project_id),
                     "new_item": created_item},
    )
    db.commit()

    return ApiSuccess(
        data={
            "id":           str(entry.id),
            "item_id":      str(item.id),
            "item_name":    item.name,
            "quantity_in":  body.quantity,
            "created_item": created_item,
        },
        message=(
            f"Added {body.quantity} {body.unit or item.default_unit or ''} "
            f"of {item.name} to project warehouse."
        ),
        status_code=201,
    )


# ── Project Warehouse: stock adjustment ──────────────────────────────────────

class AdjustProjectStockBody(BaseModel):
    item_id:         uuid.UUID
    adjustment_type: str
    quantity:        float
    notes:           Optional[str] = None


@project_warehouse_router.post(
    "/adjust",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def adjust_project_warehouse_stock(
    project_id: uuid.UUID,
    body: AdjustProjectStockBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create a stock adjustment entry in the project warehouse.
    adjustment_type: DAMAGED | LOST | RETURNED | CORRECTION_ADD | CORRECTION_SUB | OTHER_ADD | OTHER_SUB
    """
    from app.models.project import Project

    if body.adjustment_type not in ADJUSTMENT_TYPE_MAP:
        raise HTTPException(
            422, f"Invalid adjustment_type. Must be one of: {VALID_ADJUSTMENT_TYPES}"
        )
    if body.quantity <= 0:
        raise HTTPException(422, "Quantity must be greater than zero.")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    check_project_access(db, current_user, project_id)

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    movement_type, qty_field = ADJUSTMENT_TYPE_MAP[body.adjustment_type]

    now = datetime.now(timezone.utc)
    entry = StockLedger(
        project_id=project_id,
        site_id=None,
        lot_id=None,
        item_id=body.item_id,
        movement_type=movement_type,
        reference_type=f"ADJUSTMENT_{body.adjustment_type}",
        quantity_in=body.quantity  if qty_field == "quantity_in"  else 0,
        quantity_out=body.quantity if qty_field == "quantity_out" else 0,
        unit=item.default_unit,
        movement_date=now,
        entered_by=current_user.id,
        notes=body.notes or None,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="stock_ledger",
        actor_id=current_user.id,
        entity_id=entry.id,
        after_value={"movement": f"ADJUSTMENT_{body.adjustment_type}", "item": item.name,
                     "qty": body.quantity, "project_id": str(project_id)},
    )
    db.commit()

    return ApiSuccess(
        data={
            "id":              str(entry.id),
            "item_name":       item.name,
            "adjustment_type": body.adjustment_type,
            "quantity":        body.quantity,
        },
        message=(
            f"Stock adjusted: {body.adjustment_type} {body.quantity} "
            f"{item.default_unit or ''} of {item.name}."
        ),
        status_code=201,
    )


# ── Global Main Warehouse — cross-project aggregate view ─────────────────────

@global_warehouse_router.get("/main/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_global_main_warehouse_stock(db: DbSession, current_user: CurrentUser):
    """
    Returns on-hand stock at the main warehouse level (site_id IS NULL, lot_id IS NULL)
    across ALL projects + global (unassigned) stock. No project filter — company-wide view.
    """
    rows = db.execute(text("""
        SELECT
            sl.project_id,
            p.name                              AS project_name,
            p.code                              AS project_code,
            sl.item_id,
            i.name                              AS item_name,
            i.default_unit                      AS unit,
            SUM(sl.quantity_in)                 AS total_in,
            SUM(sl.quantity_out)                AS total_out,
            SUM(sl.quantity_in) - SUM(sl.quantity_out) AS on_hand,
            MAX(sl.movement_date)               AS last_movement
        FROM stock_ledger sl
        JOIN items    i ON i.id = sl.item_id
        LEFT JOIN projects p ON p.id = sl.project_id
        WHERE sl.site_id IS NULL
          AND sl.lot_id  IS NULL
        GROUP BY sl.project_id, p.name, p.code, sl.item_id, i.name, i.default_unit
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY COALESCE(p.name, ''), i.name
    """)).mappings().all()

    return ApiSuccess(
        data=[{
            "project_id":    str(r["project_id"]) if r["project_id"] else None,
            "project_name":  r["project_name"] or "Global",
            "project_code":  r["project_code"] or "GLOBAL",
            "item_id":       str(r["item_id"]),
            "item_name":     r["item_name"],
            "unit":          r["unit"],
            "on_hand":       float(r["on_hand"]),
            "total_in":      float(r["total_in"]),
            "total_out":     float(r["total_out"]),
            "last_movement": r["last_movement"].isoformat() if r["last_movement"] else None,
        } for r in rows],
        message=f"{len(rows)} item(s) in main warehouse.",
    )


@global_warehouse_router.get("/main/history", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_global_main_warehouse_history(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(100, le=500),
):
    """Recent movements across ALL main warehouses (site_id IS NULL, lot_id IS NULL)."""
    rows = db.execute(text("""
        SELECT
            sl.id,
            sl.project_id,
            p.name          AS project_name,
            sl.movement_type,
            sl.quantity_in,
            sl.quantity_out,
            sl.unit,
            sl.movement_date,
            sl.notes,
            sl.reference_type,
            i.name          AS item_name,
            u.full_name     AS entered_by_name
        FROM stock_ledger sl
        JOIN items    i ON i.id = sl.item_id
        LEFT JOIN projects p ON p.id = sl.project_id
        LEFT JOIN users u ON u.id = sl.entered_by
        WHERE sl.site_id IS NULL
          AND sl.lot_id  IS NULL
        ORDER BY sl.movement_date DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return ApiSuccess(data=[{
        "id":             str(r["id"]),
        "project_id":     str(r["project_id"]) if r["project_id"] else None,
        "project_name":   r["project_name"] or "Global",
        "movement_type":  r["movement_type"],
        "item_name":      r["item_name"],
        "quantity_in":    float(r["quantity_in"] or 0),
        "quantity_out":   float(r["quantity_out"] or 0),
        "unit":           r["unit"],
        "movement_date":  r["movement_date"].isoformat() if r["movement_date"] else None,
        "notes":          r["notes"],
        "reference_type": r["reference_type"],
        "entered_by":     r["entered_by_name"],
    } for r in rows])


# ── Global Main Warehouse: TOOL items ─────────────────────────────────────────

@global_warehouse_router.get("/main/tools", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_global_main_warehouse_tools(db: DbSession, current_user: CurrentUser):
    """List TOOL items in the global main warehouse (project_id IS NULL, item_type = TOOL)."""
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
        WHERE sl.project_id IS NULL
          AND sl.site_id IS NULL
          AND sl.lot_id  IS NULL
          AND i.item_type = 'TOOL'
        GROUP BY sl.item_id, i.name, i.default_unit
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY i.name
    """)).mappings().all()

    return ApiSuccess(
        data=[{
            "project_id":    None,
            "project_name":  "Global",
            "project_code":  "GLOBAL",
            "item_id":       str(r["item_id"]),
            "item_name":     r["item_name"],
            "unit":          r["unit"],
            "on_hand":       float(r["on_hand"]),
            "total_in":      float(r["total_in"]),
            "total_out":     float(r["total_out"]),
            "last_movement": r["last_movement"].isoformat() if r["last_movement"] else None,
        } for r in rows],
        message=f"{len(rows)} tool(s) in main warehouse.",
    )


@global_warehouse_router.get("/main/tools/locations", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def get_tool_site_locations(db: DbSession, current_user: CurrentUser):
    """Return how many of each TOOL item is currently at each site warehouse."""
    rows = db.execute(text("""
        SELECT
            sl.item_id,
            i.name                                  AS item_name,
            s.id                                    AS site_id,
            s.name                                  AS site_name,
            COALESCE(p.code, 'GLOBAL')              AS project_code,
            COALESCE(p.name, 'Global')              AS project_name,
            SUM(sl.quantity_in) - SUM(sl.quantity_out) AS on_hand
        FROM stock_ledger sl
        JOIN items i ON i.id = sl.item_id
        JOIN sites s ON s.id = sl.site_id
        LEFT JOIN projects p ON p.id = sl.project_id
        WHERE sl.site_id IS NOT NULL
          AND sl.lot_id  IS NULL
          AND i.item_type = 'TOOL'
        GROUP BY sl.item_id, i.name, s.id, s.name, p.code, p.name
        HAVING SUM(sl.quantity_in) - SUM(sl.quantity_out) > 0
        ORDER BY i.name, s.name
    """)).mappings().all()

    return ApiSuccess(
        data=[{
            "item_id":      str(r["item_id"]),
            "item_name":    r["item_name"],
            "site_id":      str(r["site_id"]),
            "site_name":    r["site_name"],
            "project_code": r["project_code"],
            "project_name": r["project_name"],
            "on_hand":      float(r["on_hand"]),
        } for r in rows],
        message=f"{len(rows)} tool-site location(s).",
    )


# ── Main Warehouse: receive stock from supplier ───────────────────────────────

class ReceiveStockBody(BaseModel):
    item_id:      uuid.UUID
    quantity:     float
    unit:         Optional[str] = None
    unit_cost:    Optional[float] = None
    supplier_ref: Optional[str] = None
    movement_date: Optional[str] = None  # ISO date "YYYY-MM-DD"; defaults to today
    notes:        Optional[str] = None


@global_warehouse_router.post(
    "/main/receive",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
def receive_main_warehouse_stock(
    body: ReceiveStockBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Receive stock from a supplier into the global main warehouse.
    No project assignment — stock is company-wide until transferred to a site.
    Creates a DELIVERY_RECEIVED ledger entry with project_id=NULL, site_id=NULL, lot_id=NULL.
    """
    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Quantity must be greater than zero.")

    from datetime import date
    movement_dt = datetime.now(timezone.utc)
    if body.movement_date:
        try:
            d = date.fromisoformat(body.movement_date)
            movement_dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(422, "Invalid movement_date format.")

    entry = StockLedger(
        project_id=None,
        site_id=None,
        lot_id=None,
        item_id=body.item_id,
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="MAIN_WAREHOUSE_RECEIVE",
        quantity_in=body.quantity,
        quantity_out=0,
        unit=body.unit or item.default_unit,
        unit_cost=body.unit_cost,
        movement_date=movement_dt,
        entered_by=current_user.id,
        notes=body.notes or (f"Received from supplier: {body.supplier_ref}" if body.supplier_ref else None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="stock_ledger",
        actor_id=current_user.id,
        entity_id=entry.id,
        after_value={"movement": "MAIN_WAREHOUSE_RECEIVE", "item": item.name,
                     "qty": body.quantity, "supplier_ref": body.supplier_ref},
    )

    return ApiSuccess(
        data={"id": str(entry.id), "item_name": item.name, "quantity_in": body.quantity},
        message=f"Received {body.quantity} {entry.unit or ''} of {item.name}.",
        status_code=201,
    )


# ── Main Warehouse: stock adjustment ─────────────────────────────────────────

ADJUSTMENT_TYPE_MAP = {
    "DAMAGED":        (MovementType.ADJUSTMENT_SUBTRACT, "quantity_out"),
    "LOST":           (MovementType.ADJUSTMENT_SUBTRACT, "quantity_out"),
    "RETURNED":       (MovementType.ADJUSTMENT_ADD,      "quantity_in"),
    "CORRECTION_ADD": (MovementType.ADJUSTMENT_ADD,      "quantity_in"),
    "CORRECTION_SUB": (MovementType.ADJUSTMENT_SUBTRACT, "quantity_out"),
    "OTHER_ADD":      (MovementType.ADJUSTMENT_ADD,      "quantity_in"),
    "OTHER_SUB":      (MovementType.ADJUSTMENT_SUBTRACT, "quantity_out"),
}
VALID_ADJUSTMENT_TYPES = list(ADJUSTMENT_TYPE_MAP.keys())


class AdjustStockBody(BaseModel):
    item_id:         uuid.UUID
    adjustment_type: str
    quantity:        float
    movement_date:   Optional[str] = None
    notes:           Optional[str] = None


@global_warehouse_router.post(
    "/main/adjust",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
def adjust_main_warehouse_stock(
    body: AdjustStockBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create a stock adjustment in the global main warehouse (project_id=NULL).
    adjustment_type: DAMAGED | LOST | RETURNED | CORRECTION_ADD | CORRECTION_SUB | OTHER_ADD | OTHER_SUB
    """
    if body.adjustment_type not in ADJUSTMENT_TYPE_MAP:
        raise HTTPException(422, f"Invalid adjustment_type. Must be one of: {VALID_ADJUSTMENT_TYPES}")
    if body.quantity <= 0:
        raise HTTPException(422, "Quantity must be greater than zero.")

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    movement_type, qty_field = ADJUSTMENT_TYPE_MAP[body.adjustment_type]

    from datetime import date
    movement_dt = datetime.now(timezone.utc)
    if body.movement_date:
        try:
            d = date.fromisoformat(body.movement_date)
            movement_dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(422, "Invalid movement_date format.")

    entry = StockLedger(
        project_id=None,
        site_id=None,
        lot_id=None,
        item_id=body.item_id,
        movement_type=movement_type,
        reference_type=f"ADJUSTMENT_{body.adjustment_type}",
        quantity_in=body.quantity if qty_field == "quantity_in" else 0,
        quantity_out=body.quantity if qty_field == "quantity_out" else 0,
        unit=item.default_unit,
        movement_date=movement_dt,
        entered_by=current_user.id,
        notes=body.notes,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="stock_ledger",
        actor_id=current_user.id,
        entity_id=entry.id,
        after_value={"movement": f"ADJUSTMENT_{body.adjustment_type}",
                     "item": item.name, "qty": body.quantity},
    )

    return ApiSuccess(
        data={"id": str(entry.id), "item_name": item.name, "adjustment_type": body.adjustment_type, "quantity": body.quantity},
        message=f"Stock adjusted: {body.adjustment_type} {body.quantity} {item.default_unit or ''} of {item.name}.",
        status_code=201,
    )


# ── Global Main Warehouse: add / top-up a tool ───────────────────────────────

class AddToolBody(BaseModel):
    name:     str
    quantity: float
    unit:     Optional[str] = None
    notes:    Optional[str] = None


@global_warehouse_router.post(
    "/main/add-tool",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
def add_main_warehouse_tool(
    body: AddToolBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Add or top-up a tool in the global main warehouse (project_id=NULL).
    Finds an existing TOOL catalog item by normalized name, or auto-creates one.
    Creates a DELIVERY_RECEIVED ledger entry.
    """
    from app.models.enums import ItemType

    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Tool name is required.")
    if body.quantity <= 0:
        raise HTTPException(422, "Quantity must be greater than zero.")

    normalized = name.lower()

    item = (
        db.query(Item)
        .filter(Item.normalized_name == normalized, Item.item_type == ItemType.TOOL)
        .first()
    )
    created_item = False
    if not item:
        now_dt = datetime.now(timezone.utc)
        item = Item(
            name=name,
            normalized_name=normalized,
            item_type=ItemType.TOOL,
            default_unit=body.unit or None,
            is_active=True,
            created_at=now_dt,
            updated_at=now_dt,
        )
        db.add(item)
        db.flush()
        created_item = True

    now = datetime.now(timezone.utc)
    entry = StockLedger(
        project_id=None,
        site_id=None,
        lot_id=None,
        item_id=item.id,
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="MAIN_WAREHOUSE_TOOL_ADD",
        quantity_in=body.quantity,
        quantity_out=0,
        unit=body.unit or item.default_unit,
        movement_date=now,
        entered_by=current_user.id,
        notes=body.notes or None,
        created_at=now,
    )
    db.add(entry)
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="stock_ledger",
        actor_id=current_user.id,
        entity_id=entry.id,
        after_value={"movement": "MAIN_WAREHOUSE_TOOL_ADD", "item": item.name,
                     "qty": body.quantity, "new_item": created_item},
    )
    db.commit()

    return ApiSuccess(
        data={
            "id":           str(entry.id),
            "item_id":      str(item.id),
            "item_name":    item.name,
            "quantity_in":  body.quantity,
            "created_item": created_item,
        },
        message=f"Added {body.quantity} {body.unit or item.default_unit or ''} of {item.name} to main warehouse.",
        status_code=201,
    )


# ── Global Main Warehouse: transfer to site (for stock with no project) ───────

@global_warehouse_router.get("/main/sites", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def list_all_sites_for_global_transfer(db: DbSession, current_user: CurrentUser):
    """Return all active sites across all projects for the global transfer modal."""
    rows = db.execute(text("""
        SELECT s.id, s.name, s.project_id, p.name AS project_name, p.code AS project_code
        FROM sites s
        JOIN projects p ON p.id = s.project_id
        WHERE s.is_active = TRUE
        ORDER BY p.name, s.name
    """)).mappings().all()
    return ApiSuccess(data=[{
        "id":           str(r["id"]),
        "name":         r["name"],
        "project_id":   str(r["project_id"]),
        "project_name": r["project_name"],
        "project_code": r["project_code"],
    } for r in rows])


class GlobalTransferToSiteRequest(BaseModel):
    item_id:  uuid.UUID
    site_id:  uuid.UUID
    quantity: float
    notes:    Optional[str] = None


@global_warehouse_router.post(
    "/main/transfer-to-site",
    response_model=ApiSuccess[dict],
    dependencies=[WRITE_ROLES],
)
def transfer_global_stock_to_site(
    body: GlobalTransferToSiteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Transfer stock from the global main warehouse (project_id=NULL) to a site warehouse.

    TRANSFER_OUT — project_id=NULL, site_id=NULL, lot_id=NULL  (leaves global pool)
    TRANSFER_IN  — project_id=site.project_id, site_id=X, lot_id=NULL  (enters site scope)
    """
    site = db.get(Site, body.site_id)
    if not site:
        raise HTTPException(404, "Site not found.")

    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found.")

    if body.quantity <= 0:
        raise HTTPException(422, "Transfer quantity must be greater than zero.")

    # Check available balance in global pool (project_id IS NULL)
    balance_row = db.execute(text("""
        SELECT SUM(quantity_in) - SUM(quantity_out) AS balance
        FROM stock_ledger
        WHERE project_id IS NULL
          AND site_id   IS NULL
          AND lot_id    IS NULL
          AND item_id    = :item_id
    """), {"item_id": str(body.item_id)}).fetchone()

    available = float(balance_row[0] or 0)
    if body.quantity > available:
        raise HTTPException(422,
            f"Insufficient global warehouse stock. "
            f"Available: {available:.3g} {item.default_unit or ''} of {item.name}; "
            f"requested {body.quantity:.3g}."
        )

    now = datetime.now(timezone.utc)
    transfer_ref = uuid.uuid4()

    db.add(StockLedger(
        project_id     = None,
        site_id        = None,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_OUT,
        reference_type = "global_to_site_transfer",
        reference_id   = transfer_ref,
        quantity_in    = 0,
        quantity_out   = body.quantity,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Transferred to {site.name}",
        created_at     = now,
    ))

    db.add(StockLedger(
        project_id     = site.project_id,
        site_id        = body.site_id,
        lot_id         = None,
        item_id        = body.item_id,
        movement_type  = MovementType.TRANSFER_IN,
        reference_type = "global_to_site_transfer",
        reference_id   = transfer_ref,
        quantity_in    = body.quantity,
        quantity_out   = 0,
        unit           = item.default_unit,
        movement_date  = now,
        entered_by     = current_user.id,
        notes          = body.notes or f"Received from Global Warehouse",
        created_at     = now,
    ))

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="global_warehouse",
        actor_id=current_user.id,
        entity_id=transfer_ref,
        after_value={
            "item": item.name,
            "quantity": body.quantity,
            "unit": item.default_unit,
            "site": site.name,
            "transfer_ref": str(transfer_ref),
        },
    )

    db.commit()

    return ApiSuccess(
        data={
            "transfer_ref": str(transfer_ref),
            "item_id":      str(body.item_id),
            "item_name":    item.name,
            "quantity":     body.quantity,
            "unit":         item.default_unit,
            "site_name":    site.name,
            "new_balance":  available - body.quantity,
        },
        message=f"Transferred {body.quantity} {item.default_unit or ''} of {item.name} to {site.name}.",
    )
