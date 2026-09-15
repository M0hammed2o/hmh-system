"""
Project isolation for Site Clerk workflows (security review before production, 2026-09-15).

A user may only read or change stock, deliveries, delivery-note captures and
transfer requests that belong to projects they are authorised for. Office-level
roles keep company-wide access; site roles need a UserProjectAccess row.

Requirements covered:
 1. Stock usage: a Site Clerk records usage on an assigned project (201), gets 403
    on an unassigned project, and cannot book usage against another project's lot
    or BOQ item. Stock ledger/balance reads are project-scoped.
 2. receive-with-document: an assigned Site Clerk can receive a delivery; the same
    clerk cannot receive for another project, or point site / lot / PO / BOQ item
    ids at another project. Nothing is written on refusal.
 3. JSON delivery create and receive-stock reject another project's site, PO,
    PO item or lot.
 4. Site delivery-note capture: upload / get / correct / verify / signature enforce
    project access via the note's site; READ_ONLY and SITE_MANAGER_VIEW may view but
    never upload, correct, verify or sign.
 5. GET /warehouse-transfers/{id} is visible only with access to the source or
    destination project (or an office-level role).
"""

import io
import json
import uuid

import pytest

from tests.conftest import (
    auth, login, make_boq_item, make_item, make_lot, make_project, make_site,
    make_supplier, make_user, make_user_project_access,
)


@pytest.fixture
def s(db, client):
    owner   = make_user(db, role="OWNER")
    office  = make_user(db, role="OFFICE_USER")
    ro      = make_user(db, role="READ_ONLY")
    clerk   = make_user(db, role="SITE_STAFF")         # access: A
    viewer  = make_user(db, role="SITE_MANAGER_VIEW")  # access: A
    clerk_b = make_user(db, role="SITE_STAFF")         # access: B
    clerk_c = make_user(db, role="SITE_STAFF")         # access: C

    a = make_project(db, owner_id=owner["id"])
    b = make_project(db, owner_id=owner["id"])
    c = make_project(db, owner_id=owner["id"])
    site_a = make_site(db, a["id"], name="Site A")
    site_b = make_site(db, b["id"], name="Site B")
    lot_a = make_lot(db, a["id"], site_a["id"], "A1")
    lot_b = make_lot(db, b["id"], site_b["id"], "B1")
    item = make_item(db, name="Cement 42.5R")
    supplier = make_supplier(db)
    boq_a = make_boq_item(db, a["id"], lot_a["id"], item["id"], qty=500)
    boq_b = make_boq_item(db, b["id"], lot_b["id"], item["id"], qty=500)

    make_user_project_access(db, clerk["id"], a["id"])
    make_user_project_access(db, viewer["id"], a["id"])
    make_user_project_access(db, clerk_b["id"], b["id"])
    make_user_project_access(db, clerk_c["id"], c["id"])

    tok = lambda u: login(client, u["email"], u["password"])
    return dict(
        a=a["id"], b=b["id"], c=c["id"], site_a=site_a["id"], site_b=site_b["id"],
        lot_a=lot_a["id"], lot_b=lot_b["id"], item=item["id"], supplier=supplier["id"],
        boq_a=boq_a["boq_item_id"], boq_b=boq_b["boq_item_id"],
        owner=tok(owner), office=tok(office), ro=tok(ro), clerk=tok(clerk),
        viewer=tok(viewer), clerk_b=tok(clerk_b), clerk_c=tok(clerk_c),
    )


def _count(db, model):
    db.expire_all()
    return db.query(model).count()


def _counts(db):
    from app.models.delivery import Delivery
    from app.models.stock import StockLedger, UsageLog
    from app.models.document_extraction import DeliveryVerification
    return tuple(_count(db, m) for m in (StockLedger, UsageLog, Delivery, DeliveryVerification))


# ── 1. Stock usage ────────────────────────────────────────────────────────────

