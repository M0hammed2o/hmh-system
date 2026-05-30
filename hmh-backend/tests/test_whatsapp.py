"""
WhatsApp webhook + notification queue tests — Phase B production hardening.

Covers:
  - HMAC signature verification (valid / invalid / missing)
  - GET webhook token verification
  - Queue drain: PENDING → SENT / MOCK_SENT / FAILED
  - Delivery status callbacks: read → ACKNOWLEDGED, failed → FAILED
  - MR approval via WhatsApp message
  - ACK command acknowledges pending queue entries
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import make_user, make_project, make_site


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _wa_text_payload(from_number: str, body: str, message_id: str = None) -> dict:
    """Build a minimal Meta webhook POST payload for a text message."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "type": "text",
                        "from": from_number.lstrip("+"),
                        "id": message_id or f"wamid.{uuid.uuid4().hex}",
                        "timestamp": "1700000000",
                        "text": {"body": body},
                    }]
                }
            }]
        }]
    }


def _wa_status_payload(message_id: str, status: str, recipient: str = "27821234567",
                        errors: list = None) -> dict:
    """Build a minimal Meta delivery-status webhook payload."""
    entry = {
        "id": message_id,          # Meta API field name is "id", not "message_id"
        "status": status,
        "recipient_id": recipient,
        "timestamp": "1700000000",
    }
    if errors:
        entry["errors"] = errors
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [entry]
                }
            }]
        }]
    }


def _make_recipient(db, phone: str = "+27821234567"):
    """Insert a minimal AlertRecipient row."""
    from app.models.alert_recipient import AlertRecipient
    r = AlertRecipient(
        name="Test Recipient",
        phone_number=phone,
        is_active=True,
        receives_critical_alerts=True,
        receives_daily_summary=False,
        receives_invoice_alerts=False,
        receives_delivery_alerts=False,
        receives_vehicle_alerts=False,
        receives_material_alerts=False,
        receives_procurement_alerts=True,
        receives_milestone_alerts=False,
        receives_payment_alerts=False,
    )
    db.add(r)
    db.flush()
    return r


