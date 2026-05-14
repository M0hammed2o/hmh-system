"""AlertRecipient CRUD service."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.alert_recipient import AlertRecipient
from app.schemas.notification import AlertRecipientCreate, AlertRecipientUpdate


def list_recipients(db: Session, active_only: bool = False) -> list[AlertRecipient]:
    q = db.query(AlertRecipient)
    if active_only:
        q = q.filter(AlertRecipient.is_active == True)
    return q.order_by(AlertRecipient.name).all()


def get_recipient(db: Session, recipient_id: uuid.UUID) -> AlertRecipient:
    r = db.get(AlertRecipient, recipient_id)
    if not r:
        raise NotFoundError(f"Recipient {recipient_id} not found.")
    return r


def create_recipient(
    db: Session,
    data: AlertRecipientCreate,
    created_by: Optional[uuid.UUID] = None,
) -> AlertRecipient:
    existing = db.query(AlertRecipient).filter(
        AlertRecipient.phone_number == data.phone_number
    ).first()
    if existing:
        raise ConflictError(f"A recipient with number {data.phone_number} already exists.")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    recipient = AlertRecipient(
        name=data.name,
        phone_number=data.phone_number,
        label=data.label,
        receives_critical_alerts=data.receives_critical_alerts,
        receives_daily_summary=data.receives_daily_summary,
        receives_invoice_alerts=data.receives_invoice_alerts,
        receives_delivery_alerts=data.receives_delivery_alerts,
        receives_vehicle_alerts=data.receives_vehicle_alerts,
        receives_material_alerts=data.receives_material_alerts,
        is_active=True,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


def update_recipient(
    db: Session,
    recipient_id: uuid.UUID,
    data: AlertRecipientUpdate,
) -> AlertRecipient:
    recipient = get_recipient(db, recipient_id)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(recipient, field, value)

    from datetime import datetime, timezone
    recipient.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(recipient)
    return recipient
