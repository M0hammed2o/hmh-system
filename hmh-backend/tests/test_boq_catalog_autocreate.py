"""
Tests for Option B: BOQ-backed delivery items auto-create a catalog Item when
item_id is absent, so stock is always updated.

Coverage:
 1. BOQ item with no catalog link → catalog Item auto-created on delivery
 2. BOQItem.item_id is permanently updated after first delivery
 3. StockLedger entry written for the auto-created item
 4. Second delivery reuses same catalog item — no duplicate created
 5. BOQ item already has item_id → no new Item created, existing id used
 6. Existing catalog item with matching normalized_name reused (no duplicate)
 7. delivery endpoint returns unlinked_count=0 for BOQ-backed items
"""

import json
import uuid
import pytest
from sqlalchemy import insert

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_item, make_supplier,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _make_lot(db, project_id: str) -> str:
    """Create a minimal Lot and return its id string."""
    from app.models.lot import Lot
    lot = Lot(
        project_id=uuid.UUID(project_id),
        lot_number=f"LOT-AUTO-{uuid.uuid4().hex[:8]}",
        created_at=_now(), updated_at=_now(),
    )
    db.add(lot)
    db.flush()
    return str(lot.id)


def _make_boq_item_no_catalog(db, project_id: str, lot_id: str,
                               description: str = "Roof Tiles",
                               unit: str = "m2") -> str:
    """Create a BOQItem with item_id=None (unlinked). Returns boq_item_id string."""
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus

    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name="Test BOQ",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=_now(),
    )
    db.add(h)
    db.flush()

    from app.models.boq import BOQSection
    sec_obj = BOQSection(
        boq_header_id=h.id,
        section_name="Test Section",
        sequence_order=1,
        created_at=_now(), updated_at=_now(),
    )
    db.add(sec_obj)
    db.flush()

    from app.models.boq import BOQItem
    boq_item_id = uuid.uuid4()
    db.execute(
        insert(BOQItem).values(
            id=boq_item_id,
            boq_section_id=sec_obj.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id),
            item_id=None,          # ← deliberately unlinked
            raw_description=description,
            item_type="MATERIAL",
            unit=unit,
            planned_quantity=50.0,
            planned_rate=100.0,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()
    return str(boq_item_id)


def _post_delivery(client, tok, project_id, site_id, supplier_id, items,
                   lot_id=None, destination="SITE_STORE"):
    data = {
        "project_id":           project_id,
        "site_id":              site_id,
        "supplier_id":          supplier_id,
        "delivery_note_number": f"DN-{uuid.uuid4().hex[:6]}",
        "destination":          destination,
        "items_json":           json.dumps(items),
        "receiver_name":        "Test Receiver",
        "receiver_signature":   "TR",
    }
    if lot_id:
        data["lot_id"] = lot_id
    return client.post(
        "/api/v1/deliveries/receive-with-document",
        data=data,
        headers=auth(tok),
    )


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    lot_id   = _make_lot(db, project["id"])
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        lot_id=lot_id,
        tok=tok,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

class TestBOQCatalogAutoCreate:

    def test_auto_creates_catalog_item(self, client, db, setup):
        """When BOQ item has no catalog link, a new Item is created on delivery."""
        from app.models.item import Item

        s = setup
        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Roof Tiles", unit="m2")

        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                           s["supplier_id"],
                           items=[{
                               "description":       "Roof Tiles",
                               "unit":              "m2",
                               "quantity_expected": 20,
                               "quantity_received": 20,
                               "quantity_rejected": 0,
                               "boq_item_id":       boq_item_id,
                           }],
                           lot_id=s["lot_id"],
                           destination="LOT")
        assert r.status_code == 201, r.text

        catalog = db.query(Item).filter(Item.normalized_name == "roof tiles").first()
        assert catalog is not None, "Catalog item was not auto-created"
        assert catalog.default_unit == "m2"

    def test_boq_item_id_permanently_linked(self, client, db, setup):
        """BOQItem.item_id is set after first delivery so future deliveries reuse it."""
        from app.models.boq import BOQItem

        s = setup
        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Steel Beam 100mm")

        _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                       s["supplier_id"],
                       items=[{
                           "description":       "Steel Beam 100mm",
                           "unit":              "pcs",
                           "quantity_expected": 5,
                           "quantity_received": 5,
                           "quantity_rejected": 0,
                           "boq_item_id":       boq_item_id,
                       }],
                       lot_id=s["lot_id"],
                       destination="LOT")

        db.expire_all()
        boq = db.get(BOQItem, uuid.UUID(boq_item_id))
        assert boq.item_id is not None, "BOQItem.item_id should be set after delivery"

    def test_stock_ledger_written(self, client, db, setup):
        """A StockLedger entry is created for the auto-linked catalog item."""
        from app.models.stock import StockLedger

        s = setup
        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Glass Panel")

        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                           s["supplier_id"],
                           items=[{
                               "description":       "Glass Panel",
                               "unit":              "pcs",
                               "quantity_expected": 10,
                               "quantity_received": 8,
                               "quantity_rejected": 2,
                               "boq_item_id":       boq_item_id,
                           }],
                           lot_id=s["lot_id"],
                           destination="LOT")
        assert r.status_code == 201, r.text

        delivery_id = uuid.UUID(r.json()["data"]["delivery_id"])
        ledger = (
            db.query(StockLedger)
            .filter(
                StockLedger.reference_id == delivery_id,
                StockLedger.boq_item_id == uuid.UUID(boq_item_id),
            )
            .first()
        )
        assert ledger is not None, "StockLedger entry should exist"
        assert float(ledger.quantity_in) == pytest.approx(8.0)

    def test_second_delivery_reuses_catalog_item(self, client, db, setup):
        """Submitting a second delivery for the same BOQ item does not create a duplicate catalog item."""
        from app.models.item import Item

        s = setup
        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Copper Wire 6mm")

        item_payload = lambda: [{  # noqa
            "description":       "Copper Wire 6mm",
            "unit":              "m",
            "quantity_expected": 100,
            "quantity_received": 100,
            "quantity_rejected": 0,
            "boq_item_id":       boq_item_id,
        }]

        _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                       s["supplier_id"], items=item_payload(),
                       lot_id=s["lot_id"], destination="LOT")
        _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                       s["supplier_id"], items=item_payload(),
                       lot_id=s["lot_id"], destination="LOT")

        count = (
            db.query(Item)
            .filter(Item.normalized_name == "copper wire 6mm")
            .count()
        )
        assert count == 1, f"Expected 1 catalog item, got {count}"

    def test_already_linked_boq_item_not_duplicated(self, client, db, setup):
        """If BOQ item already has item_id, no new Item is created."""
        from app.models.item import Item

        s = setup
        catalog = make_item(db, name="Pre-linked Tile")
        from tests.conftest import make_boq_item
        boq = make_boq_item(db, s["project_id"], s["lot_id"], catalog["id"], qty=30.0)

        before_count = db.query(Item).count()

        _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                       s["supplier_id"],
                       items=[{
                           "description":       "Pre-linked Tile",
                           "unit":              "bag",
                           "quantity_expected": 10,
                           "quantity_received": 10,
                           "quantity_rejected": 0,
                           "item_id":           catalog["id"],
                           "boq_item_id":       boq["boq_item_id"],
                       }])

        after_count = db.query(Item).count()
        assert after_count == before_count, "No new Item should be created when already linked"

    def test_reuses_existing_catalog_item_by_name(self, client, db, setup):
        """When a catalog item with the same normalized_name exists, it is reused instead of duplicated."""
        from app.models.item import Item

        s = setup
        existing = make_item(db, name="Concrete Block")
        # Override normalized_name to plain lowercase (make_item adds hex suffix)
        existing_obj = db.get(Item, uuid.UUID(existing["id"]))
        existing_obj.normalized_name = "concrete block"
        db.flush()

        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Concrete Block")

        _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                       s["supplier_id"],
                       items=[{
                           "description":       "Concrete Block",
                           "unit":              "pcs",
                           "quantity_expected": 50,
                           "quantity_received": 50,
                           "quantity_rejected": 0,
                           "boq_item_id":       boq_item_id,
                       }],
                       lot_id=s["lot_id"],
                       destination="LOT")

        count = db.query(Item).filter(Item.normalized_name == "concrete block").count()
        assert count == 1, "Should reuse existing catalog item, not create a duplicate"

    def test_unlinked_count_zero_for_boq_backed(self, client, db, setup):
        """Response data.unlinked_count is 0 when all items are BOQ-backed."""
        s = setup
        boq_item_id = _make_boq_item_no_catalog(db, s["project_id"], s["lot_id"],
                                                 description="Floor Screed")

        r = _post_delivery(client, s["tok"], s["project_id"], s["site_id"],
                           s["supplier_id"],
                           items=[{
                               "description":       "Floor Screed",
                               "unit":              "m2",
                               "quantity_expected": 40,
                               "quantity_received": 40,
                               "quantity_rejected": 0,
                               "boq_item_id":       boq_item_id,
                           }],
                           lot_id=s["lot_id"],
                           destination="LOT")
        assert r.status_code == 201, r.text
        assert r.json()["data"]["unlinked_count"] == 0
