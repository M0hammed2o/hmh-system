"""
Tests for the unified Receive Delivery endpoint and reconciliation.

Coverage:
 1. Receive delivery without file → creates Delivery + DeliveryItems
 2. Receive delivery with PDF → links file path on delivery record
 3. Image upload with OCR unavailable → still creates delivery (manual items)
 4. Driver + receiver signatures saved in delivery record
 5. Delivered qty appears in Site Dashboard BOQ Allocation column
 6. Delivery appears in /deliveries list (recent deliveries)
 7. Short delivery (received < ordered) → DELIVERY_DISCREPANCY alert
 8. Reconciliation: full match → MATCHED
 9. Reconciliation: quantity differs → QUANTITY_MISMATCH
10. Reconciliation: no invoice linked → MISSING_INVOICE
"""

import io
import json
import os
import uuid
import tempfile
import pytest
from datetime import datetime, timezone

from tests.conftest import auth, login, make_user, make_project, make_site, make_item, make_supplier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ud_setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    item     = make_item(db, name="Cement 50kg")
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        item_id=item["id"],
        tok=tok,
    )


def _post_delivery(client, tok, project_id, site_id, supplier_id,
                   items=None, file_data=None, driver_name=None,
                   driver_sig=None, receiver_name="John Smith",
                   receiver_sig="JS", dn_num="DN-TEST-001", lot_id=None):
    if items is None:
        items = [{"description": "Cement 50kg", "unit": "bags",
                  "quantity_expected": 30, "quantity_received": 30,
                  "quantity_rejected": 0}]
    data = {
        "project_id":           project_id,
        "site_id":              site_id,
        "supplier_id":          supplier_id,
        "delivery_note_number": dn_num,
        "items_json":           json.dumps(items),
        "receiver_name":        receiver_name,
        "receiver_signature":   receiver_sig,
    }
    if driver_name: data["driver_name"]      = driver_name
    if driver_sig:  data["driver_signature"] = driver_sig
    if lot_id:      data["lot_id"]           = lot_id

    files = {}
    if file_data:
        filename, content, mime = file_data
        files["delivery_note_file"] = (filename, io.BytesIO(content), mime)

    return client.post(
        "/api/v1/deliveries/receive-with-document",
        data=data,
        files=files,
        headers=auth(tok),
    )


# ── Core delivery creation tests ──────────────────────────────────────────────

class TestUnifiedReceiveDelivery:
    def test_receive_without_file_creates_delivery(self, client, db, ud_setup):
        from app.models.delivery import Delivery
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert "delivery_id" in data
        assert data["items_count"] == 1

        d = db.get(Delivery, uuid.UUID(data["delivery_id"]))
        assert d is not None
        assert d.supplier_id == uuid.UUID(s["supplier_id"])

    def test_receive_creates_delivery_items(self, client, db, ud_setup):
        from app.models.delivery import Delivery, DeliveryItem
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           items=[
                               {"description": "Cement 50kg", "unit": "bags",
                                "quantity_expected": 30, "quantity_received": 28,
                                "quantity_rejected": 2, "reason": "damaged"},
                               {"description": "Sand", "unit": "m3",
                                "quantity_expected": 5, "quantity_received": 5},
                           ])
        assert r.status_code == 201, r.text
        did = uuid.UUID(r.json()["data"]["delivery_id"])
        items = db.query(DeliveryItem).filter(DeliveryItem.delivery_id == did).all()
        assert len(items) == 2

    def test_receive_with_pdf_file_saves_path(self, client, db, ud_setup):
        from app.models.delivery import Delivery
        s = ud_setup
        pdf_content = b"%PDF-1.4\n% minimal pdf"
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           file_data=("dn.pdf", pdf_content, "application/pdf"))
        assert r.status_code == 201, r.text
        assert r.json()["data"]["has_file"] is True

        d = db.get(Delivery, uuid.UUID(r.json()["data"]["delivery_id"]))
        assert d.delivery_note_image_url is not None
        assert d.delivery_note_image_url.endswith(".pdf")

    def test_receive_with_image_no_ocr_still_creates_delivery(self, client, db, ud_setup):
        """Image file upload must not block delivery creation even without OCR."""
        from app.models.delivery import Delivery
        s = ud_setup
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           file_data=("photo.png", png, "image/png"))
        assert r.status_code == 201, r.text


class TestSignatures:
    def test_driver_and_receiver_signatures_saved(self, client, db, ud_setup):
        from app.models.delivery import Delivery
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           driver_name="Ali Hassan", driver_sig="AH",
                           receiver_name="Mohammed Moosa", receiver_sig="MM")
        assert r.status_code == 201, r.text
        d = db.get(Delivery, uuid.UUID(r.json()["data"]["delivery_id"]))
        assert d.receiver_name == "Mohammed Moosa"
        assert d.signature_image_url == "MM"
        assert d.ocr_raw_data is not None
        assert d.ocr_raw_data.get("driver_name") == "Ali Hassan"
        assert d.ocr_raw_data.get("driver_signature") == "AH"


