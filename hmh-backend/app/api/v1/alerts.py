"""System alert routes — CRUD, acknowledge/resolve, WhatsApp recipients, notification queue."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.models.enums import AlertStatus, NotificationStatus
from app.schemas.alert import AlertRead, AlertUpdate
from app.schemas.common import ApiSuccess
from app.schemas.notification import (
    AlertRecipientCreate,
    AlertRecipientRead,
    AlertRecipientUpdate,
    NotificationQueueRead,
    QueueStats,
)
from app.services import alert_service, notification_service, recipient_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Alert list + update ───────────────────────────────────────────────────────

@router.get("/", response_model=ApiSuccess[list[AlertRead]], dependencies=[ALL_ROLES])
def list_alerts(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
    status: Optional[AlertStatus] = Query(None),
    alert_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    alerts = alert_service.list_alerts(db, project_id, status, limit, alert_type)
    return ApiSuccess(data=[AlertRead.model_validate(a) for a in alerts])


@router.patch("/{alert_id}", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def update_alert(alert_id: uuid.UUID, body: AlertUpdate, db: DbSession, current_user: CurrentUser):
    alert = alert_service.update_alert(db, alert_id, body, current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert updated.")


@router.post("/{alert_id}/acknowledge", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def acknowledge_alert(alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    from app.schemas.alert import AlertUpdate as AU
    alert = alert_service.update_alert(db, alert_id, AU(status=AlertStatus.ACKNOWLEDGED), current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert acknowledged.")


@router.post("/{alert_id}/resolve", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def resolve_alert(alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    from app.schemas.alert import AlertUpdate as AU
    alert = alert_service.update_alert(db, alert_id, AU(status=AlertStatus.RESOLVED), current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert resolved.")


# ── Alert stats ───────────────────────────────────────────────────────────────

@router.get("/stats", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_alert_stats(db: DbSession, project_id: Optional[uuid.UUID] = Query(None)):
    stats = alert_service.get_stats(db, project_id)
    return ApiSuccess(data=stats)


# ── Daily summary ─────────────────────────────────────────────────────────────

@router.post("/daily-summary", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def generate_daily_summary(db: DbSession):
    """Build daily summary text and optionally send to all daily-summary recipients."""
    text = notification_service.build_daily_summary_text(db)

    # Enqueue for all daily-summary recipients
    from app.models.enums import AlertSeverity, AlertType
    from app.models.alert import SystemAlert
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    summary_alert = SystemAlert(
        alert_type=AlertType.DAILY_SUMMARY,
        severity=AlertSeverity.LOW,
        title="Daily Business Summary",
        message=text,
        status=AlertStatus.OPEN,
        notification_channel="in_app",
        created_at=now,
    )
    db.add(summary_alert)
    db.flush()

    queued = notification_service.enqueue_for_alert(db, summary_alert)
    counts = notification_service.process_queue(db)

    return ApiSuccess(
        data={
            "summary_text": text,
            "queued": len(queued),
            "send_counts": counts,
        },
        message="Daily summary generated.",
    )


# ── WhatsApp Recipients ───────────────────────────────────────────────────────

@router.get("/recipients", response_model=ApiSuccess[list[AlertRecipientRead]], dependencies=[ALL_ROLES])
def list_recipients(db: DbSession):
    recipients = recipient_service.list_recipients(db)
    return ApiSuccess(data=[AlertRecipientRead.model_validate(r) for r in recipients])


@router.post("/recipients", response_model=ApiSuccess[AlertRecipientRead], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_recipient(body: AlertRecipientCreate, db: DbSession, current_user: CurrentUser):
    recipient = recipient_service.create_recipient(db, body, created_by=current_user.id)
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient), message="Recipient added.")


@router.patch("/recipients/{recipient_id}", response_model=ApiSuccess[AlertRecipientRead], dependencies=[OFFICE_AND_ABOVE])
def update_recipient(recipient_id: uuid.UUID, body: AlertRecipientUpdate, db: DbSession):
    recipient = recipient_service.update_recipient(db, recipient_id, body)
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient))


@router.delete("/recipients/{recipient_id}", response_model=ApiSuccess[None], dependencies=[OFFICE_AND_ABOVE])
def deactivate_recipient(recipient_id: uuid.UUID, db: DbSession):
    from app.schemas.notification import AlertRecipientUpdate as ARU
    recipient_service.update_recipient(db, recipient_id, ARU(is_active=False))
    return ApiSuccess(data=None, message="Recipient deactivated.")


@router.post("/recipients/{recipient_id}/test", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def send_test_message(recipient_id: uuid.UUID, db: DbSession):
    """Send a test WhatsApp message to this recipient."""
    from app.services import whatsapp_service
    recipient = recipient_service.get_recipient(db, recipient_id)
    status, msg_id = whatsapp_service.send_text(
        recipient.phone_number,
        f"✅ *HMH Test Message*\n\nHi {recipient.name}, this is a test from the HMH Construction System.\nYou are configured as: {recipient.label or 'Recipient'}",
    )
    return ApiSuccess(
        data={"status": status, "provider_message_id": msg_id},
        message=f"Test message status: {status}",
    )


# ── Notification Queue ────────────────────────────────────────────────────────

@router.get("/queue", response_model=ApiSuccess[list[NotificationQueueRead]], dependencies=[ALL_ROLES])
def get_notification_queue(
    db: DbSession,
    status: Optional[NotificationStatus] = Query(None),
    limit: int = Query(50, le=200),
):
    entries = notification_service.get_queue(db, status, limit)
    return ApiSuccess(data=[NotificationQueueRead.model_validate(e) for e in entries])


@router.get("/queue/stats", response_model=ApiSuccess[QueueStats], dependencies=[ALL_ROLES])
def get_queue_stats(db: DbSession):
    from sqlalchemy import func
    from app.models.notification_queue import NotificationQueue
    rows = (
        db.query(NotificationQueue.status, func.count(NotificationQueue.id))
        .group_by(NotificationQueue.status)
        .all()
    )
    counts = {r[0].value: r[1] for r in rows}
    return ApiSuccess(data=QueueStats(
        pending=counts.get("PENDING", 0),
        sent=counts.get("SENT", 0),
        mock_sent=counts.get("MOCK_SENT", 0),
        failed=counts.get("FAILED", 0),
        acknowledged=counts.get("ACKNOWLEDGED", 0),
        cancelled=counts.get("CANCELLED", 0),
    ))


@router.post("/queue/process", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def process_notification_queue(db: DbSession):
    """Manually trigger queue processing (send pending messages)."""
    counts = notification_service.process_queue(db)
    return ApiSuccess(data=counts, message="Queue processed.")
