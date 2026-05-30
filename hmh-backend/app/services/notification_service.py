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

from app.core.logging_config import get_logger

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

logger = get_logger(__name__)

_WINDOW_24H = timedelta(hours=24)

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
# Phase 3Q.1 — new operational categories
_PROCUREMENT_TYPES = {
    AlertType.MR_APPROVED,
    AlertType.PO_SENT_ALERT,
    AlertType.DELIVERY_RECEIVED_ALERT,
    AlertType.WAREHOUSE_TRANSFER_COMPLETED,
    AlertType.REQUEST_PENDING_TOO_LONG,
}
_MILESTONE_TYPES = {
    AlertType.MILESTONE_COMPLETED_ALERT,
    AlertType.MILESTONE_DELAYED_ALERT,
    AlertType.SITE_DELAY,
    AlertType.LOT_DELAYED,
    AlertType.STAGE_DELAYED,
}
_PAYMENT_TYPES = {
    AlertType.INVOICE_CAPTURED,
    AlertType.PAYMENT_COMPLETED,
    AlertType.PARTIAL_PAYMENT_RECORDED,
    AlertType.OVERDUE_PAYMENT,
    AlertType.PAYMENT_DUE,         # Phase 3Q.3: approaching due date
}


def _is_critical_for_throttle(severity: AlertSeverity) -> bool:
    """CRITICAL and HIGH alerts bypass throttling — they always send immediately."""
    return severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)


def _quiet_hours_delay(now: datetime) -> Optional[timedelta]:
    """Return delay until quiet hours end, or None if not in quiet hours / quiet hours disabled."""
    if not settings.WHATSAPP_QUIET_HOURS_ENABLED:
        return None
    try:
        sh, sm = (int(x) for x in settings.WHATSAPP_QUIET_HOURS_START.split(":"))
        eh, em = (int(x) for x in settings.WHATSAPP_QUIET_HOURS_END.split(":"))
    except (ValueError, AttributeError):
        return None

    from datetime import time as dtime
    start = dtime(sh, sm)
    end = dtime(eh, em)
    cur = now.time().replace(second=0, microsecond=0)

    # Wrap-midnight: quiet if cur >= start OR cur < end
    if start > end:
        in_quiet = cur >= start or cur < end
    else:
        in_quiet = start <= cur < end

    if not in_quiet:
        return None

    end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if end_dt <= now:
        end_dt += timedelta(days=1)
    return end_dt - now


def _count_recent_sends(db: Session, recipient_id: uuid.UUID, window: timedelta) -> int:
    """Count SENT/MOCK_SENT notifications for a recipient within the given time window."""
    cutoff = datetime.now(timezone.utc) - window
    return (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.recipient_id == recipient_id,
            NotificationQueue.last_attempt_at >= cutoff,
            NotificationQueue.status.in_([
                NotificationStatus.SENT,
                NotificationStatus.MOCK_SENT,
            ]),
        )
        .count()
    )


def _should_notify(recipient: AlertRecipient, alert: SystemAlert) -> bool:
    """
    Return True if this recipient should receive this alert type.

    Phase 3Q.1: also checks project scope — if recipient.project_id is set,
    only send alerts for that specific project.
    """
    at = alert.alert_type
    sev = alert.severity

    # Project scope filter: if recipient is scoped to a project,
    # skip alerts from other projects
    if recipient.project_id is not None and alert.project_id is not None:
        if recipient.project_id != alert.project_id:
            return False

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
    # Phase 3Q.1 new categories
    if at in _PROCUREMENT_TYPES and getattr(recipient, "receives_procurement_alerts", False):
        return True
    if at in _MILESTONE_TYPES and getattr(recipient, "receives_milestone_alerts", False):
        return True
    if at in _PAYMENT_TYPES and getattr(recipient, "receives_payment_alerts", False):
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


