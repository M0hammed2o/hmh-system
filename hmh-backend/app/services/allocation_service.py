"""
Lot material allocation service.

The core money-leak stopper. Computes allocated vs used per lot+item
and enforces overrun warnings before any stock issue.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.alert import SystemAlert
from app.models.boq import BOQItem
from app.models.enums import AlertSeverity, AlertStatus, AlertType, AuditAction, MovementType
from app.models.item import Item
from app.models.lot import Lot
from app.models.stock import StockLedger, UsageLog
from app.services import audit_service


@dataclass
class LotAllocation:
    lot_id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    item_unit: Optional[str]
    allocated_quantity: float
    used_quantity: float
    remaining_quantity: float
    over_quantity: float
    is_over: bool


@dataclass
class OverrunWarning:
    lot_id: uuid.UUID
    lot_number: str
    item_id: uuid.UUID
    item_name: str
    item_unit: Optional[str]
    allocated_quantity: float
    already_used: float
    new_issue_quantity: float
    new_total: float
    over_amount: float


def get_lot_allocation(
    db: Session,
    lot_id: uuid.UUID,
    item_id: uuid.UUID,
) -> LotAllocation:
    """
    Compute the allocation status for one item in one lot.

    Allocated = sum of planned_quantity from BOQItems linked to this lot+item.
    Used      = sum of quantity_out from StockLedger for this lot+item.
    """
    item = db.get(Item, item_id)
    if not item:
        raise NotFoundError(f"Item {item_id} not found.")

    allocated = (
        db.query(func.coalesce(func.sum(BOQItem.planned_quantity), 0))
        .filter(BOQItem.lot_id == lot_id, BOQItem.item_id == item_id, BOQItem.is_active == True)
        .scalar()
    ) or 0.0

    used = (
        db.query(func.coalesce(func.sum(StockLedger.quantity_out), 0))
        .filter(StockLedger.lot_id == lot_id, StockLedger.item_id == item_id)
        .scalar()
    ) or 0.0

    remaining = max(0.0, float(allocated) - float(used))
    over = max(0.0, float(used) - float(allocated))

    return LotAllocation(
        lot_id=lot_id,
        item_id=item_id,
        item_name=item.name,
        item_unit=item.default_unit,
        allocated_quantity=float(allocated),
        used_quantity=float(used),
        remaining_quantity=remaining,
        over_quantity=over,
        is_over=float(used) > float(allocated) and float(allocated) > 0,
    )


def get_all_lot_allocations(
    db: Session,
    lot_id: uuid.UUID,
) -> list[LotAllocation]:
    """Return allocation status for every BOQ item linked to this lot."""
    rows = (
        db.query(BOQItem.item_id)
        .filter(BOQItem.lot_id == lot_id, BOQItem.item_id.isnot(None), BOQItem.is_active == True)
        .distinct()
        .all()
    )
    return [get_lot_allocation(db, lot_id, row.item_id) for row in rows]


def check_before_issue(
    db: Session,
    lot_id: uuid.UUID,
    item_id: uuid.UUID,
    issue_quantity: float,
) -> Optional[OverrunWarning]:
    """
    Check whether issuing `issue_quantity` to this lot would exceed allocation.
    Returns an OverrunWarning if it would, None if it's within budget.
    """
    lot = db.get(Lot, lot_id)
    if not lot:
        raise NotFoundError(f"Lot {lot_id} not found.")

    alloc = get_lot_allocation(db, lot_id, item_id)

    # No BOQ allocation for this item on this lot — no enforcement
    if alloc.allocated_quantity == 0:
        return None

    new_total = alloc.used_quantity + issue_quantity
    if new_total <= alloc.allocated_quantity:
        return None

    over_amount = new_total - alloc.allocated_quantity

    return OverrunWarning(
        lot_id=lot_id,
        lot_number=lot.lot_number,
        item_id=item_id,
        item_name=alloc.item_name,
        item_unit=alloc.item_unit,
        allocated_quantity=alloc.allocated_quantity,
        already_used=alloc.used_quantity,
        new_issue_quantity=issue_quantity,
        new_total=new_total,
        over_amount=over_amount,
    )


def create_overrun_alert(
    db: Session,
    warning: OverrunWarning,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    reason: str,
    actor_id: Optional[uuid.UUID] = None,
) -> SystemAlert:
    """
    Create a SystemAlert for an accepted material overrun and write audit event.
    Called after the user has supplied a reason and confirmed the issue.
    """
    msg = (
        f"OVERRUN: Lot {warning.lot_number} exceeded {warning.item_name} allocation.\n"
        f"Planned: {warning.allocated_quantity} {warning.item_unit or ''}\n"
        f"Used so far: {warning.already_used} {warning.item_unit or ''}\n"
        f"New issue: {warning.new_issue_quantity} {warning.item_unit or ''}\n"
        f"New total: {warning.new_total} {warning.item_unit or ''}\n"
        f"Over by: {warning.over_amount} {warning.item_unit or ''}\n"
        f"Reason: {reason}"
    )

    alert = SystemAlert(
        project_id=project_id,
        site_id=site_id,
        lot_id=warning.lot_id,
        reference_type="lot_item",
        alert_type=AlertType.MATERIAL_OVERUSE,
        severity=AlertSeverity.HIGH,
        title=f"Lot {warning.lot_number}: {warning.item_name} over allocation",
        message=msg,
        status=AlertStatus.OPEN,
        notification_channel="in_app",
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)

    audit_service.write_event(
        db,
        action=AuditAction.OVERRUN_ACCEPTED,
        entity_type="lot_item",
        actor_id=actor_id,
        entity_id=warning.lot_id,
        after_value={
            "lot_id": str(warning.lot_id),
            "item_id": str(warning.item_id),
            "item_name": warning.item_name,
            "allocated": warning.allocated_quantity,
            "used_before": warning.already_used,
            "new_issue": warning.new_issue_quantity,
            "new_total": warning.new_total,
            "over": warning.over_amount,
            "reason": reason,
        },
    )

    return alert