class TestStockUsageIsolation:

    def _usage(self, client, tok, project_id, **body):
        return client.post(f"/api/v1/stock/usage?project_id={project_id}", json=body, headers=auth(tok))

    def test_clerk_records_usage_on_assigned_project(self, client, db, s):
        from app.models.stock import StockLedger
        r = self._usage(client, s["clerk"], s["a"], site_id=s["site_a"], item_id=s["item"], quantity_used=2)
        assert r.status_code == 201, r.text
        db.expire_all()
        row = db.query(StockLedger).filter(StockLedger.reference_id == uuid.UUID(r.json()["data"]["id"])).one()
        assert str(row.project_id) == s["a"]
        assert float(row.quantity_out) == pytest.approx(2)

    def test_clerk_cannot_record_usage_on_unassigned_project(self, client, db, s):
        before = _counts(db)
        r = self._usage(client, s["clerk"], s["b"], site_id=s["site_b"], item_id=s["item"], quantity_used=2)
        assert r.status_code == 403, r.text
        assert _counts(db) == before

    def test_clerk_cannot_book_usage_against_other_projects_lot_or_boq_item(self, client, db, s):
        before = _counts(db)
        r = self._usage(client, s["clerk"], s["a"], site_id=s["site_a"], item_id=s["item"],
                        quantity_used=2, lot_id=s["lot_b"], overrun_reason="x")
        assert r.status_code == 404, r.text
        r = self._usage(client, s["clerk"], s["a"], site_id=s["site_a"], item_id=s["item"],
                        quantity_used=2, boq_item_id=s["boq_b"])
        assert r.status_code == 404, r.text
        assert _counts(db) == before

    def test_usage_with_evidence_refuses_unassigned_project(self, client, db, s):
        from app.models.attachment import Attachment
        before, attachments = _counts(db), _count(db, Attachment)
        r = client.post(
            "/api/v1/stock/usage-with-evidence",
            data={"project_id": s["b"], "site_id": s["site_b"], "item_id": s["item"], "quantity_used": "2"},
            files={"evidence_file": ("p.png", io.BytesIO(b"\x89PNG\r\n\x1a\n0000"), "image/png")},
            headers=auth(s["clerk"]),
        )
        assert r.status_code == 403, r.text
        assert _counts(db) == before
        assert _count(db, Attachment) == attachments

    def test_stock_reads_are_project_scoped(self, client, s):
        assert client.get(f"/api/v1/stock/ledger?project_id={s['a']}", headers=auth(s["clerk"])).status_code == 200
        assert client.get(f"/api/v1/stock/ledger?project_id={s['b']}", headers=auth(s["clerk"])).status_code == 403
        assert client.get(f"/api/v1/stock/balances?project_id={s['b']}", headers=auth(s["clerk"])).status_code == 403
        assert client.get(f"/api/v1/stock/ledger?project_id={s['b']}", headers=auth(s["office"])).status_code == 200


# ── 2. receive-with-document ──────────────────────────────────────────────────

def _receive(client, tok, s, project_id, site_id, items=None, **extra):
    items = items if items is not None else [{
        "description": "Cement 42.5R", "unit": "bag", "item_id": s["item"],
        "quantity_expected": 20, "quantity_received": 20, "quantity_rejected": 0,
    }]
    data = {
        "project_id": project_id, "site_id": site_id, "supplier_id": s["supplier"],
        "delivery_note_number": f"DN-{uuid.uuid4().hex[:6]}", "items_json": json.dumps(items),
        "receiver_name": "Clerk", "receiver_signature": "SC",
    }
    data.update(extra)
    return client.post("/api/v1/deliveries/receive-with-document", data=data, headers=auth(tok))


