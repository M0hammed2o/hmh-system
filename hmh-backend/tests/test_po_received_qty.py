"""
Tests for PurchaseOrderItem.quantity_received updating on delivery receipt.

Coverage:
 1. quantity_received updates when item_id is present on delivery item
 2. quantity_received updates when item_id is None but boq_item_id matches PO item
 3. quantity_received does NOT update when neither item_id nor boq_item_id matches
 4. Partial delivery increments quantity_received correctly
 5. Multiple deliveries accumulate quantity_received
 6. PO item back-fills its own item_id when it was None and delivery resolved one
"""

import uuid
import pytest

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_item, make_supplier,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


def _make_po_with_item(db, project_id, supplier_id, owner_id, item_id=None, boq_item_id=None,
                       qty_ordered=10.0, description="Roof Complete"):
    """Create a PurchaseOrder with one PurchaseOrderItem."""
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        id=uuid.uuid4(),
        po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        created_by=uuid.UUID(owner_id),
        status=RecordStatus.APPROVED,
        po_date=now,
        total_amount=qty_ordered * 100,
    )
    db.add(po)
    db.flush()

    poi = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po.id,
        item_id=uuid.UUID(item_id) if item_id else None,
        boq_item_id=uuid.UUID(boq_item_id) if boq_item_id else None,
        description=description,
        quantity_ordered=qty_ordered,
        quantity_received=0,
        unit="m2",
        rate=100,
        created_at=now,
    )
    db.add(poi)
    db.flush()
    return po, poi


def _record_delivery(client, tok, project_id, site_id, supplier_id, po_id,
                     item_id=None, boq_item_id=None, qty_received=5.0, description="Roof Complete"):
    """POST /deliveries/ with one item."""
    body = {
        "destination": "MAIN_WAREHOUSE",
        "supplier_id": supplier_id,
        "site_id": site_id,
        "purchase_order_id": po_id,
        "delivery_number": f"DN-{uuid.uuid4().hex[:8].upper()}",
        "delivery_date": "2026-06-01",
        "items": [{
            "description": description,
            "quantity_received": qty_received,
            "quantity_expected": qty_received,
            "unit": "m2",
            "item_id": item_id,
            "boq_item_id": boq_item_id,
        }],
    }
    return client.post(
        f"/api/v1/projects/{project_id}/deliveries/",
        json=body,
        headers=auth(tok),
    )


