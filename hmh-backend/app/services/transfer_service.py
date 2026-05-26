"""
Stock transfer service — warehouse → site → lot movements.

All stock movements go through the immutable StockLedger. Transfers to a lot
go through the allocation check first; if over allocation, the caller must
supply an overrun_reason.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, MovementType
from app.models.item import Item
from app.models.lot import Lot
from app.models.project import Project
from app.models.site import Site
from app.models.stock import StockLedger
from app.services import allocation_service, audit_service


def _write_ledger(
    db: Session,
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    lot_id: Optional[uuid.UUID],
    item_id: uuid.UUID,
    movement_type: MovementType,
    reference_type: str,
    reference_id: Optional[uuid.UUID],
    quantity_in: float,
    quantity_out: float,
    unit: Optional[str],
    unit_cost: Optional[float],
    entered_by: Optional[uuid.UUID],
    notes: Optional[str],
) -> StockLedger:
    now = datetime.now(timezone.utc)
    entry = StockLedger(
        project_id=project_id,
        site_id=site_id,
        lot_id=lot_id,
        item_id=item_id,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        quantity_in=quantity_in,
        quantity_out=quantity_out,
        unit=unit,
        unit_cost=unit_cost,
        movement_date=now,
        entered_by=entered_by,
        notes=notes,
        created_at=now,
    )
    db.add(entry)
    # Flush now so SQLAlchemy applies the uuid.uuid4() column default and
    # populates entry.id before the caller tries to read it.
    db.flush()
    if entry.id is None:
        raise RuntimeError("StockLedger.id was not populated after flush — check column default.")
    return entry


def refresh_stock_balances(db: Session) -> bool:
    """
    Refresh the stock_balances materialized view.
    Safe to call anytime; returns True if refreshed, False if view absent.
    Isolated from the caller's transaction via to_regclass existence check.
    """
    try:
        exists = db.execute(
            text("SELECT to_regclass('public.stock_balances')")
        ).scalar()
        if not exists:
            return False
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
        db.commit()
        return True
    except Exception:
        return False


def transfer_to_lot(
    db: Session,
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    lot_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: float,
    entered_by: Optional[uuid.UUID] = None,
    notes: Optional[str] = None,
    overrun_reason: Optional[str] = None,
    boq_item_id: Optional[uuid.UUID] = None,
    unit_cost: Optional[float] = None,
) -> StockLedger:
    """
    Transfer stock from site store into a specific lot.

    Runs BOQ allocation check. Raises ValidationError with overrun detail
    if allocation exceeded and no overrun_reason provided.
    """
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    lot = db.get(Lot, lot_id)
    if not lot or lot.project_id != project_id:
        raise NotFoundError(f"Lot {lot_id} not found in project {project_id}.")
    item = db.get(Item, item_id)
    if not item:
        raise NotFoundError(f"Item {item_id} not found.")

    # BOQ allocation check
    warning = allocation_service.check_before_issue(db, lot_id, item_id, quantity)
    if warning and not overrun_reason:
        raise ValidationError(
            "Lot allocation exceeded. Provide overrun_reason to proceed.",
            detail={
                "overrun": True,
                "lot_number": warning.lot_number,
                "item_name": warning.item_name,
                "item_unit": warning.item_unit,
                "allocated_quantity": warning.allocated_quantity,
                "already_used": warning.already_used,
                "new_issue_quantity": warning.new_issue_quantity,
                "new_total": warning.new_total,
                "over_amount": warning.over_amount,
            },
        )

    # Duplicate-submit guard: reject identical transfer from same user within 10 s.
    # Prevents double-click / network retry from writing two identical ledger entries.
    from datetime import timedelta
    _window = datetime.now(timezone.utc) - timedelta(seconds=10)
    _dup = db.query(StockLedger).filter(
        StockLedger.project_id    == project_id,
        StockLedger.lot_id        == lot_id,
        StockLedger.item_id       == item_id,
        StockLedger.movement_type == MovementType.TRANSFER_IN,
        StockLedger.quantity_in   == quantity,
        StockLedger.entered_by    == entered_by,
        StockLedger.created_at    >= _window,
    ).first()
    if _dup:
        raise ConflictError(
            "Duplicate transfer detected (same item, quantity and user within 10 s). "
            "If intentional, wait a moment and retry."
        )

    # _write_ledger flushes internally; entry.id is set on return
    entry = _write_ledger(
        db,
        project_id=project_id,
        site_id=site_id,
        lot_id=lot_id,
        item_id=item_id,
        movement_type=MovementType.TRANSFER_IN,
        reference_type="lot_transfer",
        reference_id=None,
        quantity_in=quantity,
        quantity_out=0,
        unit=item.default_unit,
        unit_cost=unit_cost,
        entered_by=entered_by,
        notes=notes,
    )

    if warning and overrun_reason:
        allocation_service.create_overrun_alert(
            db, warning, project_id, site_id, overrun_reason, actor_id=entered_by
        )

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="stock_ledger",
        actor_id=entered_by,
        entity_id=entry.id,
        after_value={
            "project_id": str(project_id),
            "site_id": str(site_id),
            "lot_id": str(lot_id),
            "item_id": str(item_id),
            "item_name": item.name,
            "quantity": quantity,
            "overrun": bool(warning),
        },
    )

    db.commit()
    # SQLAlchemy does not expire primary keys on commit, so entry.id remains valid.
    # Do NOT call refresh_stock_balances here — it runs its own commit which
    # conflicts with the test transaction harness. Call it from a background task.

    # WhatsApp notification: warehouse transfer completed (fire-and-forget)
    # 1-hour project-level cooldown: skip if a WAREHOUSE_TRANSFER_COMPLETED
    # notification was already created for this project in the last hour.
    try:
        from app.services.notification_service import enqueue_direct
        from app.models.enums import AlertType, AlertSeverity
        from app.models.notification_queue import NotificationQueue
        from app.models.alert import SystemAlert
        from app.models.enums import AlertStatus
        from datetime import timedelta

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = (
            db.query(SystemAlert)
            .filter(
                SystemAlert.project_id == project_id,
                SystemAlert.alert_type == AlertType.WAREHOUSE_TRANSFER_COMPLETED,
                SystemAlert.created_at >= one_hour_ago,
            )
            .first()
        )
        if not recent:
            lot_label = f"lot {lot.lot_number}" if lot.lot_number else "lot"
            enqueue_direct(
                db,
                alert_type=AlertType.WAREHOUSE_TRANSFER_COMPLETED,
                severity=AlertSeverity.LOW,
                title=f"Stock Transferred: {item.name}",
                message=(
                    f"{quantity} {item.default_unit or 'units'} of {item.name} "
                    f"transferred to {lot_label}."
                ),
                project_id=project_id,
                entity_type="stock_ledger",
                entity_id=entry.id,
            )
            db.commit()
    except Exception:
        pass

    return entry


def transfer_to_site(
    db: Session,
    *,
    project_id: uuid.UUID,
    from_site_id: uuid.UUID,
    to_site_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: float,
    entered_by: Optional[uuid.UUID] = None,
    notes: Optional[str] = None,
    unit_cost: Optional[float] = None,
) -> tuple[StockLedger, StockLedger]:
    """Move stock between two sites (e.g. main warehouse → site store)."""
    item = db.get(Item, item_id)
    if not item:
        raise NotFoundError(f"Item {item_id} not found.")

    # Duplicate-submit guard: reject identical site transfer from same user within 10 s.
    from datetime import timedelta
    _window = datetime.now(timezone.utc) - timedelta(seconds=10)
    _dup = db.query(StockLedger).filter(
        StockLedger.project_id    == project_id,
        StockLedger.site_id       == from_site_id,
        StockLedger.item_id       == item_id,
        StockLedger.movement_type == MovementType.TRANSFER_OUT,
        StockLedger.quantity_out  == quantity,
        StockLedger.entered_by    == entered_by,
        StockLedger.created_at    >= _window,
    ).first()
    if _dup:
        raise ConflictError(
            "Duplicate transfer detected (same item, quantity and user within 10 s). "
            "If intentional, wait a moment and retry."
        )

    # Both calls flush internally; IDs are set before returning
    out_entry = _write_ledger(
        db,
        project_id=project_id,
        site_id=from_site_id,
        lot_id=None,
        item_id=item_id,
        movement_type=MovementType.TRANSFER_OUT,
        reference_type="site_transfer",
        reference_id=None,
        quantity_in=0,
        quantity_out=quantity,
        unit=item.default_unit,
        unit_cost=unit_cost,
        entered_by=entered_by,
        notes=f"Transfer to site {to_site_id}. {notes or ''}".strip(),
    )

    in_entry = _write_ledger(
        db,
        project_id=project_id,
        site_id=to_site_id,
        lot_id=None,
        item_id=item_id,
        movement_type=MovementType.TRANSFER_IN,
        reference_type="site_transfer",
        reference_id=out_entry.id,
        quantity_in=quantity,
        quantity_out=0,
        unit=item.default_unit,
        unit_cost=unit_cost,
        entered_by=entered_by,
        notes=f"Transfer from site {from_site_id}. {notes or ''}".strip(),
    )

    audit_service.write_event(
        db,
        action=AuditAction.TRANSFER,
        entity_type="stock_ledger",
        actor_id=entered_by,
        entity_id=out_entry.id,
        after_value={
            "project_id": str(project_id),
            "from_site_id": str(from_site_id),
            "to_site_id": str(to_site_id),
            "item_id": str(item_id),
            "quantity": quantity,
        },
    )

    db.commit()
    # See transfer_to_lot: do not call refresh_stock_balances here.
    return out_entry, in_entry
