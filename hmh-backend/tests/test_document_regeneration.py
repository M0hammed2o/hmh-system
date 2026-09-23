"""
Read-only PO / MR document regeneration (2026-09-23).

GET /purchase-orders/{id}/document and GET /material-requests/{id}/document
re-render the PDF from the existing record so the office can view or
re-download it. They must never create a PO/MR, store an attachment, change a
status or send an email — unlike /send-email and /finalize-pos, which do.
"""

import uuid

import pytest

from tests.conftest import (
    auth, login, make_project, make_site, make_supplier, make_user, make_user_project_access,
)


@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    outsider = make_user(db, role="SITE_STAFF")      # no access to this project
    project  = make_project(db, owner_id=owner["id"])
    other    = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db, name="Prem Glazzing", email="glazing@test.com")
    make_user_project_access(db, outsider["id"], other["id"])
    return dict(
        owner_id=owner["id"], project_id=project["id"], site_id=site["id"],
        supplier=supplier,
        tok=login(client, owner["email"], owner["password"]),
        outsider_tok=login(client, outsider["email"], outsider["password"]),
    )


def _approved_mr(client, s):
    r = client.post(
        f"/api/v1/projects/{s['project_id']}/material-requests/",
        json={
            "site_id": s["site_id"],
            "delivery_destination": "SITE_STORE",
            "preferred_supplier_id": s["supplier"]["id"],
            "items": [{"description": "Glass Set", "quantity_requested": 2, "unit": "ea"}],
        },
        headers=auth(s["tok"]),
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    client.post(f"/api/v1/material-requests/{mr['id']}/submit", headers=auth(s["tok"]))
    r = client.post(f"/api/v1/material-requests/{mr['id']}/approve",
                    json={"send_supplier_email": False}, headers=auth(s["tok"]))
    assert r.status_code == 200, r.text
    return mr


def _po(db, s):
    from decimal import Decimal
    from datetime import datetime, timezone
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus, VatMode
    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=f"PO-GLZ-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(s["project_id"]),
        site_id=uuid.UUID(s["site_id"]),
        supplier_id=uuid.UUID(s["supplier"]["id"]),
        status=RecordStatus.APPROVED,
        po_date=now,
        subtotal_amount=Decimal("2242.00"),
        vat_amount=Decimal("292.43"),
        total_amount=Decimal("2242.00"),
        created_by=uuid.UUID(s["owner_id"]),
        created_at=now, updated_at=now,
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderItem(
        purchase_order_id=po.id, description="Glass Set", quantity_ordered=2,
        unit="ea", rate=1121.0, vat_mode=VatMode.EXCLUSIVE, vat_rate=15.0,
        line_total=2242.0, quantity_received=0.0, created_at=now,
    ))
    db.commit()
    return po


def _counts(db):
    from app.models.attachment import Attachment
    from app.models.material_request import MaterialRequest
    from app.models.mr_email_log import MREmailLog
    from app.models.purchase_order import PurchaseOrder
    db.expire_all()
    return tuple(db.query(m).count() for m in (PurchaseOrder, MaterialRequest, Attachment, MREmailLog))


class TestDocumentRegeneration:

    def test_po_document_renders_a_pdf(self, client, db, setup):
        s = setup
        po = _po(db, s)
        r = client.get(f"/api/v1/purchase-orders/{po.id}/document", headers=auth(s["tok"]))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert po.po_number in r.headers.get("content-disposition", "")

    def test_mr_document_renders_a_pdf(self, client, db, setup):
        s = setup
        mr = _approved_mr(client, s)
        r = client.get(f"/api/v1/material-requests/{mr['id']}/document", headers=auth(s["tok"]))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_regeneration_changes_nothing(self, client, db, setup):
        """No new PO/MR, no stored attachment, no email log, no status change."""
        from app.models.material_request import MaterialRequest
        from app.models.purchase_order import PurchaseOrder
        s = setup
        po = _po(db, s)
        mr = _approved_mr(client, s)
        before = _counts(db)
        po_status_before = po.status
        mr_status_before = db.get(MaterialRequest, uuid.UUID(mr["id"])).status

        for _ in range(2):  # repeat — still no side effects
            assert client.get(f"/api/v1/purchase-orders/{po.id}/document", headers=auth(s["tok"])).status_code == 200
            assert client.get(f"/api/v1/material-requests/{mr['id']}/document", headers=auth(s["tok"])).status_code == 200

        assert _counts(db) == before, "regeneration must not create records"
        db.expire_all()
        assert db.get(PurchaseOrder, po.id).status == po_status_before
        assert db.get(MaterialRequest, uuid.UUID(mr["id"])).status == mr_status_before

    def test_unknown_ids_return_404(self, client, db, setup):
        s = setup
        assert client.get(f"/api/v1/purchase-orders/{uuid.uuid4()}/document", headers=auth(s["tok"])).status_code == 404
        assert client.get(f"/api/v1/material-requests/{uuid.uuid4()}/document", headers=auth(s["tok"])).status_code == 404

    def test_other_projects_user_cannot_regenerate(self, client, db, setup):
        s = setup
        po = _po(db, s)
        mr = _approved_mr(client, s)
        assert client.get(f"/api/v1/purchase-orders/{po.id}/document",
                          headers=auth(s["outsider_tok"])).status_code == 403
        assert client.get(f"/api/v1/material-requests/{mr['id']}/document",
                          headers=auth(s["outsider_tok"])).status_code == 403
