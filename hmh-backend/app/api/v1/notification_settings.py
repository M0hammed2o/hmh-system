"""
Notification Settings API — Phase 3Q.1.

Manages WhatsApp alert recipients and per-project notification configuration.
All endpoints are OFFICE_AND_ABOVE — site staff cannot manage notification settings.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RecipientCreate(BaseModel):
    name:                        str
    phone_number:                str              # E.164 e.g. +27831234567
    label:                       Optional[str] = None
    project_id:                  Optional[uuid.UUID] = None
    receives_critical_alerts:    bool = True
    receives_daily_summary:      bool = True
    receives_invoice_alerts:     bool = False
    receives_delivery_alerts:    bool = False
    receives_vehicle_alerts:     bool = False
    receives_material_alerts:    bool = False
    receives_procurement_alerts: bool = False
    receives_milestone_alerts:   bool = False
    receives_payment_alerts:     bool = False


class RecipientUpdate(BaseModel):
    name:                        Optional[str]         = None
    label:                       Optional[str]         = None
    project_id:                  Optional[uuid.UUID]   = None
    is_active:                   Optional[bool]        = None
    receives_critical_alerts:    Optional[bool]        = None
    receives_daily_summary:      Optional[bool]        = None
    receives_invoice_alerts:     Optional[bool]        = None
    receives_delivery_alerts:    Optional[bool]        = None
    receives_vehicle_alerts:     Optional[bool]        = None
    receives_material_alerts:    Optional[bool]        = None
    receives_procurement_alerts: Optional[bool]        = None
    receives_milestone_alerts:   Optional[bool]        = None
    receives_payment_alerts:     Optional[bool]        = None


def _recipient_to_dict(r) -> dict:
    return {
        "id":                          str(r.id),
        "name":                        r.name,
        "phone_number":                r.phone_number,
        "label":                       r.label,
        "project_id":                  str(r.project_id) if r.project_id else None,
        "is_active":                   r.is_active,
        "receives_critical_alerts":    r.receives_critical_alerts,
        "receives_daily_summary":      r.receives_daily_summary,
        "receives_invoice_alerts":     r.receives_invoice_alerts,
        "receives_delivery_alerts":    r.receives_delivery_alerts,
        "receives_vehicle_alerts":     r.receives_vehicle_alerts,
        "receives_material_alerts":    r.receives_material_alerts,
        "receives_procurement_alerts": getattr(r, "receives_procurement_alerts", False),
        "receives_milestone_alerts":   getattr(r, "receives_milestone_alerts", False),
        "receives_payment_alerts":     getattr(r, "receives_payment_alerts", False),
        "last_inbound_at":             r.last_inbound_at.isoformat() if r.last_inbound_at else None,
        "created_at":                  r.created_at.isoformat() if hasattr(r, "created_at") and r.created_at else None,
    }


# ── Recipients CRUD ───────────────────────────────────────────────────────────

@router.get("/recipients", response_model=ApiSuccess[list[dict]], dependencies=[OFFICE_AND_ABOVE])
def list_recipients(
    db: DbSession,
    include_inactive: bool = Query(False),
    project_id: Optional[uuid.UUID] = Query(None),
):
    """List all WhatsApp alert recipients, optionally filtered by project."""
    from app.models.alert_recipient import AlertRecipient

    q = db.query(AlertRecipient)
    if not include_inactive:
        q = q.filter(AlertRecipient.is_active == True)  # noqa: E712
    if project_id:
        q = q.filter(
            (AlertRecipient.project_id == project_id) | (AlertRecipient.project_id.is_(None))
        )
    recipients = q.order_by(AlertRecipient.name).all()
    return ApiSuccess(data=[_recipient_to_dict(r) for r in recipients])


@router.post(
    "/recipients",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_recipient(body: RecipientCreate, db: DbSession, current_user: CurrentUser):
    """Add a new WhatsApp alert recipient."""
    from app.models.alert_recipient import AlertRecipient
    from app.models.project import Project
    from datetime import datetime, timezone

    # Validate phone uniqueness
    existing = db.query(AlertRecipient).filter(
        AlertRecipient.phone_number == body.phone_number
    ).first()
    if existing:
        raise HTTPException(409, f"Phone number {body.phone_number} already registered.")

    # Validate project if provided
    if body.project_id:
        if not db.get(Project, body.project_id):
            raise HTTPException(404, "Project not found.")

    now = datetime.now(timezone.utc)
    r = AlertRecipient(
        name=body.name,
        phone_number=body.phone_number,
        label=body.label,
        project_id=body.project_id,
        is_active=True,
        receives_critical_alerts=body.receives_critical_alerts,
        receives_daily_summary=body.receives_daily_summary,
        receives_invoice_alerts=body.receives_invoice_alerts,
        receives_delivery_alerts=body.receives_delivery_alerts,
        receives_vehicle_alerts=body.receives_vehicle_alerts,
        receives_material_alerts=body.receives_material_alerts,
        receives_procurement_alerts=body.receives_procurement_alerts,
        receives_milestone_alerts=body.receives_milestone_alerts,
        receives_payment_alerts=body.receives_payment_alerts,
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return ApiSuccess(data=_recipient_to_dict(r), message="Recipient created.")


@router.patch(
    "/recipients/{recipient_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_recipient(
    recipient_id: uuid.UUID, body: RecipientUpdate, db: DbSession
):
    """Update a recipient's settings or category subscriptions."""
    from app.models.alert_recipient import AlertRecipient
    from datetime import datetime, timezone

    r = db.get(AlertRecipient, recipient_id)
    if not r:
        raise HTTPException(404, "Recipient not found.")

    fields = body.model_fields_set
    for field in fields:
        val = getattr(body, field)
        if val is not None or field in {"project_id"}:
            setattr(r, field, val)

    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    return ApiSuccess(data=_recipient_to_dict(r), message="Recipient updated.")


