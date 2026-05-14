"""
Seed fake test alerts for WhatsApp ACK flow testing.

Usage:
    python scripts/seed_test_alerts.py [--force]

Options:
    --force    Re-create alerts even if unacknowledged ones already exist.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.alert import SystemAlert
from app.models.alert_recipient import AlertRecipient
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    NotificationChannel,
    NotificationStatus,
)
from app.models.notification_queue import NotificationQueue
from app.services import whatsapp_service

PHONE = "27837866021"
NAME  = "Mohammed Moosa"
LABEL = "Owner"

TEST_ALERTS = [
    dict(
        title      = "BOQ Overrun Alert",
        message    = "CRITICAL: Lot 12 has requested 20 bags of cement but BOQ allocation is 10 bags. Please review.",
        alert_type = AlertType.BOQ_ALLOCATION_EXCEEDED,
        severity   = AlertSeverity.CRITICAL,
    ),
    dict(
        title      = "Delivery Mismatch Alert",
        message    = "HIGH: Delivery note DN-004 does not match invoice INV-004. Cement quantity differs.",
        alert_type = AlertType.DELIVERY_MISMATCH,
        severity   = AlertSeverity.HIGH,
    ),
    dict(
        title      = "Stage Delay Alert",
        message    = "MEDIUM: Lot 8 foundation stage is 2 days behind schedule.",
        alert_type = AlertType.STAGE_DELAYED,
        severity   = AlertSeverity.MEDIUM,
    ),
]


def _find_duplicate_titles(db, force: bool) -> set[str]:
    if force:
        return set()
    dupes: set[str] = set()
    for spec in TEST_ALERTS:
        exists = (
            db.query(NotificationQueue)
            .join(SystemAlert, NotificationQueue.alert_id == SystemAlert.id)
            .filter(
                SystemAlert.title == spec["title"],
                NotificationQueue.phone_number == PHONE,
                NotificationQueue.acknowledged_at.is_(None),
                NotificationQueue.status != NotificationStatus.ACKNOWLEDGED,
            )
            .first()
        )
        if exists:
            dupes.add(spec["title"])
    return dupes


def main(force: bool) -> None:
    db = SessionLocal()
    try:
        # ── Recipient ──────────────────────────────────────────────────────────
        recipient = (
            db.query(AlertRecipient)
            .filter(AlertRecipient.phone_number == PHONE)
            .first()
        )
        if not recipient:
            recipient = AlertRecipient(
                name                     = NAME,
                phone_number             = PHONE,
                label                    = LABEL,
                receives_critical_alerts = True,
                receives_delivery_alerts = True,
                receives_material_alerts = True,
                is_active                = True,
            )
            db.add(recipient)
            db.flush()
            print(f"Created recipient  : {recipient.id}  ({NAME} / {PHONE})", flush=True)
        else:
            print(f"Found recipient    : {recipient.id}  ({recipient.name} / {recipient.phone_number})", flush=True)

        # ── Duplicate guard ────────────────────────────────────────────────────
        skip_titles = _find_duplicate_titles(db, force)
        if skip_titles:
            print(
                f"\nSkipping {len(skip_titles)} already-unacknowledged alert(s): "
                + ", ".join(f'"{t}"' for t in skip_titles)
                + "\nPass --force to re-create them.",
                flush=True,
            )

        # ── Create alerts + queue entries ──────────────────────────────────────
        created: list[dict] = []

        for spec in TEST_ALERTS:
            if spec["title"] in skip_titles:
                continue

            now = datetime.now(timezone.utc)

            alert = SystemAlert(
                alert_type           = spec["alert_type"],
                severity             = spec["severity"],
                title                = spec["title"],
                message              = spec["message"],
                status               = AlertStatus.OPEN,
                notification_channel = "whatsapp",
                sent_at              = now,
                created_at           = now,
            )
            db.add(alert)
            db.flush()

            queue_entry = NotificationQueue(
                alert_id                 = alert.id,
                recipient_id             = recipient.id,
                channel                  = NotificationChannel.WHATSAPP,
                phone_number             = PHONE,
                message_body             = spec["message"],
                status                   = NotificationStatus.SENT,
                requires_acknowledgement = True,
                acknowledged_at          = None,
                attempt_count            = 1,
                last_attempt_at          = now,
                created_at               = now,
            )

            # Send or mock-send
            if settings.WHATSAPP_ENABLED:
                try:
                    send_status, provider_id = whatsapp_service.send_text_message(PHONE, spec["message"])
                    if provider_id:
                        queue_entry.provider_message_id = provider_id
                except Exception as exc:
                    send_status = f"ERROR: {exc}"
            else:
                send_status = "MOCK_SENT (WHATSAPP_ENABLED=false)"

            db.add(queue_entry)
            db.flush()

            created.append({
                "title"      : spec["title"],
                "alert_id"   : str(alert.id),
                "queue_id"   : str(queue_entry.id),
                "send_status": send_status,
            })

        db.commit()

        # ── Print results ──────────────────────────────────────────────────────
        print("\n--- Seeded Test Alerts ---", flush=True)
        if not created:
            print("  No new alerts created (all duplicates were skipped).", flush=True)
        else:
            for item in created:
                print(f"  Title       : {item['title']}", flush=True)
                print(f"  Alert ID    : {item['alert_id']}", flush=True)
                print(f"  Queue ID    : {item['queue_id']}", flush=True)
                print(f"  Send status : {item['send_status']}", flush=True)
                print("", flush=True)

        print("--- Instructions ---", flush=True)
        print("  Now reply ACK on WhatsApp to acknowledge these alerts.", flush=True)
        print("---\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed fake test alerts for WhatsApp ACK flow testing."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-create alerts even if unacknowledged duplicates exist.",
    )
    args = parser.parse_args()
    main(args.force)
