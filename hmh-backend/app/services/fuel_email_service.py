"""Durable, best-effort Fuel workflow email notifications."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import UserRole
from app.models.fuel_management import FuelEmailLog, FuelOrder
from app.models.supplier import Supplier
from app.models.user import User
from app.services import email_service

log = logging.getLogger(__name__)
MANAGEMENT_ROLES = {UserRole.OWNER, UserRole.OFFICE_ADMIN, UserRole.PROCUREMENT_LEAD}


def _now():
    return datetime.now(timezone.utc)


def _frontend_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Frontend email paths must be local absolute paths")
    return f"{settings.FRONTEND_BASE_URL}{path}"


def _recipients(db: Session, order: FuelOrder, event_type: str) -> list[User]:
    requester = db.get(User, order.requested_by)
    management = db.query(User).filter(User.is_active.is_(True), User.role.in_(MANAGEMENT_ROLES)).all()
    users = management if event_type in {"SUBMITTED", "DELIVERED"} else ([requester] if requester else [])
    if event_type in {"APPROVED", "REJECTED", "ORDERED", "DELIVERED"} and requester:
        users.append(requester)
    unique = {}
    for user in users:
        if user and user.email:
            unique[user.email.lower()] = user
    return list(unique.values())


def queue_event(db: Session, order: FuelOrder, event_type: str, *, delivery_id=None) -> list[FuelEmailLog]:
    """Persist recipients before attempting delivery; never raises to the caller."""
    try:
        subject = f"Fuel request {order.order_number}: {event_type.replace('_', ' ').title()}"
        rows = []
        for user in _recipients(db, order, event_type):
            row = FuelEmailLog(order_id=order.id, delivery_id=delivery_id, event_type=event_type,
                               recipient_user_id=user.id, recipient_email=user.email,
                               subject=subject, status="PENDING", attempt_count=0)
            db.add(row); rows.append(row)
        if event_type == "ORDERED" and order.supplier_id:
            supplier = db.get(Supplier, order.supplier_id)
            if supplier and supplier.email and supplier.email.lower() not in {r.recipient_email.lower() for r in rows}:
                row = FuelEmailLog(order_id=order.id, event_type=event_type,
                                   recipient_email=supplier.email, subject=subject,
                                   status="PENDING", attempt_count=0)
                db.add(row); rows.append(row)
        db.commit()
        for row in rows:
            _deliver(db, row, order)
        return rows
    except Exception:
        db.rollback()
        log.exception("Fuel email queue failed without affecting workflow event %s", event_type)
        return []


def _deliver(db: Session, row: FuelEmailLog, order: Optional[FuelOrder] = None) -> None:
    try:
        order = order or (db.get(FuelOrder, row.order_id) if row.order_id else None)
        action = _frontend_url(f"/notifications/fuel-order/{order.id}" if order else "/alerts")
        body = (f"<p>{row.subject}</p><p>Requested litres: {float(order.requested_litres):,.2f}</p>"
                f'<p><a href="{action}">Open the fuel request</a></p>' if order else f"<p>{row.subject}</p>")
        result = email_service.send_email(row.recipient_email, row.subject, body, cc=[], bcc=[])
        row.attempt_count += 1
        row.last_attempt_at = _now()
        row.status = result.get("status", "FAILED")
        row.error_message = result.get("error")
        row.next_attempt_at = (_now() + timedelta(minutes=5 * row.attempt_count)) if row.status == "FAILED" and row.attempt_count < 3 else None
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            row = db.get(FuelEmailLog, row.id)
            if row:
                row.attempt_count += 1; row.last_attempt_at = _now(); row.status = "FAILED"
                row.error_message = str(exc)[:2000]
                row.next_attempt_at = _now() + timedelta(minutes=5 * row.attempt_count) if row.attempt_count < 3 else None
                db.commit()
        except Exception:
            db.rollback()
        log.exception("Fuel email delivery failed without rolling back fuel workflow")


def retry_failed(db: Session, limit: int = 50) -> dict:
    rows = db.query(FuelEmailLog).filter(
        FuelEmailLog.status.in_(["PENDING", "FAILED"]), FuelEmailLog.attempt_count < 3
    ).order_by(FuelEmailLog.created_at).limit(limit).all()
    for row in rows:
        _deliver(db, row)
    return {"processed": len(rows), "failed": sum(1 for r in rows if r.status == "FAILED")}