def _make_alert(db, project_id=None):
    """Insert a minimal SystemAlert row."""
    from app.models.alert import SystemAlert
    from app.models.enums import AlertType, AlertStatus, AlertSeverity
    a = SystemAlert(
        alert_type=AlertType.LOW_STOCK,
        severity=AlertSeverity.HIGH,
        status=AlertStatus.OPEN,
        title="Low Stock Alert",
        message="Item X is running low",
        project_id=uuid.UUID(project_id) if project_id else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _make_queue_entry(db, recipient, alert, phone: str = "+27821234567",
                      status: str = "PENDING", next_attempt_offset_secs: int = -60,
                      requires_acknowledgement: bool = False):
    """Insert a NotificationQueue row ready to be processed."""
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationStatus, NotificationChannel
    entry = NotificationQueue(
        alert_id=alert.id,
        recipient_id=recipient.id,
        channel=NotificationChannel.WHATSAPP,
        phone_number=phone,
        message_body="Test alert: Low Stock Alert",
        status=NotificationStatus(status),
        attempt_count=0,
        next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=next_attempt_offset_secs),
        requires_acknowledgement=requires_acknowledgement,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def _login(client, db, role: str = "OFFICE_MANAGER"):
    user = make_user(db, role=role)
    resp = client.post("/api/v1/auth/login", json={"email": user["email"], "password": user["password"]})
    return resp.json()["data"]["access_token"]


# ── 1. HMAC signature verification ───────────────────────────────────────────

class TestHmacVerification:

    def test_valid_signature_passes(self, client):
        """POST /whatsapp/webhook with correct HMAC signature is accepted."""
        secret = "test_app_secret_12345"
        body = json.dumps(_wa_text_payload("27821234567", "ok")).encode()
        sig = _build_signature(body, secret)

        with patch("app.api.v1.whatsapp_webhook.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = secret
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
            )
        # 200 means signature passed and payload was processed
        assert resp.status_code == 200

    def test_invalid_signature_rejected(self, client):
        """POST /whatsapp/webhook with wrong HMAC returns 403."""
        secret = "real_secret"
        body = json.dumps(_wa_text_payload("27821234567", "ok")).encode()
        wrong_sig = _build_signature(body, "wrong_secret")

        with patch("app.api.v1.whatsapp_webhook.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = secret
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": wrong_sig},
            )
        assert resp.status_code == 403

    def test_missing_signature_rejected_when_secret_configured(self, client):
        """No X-Hub-Signature-256 header → 403 when APP_SECRET is set."""
        body = json.dumps(_wa_text_payload("27821234567", "ok")).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = "configured_secret"
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 403

    def test_no_secret_configured_passes_without_header(self, client):
        """When WHATSAPP_APP_SECRET is empty (dev mode), any POST is accepted."""
        body = json.dumps(_wa_text_payload("27821234567", "ok")).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        # Passes signature check; may still return 200 even if processing fails
        assert resp.status_code != 403


# ── 2. GET webhook verification ───────────────────────────────────────────────

class TestGetVerification:

    def test_valid_token_returns_challenge(self, client):
        """GET with correct token returns the challenge string."""
        with patch("app.services.whatsapp_service.settings") as ms:
            ms.WHATSAPP_VERIFY_TOKEN = "my_test_token"
            resp = client.get(
                "/api/v1/whatsapp/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "my_test_token",
                    "hub.challenge": "challenge_abc123",
                },
            )
        assert resp.status_code == 200
        assert resp.text == "challenge_abc123"

    def test_wrong_token_returns_403(self, client):
        """GET with wrong token returns 403."""
        with patch("app.services.whatsapp_service.settings") as ms:
            ms.WHATSAPP_VERIFY_TOKEN = "real_token"
            resp = client.get(
                "/api/v1/whatsapp/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong_token",
                    "hub.challenge": "ignored",
                },
            )
        assert resp.status_code == 403


# ── 3. Queue processing ───────────────────────────────────────────────────────

class TestQueueProcessing:

    def test_pending_entry_sent_via_mock(self, client, db):
        """PENDING queue entry within next_attempt window is processed and becomes MOCK_SENT."""
        from app.models.enums import NotificationStatus
        recipient = _make_recipient(db)
        # Open the 24-hour conversation window so free-text send path is taken.
        recipient.last_inbound_at = datetime.now(timezone.utc)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert)
        db.commit()

        # Patch BOTH send paths so no real HTTP calls happen regardless of whether
        # the notification service uses send_text (24h window) or send_template_message
        # (when WHATSAPP_ALERT_TEMPLATE_NAME is configured in .env).
        with patch("app.services.notification_service.whatsapp_service.send_text",
                   return_value=("MOCK_SENT", None)), \
             patch("app.services.notification_service.whatsapp_service.send_template_message",
                   return_value=("MOCK_SENT", None)):
            from app.services.notification_service import process_queue
            result = process_queue(db)

        db.refresh(entry)
        assert result.get("mock_sent", 0) >= 1
        assert entry.status == NotificationStatus.MOCK_SENT

    def test_future_entry_not_processed(self, client, db):
        """Queue entry with next_attempt_at in the future is NOT processed."""
        from app.models.enums import NotificationStatus
        recipient = _make_recipient(db)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert, next_attempt_offset_secs=3600)
        db.commit()

        from app.services.notification_service import process_queue
        process_queue(db)

        db.refresh(entry)
        assert entry.status == NotificationStatus.PENDING

    def test_failed_send_sets_status_failed(self, client, db):
        """When whatsapp_service returns FAILED, queue entry becomes FAILED."""
        from app.models.enums import NotificationStatus
        recipient = _make_recipient(db)
        recipient.last_inbound_at = datetime.now(timezone.utc)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert)
        db.commit()

        # Patch BOTH send paths: template is used when WHATSAPP_ALERT_TEMPLATE_NAME
        # is configured in .env, so both must return FAILED for the assertion to hold.
        with patch("app.services.notification_service.whatsapp_service.send_text",
                   return_value=("FAILED", "network error")), \
             patch("app.services.notification_service.whatsapp_service.send_template_message",
                   return_value=("FAILED", "network error")):
            from app.services.notification_service import process_queue
            result = process_queue(db)

        db.refresh(entry)
        assert entry.status == NotificationStatus.FAILED
        assert result.get("failed", 0) >= 1


