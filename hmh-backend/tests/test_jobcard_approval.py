"""
Flow D — Job Card Labour Approval Chain

Tests:
  - Create JobCard → DRAFT
  - Submit → SUBMITTED
  - Site approve → SITE_APPROVED
  - Office approve → OFFICE_APPROVED
  - Before full approval: status not PAYMENT_APPROVED/PAID
  - Amount > threshold → owner_approval_required=True
  - Owner approve (if required) → OWNER_APPROVED
  - Approve payment → PAYMENT_APPROVED
  - Mark paid → PAID
  - Reject → REJECTED
  - Audit trail events present after transitions
"""
import uuid
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import (
    auth, login, make_lot, make_project,
    make_site, make_user,
)
from app.models.job_card import OWNER_APPROVAL_THRESHOLD


@pytest.fixture()
def jc_setup(db: Session, client: TestClient):
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    site_mgr = make_user(db, role="SITE_MANAGER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    lot = make_lot(db, project["id"], site["id"])
    db.flush()
    return {
        "owner": owner, "office": office, "site_mgr": site_mgr,
        "project": project, "site": site, "lot": lot,
    }


def _create_jc(client, setup, rate=500.0, quantity=5.0, tok=None):
    tok = tok or login(client, setup["site_mgr"]["email"], setup["site_mgr"]["password"])
    r = client.post(
        f"/api/v1/projects/{setup['project']['id']}/job-cards/",
        json={
            "site_id": setup["site"]["id"],
            "lot_id": setup["lot"]["id"],
            "work_description": "Brickwork test",
            "work_type": "DAILY_LABOUR",
            "worker_name": "Test Worker",
            "quantity": quantity,
            "unit": "days",
            "rate": rate,
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"], tok


def test_create_job_card_draft(db: Session, client: TestClient, jc_setup: dict):
    """New job card starts in DRAFT, total_amount calculated correctly."""
    jc, _ = _create_jc(client, jc_setup, rate=600.0, quantity=5.0)
    assert jc["status"] == "DRAFT"
    assert jc["total_amount"] == 3000.0
    assert jc["owner_approval_required"] is False  # 3000 < threshold


def test_job_card_above_threshold_requires_owner(db: Session, client: TestClient, jc_setup: dict):
    """Job card above threshold must set owner_approval_required=True."""
    rate = OWNER_APPROVAL_THRESHOLD + 1000
    jc, _ = _create_jc(client, jc_setup, rate=rate, quantity=1.0)
    assert jc["owner_approval_required"] is True


def test_full_approval_chain_below_threshold(db: Session, client: TestClient, jc_setup: dict):
    """Below threshold: DRAFT → SUBMITTED → SITE_APPROVED → OFFICE_APPROVED → PAYMENT_APPROVED → PAID."""
    jc, site_tok = _create_jc(client, jc_setup)
    jc_id = jc["id"]
    office_tok = login(client, jc_setup["office"]["email"], jc_setup["office"]["password"])

    # Submit
    r = client.post(f"/api/v1/job-cards/{jc_id}/submit", headers=auth(site_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "SUBMITTED"

    # Site approve
    r = client.post(f"/api/v1/job-cards/{jc_id}/site-approve", headers=auth(site_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "SITE_APPROVED"

    # Office approve
    r = client.post(f"/api/v1/job-cards/{jc_id}/office-approve", headers=auth(office_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "OFFICE_APPROVED"

    # Approve payment
    r = client.post(f"/api/v1/job-cards/{jc_id}/approve-payment", headers=auth(office_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "PAYMENT_APPROVED"

    # Mark paid
    r = client.post(f"/api/v1/job-cards/{jc_id}/mark-paid", headers=auth(office_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "PAID"


def test_not_payable_until_office_approved(db: Session, client: TestClient, jc_setup: dict):
    """approve-payment must fail if not at OFFICE_APPROVED (below threshold)."""
    jc, site_tok = _create_jc(client, jc_setup)
    jc_id = jc["id"]
    office_tok = login(client, jc_setup["office"]["email"], jc_setup["office"]["password"])

    # Try approve-payment while still DRAFT → should fail
    r = client.post(f"/api/v1/job-cards/{jc_id}/approve-payment", headers=auth(office_tok))
    assert r.status_code in (400, 422), f"Expected error, got {r.status_code}: {r.text}"

    # Submit + site approve + office approve → then payment works
    client.post(f"/api/v1/job-cards/{jc_id}/submit", headers=auth(site_tok))
    client.post(f"/api/v1/job-cards/{jc_id}/site-approve", headers=auth(site_tok))
    client.post(f"/api/v1/job-cards/{jc_id}/office-approve", headers=auth(office_tok))

    r = client.post(f"/api/v1/job-cards/{jc_id}/approve-payment", headers=auth(office_tok))
    assert r.status_code == 200


def test_above_threshold_requires_owner_approve(db: Session, client: TestClient, jc_setup: dict):
    """Above threshold: approve-payment must fail without owner approval."""
    rate = OWNER_APPROVAL_THRESHOLD + 5000
    jc, site_tok = _create_jc(client, jc_setup, rate=rate, quantity=1.0)
    jc_id = jc["id"]
    office_tok = login(client, jc_setup["office"]["email"], jc_setup["office"]["password"])
    owner_tok = login(client, jc_setup["owner"]["email"], jc_setup["owner"]["password"])

    client.post(f"/api/v1/job-cards/{jc_id}/submit", headers=auth(site_tok))
    client.post(f"/api/v1/job-cards/{jc_id}/site-approve", headers=auth(site_tok))
    client.post(f"/api/v1/job-cards/{jc_id}/office-approve", headers=auth(office_tok))

    # Still OFFICE_APPROVED, not OWNER_APPROVED → approve-payment should fail
    r = client.post(f"/api/v1/job-cards/{jc_id}/approve-payment", headers=auth(office_tok))
    assert r.status_code in (400, 422)

    # Owner approves
    r = client.post(f"/api/v1/job-cards/{jc_id}/owner-approve", headers=auth(owner_tok))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "OWNER_APPROVED"

    # Now payment approval works
    r = client.post(f"/api/v1/job-cards/{jc_id}/approve-payment", headers=auth(office_tok))
    assert r.status_code == 200


def test_reject_job_card(db: Session, client: TestClient, jc_setup: dict):
    """Any non-paid job card can be rejected with a reason."""
    jc, site_tok = _create_jc(client, jc_setup)
    jc_id = jc["id"]
    office_tok = login(client, jc_setup["office"]["email"], jc_setup["office"]["password"])

    client.post(f"/api/v1/job-cards/{jc_id}/submit", headers=auth(site_tok))

    r = client.post(
        f"/api/v1/job-cards/{jc_id}/reject",
        json={"reason": "Work not completed to standard"},
        headers=auth(office_tok),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "REJECTED"
    assert data["rejection_reason"] == "Work not completed to standard"


def test_job_card_audit_trail(db: Session, client: TestClient, jc_setup: dict):
    """Audit events are written for job card state transitions."""
    from app.models.audit import AuditEvent

    jc, site_tok = _create_jc(client, jc_setup)
    jc_id = jc["id"]

    before = db.query(AuditEvent).count()
    client.post(f"/api/v1/job-cards/{jc_id}/submit", headers=auth(site_tok))
    after = db.query(AuditEvent).count()

    assert after > before, "Expected audit event on submit"


def test_job_card_summary(db: Session, client: TestClient, jc_setup: dict):
    """Project job card summary returns pending_payment_count."""
    tok = login(client, jc_setup["office"]["email"], jc_setup["office"]["password"])

    r = client.get(
        f"/api/v1/projects/{jc_setup['project']['id']}/job-cards/summary",
        headers=auth(tok),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "pending_payment_count" in data
    assert "pending_payment_amount" in data
