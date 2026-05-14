"""
Tests for Material Request approval email workflow.

Covers:
- Approval auto-sends email to preferred supplier (mock mode → MOCK_SENT)
- No email sent when no preferred supplier
- Duplicate email not sent on second approval (idempotent)
- Resend endpoint creates new log entry
- Failed email (no supplier email) creates SystemAlert
- Email log endpoint returns history
- email_log field present in MR read response
"""

import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mr_setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    tok     = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


def _create_and_submit_mr(client, tok, project_id, site_id, supplier_id=None):
    body = {
        "site_id": site_id,
        "notes": "Test request",
        "items": [{"description": "Cement 50kg bags", "quantity_requested": 20.0, "unit": "bags"}],
    }
    if supplier_id:
        body["preferred_supplier_id"] = supplier_id

    r = client.post(f"/api/v1/projects/{project_id}/material-requests/", json=body,
                    headers=auth(tok))
    assert r.status_code == 201, r.text
    mr_id = r.json()["data"]["id"]

    r2 = client.post(f"/api/v1/material-requests/{mr_id}/submit", headers=auth(tok))
    assert r2.status_code in (200, 201), r2.text
    return mr_id


def _approve_mr(client, tok, mr_id):
    r = client.post(f"/api/v1/material-requests/{mr_id}/approve", json={}, headers=auth(tok))
    return r


# ── Email auto-send on approval ───────────────────────────────────────────────

class TestMRApprovalEmail:
    def test_approval_with_supplier_creates_email_log(self, client, db, mr_setup):
        from app.models.mr_email_log import MREmailLog
        s   = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])

        before = db.query(MREmailLog).count()
        r = _approve_mr(client, s["tok"], mr_id)
        assert r.status_code in (200, 201), r.text

        after = db.query(MREmailLog).count()
        assert after > before, "Expected MREmailLog to be created on approval"

        log = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).first()
        assert log is not None
        assert log.status in ("SENT", "MOCK_SENT")

    def test_approval_mock_mode_creates_mock_sent_log(self, client, db, mr_setup):
        """SMTP_ENABLED=false → MOCK_SENT log."""
        from app.models.mr_email_log import MREmailLog
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        _approve_mr(client, s["tok"], mr_id)

        log = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).first()
        assert log is not None
        assert log.status == "MOCK_SENT"   # settings.SMTP_ENABLED is False in tests

    def test_approval_without_supplier_does_not_crash(self, client, db, mr_setup):
        """No preferred supplier → approval succeeds, email log shows FAILED."""
        from app.models.mr_email_log import MREmailLog
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], supplier_id=None)
        r = _approve_mr(client, s["tok"], mr_id)
        assert r.status_code in (200, 201), r.text
        # No email sent → no log (or a FAILED log)
        log = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).first()
        # Either no log or a FAILED log — both are acceptable
        if log:
            assert log.status == "FAILED"

    def test_no_duplicate_email_on_second_approval(self, client, db, mr_setup):
        """Second approve (if allowed) does NOT create a second email log."""
        from app.models.mr_email_log import MREmailLog
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])

        _approve_mr(client, s["tok"], mr_id)
        count_after_first = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).count()

        # Second approval attempt (may fail with validation error — that's fine)
        _approve_mr(client, s["tok"], mr_id)
        count_after_second = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).count()

        assert count_after_second == count_after_first, (
            "Second approval must not create a duplicate email log"
        )

    def test_failed_email_missing_address_creates_alert(self, client, db, mr_setup):
        """Supplier with no email → FAILED log and SystemAlert created."""
        from app.models.mr_email_log import MREmailLog
        from app.models.alert import SystemAlert
        from app.models.supplier import Supplier

        s = mr_setup
        # Clear supplier email
        sup = db.get(Supplier, uuid.UUID(s["supplier_id"]))
        sup.email = None
        db.flush()

        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        before_alerts = db.query(SystemAlert).count()

        _approve_mr(client, s["tok"], mr_id)

        log = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).first()
        assert log is not None
        assert log.status == "FAILED"

        after_alerts = db.query(SystemAlert).count()
        assert after_alerts > before_alerts, "Expected a SystemAlert on email failure"