def _po_for(client, s, project_id, site_id):
    r = client.post(
        f"/api/v1/projects/{project_id}/purchase-orders/",
        json={"supplier_id": s["supplier"], "site_id": site_id, "items": [{
            "description": "Cement 42.5R", "quantity_ordered": 20, "unit": "bag",
            "rate": 100.0, "vat_mode": "INCLUSIVE", "vat_rate": 15.0,
        }]},
        headers=auth(s["owner"]),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


class TestReceiveWithDocumentIsolation:

    def test_clerk_receives_delivery_for_assigned_project(self, client, db, s):
        from app.models.delivery import Delivery
        from app.models.stock import StockLedger
        r = _receive(client, s["clerk"], s, s["a"], s["site_a"])
        assert r.status_code == 201, r.text
        d = db.get(Delivery, uuid.UUID(r.json()["data"]["delivery_id"]))
        assert str(d.project_id) == s["a"]
        rows = db.query(StockLedger).filter(StockLedger.reference_id == d.id).all()
        assert len(rows) == 1 and str(rows[0].project_id) == s["a"]

    def test_clerk_cannot_receive_for_unassigned_project(self, client, db, s):
        before = _counts(db)
        r = _receive(client, s["clerk"], s, s["b"], s["site_b"])
        assert r.status_code == 403, r.text
        assert _counts(db) == before

    def test_clerk_cannot_point_ids_at_another_project(self, client, db, s):
        po_b = _po_for(client, s, s["b"], s["site_b"])
        before = _counts(db)

        r = _receive(client, s["clerk"], s, s["a"], s["site_b"])
        assert r.status_code == 404, r.text
        r = _receive(client, s["clerk"], s, s["a"], s["site_a"], destination="LOT", lot_id=s["lot_b"])
        assert r.status_code == 404, r.text
        r = _receive(client, s["clerk"], s, s["a"], s["site_a"], purchase_order_id=po_b["id"])
        assert r.status_code == 404, r.text
        r = _receive(client, s["clerk"], s, s["a"], s["site_a"], items=[{
            "description": "Cement 42.5R", "unit": "bag", "boq_item_id": s["boq_b"],
            "quantity_expected": 5, "quantity_received": 5,
        }])
        assert r.status_code == 404, r.text

        assert _counts(db) == before


# ── 3. JSON delivery create + receive-stock ───────────────────────────────────

class TestJsonDeliveryIsolation:

    def _create(self, client, tok, s, project_id, site_id, **extra):
        body = {"supplier_id": s["supplier"], "site_id": site_id, "items": [
            {"description": "Cement 42.5R", "quantity_received": 10, "quantity_expected": 10,
             "unit": "bag", "item_id": s["item"]},
        ]}
        body.update(extra)
        return client.post(f"/api/v1/projects/{project_id}/deliveries/", json=body, headers=auth(tok))

    def test_create_rejects_other_projects_site_po_and_po_item(self, client, db, s):
        from app.models.purchase_order import PurchaseOrderItem
        po_b = _po_for(client, s, s["b"], s["site_b"])
        po_b_item = db.query(PurchaseOrderItem).filter(PurchaseOrderItem.purchase_order_id == uuid.UUID(po_b["id"])).first()
        before = _counts(db)

        assert self._create(client, s["clerk"], s, s["a"], s["site_b"]).status_code == 404
        assert self._create(client, s["clerk"], s, s["a"], s["site_a"], purchase_order_id=po_b["id"]).status_code == 404
        r = self._create(client, s["clerk"], s, s["a"], s["site_a"], items=[
            {"description": "Cement 42.5R", "quantity_received": 10, "purchase_order_item_id": str(po_b_item.id)},
        ])
        assert r.status_code == 404, r.text
        assert _counts(db) == before

        assert self._create(client, s["clerk"], s, s["a"], s["site_a"]).status_code == 201

    def test_receive_stock_rejects_other_projects_lot(self, client, db, s):
        from app.models.stock import StockLedger
        delivery_id = self._create(client, s["clerk"], s, s["a"], s["site_a"]).json()["data"]["id"]
        ledger_before = _count(db, StockLedger)

        r = client.post(f"/api/v1/deliveries/{delivery_id}/receive-stock",
                        json={"destination": "LOT", "lot_id": s["lot_b"], "overrun_reason": "x"},
                        headers=auth(s["clerk"]))
        assert r.status_code == 404, r.text
        assert _count(db, StockLedger) == ledger_before

        r = client.post(f"/api/v1/deliveries/{delivery_id}/receive-stock",
                        json={"destination": "LOT", "lot_id": s["lot_a"], "overrun_reason": "x"},
                        headers=auth(s["clerk"]))
        assert r.status_code == 200, r.text


# ── 4. Site delivery-note capture ─────────────────────────────────────────────

def _upload(client, tok, site_id, **form):
    data = {"site_id": site_id, "supplier_name": "Test Supplier"}
    data.update(form)
    return client.post(
        "/api/v1/site-capture/delivery-note/upload",
        files={"file": ("dn.pdf", io.BytesIO(b"DELIVERY NOTE\nDN-ISO-001\nCement 20 bags"), "application/pdf")},
        data=data, headers=auth(tok),
    )


def _mutations(client, tok, vid):
    return {
        "correct": client.post(f"/api/v1/site-capture/delivery-note/{vid}/correct",
                               json={"supplier_name": "Tampered", "items": []}, headers=auth(tok)).status_code,
        "verify": client.post(f"/api/v1/site-capture/delivery-note/{vid}/verify", headers=auth(tok)).status_code,
        "signature": client.post(f"/api/v1/site-capture/delivery-note/{vid}/signature",
                                 json={"signature_data": "Tamper", "signed_by_name": "x"}, headers=auth(tok)).status_code,
    }


def _verification(db, vid):
    from app.models.document_extraction import DeliveryVerification
    db.expire_all()
    return db.get(DeliveryVerification, uuid.UUID(vid))


class TestSiteCaptureIsolation:

    def test_upload_is_project_scoped(self, client, db, s):
        po_b = _po_for(client, s, s["b"], s["site_b"])
        assert _upload(client, s["clerk"], s["site_a"]).status_code == 201

        before = _counts(db)
        assert _upload(client, s["clerk"], s["site_b"]).status_code == 403
        assert _upload(client, s["clerk"], s["site_a"], lot_id=s["lot_b"]).status_code == 404
        assert _upload(client, s["clerk"], s["site_a"], purchase_order_id=po_b["id"]).status_code == 404
        assert _counts(db) == before

    def test_clerk_cannot_read_or_change_another_projects_note(self, client, db, s):
        vid = _upload(client, s["owner"], s["site_b"]).json()["data"]["id"]

        assert client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(s["clerk"])).status_code == 403
        assert _mutations(client, s["clerk"], vid) == {"correct": 403, "verify": 403, "signature": 403}
        v = _verification(db, vid)
        assert v.verification_status == "DRAFT" and v.signed_at is None and v.supplier_name == "Test Supplier"

        assert client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(s["clerk_b"])).status_code == 200

    def test_clerk_full_capture_flow_on_assigned_project(self, client, db, s):
        vid = _upload(client, s["clerk"], s["site_a"]).json()["data"]["id"]
        assert client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(s["clerk"])).status_code == 200
        assert _mutations(client, s["clerk"], vid) == {"correct": 200, "verify": 200, "signature": 200}
        v = _verification(db, vid)
        assert v.verification_status == "VERIFIED" and v.signed_at is not None

    @pytest.mark.parametrize("role_tok", ["ro", "viewer"])
    def test_read_only_roles_can_view_but_never_mutate(self, client, db, s, role_tok):
        vid = _upload(client, s["clerk"], s["site_a"]).json()["data"]["id"]
        tok = s[role_tok]
        before = _counts(db)

        assert client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(tok)).status_code == 200
        assert _upload(client, tok, s["site_a"]).status_code == 403
        assert _mutations(client, tok, vid) == {"correct": 403, "verify": 403, "signature": 403}

        v = _verification(db, vid)
        assert v.verification_status == "DRAFT" and v.signed_at is None and v.supplier_name == "Test Supplier"
        assert _counts(db) == before

    def test_unknown_note_is_404(self, client, s):
        assert client.get(f"/api/v1/site-capture/delivery-note/{uuid.uuid4()}", headers=auth(s["clerk"])).status_code == 404