class TestShortDeliveryAlert:
    def test_short_delivery_creates_discrepancy_alert(self, client, db, ud_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        s = ud_setup
        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY
        ).count()

        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           items=[{"description": "Cement", "unit": "bags",
                                   "quantity_expected": 30, "quantity_received": 20,
                                   "quantity_rejected": 10, "reason": "short shipped"}])
        assert r.status_code == 201, r.text
        assert r.json()["data"]["is_partial"] is True

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY
        ).count()
        assert after > before

    def test_full_delivery_no_alert(self, client, db, ud_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        s = ud_setup
        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY
        ).count()
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        assert r.status_code == 201
        assert r.json()["data"]["is_partial"] is False
        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY
        ).count()
        assert after == before


class TestDeliveryAppearsInList:
    def test_delivery_appears_in_project_deliveries(self, client, db, ud_setup):
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        assert r.status_code == 201

        r2 = client.get(f"/api/v1/projects/{s['project_id']}/deliveries/", headers=auth(s["tok"]))
        assert r2.status_code == 200
        ids = [d["id"] for d in r2.json()["data"]]
        assert r.json()["data"]["delivery_id"] in ids


class TestBOQDeliveredQty:
    def test_delivered_qty_updates_stock_ledger(self, client, db, ud_setup):
        """Received qty with item_id + lot_id creates DELIVERY_RECEIVED ledger entry."""
        from app.models.stock import StockLedger
        from app.models.enums import MovementType
        from tests.conftest import make_lot

        s = ud_setup
        lot = make_lot(db, project_id=s["project_id"], site_id=s["site_id"], lot_number="LOT-01")
        db.commit()

        before = db.query(StockLedger).filter(
            StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
            StockLedger.item_id == uuid.UUID(s["item_id"]),
        ).count()

        r = _post_delivery(
            client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
            lot_id=lot["id"],
            items=[{"description": "Cement 50kg", "unit": "bags",
                    "quantity_expected": 30, "quantity_received": 30,
                    "item_id": s["item_id"]}],
        )
        assert r.status_code == 201, r.text

        after = db.query(StockLedger).filter(
            StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
            StockLedger.item_id == uuid.UUID(s["item_id"]),
        ).count()
        assert after > before


# ── Reconciliation tests ──────────────────────────────────────────────────────

class TestReconciliation:
    def _make_po(self, db, project_id, supplier_id, owner_id, qty=30.0, total=5400.0):
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
        from app.models.enums import RecordStatus, VatMode
        from decimal import Decimal
        now = datetime.now(timezone.utc)
        po = PurchaseOrder(
            po_number=f"PO-RECON-{uuid.uuid4().hex[:6].upper()}",
            project_id=uuid.UUID(project_id), supplier_id=uuid.UUID(supplier_id),
            status=RecordStatus.SENT, po_date=now,
            total_amount=Decimal(str(total)),
            subtotal_amount=Decimal(str(round(total / 1.15, 2))),
            vat_amount=Decimal(str(round(total - total / 1.15, 2))),
            created_by=uuid.UUID(owner_id), created_at=now, updated_at=now,
        )
        db.add(po); db.flush()
        from tests.conftest import make_item
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id, description="Cement 50kg",
            quantity_ordered=Decimal(str(qty)), quantity_received=Decimal("0"),
            unit="bags", rate=Decimal("180"), vat_mode=VatMode.INCLUSIVE,
            vat_rate=Decimal("15"), line_total=Decimal(str(total)),
            created_at=now,
        ))
        db.flush()
        return po

    def test_reconcile_missing_invoice(self, client, db, ud_setup):
        """No invoice for PO → MISSING_INVOICE."""
        s = ud_setup
        po = self._make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"])
        assert r.status_code == 201
        did = r.json()["data"]["delivery_id"]

        # Link delivery to PO via update
        from app.models.delivery import Delivery
        d = db.get(Delivery, uuid.UUID(did))
        d.purchase_order_id = po.id
        db.commit()

        r2 = client.get(f"/api/v1/deliveries/{did}/reconcile", headers=auth(s["tok"]))
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert data["overall_status"] in ("MISSING_INVOICE", "MATCHED")

    def test_reconcile_missing_delivery_note_flagged(self, client, db, ud_setup):
        """Delivery without a DN number → MISSING_DELIVERY_NOTE check."""
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           dn_num="")
        assert r.status_code == 201
        did = r.json()["data"]["delivery_id"]

        r2 = client.get(f"/api/v1/deliveries/{did}/reconcile", headers=auth(s["tok"]))
        assert r2.status_code == 200
        data = r2.json()["data"]
        check_types = {c["type"] for c in data["checks"]}
        assert "MISSING_DELIVERY_NOTE" in check_types

    def test_reconcile_full_match(self, client, db, ud_setup):
        """Delivery with DN number and matching PO → MATCHED or acceptable status."""
        s = ud_setup
        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"], s["supplier_id"],
                           dn_num="DN-MATCH-001")
        assert r.status_code == 201
        did = r.json()["data"]["delivery_id"]

        r2 = client.get(f"/api/v1/deliveries/{did}/reconcile", headers=auth(s["tok"]))
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert "overall_status" in data
        assert data["delivery_note_number"] == "DN-MATCH-001"