# ── Resend endpoint ───────────────────────────────────────────────────────────

class TestMREmailResend:
    def test_resend_creates_new_log_entry(self, client, db, mr_setup):
        """Resend always creates a fresh log entry regardless of prior sends."""
        from app.models.mr_email_log import MREmailLog
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        _approve_mr(client, s["tok"], mr_id)

        before = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).count()

        r = client.post(f"/api/v1/material-requests/{mr_id}/send-email", headers=auth(s["tok"]))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] in ("SENT", "MOCK_SENT", "FAILED")

        after = db.query(MREmailLog).filter(
            MREmailLog.material_request_id == uuid.UUID(mr_id)
        ).count()
        assert after > before, "Resend must create a new log entry"

    def test_resend_fails_if_not_approved(self, client, db, mr_setup):
        """Only APPROVED requests can have email resent."""
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        # MR is SUBMITTED, not APPROVED
        r = client.post(f"/api/v1/material-requests/{mr_id}/send-email", headers=auth(s["tok"]))
        assert r.status_code in (400, 422), r.text

    def test_resend_returns_status(self, client, db, mr_setup):
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        _approve_mr(client, s["tok"], mr_id)

        r = client.post(f"/api/v1/material-requests/{mr_id}/send-email", headers=auth(s["tok"]))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "status" in data
        assert "sent_to_email" in data


# ── Email log history ─────────────────────────────────────────────────────────

class TestMREmailLog:
    def test_email_log_endpoint_returns_history(self, client, db, mr_setup):
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        _approve_mr(client, s["tok"], mr_id)

        r = client.get(f"/api/v1/material-requests/{mr_id}/email-log", headers=auth(s["tok"]))
        assert r.status_code == 200
        logs = r.json()["data"]
        assert isinstance(logs, list)
        assert len(logs) >= 1
        assert "status" in logs[0]
        assert "sent_to_email" in logs[0]

    def test_mr_read_includes_email_log_field(self, client, db, mr_setup):
        """GET /material-requests/{id} response includes email_log field."""
        s     = mr_setup
        mr_id = _create_and_submit_mr(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        _approve_mr(client, s["tok"], mr_id)

        r = client.get(f"/api/v1/material-requests/{mr_id}", headers=auth(s["tok"]))
        assert r.status_code == 200
        data = r.json()["data"]
        # email_log may be None (before approval) or a dict (after approval)
        assert "email_log" in data


# ── Email body content ────────────────────────────────────────────────────────

class TestMREmailBody:
    def test_email_body_contains_request_number(self, db, mr_setup):
        """build_mr_email_body includes the request number."""
        from app.services.email_service import build_mr_email_body
        from app.models.material_request import MaterialRequest

        s     = mr_setup
        # Create a minimal MR object
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination
        now = datetime.now(timezone.utc)
        mr = MaterialRequest(
            request_number="MR-TEST-999",
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            requested_by=uuid.UUID(s["owner_id"]),
            status=RecordStatus.APPROVED,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            requested_date=now,
            preferred_supplier_id=uuid.UUID(s["supplier_id"]),
            items=[],
        )
        subject, body = build_mr_email_body(db, mr)
        assert "MR-TEST-999" in subject
        assert "MR-TEST-999" in body

    def test_email_body_contains_hmh_branding(self, db, mr_setup):
        from app.services.email_service import build_mr_email_body
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

        s   = mr_setup   # define s first
        now = datetime.now(timezone.utc)
        mr  = MaterialRequest(
            request_number="MR-BRAND-001",
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            requested_by=uuid.UUID(s["owner_id"]),
            status=RecordStatus.APPROVED,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            requested_date=now,
            preferred_supplier_id=None,
            items=[],
        )
        db.add(mr)
        db.flush()
        _, body = build_mr_email_body(db, mr)
        assert "HMH Group" in body
        assert "procurementhmhgroup@gmail.com" in body
