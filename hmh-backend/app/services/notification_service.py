"""
Notification service — queue management and escalation.

Responsibilities:
 - Enqueue WhatsApp notifications for a SystemAlert
 - Send queued messages (called from route or background task)
 - Process incoming acknowledgements from WhatsApp webhook
 - Escalation: schedule follow-up attempts for unacknowledged CRITICAL/HIGH alerts
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import SystemAlert
from app.models.alert_recipient import AlertRecipient
from app.models.enums import (
    AlertSeverity, AlertStatus, AlertType,
    NotificationChannel, NotificationStatus,
)
from app.models.notification_queue import NotificationQueue
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

# Alert types that map to each recipient subscription
_MATERIAL_TYPES = {
    AlertType.MATERIAL_OVERUSE,
    AlertType.BOQ_VARIANCE_OVERUSE,
    AlertType.BOQ_ALLOCATION_EXCEEDED,
    AlertType.LOW_STOCK,
    AlertType.NEGATIVE_STOCK,
}
_DELIVERY_TYPES = {
    AlertType.DELIVERY_MISMATCH,
    AlertType.DELIVERY_NOTE_MISSING,
    AlertType.SIGNATURE_MISSING,
    AlertType.DELIVERY_DISCREPANCY,
    AlertType.DELIVERY_WITHOUT_PO,
    AlertType.DELIVERY_SIGNATURE_MISSING,
}
_INVOICE_TYPES = {
    AlertType.INVOICE_MISMATCH,
    AlertType.INVOICE_UNMATCHED,
    AlertType.INVOICE_MISSING_DELIVERY_NOTE,
    AlertType.OVERDUE_PAYMENT,
}
_VEHICLE_TYPES = {
    AlertType.VEHICLE_REPAIR_LOGGED,
    AlertType.FUEL_USAGE_HIGH,
}


def _should_notify(recipient: AlertRecipient, alert: SystemAlert) -> bool:
    """Return True if this recipient should receive this alert type."""
    at = alert.alert_type
    sev = alert.severity

    # Always notify active recipients who get critical
    if sev in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) and recipient.receives_critical_alerts:
        return True
    if at in _MATERIAL_TYPES and recipient.receives_material_alerts:
        return True
    if at in _DELIVERY_TYPES and recipient.receives_delivery_alerts:
        return True
    if at in _INVOICE_TYPES and recipient.receives_invoice_alerts:
        return True
    if at in _VEHICLE_TYPES and recipient.receives_vehicle_alerts:
        return True
    if at in (AlertType.DAILY_SUMMARY, AlertType.WEEKLY_SUMMARY) and recipient.receives_daily_summary:
        return True
    return False


def _escalation_minutes(severity: AlertSeverity, attempt: int) -> Optional[int]:
    """Return minutes until next attempt, or None if max reached."""
    if severity == AlertSeverity.CRITICAL:
        schedule = [0, 5, 15, 30, 60]  # attempt 0=immediate, then +5, +10(total15), +15(total30)...
        max_attempts = settings.CRITICAL_ALERT_MAX_ATTEMPTS
    elif severity == AlertSeverity.HIGH:
        schedule = [0, settings.HIGH_ALERT_FIRST_REMINDER_MINUTES]
        max_attempts = settings.HIGH_ALERT_MAX_ATTEMPTS
    else:
        return None  # MEDIUM/LOW: no escalation

    if attempt >= max_attempts:
        return None
    if attempt < len(schedule):
        return schedule[attempt]
    return None


def enqueue_for_alert(db: Session, alert: SystemAlert) -> list[NotificationQueue]:
    """
    Create NotificationQueue records for all matching active recipients.
    Called immediately after a SystemAlert is created.
    """
    recipients = (
        db.query(AlertRecipient)
        .filter(AlertRecipient.is_active == True)
        .all()
    )

    now = datetime.now(timezone.utc)
    queued: list[NotificationQueue] = []

    for recipient in recipients:
        if not _should_notify(recipient, alert):
            continue

        message = _build_message(alert)
        requires_ack = alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)

        entry = NotificationQueue(
            id=uuid.uuid4(),
            alert_id=alert.id,
            recipient_id=recipient.id,
            channel=NotificationChannel.WHATSAPP,
            phone_number=recipient.phone_number,
            message_body=message,
            status=NotificationStatus.PENDING,
            attempt_count=0,
            next_attempt_at=now,
            requires_acknowledgement=requires_ack,
            created_at=now,
        )
        db.add(entry)
        queued.append(entry)

    db.flush()
    return queued


def _send_for_queue_entry(entry: NotificationQueue) -> tuple[str, Optional[str]]:
    """
    Send an automatic WhatsApp alert using an approved Meta template.

    All automatic alert notifications (process_queue) use template messages so
    they work regardless of whether the recipient has messaged us recently.
    Free-form replies (OK/APPROVE/REJECT/LIST) are handled directly in the
    webhook handler and are always in-window by definition.

    If WHATSAPP_ALERT_TEMPLATE_NAME is not configured, the send fails with a
    clear diagnostic message.
    """
    template_name = settings.WHATSAPP_ALERT_TEMPLATE_NAME
    if not template_name:
        msg = (
            "WhatsApp template not configured. Automatic alerts require an approved "
            "WhatsApp template. Set WHATSAPP_ALERT_TEMPLATE_NAME in environment variables."
        )
        logger.error("WhatsApp send FAILED: %s (phone=%s)", msg, entry.phone_number)
        print(
            f"[WA-SEND] FAILED — no template configured"
            f" | phone={entry.phone_number}",
            flush=True,
        )
        return ("FAILED", msg)

    lang = settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"
    logger.info(
        "WhatsApp send: TEMPLATE '%s' lang=%s to %s",
        template_name, lang, entry.phone_number,
    )
    print(
        f"[WA-SEND] TEMPLATE '{template_name}' lang={lang}"
        f" | phone={entry.phone_number}",
        flush=True,
    )
    status, msg_id = whatsapp_service.send_template_message(
        entry.phone_number, template_name, lang
    )
    print(
        f"[WA-SEND] Result: status={status} provider_message_id={msg_id}"
        f" | phone={entry.phone_number}",
        flush=True,
    )
    return status, msg_id


def process_queue(db: Session) -> dict:
    """
    Send all PENDING queue entries whose next_attempt_at <= now.
    Returns counts: {sent, mock_sent, failed, skipped}.
    """
    now = datetime.now(timezone.utc)
    pending = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.status.in_([NotificationStatus.PENDING, NotificationStatus.FAILED]),
            NotificationQueue.next_attempt_at <= now,
        )
        .all()
    )

    counts = {"sent": 0, "mock_sent": 0, "failed": 0, "skipped": 0}

    for entry in pending:
        # Check if already acknowledged
        if entry.acknowledged_at:
            entry.status = NotificationStatus.ACKNOWLEDGED
            counts["skipped"] += 1
            continue

        # Check if parent alert was resolved/acknowledged
        if entry.alert_id:
            alert = db.get(SystemAlert, entry.alert_id)
            if alert and alert.status in (AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED):
                entry.status = NotificationStatus.CANCELLED
                counts["skipped"] += 1
                continue

        # Attempt send — chooses free-form or template based on 24h window
        status_str, provider_id = _send_for_queue_entry(entry)

        entry.attempt_count += 1
        entry.last_attempt_at = now
        entry.provider_message_id = provider_id

        if status_str == "SENT":
            entry.status = NotificationStatus.SENT
            counts["sent"] += 1
            # Schedule next attempt for escalation if not acknowledged
            _schedule_next(entry, alert if entry.alert_id else None)
        elif status_str == "MOCK_SENT":
            entry.status = NotificationStatus.MOCK_SENT
            counts["mock_sent"] += 1
            _schedule_next(entry, alert if entry.alert_id else None)
        else:
            entry.status = NotificationStatus.FAILED
            entry.error_message = provider_id
            counts["failed"] += 1

    db.commit()
    return counts


def _schedule_next(entry: NotificationQueue, alert: Optional[SystemAlert]) -> None:
    """If escalation is needed, schedule the next attempt."""
    if not entry.requires_acknowledgement or not alert:
        return
    if entry.acknowledged_at:
        return

    minutes = _escalation_minutes(alert.severity, entry.attempt_count)
    if minutes is None:
        # Max attempts reached — leave as-is (SENT/MOCK_SENT, no more retries)
        return

    now = datetime.now(timezone.utc)
    entry.status = NotificationStatus.PENDING
    entry.next_attempt_at = now + timedelta(minutes=minutes)


def _phone_variants(phone: str) -> list[str]:
    """
    Return all normalised forms of a phone number so we can match regardless
    of how it was stored (+27…, 27…, 0…).
    """
    digits = phone.strip().lstrip("+")
    variants = [digits, f"+{digits}"]
    if digits.startswith("27") and len(digits) == 11:
        variants.append("0" + digits[2:])
    return list(dict.fromkeys(variants))  # deduplicated, order preserved


def acknowledge_by_phone(db: Session, phone_number: str) -> int:
    """
    Mark all pending/sent notifications for this phone as acknowledged.
    Tries all normalised variants of the phone number so format differences
    (e.g. +27831234567 vs 27831234567 vs 0831234567) are handled.
    Returns total count of records updated.
    """
    now = datetime.now(timezone.utc)

    entries = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.phone_number.in_(_phone_variants(phone_number)),
            NotificationQueue.status.in_([
                NotificationStatus.SENT,
                NotificationStatus.MOCK_SENT,
                NotificationStatus.PENDING,
            ]),
            NotificationQueue.acknowledged_at.is_(None),
            NotificationQueue.requires_acknowledgement == True,
        )
        .all()
    )

    updated = 0
    alert_ids: set[uuid.UUID] = set()
    for entry in entries:
        entry.status = NotificationStatus.ACKNOWLEDGED
        entry.acknowledged_at = now
        if entry.alert_id:
            alert_ids.add(entry.alert_id)
        updated += 1

    # Acknowledge parent alerts
    for alert_id in alert_ids:
        alert = db.get(SystemAlert, alert_id)
        if alert and alert.status == AlertStatus.OPEN:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = now

    db.commit()
    return updated


_ACTION_HINT = "Reply:\nOK → acknowledge\nAPPROVE → approve\nREJECT → reject"

_SEVERITY_PREFIX_RE = re.compile(
    r"^(CRITICAL|HIGH|MEDIUM|NOTICE|LOW|INFO)\s*:\s*", re.IGNORECASE
)


def _build_message(alert: SystemAlert) -> str:
    """Build the WhatsApp message body for an alert."""
    label = {
        AlertSeverity.CRITICAL: "CRITICAL",
        AlertSeverity.HIGH:     "HIGH",
        AlertSeverity.MEDIUM:   "NOTICE",
        AlertSeverity.LOW:      "INFO",
    }.get(alert.severity, "ALERT")

    # Strip any leading severity prefix from the raw message, take first sentence
    clean = _SEVERITY_PREFIX_RE.sub("", alert.message).strip()
    sentence = clean.split(".")[0].strip()
    if len(sentence) > 120:
        sentence = sentence[:117] + "..."

    return f"{label}: {alert.title}\n{sentence}\n\n{_ACTION_HINT}"


def get_queue(
    db: Session,
    status: Optional[NotificationStatus] = None,
    limit: int = 50,
) -> list[NotificationQueue]:
    q = db.query(NotificationQueue).order_by(NotificationQueue.created_at.desc())
    if status:
        q = q.filter(NotificationQueue.status == status)
    return q.limit(limit).all()


def build_daily_summary_text(db: Session) -> str:
    """Build the daily summary message body using existing dashboard stats."""
    from app.services.dashboard_service import get_stats

    stats = get_stats(db)
    now = datetime.now(timezone.utc)

    lines = [
        f"📊 *HMH Daily Summary — {now.strftime('%d %b %Y')}*",
        "",
        f"Active Projects: {stats.active_projects}",
        f"Active Sites: {stats.active_sites}",
        f"Open Alerts: {stats.open_alerts}",
        f"Pending Invoices: {stats.pending_invoices}",
        f"Pending Payments: {stats.pending_payments}",
        f"Open POs: {stats.open_purchase_orders}",
        f"Fuel Cost (total): R{stats.fuel_total_cost:,.0f}",
        f"Total Paid: R{stats.total_paid_amount:,.0f}",
    ]
    return "\n".join(lines)