def enqueue_for_alert(
    db: Session,
    alert: SystemAlert,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
) -> list[NotificationQueue]:
    """
    Create NotificationQueue records for all matching active recipients.
    Called immediately after a SystemAlert is created.

    Phase 3Q.1: optional entity_type + entity_id for deep-linking in notifications.
    """
    recipients = (
        db.query(AlertRecipient)
        .filter(AlertRecipient.is_active == True)  # noqa: E712
        .all()
    )

    now = datetime.now(timezone.utc)
    queued: list[NotificationQueue] = []

    for recipient in recipients:
        if not _should_notify(recipient, alert):
            continue

        # Dedup: skip if a non-failed/cancelled entry already exists for this alert+recipient
        existing = (
            db.query(NotificationQueue)
            .filter(
                NotificationQueue.alert_id == alert.id,
                NotificationQueue.recipient_id == recipient.id,
                NotificationQueue.status.notin_([
                    NotificationStatus.FAILED,
                    NotificationStatus.CANCELLED,
                ]),
            )
            .first()
        )
        if existing:
            continue

        message = _build_message(alert)
        requires_ack = alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)

        # Cost optimization: delay non-critical alerts by SUMMARY_INTERVAL_MINUTES
        next_at = now
        if settings.WHATSAPP_COST_OPTIMIZATION_ENABLED and not _is_critical_for_throttle(alert.severity):
            next_at = now + timedelta(minutes=settings.WHATSAPP_SUMMARY_INTERVAL_MINUTES)
            # Quiet hours: push further if in quiet period (non-critical only)
            quiet_delay = _quiet_hours_delay(now)
            if quiet_delay:
                next_at = max(next_at, now + quiet_delay)

        entry = NotificationQueue(
            id=uuid.uuid4(),
            alert_id=alert.id,
            recipient_id=recipient.id,
            channel=NotificationChannel.WHATSAPP,
            phone_number=recipient.phone_number,
            message_body=message,
            status=NotificationStatus.PENDING,
            attempt_count=0,
            next_attempt_at=next_at,
            requires_acknowledgement=requires_ack,
            created_at=now,
            # Phase 3Q.1: entity context
            project_id=alert.project_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(entry)
        queued.append(entry)

    db.flush()
    return queued


def enqueue_direct(
    db: Session,
    *,
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    message: str,
    project_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
) -> list[NotificationQueue]:
    """
    Phase 3Q.1 helper: create a SystemAlert and immediately enqueue it
    in one call. Use this from service-layer triggers (MR approve, PO sent, etc.)
    that need to send a WhatsApp notification but don't otherwise
    create a dedicated alert record.

    Never raises — notification failures must never block the business operation.
    Uses a DB savepoint (begin_nested) so that if the notification INSERT fails,
    only the savepoint rolls back; the parent transaction (business operation) is
    completely unaffected. Returns the queued entries (empty if no recipients match).
    """
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertStatus

        now = datetime.now(timezone.utc)

        with db.begin_nested():   # savepoint — isolates notification writes from parent tx
            alert = SystemAlert(
                project_id=project_id,
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                status=AlertStatus.OPEN,
                notification_channel="whatsapp",
                created_at=now,
            )
            db.add(alert)
            db.flush()

            queued = enqueue_for_alert(db, alert, entity_type=entity_type, entity_id=entity_id)

        return queued
    except Exception as exc:
        logger.exception("enqueue_direct failed (non-fatal): %s", exc)
        return []


def _send_for_queue_entry(entry: NotificationQueue, db: Session) -> tuple[str, Optional[str]]:
    """
    Send a WhatsApp alert with a three-tier fallback strategy:

      1. Template configured  → send_template_message (works any time)
      2. No template, recipient in 24h window → send_text (free-form)
      3. No template, outside 24h window → FAILED with clear reason (no crash)

    Free-form command replies (OK/APPROVE/REJECT) are sent directly in the
    webhook handler and are always in-window, so they are unaffected.
    """
    # Select template: daily summary types use their own template
    is_daily = False
    if entry.alert_id:
        _alert_obj = db.get(SystemAlert, entry.alert_id)
        if _alert_obj and _alert_obj.alert_type in (AlertType.DAILY_SUMMARY, AlertType.WEEKLY_SUMMARY):
            is_daily = True

    if is_daily and settings.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME:
        template_name = settings.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME
    else:
        template_name = settings.WHATSAPP_ALERT_TEMPLATE_NAME

    # ── Tier 1: approved template ─────────────────────────────────────────────
    if template_name:
        lang = settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"

        # Build body components from queue entry so param count matches the template.
        var_count = max(0, int(getattr(settings, "WHATSAPP_ALERT_TEMPLATE_BODY_VAR_COUNT", 2)))
        components: list | None = None
        if var_count > 0:
            # Derive title and first sentence of body from the queued message
            msg_lines = (entry.message_body or "").split("\n")
            title_line = msg_lines[0][:100] if msg_lines else "Alert"
            body_line  = msg_lines[1][:200] if len(msg_lines) > 1 else title_line
            live_params = [title_line, body_line, "HMH Group"]
            parameters = [
                {"type": "text", "text": live_params[i] if i < len(live_params) else f"param{i+1}"}
                for i in range(var_count)
            ]
            components = [{"type": "body", "parameters": parameters}]

        logger.info("WA-SEND template='%s' lang=%s phone=%s", template_name, lang, entry.phone_number)
        status, msg_id = whatsapp_service.send_template_message(
            entry.phone_number, template_name, lang, components=components
        )
        if status == "FAILED":
            logger.error(
                "WA-TEMPLATE-FAILED template='%s' phone=%s error=%s — "
                "verify template name in Meta Business Manager",
                template_name, entry.phone_number, msg_id,
            )
        else:
            logger.info("WA-SEND result status=%s msg_id=%s phone=%s", status, msg_id, entry.phone_number)
        return status, msg_id

    # ── Tier 2: no template — check 24h window ────────────────────────────────
    now = datetime.now(timezone.utc)
    recipient = db.get(AlertRecipient, entry.recipient_id) if entry.recipient_id else None
    last_inbound = recipient.last_inbound_at if recipient else None
    in_window = last_inbound is not None and (now - last_inbound) <= _WINDOW_24H

    if in_window:
        logger.info("WA-SEND free-form last_inbound=%s phone=%s", last_inbound.isoformat(), entry.phone_number)
        return whatsapp_service.send_text(entry.phone_number, entry.message_body)

    # ── Tier 3: no template, outside window — fail gracefully ─────────────────
    msg = (
        "WhatsApp 24-hour window closed and no template configured. "
        "Set WHATSAPP_ALERT_TEMPLATE_NAME to send alerts at any time."
    )
    logger.error("WA-SEND FAILED no_template window_closed phone=%s last_inbound=%s", entry.phone_number, last_inbound)
    return ("FAILED", msg)


def process_queue(db: Session) -> dict:
    """
    Send all PENDING queue entries whose next_attempt_at <= now.
    Returns counts: {sent, mock_sent, failed, skipped}.
    """
    now = datetime.now(timezone.utc)
    # WITH FOR UPDATE SKIP LOCKED: if two workers run simultaneously, each claims
    # a disjoint set of rows. No duplicate sends possible.
    pending = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.status.in_([NotificationStatus.PENDING, NotificationStatus.FAILED]),
            NotificationQueue.next_attempt_at <= now,
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    counts = {"sent": 0, "mock_sent": 0, "failed": 0, "skipped": 0}

    for entry in pending:
        # Check if already acknowledged
        if entry.acknowledged_at:
            entry.status = NotificationStatus.ACKNOWLEDGED
            counts["skipped"] += 1
            continue

        # Hourly cap: skip low-priority sends when recipient hit the per-hour limit
        if settings.WHATSAPP_COST_OPTIMIZATION_ENABLED and entry.recipient_id:
            max_ph = settings.WHATSAPP_MAX_ALERTS_PER_HOUR_PER_RECIPIENT
            if max_ph > 0:
                recent = _count_recent_sends(db, entry.recipient_id, timedelta(hours=1))
                if recent >= max_ph:
                    logger.info(
                        "WA hourly cap reached recipient=%s recent=%d max=%d — skipping",
                        entry.recipient_id, recent, max_ph,
                    )
                    counts["skipped"] += 1
                    continue

        # Check if parent alert was resolved/acknowledged
        alert = None
        if entry.alert_id:
            alert = db.get(SystemAlert, entry.alert_id)
            if alert and alert.status in (AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED):
                entry.status = NotificationStatus.CANCELLED
                counts["skipped"] += 1
                continue

        # Attempt send — chooses free-form or template based on 24h window
        status_str, provider_id = _send_for_queue_entry(entry, db)

        entry.attempt_count += 1
        entry.last_attempt_at = now
        entry.provider_message_id = provider_id

        if status_str == "SENT":
            entry.status = NotificationStatus.SENT
            counts["sent"] += 1
            _schedule_next(entry, alert)
        elif status_str == "MOCK_SENT":
            entry.status = NotificationStatus.MOCK_SENT
            counts["mock_sent"] += 1
            _schedule_next(entry, alert)
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


_OPERATIONAL_LABELS: dict = {
    AlertType.MR_APPROVED:                  ("INFO",   "✅"),
    AlertType.PO_SENT_ALERT:                ("INFO",   "📤"),
    AlertType.DELIVERY_RECEIVED_ALERT:      ("INFO",   "📦"),
    AlertType.WAREHOUSE_TRANSFER_COMPLETED: ("INFO",   "🔄"),
    AlertType.INVOICE_CAPTURED:             ("INFO",   "🧾"),
    AlertType.PAYMENT_COMPLETED:            ("INFO",   "💰"),
    AlertType.PARTIAL_PAYMENT_RECORDED:     ("NOTICE", "⚡"),
    AlertType.MILESTONE_COMPLETED_ALERT:    ("INFO",   "🏁"),
    AlertType.MILESTONE_DELAYED_ALERT:      ("NOTICE", "⏰"),
    AlertType.OVERDUE_PAYMENT:              ("HIGH",   "❗"),
    AlertType.PAYMENT_DUE:                  ("NOTICE", "📅"),
    AlertType.LOW_STOCK:                    ("NOTICE", "⚠️"),
    AlertType.FUEL_USAGE_HIGH:              ("NOTICE", "⛽"),
}


def _build_message(alert: SystemAlert) -> str:
    """
    Build the WhatsApp message body for an alert.

    Phase 3Q.1: operational alerts get emoji prefixes and concise one-line format.
    Critical/High alerts keep the action hint for acknowledgment.
    """
    label = {
        AlertSeverity.CRITICAL: "CRITICAL",
        AlertSeverity.HIGH:     "HIGH",
        AlertSeverity.MEDIUM:   "NOTICE",
        AlertSeverity.LOW:      "INFO",
    }.get(alert.severity, "ALERT")

    # Emoji + label override for operational types
    if alert.alert_type in _OPERATIONAL_LABELS:
        op_label, emoji = _OPERATIONAL_LABELS[alert.alert_type]
        label = op_label
    else:
        emoji = ""

    # Strip any leading severity prefix from the raw message, take first sentence
    clean = _SEVERITY_PREFIX_RE.sub("", alert.message).strip()
    sentence = clean.split(".")[0].strip()
    if len(sentence) > 120:
        sentence = sentence[:117] + "..."

    prefix = f"{emoji} " if emoji else ""
    body = f"{prefix}{label}: {alert.title}\n{sentence}"

    # Action hint only for critical/high alerts that need acknowledgment
    requires_ack = alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)
    if requires_ack:
        body += f"\n\n{_ACTION_HINT}"

    return body


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
