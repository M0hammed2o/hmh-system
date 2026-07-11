"""Business logic for warehouse-to-warehouse stock transfer requests (project-to-project with 3-person approval)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.enums import AlertSeverity, AlertType, AuditAction, MovementType
from app.models.item import Item
from app.models.project import Project
from app.models.user import User
from app.models.warehouse_transfer import (
    TRANSFER_VOTES_REQUIRED,
    WarehouseTransferRequest,
    WarehouseTransferStatus,
    WarehouseTransferVote,
)
from app.services import audit_service


def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found.")
    return p


def _item_or_404(db: Session, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found.")
    return item


def _get_on_hand(db: Session, project_id: uuid.UUID, item_id: uuid.UUID) -> float:
    """Return project warehouse on-hand quantity for an item (site_id IS NULL)."""
    row = db.execute(text("""
        SELECT COALESCE(SUM(quantity_in) - SUM(quantity_out), 0) AS on_hand
        FROM stock_ledger
        WHERE project_id = :project_id
          AND item_id = :item_id
          AND site_id IS NULL
          AND lot_id IS NULL
    """), {"project_id": str(project_id), "item_id": str(item_id)}).mappings().first()
    return float(row["on_hand"]) if row else 0.0


def create_transfer_request(
    db: Session,
    from_project_id: uuid.UUID,
    to_project_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: float,
    reason: str,
    requested_by: uuid.UUID,
    notes: Optional[str] = None,
) -> WarehouseTransferRequest:
    if from_project_id == to_project_id:
        raise HTTPException(400, "Source and destination project must be different.")

    from_project = _project_or_404(db, from_project_id)
    _project_or_404(db, to_project_id)
    item = _item_or_404(db, item_id)

    on_hand = _get_on_hand(db, from_project_id, item_id)
    if quantity > on_hand:
        raise HTTPException(
            400,
            f"Insufficient stock: {on_hand:.2f} {item.default_unit or ''} available, "
            f"requested {quantity:.2f}.",
        )

    now = datetime.now(timezone.utc)
    req = WarehouseTransferRequest(
        from_project_id=from_project_id,
        to_project_id=to_project_id,
        item_id=item_id,
        quantity=quantity,
        unit=item.default_unit,
        reason=reason,
        notes=notes,
        status=WarehouseTransferStatus.PENDING,
        requested_by=requested_by,
        requested_at=now,
    )
    db.add(req)
    db.flush()

    audit_service.write_event(
        db, AuditAction.CREATE, "warehouse_transfer_request", requested_by, req.id,
        after_value={
            "from_project": str(from_project_id),
            "to_project": str(to_project_id),
            "item": str(item_id),
            "quantity": quantity,
            "reason": reason,
        },
    )

    # Alert office
    try:
        from app.models.alert import SystemAlert
        from app.services.notification_service import enqueue_for_alert
        alert = SystemAlert(
            alert_type=AlertType.WAREHOUSE_TRANSFER_COMPLETED,
            severity=AlertSeverity.MEDIUM,
            title=f"Transfer Request: {item.name}",
            message=(
                f"Site clerk requested to transfer {quantity:.2f} {item.default_unit or ''} of "
                f"'{item.name}' from project '{from_project.name}' to another project.\n"
                f"Reason: {reason}\n"
                f"Requires {TRANSFER_VOTES_REQUIRED} office approvals."
            ),
            project_id=from_project_id,
            entity_type="warehouse_transfer_request",
            entity_id=req.id,
        )
        db.add(alert)
        db.flush()
        enqueue_for_alert(db, alert)
    except Exception:
        pass  # Never block the request submission

    db.commit()
    db.refresh(req)
    return req


def list_transfer_requests(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> list[WarehouseTransferRequest]:
    q = db.query(WarehouseTransferRequest)
    if project_id:
        q = q.filter(
            (WarehouseTransferRequest.from_project_id == project_id)
            | (WarehouseTransferRequest.to_project_id == project_id)
        )
    if status:
        q = q.filter(WarehouseTransferRequest.status == status)
    return q.order_by(WarehouseTransferRequest.requested_at.desc()).all()


def get_transfer_request(db: Session, transfer_id: uuid.UUID) -> WarehouseTransferRequest:
    req = db.get(WarehouseTransferRequest, transfer_id)
    if not req:
        raise HTTPException(404, "Transfer request not found.")
    return req


def cast_vote(
    db: Session,
    transfer_id: uuid.UUID,
    voter_id: uuid.UUID,
    notes: Optional[str] = None,
) -> WarehouseTransferRequest:
    req = get_transfer_request(db, transfer_id)
    if req.status != WarehouseTransferStatus.PENDING:
        raise HTTPException(400, "Can only vote on PENDING transfer requests.")

    existing = db.query(WarehouseTransferVote).filter(
        WarehouseTransferVote.transfer_request_id == transfer_id,
        WarehouseTransferVote.voted_by == voter_id,
    ).first()
    if existing:
        raise HTTPException(409, "You have already voted on this transfer request.")

    now = datetime.now(timezone.utc)
    vote = WarehouseTransferVote(
        transfer_request_id=transfer_id,
        voted_by=voter_id,
        voted_at=now,
        is_override=False,
        notes=notes,
    )
    db.add(vote)
    db.flush()

    vote_count = db.query(WarehouseTransferVote).filter(
        WarehouseTransferVote.transfer_request_id == transfer_id,
        WarehouseTransferVote.is_override.is_(False),
    ).count()

    if vote_count >= TRANSFER_VOTES_REQUIRED:
        _execute_transfer(db, req, voter_id, now)
    else:
        db.commit()
        db.refresh(req)

    return req


def override_approve(
    db: Session,
    transfer_id: uuid.UUID,
    approver_id: uuid.UUID,
    notes: Optional[str] = None,
) -> WarehouseTransferRequest:
    req = get_transfer_request(db, transfer_id)
    if req.status != WarehouseTransferStatus.PENDING:
        raise HTTPException(400, "Transfer request is not pending.")

    now = datetime.now(timezone.utc)
    vote = WarehouseTransferVote(
        transfer_request_id=transfer_id,
        voted_by=approver_id,
        voted_at=now,
        is_override=True,
        notes=notes or "Owner override",
    )
    db.add(vote)
    db.flush()
    _execute_transfer(db, req, approver_id, now)
    return req


def reject_transfer(
    db: Session,
    transfer_id: uuid.UUID,
    rejector_id: uuid.UUID,
    reason: str,
) -> WarehouseTransferRequest:
    req = get_transfer_request(db, transfer_id)
    if req.status != WarehouseTransferStatus.PENDING:
        raise HTTPException(400, "Transfer request is not pending.")

    req.status = WarehouseTransferStatus.REJECTED
    req.rejection_reason = reason

    audit_service.write_event(
        db, AuditAction.REJECT, "warehouse_transfer_request", rejector_id, transfer_id,
        after_value={"rejection_reason": reason},
    )
    db.commit()
    db.refresh(req)
    return req


def _execute_transfer(
    db: Session,
    req: WarehouseTransferRequest,
    executor_id: uuid.UUID,
    now: datetime,
) -> None:
    """Write paired TRANSFER_OUT / TRANSFER_IN stock ledger entries and mark as EXECUTED."""
    on_hand = _get_on_hand(db, req.from_project_id, req.item_id)
    if req.quantity > on_hand:
        raise HTTPException(
            400,
            f"Insufficient stock at time of execution: {on_hand:.2f} available, "
            f"requested {req.quantity:.2f}.",
        )

    transfer_ref = uuid.uuid4()

    # OUT from source project
    db.execute(text("""
        INSERT INTO stock_ledger
            (id, project_id, site_id, lot_id, item_id, movement_type, quantity_in, quantity_out,
             unit, unit_cost, reference_type, reference_id, movement_date, notes)
        VALUES
            (gen_random_uuid(), :from_proj, NULL, NULL, :item_id, 'TRANSFER_OUT', 0, :qty,
             :unit, 0, 'project_to_project_transfer', :ref_id, :now, :notes)
    """), {
        "from_proj": str(req.from_project_id),
        "item_id": str(req.item_id),
        "qty": req.quantity,
        "unit": req.unit or "",
        "ref_id": str(transfer_ref),
        "now": now,
        "notes": f"Transfer to project — approved. Reason: {req.reason}",
    })

    # IN to destination project
    db.execute(text("""
        INSERT INTO stock_ledger
            (id, project_id, site_id, lot_id, item_id, movement_type, quantity_in, quantity_out,
             unit, unit_cost, reference_type, reference_id, movement_date, notes)
        VALUES
            (gen_random_uuid(), :to_proj, NULL, NULL, :item_id, 'TRANSFER_IN', :qty, 0,
             :unit, 0, 'project_to_project_transfer', :ref_id, :now, :notes)
    """), {
        "to_proj": str(req.to_project_id),
        "item_id": str(req.item_id),
        "qty": req.quantity,
        "unit": req.unit or "",
        "ref_id": str(transfer_ref),
        "now": now,
        "notes": f"Transfer from project — approved. Reason: {req.reason}",
    })

    req.status = WarehouseTransferStatus.EXECUTED
    req.executed_at = now
    req.executed_by = executor_id

    audit_service.write_event(
        db, AuditAction.TRANSFER, "warehouse_transfer_request", executor_id, req.id,
        after_value={"status": "EXECUTED", "transfer_ref": str(transfer_ref)},
    )

    db.commit()
    db.refresh(req)
