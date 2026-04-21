"""Stock service — ledger reads, balances, usage logging."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import MovementType
from app.models.item import Item
from app.models.project import Project
from app.models.site import Site
from app.models.stock import StockLedger, UsageLog
from app.schemas.stock import StockBalanceRead, UsageLogCreate


def list_ledger(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    item_id: Optional[uuid.UUID] = None,
    limit: int = 200,
) -> list[StockLedger]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    q = db.query(StockLedger).filter(StockLedger.project_id == project_id)
    if site_id:
        q = q.filter(StockLedger.site_id == site_id)
    if item_id:
        q = q.filter(StockLedger.item_id == item_id)
    return q.order_by(StockLedger.movement_date.desc()).limit(limit).all()


def get_balances(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
) -> list[StockBalanceRead]:
    """Query stock_balances materialized view with optional item name join."""
    sql = text("""
        SELECT
            sb.project_id,
            sb.site_id,
            sb.lot_id,
            sb.item_id,
            sb.balance,
            sb.last_movement_date,
            i.name  AS item_name,
            i.default_unit AS item_unit
        FROM stock_balances sb
        JOIN items i ON i.id = sb.item_id
        WHERE sb.project_id = :project_id
        {site_filter}
        ORDER BY i.name
    """.format(site_filter="AND sb.site_id = :site_id" if site_id else ""))

    params: dict = {"project_id": project_id}
    if site_id:
        params["site_id"] = site_id

    rows = db.execute(sql, params).mappings().all()
    return [StockBalanceRead(**dict(row)) for row in rows]


def record_usage(
    db: Session,
    project_id: uuid.UUID,
    data: UsageLogCreate,
    recorded_by_id: uuid.UUID,
) -> UsageLog:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    site = db.get(Site, data.site_id)
    if not site or site.project_id != project_id:
        raise NotFoundError(f"Site {data.site_id} not found in this project.")

    item = db.get(Item, data.item_id)
    if not item:
        raise NotFoundError(f"Item {data.item_id} not found.")

    now = datetime.now(timezone.utc)
    usage_date = data.usage_date or now

    usage = UsageLog(
        project_id=project_id,
        site_id=data.site_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        item_id=data.item_id,
        boq_item_id=data.boq_item_id,
        quantity_used=data.quantity_used,
        used_by_person_name=data.used_by_person_name,
        used_by_team_name=data.used_by_team_name,
        recorded_by_user_id=recorded_by_id,
        usage_date=usage_date,
        comments=data.comments,
        created_at=now,
    )
    db.add(usage)
    db.flush()

    # Write immutable ledger entry
    ledger = StockLedger(
        project_id=project_id,
        site_id=data.site_id,
        lot_id=data.lot_id,
        item_id=data.item_id,
        boq_item_id=data.boq_item_id,
        movement_type=MovementType.USAGE,
        reference_type="usage_log",
        reference_id=usage.id,
        quantity_in=0,
        quantity_out=data.quantity_used,
        unit=item.default_unit,
        movement_date=usage_date,
        entered_by=recorded_by_id,
        created_at=now,
    )
    db.add(ledger)
    db.commit()

    # Refresh materialized view
    try:
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
        db.commit()
    except Exception:
        pass

    db.refresh(usage)
    return usage