# ── 5. Transfer request visibility ────────────────────────────────────────────

class TestTransferRequestVisibility:

    def test_get_transfer_requires_access_to_source_or_destination(self, client, db, s):
        from app.models.warehouse_transfer import WarehouseTransferRequest
        from tests.conftest import make_stock
        make_stock(db, s["a"], None, s["item"], qty=30)
        r = client.post(f"/api/v1/projects/{s['a']}/warehouse-transfers/",
                        json={"to_project_id": s["b"], "item_id": s["item"], "quantity": 5, "reason": "iso"},
                        headers=auth(s["office"]))
        assert r.status_code == 200, r.text
        tid = r.json()["data"]["id"]
        url = f"/api/v1/warehouse-transfers/{tid}"

        assert client.get(url, headers=auth(s["clerk_c"])).status_code == 403   # neither end
        assert client.get(url, headers=auth(s["clerk"])).status_code == 200     # source
        assert client.get(url, headers=auth(s["clerk_b"])).status_code == 200   # destination
        for tok in ("office", "ro", "owner"):                                   # office-level
            assert client.get(url, headers=auth(s[tok])).status_code == 200
        assert client.get(f"/api/v1/warehouse-transfers/{uuid.uuid4()}", headers=auth(s["clerk_c"])).status_code == 404
        assert db.get(WarehouseTransferRequest, uuid.UUID(tid)).status == "PENDING"