# ── 4. Delivery status callbacks ─────────────────────────────────────────────

class TestDeliveryStatus:

    def test_read_status_marks_read(self, client, db):
        """Delivery status 'read' from Meta marks the queue entry as READ with acknowledged_at set."""
        from app.models.notification_queue import NotificationQueue
        from app.models.enums import NotificationStatus

        msg_id = f"wamid.{uuid.uuid4().hex}"
        recipient = _make_recipient(db)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert, status="SENT")
        entry.provider_message_id = msg_id
        db.commit()

        payload = _wa_status_payload(msg_id, "read")
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms:
            ms.WHATSAPP_APP_SECRET = ""  # skip HMAC in test
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        db.refresh(entry)
        assert entry.status == NotificationStatus.READ
        assert entry.acknowledged_at is not None

    def test_failed_status_marks_failed(self, client, db):
        """Delivery status 'failed' from Meta marks the queue entry as FAILED."""
        from app.models.enums import NotificationStatus

        msg_id = f"wamid.{uuid.uuid4().hex}"
        recipient = _make_recipient(db)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert, status="SENT")
        entry.provider_message_id = msg_id
        db.commit()

        payload = _wa_status_payload(msg_id, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}])
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms:
            ms.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        db.refresh(entry)
        assert entry.status == NotificationStatus.FAILED
        assert "131026" in (entry.error_message or "")

    def test_status_unknown_message_id_is_noop(self, client, db):
        """Status for an unknown message_id doesn't crash — silently ignored."""
        payload = _wa_status_payload("wamid.nonexistent", "read")
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms:
            ms.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 200


# ── 5. Inbound command handling ───────────────────────────────────────────────

