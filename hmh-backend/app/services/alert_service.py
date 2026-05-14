"""System alert service."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.alert import SystemAlert
from app.models.enums import AlertSeverity, AlertStatus, AlertType
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
    alert_type: Optional[str] = None,
) -> list[SystemAlert]:
    q = db.query(SystemAlert)
    if project_id:
        q = q.filter(SystemAlert.project_id == project_id)
    if status:
        q = q.filter(SystemAlert.status == status)
    if alert_type:
        q = q.filter(SystemAlert.alert_type == alert_type)
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


def get_stats(db: Session, project_id: Optional[uuid.UUID] = None) -> dict:
    """Return alert counts grouped by status and severity."""
    q = db.query(SystemAlert)
    if project_id:
        q = q.filter(SystemAlert.project_id == project_id)

    alerts = q.all()

    by_status = {}
    for a in alerts:
        key = a.status.value
        by_status[key] = by_status.get(key, 0) + 1

    critical_open = sum(
        1 for a in alerts
        if a.severity == AlertSeverity.CRITICAL and a.status == AlertStatus.OPEN
    )
    high_open = sum(
        1 for a in alerts
        if a.severity == AlertSeverity.HIGH and a.status == AlertStatus.OPEN
    )

    # Pending WhatsApp acknowledgements
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationStatus
    pending_ack = (
        db.query(func.count(NotificationQueue.id))
        .filter(
            NotificationQueue.requires_acknowledgement == True,
            NotificationQueue.acknowledged_at.is_(None),
            NotificationQueue.status.in_([
                NotificationStatus.SENT,
                NotificationStatus.MOCK_SENT,
                NotificationStatus.PENDING,
            ]),
        )
        .scalar()
    ) or 0

    failed_sends = (
        db.query(func.count(NotificationQueue.id))
        .filter(NotificationQueue.status == NotificationStatus.FAILED)
        .scalar()
    ) or 0

    return {
        "total": len(alerts),
        "open": by_status.get("OPEN", 0),
        "acknowledged": by_status.get("ACKNOWLEDGED", 0),
        "resolved": by_status.get("RESOLVED", 0),
        "critical_open": critical_open,
        "high_open": high_open,
        "pending_whatsapp_ack": pending_ack,
        "failed_whatsapp_sends": failed_sends,
    }