@router.delete(
    "/recipients/{recipient_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_recipient(recipient_id: uuid.UUID, db: DbSession):
    """Soft-delete (deactivate) a recipient."""
    from app.models.alert_recipient import AlertRecipient

    r = db.get(AlertRecipient, recipient_id)
    if not r:
        raise HTTPException(404, "Recipient not found.")

    r.is_active = False
    db.commit()
    return ApiSuccess(data={"id": str(r.id)}, message="Recipient deactivated.")


@router.post(
    "/recipients/{recipient_id}/send-test",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def send_test_notification(recipient_id: uuid.UUID, db: DbSession):
    """
    Send a MOCK test message to a recipient to verify their WhatsApp number.
    Always uses MOCK mode regardless of WHATSAPP_ENABLED — never charges quota.
    """
    from app.models.alert_recipient import AlertRecipient
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationChannel, NotificationStatus
    from datetime import datetime, timezone

    r = db.get(AlertRecipient, recipient_id)
    if not r:
        raise HTTPException(404, "Recipient not found.")

    now = datetime.now(timezone.utc)
    test_body = (
        f"TEST: HMH Alert System\n"
        f"This is a test message for {r.name}.\n"
        f"If you receive this, your WhatsApp number is correctly configured.\n"
        f"— HMH Construction OS"
    )

    # Queue a test entry (always mock)
    entry = NotificationQueue(
        recipient_id=r.id,
        channel=NotificationChannel.WHATSAPP,
        phone_number=r.phone_number,
        message_body=test_body,
        status=NotificationStatus.MOCK_SENT,   # test = always mock
        attempt_count=1,
        last_attempt_at=now,
        next_attempt_at=now,
        requires_acknowledgement=False,
        created_at=now,
    )
    db.add(entry)
    db.commit()

    return ApiSuccess(
        data={"recipient": r.name, "phone": r.phone_number, "status": "MOCK_SENT"},
        message=f"Test notification queued (mock) for {r.name}.",
    )


# ── Queue stats (lightweight summary for settings page) ──────────────────────

@router.get("/queue-stats", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def queue_stats(db: DbSession):
    """Return high-level notification queue statistics for the settings page header."""
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationStatus
    from sqlalchemy import func

    rows = (
        db.query(NotificationQueue.status, func.count(NotificationQueue.id).label("cnt"))
        .group_by(NotificationQueue.status)
        .all()
    )
    counts = {r.status.value: r.cnt for r in rows}
    return ApiSuccess(data={
        "pending":      counts.get("PENDING", 0),
        "sent":         counts.get("SENT", 0),
        "mock_sent":    counts.get("MOCK_SENT", 0),
        "failed":       counts.get("FAILED", 0),
        "acknowledged": counts.get("ACKNOWLEDGED", 0),
        "total":        sum(counts.values()),
    })


# ── Trigger daily summary (authenticated, for testing from UI) ────────────────

@router.post("/trigger-daily-summary", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def trigger_daily_summary(db: DbSession):
    """
    Manually trigger the 6pm daily summary right now.
    Builds the summary text and sends to all recipients with receives_daily_summary=True.
    Useful for testing the summary before the automated 6pm cron fires.
    """
    from app.models.alert import SystemAlert
    from app.models.alert_recipient import AlertRecipient
    from app.models.enums import AlertType, AlertSeverity, NotificationChannel
    from app.services.notification_service import build_daily_summary_text, enqueue_for_alert, process_queue

    recipients = (
        db.query(AlertRecipient)
        .filter(AlertRecipient.is_active == True, AlertRecipient.receives_daily_summary == True)  # noqa: E712
        .all()
    )
    if not recipients:
        return ApiSuccess(data={"queued": 0, "sent": 0}, message="No recipients have Daily Summary enabled.")

    text = build_daily_summary_text(db)
    alert = SystemAlert(
        alert_type=AlertType.DAILY_SUMMARY,
        severity=AlertSeverity.LOW,
        title="Daily Summary",
        message=text,
        notification_channel=NotificationChannel.WHATSAPP,
    )
    db.add(alert)
    db.flush()

    queued = 0
    for r in recipients:
        enqueue_for_alert(db, alert, r)
        queued += 1
    db.commit()

    sent, mock, failed = process_queue(db)
    return ApiSuccess(
        data={"queued": queued, "sent": sent, "mock_sent": mock, "failed": failed},
        message=f"Daily summary sent to {queued} recipient(s).",
    )
