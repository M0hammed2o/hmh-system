"""
Optional supplier email on Material Request approval.

Requirement (2026-09-16): the office approver may untick "Send email to supplier
after approval". The MR still approves normally; the automatic email is skipped,
never faked as sent, and can still be sent manually afterwards.

Covered:
 1. Default approval still sends/queues the supplier email (unchanged behaviour).
 2. send_supplier_email=false approves the MR but sends no email.
 3. No false SENT/MOCK_SENT log is written — the skip is logged as SKIPPED.
 4. The email can still be sent manually afterwards.
 5. Supplier selection (header and line) is unchanged either way.
 6. The pipeline distinguishes sent / not sent yet / intentionally skipped, and a
    skipped email does not stall the workflow.
 7. The procurement-approve route (used by the office UI) honours the flag too.
"""

import uuid

import pytest

from tests.conftest import (
    auth, login, make_project, make_site, make_supplier, make_user, make_user_project_access,
)

SENT_STATUSES = ("SENT", "MOCK_SENT")


@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    office   = make_user(db, role="OFFICE_USER")
    lead     = make_user(db, role="PROCUREMENT_LEAD")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db, email="supplier@test.com")
    make_user_project_access(db, office["id"], project["id"])
    make_user_project_access(db, lead["id"], project["id"])
    return dict(
        project_id=project["id"], site_id=site["id"], supplier=supplier,
        office_tok=login(client, office["email"], office["password"]),
        lead_tok=login(client, lead["email"], lead["password"]),
        owner_tok=login(client, owner["email"], owner["password"]),
    )


def _submitted_mr(client, s):
    r = client.post(
        f"/api/v1/projects/{s['project_id']}/material-requests/",
        json={
            "site_id": s["site_id"],
            "delivery_destination": "SITE_STORE",
            "preferred_supplier_id": s["supplier"]["id"],
            "items": [{
                "description": "Cement bags",
                "quantity_requested": 10,
                "unit": "bag",
                "preferred_supplier_id": s["supplier"]["id"],
            }],
        },
        headers=auth(s["office_tok"]),
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert client.post(f"/api/v1/material-requests/{mr['id']}/submit",
                       headers=auth(s["office_tok"])).status_code == 200
    return mr


def _logs(db, mr_id):
    from app.models.mr_email_log import MREmailLog
    db.expire_all()
    return db.query(MREmailLog).filter(MREmailLog.material_request_id == uuid.UUID(mr_id)).all()


def _pipeline_step3(client, s, mr_id):
    r = client.get(f"/api/v1/procurement/mrs/{mr_id}/pipeline", headers=auth(s["owner_tok"]))
    assert r.status_code == 200, r.text
    return r.json()["data"]["steps"][2]


class TestApprovalEmailFlag:

    def test_default_approval_still_sends_supplier_email(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)

        r = client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                        json={}, headers=auth(s["office_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "APPROVED"

        logs = _logs(db, mr["id"])
        assert [l.status for l in logs if l.status in SENT_STATUSES], "default must still email the supplier"
        assert not [l for l in logs if l.status == "SKIPPED"]

        step3 = _pipeline_step3(client, s, mr["id"])
        assert step3["status"] == "COMPLETE"
        assert step3["email_sent"] is True
        assert step3["email_skipped"] is False

    def test_approval_without_email_skips_send_and_logs_no_false_sent(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)

        r = client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                        json={"send_supplier_email": False}, headers=auth(s["office_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "APPROVED", "MR must still approve normally"

        logs = _logs(db, mr["id"])
        assert not [l for l in logs if l.status in SENT_STATUSES], "no email may be sent or faked as sent"
        skipped = [l for l in logs if l.status == "SKIPPED"]
        assert len(skipped) == 1
        assert skipped[0].sent_at is None, "a skipped email must not look delivered"

    def test_pipeline_reports_skipped_without_stalling(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)
        client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                    json={"send_supplier_email": False}, headers=auth(s["office_tok"]))

        step3 = _pipeline_step3(client, s, mr["id"])
        assert step3["email_sent"] is False, "must never be reported as sent"
        assert step3["email_skipped"] is True
        assert step3["status"] == "COMPLETE", "a deliberate skip must not stall the pipeline"
        assert step3["email_logs"] == [], "skipped rows must not appear as delivered emails"

    def test_email_can_still_be_sent_manually_after_skipping(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)
        client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                    json={"send_supplier_email": False}, headers=auth(s["office_tok"]))

        r = client.post(f"/api/v1/material-requests/{mr['id']}/send-email", headers=auth(s["office_tok"]))
        assert r.status_code == 200, r.text

        logs = _logs(db, mr["id"])
        assert [l for l in logs if l.status in SENT_STATUSES], "manual send must still work after a skip"

        step3 = _pipeline_step3(client, s, mr["id"])
        assert step3["email_sent"] is True
        assert step3["email_skipped"] is False, "once really sent it is no longer 'skipped'"

    @pytest.mark.parametrize("send_email", [True, False])
    def test_supplier_selection_is_unchanged(self, client, db, setup, send_email):
        s = setup
        mr = _submitted_mr(client, s)

        r = client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                        json={"send_supplier_email": send_email}, headers=auth(s["office_tok"]))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["preferred_supplier_id"] == s["supplier"]["id"]
        assert data["items"][0]["preferred_supplier_id"] == s["supplier"]["id"]

    def test_procurement_approve_route_honours_the_flag(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)

        r = client.post(f"/api/v1/material-requests/{mr['id']}/procurement-approve",
                        json={"send_supplier_email": False}, headers=auth(s["lead_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "APPROVED"

        logs = _logs(db, mr["id"])
        assert not [l for l in logs if l.status in SENT_STATUSES]
        assert len([l for l in logs if l.status == "SKIPPED"]) == 1

    def test_procurement_approve_route_defaults_to_sending(self, client, db, setup):
        s = setup
        mr = _submitted_mr(client, s)

        r = client.post(f"/api/v1/material-requests/{mr['id']}/procurement-approve",
                        json={}, headers=auth(s["lead_tok"]))
        assert r.status_code == 200, r.text
        assert [l for l in _logs(db, mr["id"]) if l.status in SENT_STATUSES]
