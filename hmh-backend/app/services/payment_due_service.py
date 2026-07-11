"""
Scan invoices for approaching and overdue payment due dates.

Called by:
  - POST /api/v1/internal/scan-payment-due   (cron, daily)
  - POST /api/v1/notification-settings/scan-payment-due   (manual trigger, office)

Deduplication: we check for an existing SystemAlert with the same entity_id
and alert_type created in the last 23 hours before creating another one,
so repeated scans don't spam the same invoice multiple times per day.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Warn N days before due date
WARNING_DAYS_BEFORE = 7


def scan_payment_due(db: Session) -> dict:
    """
    Scan unpaid invoices for approaching / overdue payment due dates.

    Returns a dict with counts: {warnings_queued, overdue_queued, already_notified, errors}
    """
    from app.models.alert import SystemAlert
    from app.models.enums import AlertSeverity, AlertType
    from app.models.invoice import Invoice
    from app.models.supplier import Supplier
    from app.services.notification_service import enqueue_for_alert

    today = date.today()
    warn_threshold = today + timedelta(days=WARNING_DAYS_BEFORE)

    # Unpaid statuses — anything that hasn't been fully settled
    unpaid_statuses = ("DRAFT", "SUBMITTED", "APPROVED", "INVOICED", "PARTIALLY_PAID", "SENT")

    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.due_date.isnot(None),
            Invoice.status.in_(unpaid_statuses),
        )
        .all()
    )

    warnings_queued = 0
    overdue_queued  = 0
    already_notified = 0
    errors = 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=23)

    for inv in invoices:
        if inv.due_date is None:
            continue

        due = inv.due_date
        is_overdue  = due < today
        is_upcoming = not is_overdue and due <= warn_threshold

        if not is_overdue and not is_upcoming:
            continue

        # Deduplicate: skip if we already sent this type of alert recently
        alert_type = AlertType.OVERDUE_PAYMENT if is_overdue else AlertType.PAYMENT_DUE
        existing = (
            db.query(SystemAlert)
            .filter(
                SystemAlert.entity_id == inv.id,
                SystemAlert.alert_type == alert_type,
                SystemAlert.created_at >= cutoff,
            )
            .first()
        )
        if existing:
            already_notified += 1
            continue

        # Resolve supplier name
        supplier_name = "Unknown supplier"
        try:
            sup = db.get(Supplier, inv.supplier_id)
            if sup:
                supplier_name = sup.name
        except Exception:
            pass

        days_diff = (due - today).days

        if is_overdue:
            title = f"OVERDUE: Invoice #{inv.invoice_number}"
            message = (
                f"Invoice #{inv.invoice_number} from {supplier_name} "
                f"was due on {due.strftime('%d %b %Y')} "
                f"({abs(days_diff)} day{'s' if abs(days_diff) != 1 else ''} overdue).\n"
                f"Amount: R {inv.total_amount:,.2f}\n"
                f"Please arrange payment urgently."
            )
            severity = AlertSeverity.HIGH
        else:
            title = f"Payment Due Soon: {supplier_name}"
            message = (
                f"Invoice #{inv.invoice_number} from {supplier_name} "
                f"is due on {due.strftime('%d %b %Y')} "
                f"({days_diff} day{'s' if days_diff != 1 else ''} remaining).\n"
                f"Amount: R {inv.total_amount:,.2f}\n"
                f"Please arrange payment before the due date."
            )
            severity = AlertSeverity.MEDIUM

        try:
            alert = SystemAlert(
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                project_id=inv.project_id,
                entity_type="invoice",
                entity_id=inv.id,
            )
            db.add(alert)
            db.flush()
            enqueue_for_alert(db, alert)
            db.commit()

            if is_overdue:
                overdue_queued += 1
            else:
                warnings_queued += 1

        except Exception as e:
            log.error("Failed to create payment-due alert for invoice %s: %s", inv.id, e)
            db.rollback()
            errors += 1

    return {
        "warnings_queued":  warnings_queued,
        "overdue_queued":   overdue_queued,
        "already_notified": already_notified,
        "errors":           errors,
        "scanned":          len(invoices),
    }