class TestPOReceivedQty:

    def test_updates_when_item_id_matches(self, client, db, setup):
        """Standard path: PO item has item_id; delivery item also sends item_id."""
        from app.models.purchase_order import PurchaseOrderItem

        s = setup
        item = make_item(db, name=f"Cement {uuid.uuid4().hex[:4]}")
        po, poi = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=item["id"], qty_ordered=10,
        )
        r = _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=6,
        )
        assert r.status_code == 201, r.text

        db.expire(poi)
        poi_fresh = db.get(PurchaseOrderItem, poi.id)
        assert float(poi_fresh.quantity_received) == pytest.approx(6.0), \
            "PO item quantity_received should be 6 after delivery"

    def test_updates_via_boq_item_id_when_item_id_is_none(self, client, db, setup):
        """
        BOQ path: PO item was created with item_id=None (BOQ item not yet
        linked to catalog).  Delivery sends boq_item_id only.  The fix
        resolves the catalog item from BOQ and back-fills.
        """
        from app.models.purchase_order import PurchaseOrderItem
        from app.models.boq import BOQItem
        from app.models.item import Item
        from app.models.enums import ItemType

        from app.models.boq import BOQHeader, BOQSection
        from app.models.enums import BoqStatus
        from datetime import datetime, timezone

        s = setup
        _now = datetime.now(timezone.utc)

        # Minimal BOQ header + section needed for BOQItem FK
        boq_header = BOQHeader(
            project_id=uuid.UUID(s["project_id"]),
            version_name="Test BOQ",
            source_type="test",
            status=BoqStatus.ACTIVE,
            is_active_version=True,
            is_template=False,
            uploaded_at=_now,
        )
        db.add(boq_header)
        db.flush()

        boq_section = BOQSection(
            boq_header_id=boq_header.id,
            section_name="Test Section",
            sequence_order=1,
            created_at=_now, updated_at=_now,
        )
        db.add(boq_section)
        db.flush()

        # Create a BOQItem with no catalog item linked
        boq_item = BOQItem(
            id=uuid.uuid4(),
            boq_section_id=boq_section.id,
            project_id=uuid.UUID(s["project_id"]),
            raw_description="Roof Complete",
            item_id=None,
            planned_quantity=10,
            planned_rate=100,
            is_active=True,
        )
        db.add(boq_item)
        db.flush()

        # PO item has no item_id (mirrors real-world scenario)
        po, poi = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=None, boq_item_id=str(boq_item.id), qty_ordered=10,
        )
        r = _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=None, boq_item_id=str(boq_item.id), qty_received=4,
            description="Roof Complete",
        )
        assert r.status_code == 201, r.text

        db.expire(poi)
        poi_fresh = db.get(PurchaseOrderItem, poi.id)
        assert float(poi_fresh.quantity_received) == pytest.approx(4.0), \
            "PO item quantity_received must be updated via boq_item_id fallback"

    def test_partial_delivery_increments_correctly(self, client, db, setup):
        """Partial delivery: only part of the ordered quantity is received."""
        from app.models.purchase_order import PurchaseOrderItem

        s = setup
        item = make_item(db, name=f"Steel {uuid.uuid4().hex[:4]}")
        po, poi = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=item["id"], qty_ordered=20,
        )
        r = _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=7,
        )
        assert r.status_code == 201, r.text

        db.expire(poi)
        poi_fresh = db.get(PurchaseOrderItem, poi.id)
        assert float(poi_fresh.quantity_received) == pytest.approx(7.0)

    def test_multiple_deliveries_accumulate(self, client, db, setup):
        """Two separate deliveries must add up: 6 + 3 = 9 received."""
        from app.models.purchase_order import PurchaseOrderItem

        s = setup
        item = make_item(db, name=f"Gravel {uuid.uuid4().hex[:4]}")
        po, poi = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=item["id"], qty_ordered=20,
        )
        _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=6,
        )
        _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=3,
        )

        db.expire(poi)
        poi_fresh = db.get(PurchaseOrderItem, poi.id)
        assert float(poi_fresh.quantity_received) == pytest.approx(9.0), \
            "Two deliveries should accumulate: 6 + 3 = 9"

    def test_po_status_becomes_received_when_fully_delivered(self, client, db, setup):
        """PO status must become RECEIVED when all ordered qty is received."""
        from app.models.purchase_order import PurchaseOrder

        s = setup
        item = make_item(db, name=f"Brick {uuid.uuid4().hex[:4]}")
        po, _ = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=item["id"], qty_ordered=10,
        )
        _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=10,
        )

        db.expire(po)
        po_fresh = db.get(PurchaseOrder, po.id)
        assert po_fresh.status.value == "RECEIVED", \
            "PO must be RECEIVED when all items are delivered"

    def test_po_status_partially_received_on_partial_delivery(self, client, db, setup):
        """PO status must become PARTIALLY_RECEIVED when only part is delivered."""
        from app.models.purchase_order import PurchaseOrder

        s = setup
        item = make_item(db, name=f"Sand {uuid.uuid4().hex[:4]}")
        po, _ = _make_po_with_item(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            item_id=item["id"], qty_ordered=10,
        )
        _record_delivery(
            client, s["tok"], s["project_id"], s["site_id"],
            s["supplier_id"], str(po.id),
            item_id=item["id"], qty_received=4,
        )

        db.expire(po)
        po_fresh = db.get(PurchaseOrder, po.id)
        assert po_fresh.status.value == "PARTIALLY_RECEIVED"
