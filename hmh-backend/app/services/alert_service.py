"""System alert service."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.alert import SystemAlert
from app.models.enums import AlertStatus
from app.schemas.alert import AlertUpdate


def _get_or_404(db: Session, alert_id: uuid.UUID) -> SystemAlert:
    a = db.get(SystemAlert, alert_id)
    if not a:
        raise NotFoundError(f"Alert {alert_id} not found.")
    return a


def list_alerts(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[AlertStatus] = None,
    limit: int = 100,
) -> list[SystemAlert]:
    q = db.query(SystemAlert)
    if project_id:
        q = q.filter(SystemAlert.project_id == project_id)
    if status:
        q = q.filter(SystemAlert.status == status)
    return q.order_by(SystemAlert.created_at.desc()).limit(limit).all()


def update_alert(
    db: Session,
    alert_id: uuid.UUID,
    data: AlertUpdate,
    acting_user_id: uuid.UUID,
) -> SystemAlert:
    alert = _get_or_404(db, alert_id)
    now = datetime.now(timezone.utc)

    if data.status is not None:
        if data.status == AlertStatus.ACKNOWLEDGED:
            alert.acknowledged_by = acting_user_id
            alert.acknowledged_at = now
        elif data.status == AlertStatus.RESOLVED:
            alert.resolved_by = acting_user_id
            alert.resolved_at = now
        alert.status = data.status

    db.commit()
    db.refresh(alert)
    return alert