class TestInboundCommands:

    def test_ack_command_marks_queue_acknowledged(self, client, db):
        """Sending 'ok' via WhatsApp acknowledges pending queue entries for that phone."""
        from app.models.enums import NotificationStatus

        phone = "+27831111111"
        recipient = _make_recipient(db, phone=phone)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert, phone=phone, requires_acknowledgement=True)
        db.commit()

        payload = _wa_text_payload(phone.lstrip("+"), "ok")
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms, \
             patch("app.api.v1.whatsapp_webhook._reply"):
            ms.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        db.refresh(entry)
        assert entry.status == NotificationStatus.ACKNOWLEDGED

    def test_mr_approve_via_whatsapp(self, client, db):
        """Sending 'approve MR-XXXX' via WhatsApp approves the material request."""
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus, UserRole, MRPriority, DeliveryDestination
        from app.models.user import User
        from app.core.security import hash_password

        now = datetime.now(timezone.utc)
        owner = User(
            full_name="Owner",
            email=f"owner_{uuid.uuid4().hex[:6]}@test.com",
            password_hash=hash_password("Test@1234"),
            role=UserRole.OWNER,
            is_active=True,
            must_reset_password=False,
            created_at=now, updated_at=now,
        )
        db.add(owner)
        db.flush()

        project = make_project(db, str(owner.id))
        site = make_site(db, project["id"])

        mr = MaterialRequest(
            project_id=uuid.UUID(project["id"]),
            site_id=uuid.UUID(site["id"]),
            request_number="MR-TEST001",
            requested_by=owner.id,
            status=RecordStatus.SUBMITTED,
            requested_date=now,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            created_at=now, updated_at=now,
        )
        db.add(mr)
        db.flush()
        db.commit()

        phone = "+27841111111"
        payload = _wa_text_payload(phone.lstrip("+"), "approve MR-TEST001")
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms, \
             patch("app.api.v1.whatsapp_webhook._reply"):
            ms.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        data = resp.json().get("data", {})
        approved = data.get("approved", [])
        assert any(a.get("mr_number") == "MR-TEST001" for a in approved)

        db.refresh(mr)
        assert mr.status == RecordStatus.APPROVED

    def test_unknown_command_does_not_crash(self, client, db):
        """Unrecognised message returns 200 and sends the help text reply."""
        phone = "+27851111111"
        payload = _wa_text_payload(phone.lstrip("+"), "what is the weather today")
        body = json.dumps(payload).encode()

        with patch("app.api.v1.whatsapp_webhook.settings") as ms, \
             patch("app.api.v1.whatsapp_webhook._reply") as mock_reply:
            ms.WHATSAPP_APP_SECRET = ""
            resp = client.post(
                "/api/v1/whatsapp/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        # _reply should have been called with the help text
        mock_reply.assert_called_once()
        call_args = mock_reply.call_args[0]
        assert "APPROVE" in call_args[1] or "ACK" in call_args[1]


# ── 6. Internal cron endpoint ─────────────────────────────────────────────────

class TestCronEndpoint:

    def test_correct_secret_processes_queue(self, client, db):
        """POST /api/v1/internal/process-notifications with correct secret returns 200."""
        with patch("main.settings") as ms:
            ms.CRON_SECRET = "test_cron_secret_xyz"
            resp = client.post(
                "/api/v1/internal/process-notifications",
                headers={"X-Cron-Secret": "test_cron_secret_xyz"},
            )
        assert resp.status_code == 200

    def test_wrong_secret_returns_403(self, client):
        """POST /internal/process-notifications with wrong secret returns 403."""
        with patch("main.settings") as ms:
            ms.CRON_SECRET = "real_secret"
            resp = client.post(
                "/api/v1/internal/process-notifications",
                headers={"X-Cron-Secret": "wrong_secret"},
            )
        assert resp.status_code == 403

    def test_no_cron_secret_configured_returns_404(self, client):
        """When CRON_SECRET is not set, endpoint is hidden (404, not 403)."""
        with patch("main.settings") as ms:
            ms.CRON_SECRET = ""
            resp = client.post("/api/v1/internal/process-notifications")
        assert resp.status_code == 404


# ── 7. Cost optimization ──────────────────────────────────────────────────────

class TestCostOptimization:

    def _make_material_recipient(self, db, phone: str = "+27829001001"):
        """Recipient that receives material alerts (for MEDIUM/LOW severity tests)."""
        from app.models.alert_recipient import AlertRecipient
        r = AlertRecipient(
            name="Material Recipient",
            phone_number=phone,
            is_active=True,
            receives_critical_alerts=False,
            receives_material_alerts=True,
            receives_daily_summary=False,
            receives_invoice_alerts=False,
            receives_delivery_alerts=False,
            receives_vehicle_alerts=False,
            receives_procurement_alerts=False,
            receives_milestone_alerts=False,
            receives_payment_alerts=False,
        )
        db.add(r)
        db.flush()
        return r

    def _make_medium_alert(self, db):
        """LOW_STOCK alert with MEDIUM severity."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertStatus, AlertSeverity
        a = SystemAlert(
            alert_type=AlertType.LOW_STOCK,
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.OPEN,
            title="Medium Stock Alert",
            message="Item Y is running slightly low",
            created_at=datetime.now(timezone.utc),
        )
        db.add(a)
        db.flush()
        return a

    # ── Config: template name split ───────────────────────────────────────────

    def test_template_name_split_in_config(self):
        """model_validator splits comma-separated WHATSAPP_ALERT_TEMPLATE_NAME correctly."""
        from app.core.config import Settings
        s = Settings(
            _env_file=None,
            SECRET_KEY="test_secret_key_minimum_32_chars_long____",
            WHATSAPP_ALERT_TEMPLATE_NAME="hmh_daily_summary, hmh_alert_notification",
            WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME="",
        )
        assert s.WHATSAPP_ALERT_TEMPLATE_NAME == "hmh_alert_notification"
        assert s.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME == "hmh_daily_summary"

    def test_existing_daily_summary_field_not_overwritten(self):
        """If WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME is already set, the split doesn't overwrite it."""
        from app.core.config import Settings
        s = Settings(
            _env_file=None,
            SECRET_KEY="test_secret_key_minimum_32_chars_long____",
            WHATSAPP_ALERT_TEMPLATE_NAME="old_daily, hmh_alert_notification",
            WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME="my_custom_daily",
        )
        assert s.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME == "my_custom_daily"
        assert s.WHATSAPP_ALERT_TEMPLATE_NAME == "hmh_alert_notification"

    # ── Template selection ────────────────────────────────────────────────────

    def test_alert_template_used_for_normal_alerts(self, client, db):
        """_send_for_queue_entry selects ALERT template for a normal alert."""
        recipient = _make_recipient(db)
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert)
        db.commit()

        captured = {}

        def mock_send_tpl(phone, template_name, lang, components=None):
            captured["template_name"] = template_name
            return ("MOCK_SENT", None)

        with patch("app.services.notification_service.settings") as ms, \
             patch("app.services.notification_service.whatsapp_service.send_template_message",
                   side_effect=mock_send_tpl):
            ms.WHATSAPP_ALERT_TEMPLATE_NAME = "hmh_alert_notification"
            ms.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME = "hmh_daily_summary"
            ms.WHATSAPP_ALERT_TEMPLATE_LANGUAGE = "en_US"
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = False

            from app.services.notification_service import _send_for_queue_entry
            _send_for_queue_entry(entry, db)

        assert captured.get("template_name") == "hmh_alert_notification"

    def test_daily_summary_template_used_for_summary_alerts(self, client, db):
        """_send_for_queue_entry selects DAILY_SUMMARY template for DAILY_SUMMARY alert type."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertStatus, AlertSeverity
        recipient = _make_recipient(db)
        summary_alert = SystemAlert(
            alert_type=AlertType.DAILY_SUMMARY,
            severity=AlertSeverity.LOW,
            status=AlertStatus.OPEN,
            title="Daily Summary",
            message="Today's summary",
            created_at=datetime.now(timezone.utc),
        )
        db.add(summary_alert)
        db.flush()
        entry = _make_queue_entry(db, recipient, summary_alert)
        db.commit()

        captured = {}

        def mock_send_tpl(phone, template_name, lang, components=None):
            captured["template_name"] = template_name
            return ("MOCK_SENT", None)

        with patch("app.services.notification_service.settings") as ms, \
             patch("app.services.notification_service.whatsapp_service.send_template_message",
                   side_effect=mock_send_tpl):
            ms.WHATSAPP_ALERT_TEMPLATE_NAME = "hmh_alert_notification"
            ms.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME = "hmh_daily_summary"
            ms.WHATSAPP_ALERT_TEMPLATE_LANGUAGE = "en_US"
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = False

            from app.services.notification_service import _send_for_queue_entry
            _send_for_queue_entry(entry, db)

        assert captured.get("template_name") == "hmh_daily_summary"

    def test_missing_template_and_closed_window_returns_failed(self, client, db):
        """No template + 24h window closed → FAILED (no crash, clear log)."""
        recipient = _make_recipient(db)
        recipient.last_inbound_at = None  # window closed
        alert = _make_alert(db)
        entry = _make_queue_entry(db, recipient, alert)
        db.commit()

        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_ALERT_TEMPLATE_NAME = ""
            ms.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME = ""
            ms.WHATSAPP_ALERT_TEMPLATE_LANGUAGE = "en_US"
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = False

            from app.services.notification_service import _send_for_queue_entry
            status, msg = _send_for_queue_entry(entry, db)

        assert status == "FAILED"
        assert "template" in msg.lower()

    # ── Throttling ────────────────────────────────────────────────────────────

    def test_critical_alert_queued_immediately(self, client, db):
        """CRITICAL severity alerts are queued with next_attempt_at = now (no delay)."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertStatus, AlertSeverity
        recipient = _make_recipient(db)
        crit_alert = SystemAlert(
            alert_type=AlertType.LOW_STOCK,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.OPEN,
            title="Critical Alert",
            message="Critical issue",
            created_at=datetime.now(timezone.utc),
        )
        db.add(crit_alert)
        db.flush()
        db.commit()

        now = datetime.now(timezone.utc)

        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = True
            ms.WHATSAPP_SUMMARY_INTERVAL_MINUTES = 60
            ms.WHATSAPP_QUIET_HOURS_ENABLED = False
            ms.CRITICAL_ALERT_MAX_ATTEMPTS = 5
            ms.HIGH_ALERT_MAX_ATTEMPTS = 2

            from app.services.notification_service import enqueue_for_alert
            queued = enqueue_for_alert(db, crit_alert)
        db.commit()

        assert len(queued) >= 1
        for entry in queued:
            db.refresh(entry)
            assert entry.next_attempt_at <= now + timedelta(seconds=5)

    def test_medium_alert_queued_with_delay(self, client, db):
        """MEDIUM severity alert gets delayed by SUMMARY_INTERVAL_MINUTES."""
        recipient = self._make_material_recipient(db)
        alert = self._make_medium_alert(db)
        db.commit()

        now = datetime.now(timezone.utc)

        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = True
            ms.WHATSAPP_SUMMARY_INTERVAL_MINUTES = 60
            ms.WHATSAPP_QUIET_HOURS_ENABLED = False
            ms.CRITICAL_ALERT_MAX_ATTEMPTS = 5
            ms.HIGH_ALERT_MAX_ATTEMPTS = 2

            from app.services.notification_service import enqueue_for_alert
            queued = enqueue_for_alert(db, alert)
        db.commit()

        assert len(queued) >= 1
        for entry in queued:
            db.refresh(entry)
            assert entry.next_attempt_at >= now + timedelta(minutes=55)

    # ── Hourly cap ────────────────────────────────────────────────────────────

    def test_hourly_cap_skips_entry(self, client, db):
        """process_queue skips a PENDING entry when the recipient hit the hourly cap."""
        from app.models.enums import NotificationStatus
        from app.models.notification_queue import NotificationQueue
        from app.models.enums import NotificationChannel

        recipient = _make_recipient(db)
        alert = _make_alert(db)

        # Simulate 2 already-sent entries within the last hour (to hit a cap of 2)
        now = datetime.now(timezone.utc)
        for _ in range(2):
            sent = NotificationQueue(
                alert_id=alert.id,
                recipient_id=recipient.id,
                channel=NotificationChannel.WHATSAPP,
                phone_number=recipient.phone_number,
                message_body="prior send",
                status=NotificationStatus.SENT,
                attempt_count=1,
                last_attempt_at=now - timedelta(minutes=30),
                next_attempt_at=now - timedelta(minutes=30),
                requires_acknowledgement=False,
                created_at=now - timedelta(minutes=30),
            )
            db.add(sent)
        db.flush()

        # New PENDING entry to process
        pending = _make_queue_entry(db, recipient, alert)
        db.commit()

        with patch("app.services.notification_service.settings") as ms, \
             patch("app.services.notification_service.whatsapp_service.send_text",
                   return_value=("MOCK_SENT", None)), \
             patch("app.services.notification_service.whatsapp_service.send_template_message",
                   return_value=("MOCK_SENT", None)):
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = True
            ms.WHATSAPP_MAX_ALERTS_PER_HOUR_PER_RECIPIENT = 2  # cap = 2, already at 2
            ms.WHATSAPP_ALERT_TEMPLATE_NAME = ""
            ms.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME = ""

            from app.services.notification_service import process_queue
            result = process_queue(db)

        db.refresh(pending)
        assert result.get("skipped", 0) >= 1
        assert pending.status == NotificationStatus.PENDING

    # ── Quiet hours ───────────────────────────────────────────────────────────

    def test_quiet_hours_delay_in_quiet_period(self):
        """_quiet_hours_delay returns non-None when current time is in quiet hours."""
        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_QUIET_HOURS_ENABLED = True
            ms.WHATSAPP_QUIET_HOURS_START = "20:00"
            ms.WHATSAPP_QUIET_HOURS_END = "07:00"

            from app.services.notification_service import _quiet_hours_delay
            # 21:00 UTC is within 20:00–07:00 quiet hours
            test_time = datetime(2026, 5, 26, 21, 0, 0, tzinfo=timezone.utc)
            delay = _quiet_hours_delay(test_time)

        assert delay is not None
        # 07:00 next day is 10 hours away
        assert timedelta(hours=9) < delay < timedelta(hours=11)

    def test_quiet_hours_no_delay_outside_period(self):
        """_quiet_hours_delay returns None when outside quiet hours."""
        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_QUIET_HOURS_ENABLED = True
            ms.WHATSAPP_QUIET_HOURS_START = "20:00"
            ms.WHATSAPP_QUIET_HOURS_END = "07:00"

            from app.services.notification_service import _quiet_hours_delay
            # 10:00 UTC is outside 20:00–07:00
            test_time = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
            delay = _quiet_hours_delay(test_time)

        assert delay is None

    def test_quiet_hours_disabled_returns_none(self):
        """_quiet_hours_delay returns None when quiet hours are disabled."""
        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_QUIET_HOURS_ENABLED = False

            from app.services.notification_service import _quiet_hours_delay
            delay = _quiet_hours_delay(datetime(2026, 5, 26, 22, 0, 0, tzinfo=timezone.utc))

        assert delay is None

    # ── Deduplication ─────────────────────────────────────────────────────────

    def test_dedup_same_alert_same_recipient(self, client, db):
        """Second enqueue_for_alert call for the same alert produces no duplicate entries."""
        from app.models.notification_queue import NotificationQueue

        recipient = _make_recipient(db)
        alert = _make_alert(db)
        db.commit()

        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = False
            ms.WHATSAPP_QUIET_HOURS_ENABLED = False
            ms.CRITICAL_ALERT_MAX_ATTEMPTS = 5
            ms.HIGH_ALERT_MAX_ATTEMPTS = 2

            from app.services.notification_service import enqueue_for_alert
            first = enqueue_for_alert(db, alert)
            db.commit()

            count_after_first = db.query(NotificationQueue).filter(
                NotificationQueue.alert_id == alert.id,
            ).count()

            second = enqueue_for_alert(db, alert)
            db.commit()

            count_after_second = db.query(NotificationQueue).filter(
                NotificationQueue.alert_id == alert.id,
            ).count()

        assert len(first) >= 1
        assert len(second) == 0
        assert count_after_second == count_after_first

    def test_no_dedup_different_alerts(self, client, db):
        """Two different alerts for the same recipient both create queue entries."""
        from app.models.notification_queue import NotificationQueue

        recipient = _make_recipient(db)
        alert1 = _make_alert(db)
        alert2 = _make_alert(db)
        db.commit()

        with patch("app.services.notification_service.settings") as ms:
            ms.WHATSAPP_COST_OPTIMIZATION_ENABLED = False
            ms.WHATSAPP_QUIET_HOURS_ENABLED = False
            ms.CRITICAL_ALERT_MAX_ATTEMPTS = 5
            ms.HIGH_ALERT_MAX_ATTEMPTS = 2

            from app.services.notification_service import enqueue_for_alert
            q1 = enqueue_for_alert(db, alert1)
            q2 = enqueue_for_alert(db, alert2)
            db.commit()

        assert len(q1) >= 1
        assert len(q2) >= 1
