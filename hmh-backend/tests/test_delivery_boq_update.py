"""
Tests: receiving a delivery updates the site dashboard BOQ material summary.

Covers:
  1. Delivered qty appears after a delivery is received directly to a lot
  2. Used qty appears after recording material usage at the lot
  3. Status transitions: OK → LOW → OVER_BOQ as usage climbs
  4. Dedup fix — same material in two BOQ sections collapses to one row:
     a. planned qty is summed (26 + 13 = 39)
     b. delivered qty counts stock from the alias section
     c. unit-case mismatch ("Rolls" vs "rolls") still deduplicates
  5. Non-catalog items (boq_item_id only, no item_id) also track delivered qty
"""

import json
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import insert

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_lot,
    make_item, make_boq_item, make_supplier,
)


# ── Shared helper ──────────────────────────────────────────────────────────────

def _receive(client, tok, *, project_id, site_id, supplier_id, lot_id, items):
    """POST to receive-with-document with destination=LOT (no file)."""
    return client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":           project_id,
            "site_id":              site_id,
            "supplier_id":          supplier_id,
            "delivery_note_number": f"DN-{uuid.uuid4().hex[:6]}",
            "lot_id":               lot_id,
            "destination":          "LOT",
            "receiver_name":        "Test Receiver",
            "receiver_signature":   "TR",
            "items_json":           json.dumps(items),
        },
        headers=auth(tok),
    )


def _summary(client, tok, site_id, lot_id):
    """GET the material summary for a lot."""
    return client.get(
        f"/api/v1/site-dashboard/{site_id}/lots/{lot_id}/material-summary",
        headers=auth(tok),
    )


def _make_boq_item_raw(db, *, project_id, lot_id, item_id=None,
                       description="Brickforce", unit="rolls", qty=26.0,
                       section_name="Section A"):
    """Create a BOQ item via core INSERT (avoids GENERATED column issue).
    Returns the new boq_item_id as a string.
    """
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus, ItemType

    now = datetime.now(timezone.utc)

    hdr = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=f"BOQ {section_name}",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=now,
    )
    db.add(hdr)
    db.flush()

    sec = BOQSection(
        boq_header_id=hdr.id,
        section_name=section_name,
        sequence_order=1,
        created_at=now, updated_at=now,
    )
    db.add(sec)
    db.flush()

    boq_id = uuid.uuid4()
    db.execute(
        insert(BOQItem).values(
            id=boq_id,
            boq_section_id=sec.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id),
            item_id=uuid.UUID(item_id) if item_id else None,
            raw_description=description,
            item_type=ItemType.MATERIAL.value,
            unit=unit,
            planned_quantity=qty,
            planned_rate=10.0,
            sort_order=1,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    return str(boq_id)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    lot      = make_lot(db, project_id=project["id"], site_id=site["id"], lot_number="1")
    item     = make_item(db, name="Cement 50kg", unit="bag")
    supplier = make_supplier(db)
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        lot_id=lot["id"],
        item_id=item["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


# ── Test 1: delivery updates delivered_qty ────────────────────────────────────

class TestDeliveryUpdatesBOQ:

    def test_delivered_qty_zero_before_delivery(self, client, db, setup):
        s = setup
        boq_id = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=s["item_id"], qty=50.0,
        )
        db.commit()

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert float(row["boq_allocated_qty"]) == pytest.approx(50.0)
        assert float(row["delivered_qty"])     == pytest.approx(0.0)
        assert float(row["used_qty"])          == pytest.approx(0.0)

    def test_receive_delivery_updates_delivered_qty(self, client, db, setup):
        s = setup
        boq_id = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=s["item_id"], qty=50.0,
        )
        db.commit()

        r = _receive(
            client, s["tok"],
            project_id=s["project_id"],
            site_id=s["site_id"],
            supplier_id=s["supplier_id"],
            lot_id=s["lot_id"],
            items=[{
                "description":       "Cement 50kg",
                "unit":              "bag",
                "item_id":           s["item_id"],
                "boq_item_id":       boq_id,
                "quantity_expected": 30,
                "quantity_received": 30,
                "quantity_rejected": 0,
            }],
        )
        assert r.status_code == 201, r.text

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert float(row["boq_allocated_qty"]) == pytest.approx(50.0)
        assert float(row["delivered_qty"])     == pytest.approx(30.0)
        assert float(row["used_qty"])          == pytest.approx(0.0)
        assert float(row["remaining_qty"])     == pytest.approx(50.0)  # allocated - used

    def test_multiple_deliveries_accumulate(self, client, db, setup):
        s = setup
        boq_id = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=s["item_id"], qty=100.0,
        )
        db.commit()

        item = {"description": "Cement 50kg", "unit": "bag",
                "item_id": s["item_id"], "boq_item_id": boq_id,
                "quantity_received": 0, "quantity_rejected": 0}

        for qty in [20, 30]:
            r = _receive(
                client, s["tok"],
                project_id=s["project_id"],
                site_id=s["site_id"],
                supplier_id=s["supplier_id"],
                lot_id=s["lot_id"],
                items=[{**item, "quantity_received": qty}],
            )
            assert r.status_code == 201, r.text

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        row = r.json()["data"][0]
        assert float(row["delivered_qty"]) == pytest.approx(50.0)  # 20 + 30


# ── Test 2: usage updates used_qty ────────────────────────────────────────────

class TestUsageUpdatesBOQ:

    def test_record_usage_updates_used_qty(self, client, db, setup):
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = setup
        boq_id = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=s["item_id"], qty=50.0,
        )
        db.commit()

        # First receive the stock so there is something to use
        r = _receive(
            client, s["tok"],
            project_id=s["project_id"],
            site_id=s["site_id"],
            supplier_id=s["supplier_id"],
            lot_id=s["lot_id"],
            items=[{
                "description": "Cement 50kg", "unit": "bag",
                "item_id": s["item_id"], "boq_item_id": boq_id,
                "quantity_received": 40, "quantity_rejected": 0,
            }],
        )
        assert r.status_code == 201, r.text

        # Record 15 bags used at lot level
        now = datetime.now(timezone.utc)
        db.add(StockLedger(
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            lot_id=uuid.UUID(s["lot_id"]),
            item_id=uuid.UUID(s["item_id"]),
            movement_type=MovementType.USAGE,
            reference_type="test",
            quantity_in=0,
            quantity_out=15,
            movement_date=now,
            created_at=now,
        ))
        db.commit()

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert float(row["delivered_qty"])  == pytest.approx(40.0)
        assert float(row["used_qty"])       == pytest.approx(15.0)
        assert float(row["remaining_qty"])  == pytest.approx(35.0)  # 50 allocated - 15 used

    def test_status_transitions_with_usage(self, client, db, setup):
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = setup
        _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=s["item_id"], qty=100.0,
        )
        db.commit()

        def _add_usage(qty):
            now = datetime.now(timezone.utc)
            db.add(StockLedger(
                project_id=uuid.UUID(s["project_id"]),
                site_id=uuid.UUID(s["site_id"]),
                lot_id=uuid.UUID(s["lot_id"]),
                item_id=uuid.UUID(s["item_id"]),
                movement_type=MovementType.USAGE,
                reference_type="test",
                quantity_in=0, quantity_out=qty,
                movement_date=now, created_at=now,
            ))
            db.commit()

        def _get_status():
            r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
            return r.json()["data"][0]["status"]

        # No usage → OK
        assert _get_status() == "OK"

        # 87 used of 100 allocated (87% used, 13% remaining → LOW)
        _add_usage(87)
        assert _get_status() == "LOW"

        # 15 more → 102 total used, exceeds 100 allocated → OVER_BOQ
        _add_usage(15)
        assert _get_status() == "OVER_BOQ"


# ── Test 3: BOQ deduplication across sections ─────────────────────────────────

class TestBOQDeduplication:

    def test_same_material_two_sections_shows_one_row(self, client, db, setup):
        """Two BOQ entries for the same material in different sections produce
        one row with their allocated quantities summed.

        Uses item_id=None (non-catalog) so raw_description is the key and the
        returned description matches what we filter on.
        """
        s = setup

        # Section A: Brickforce, 26 rolls — no catalog link
        _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Brickforce", unit="rolls", qty=26.0,
            section_name="Section A",
        )
        # Section B: same description + unit, 13 rolls
        _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Brickforce", unit="rolls", qty=13.0,
            section_name="Section B",
        )
        db.commit()

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        data = r.json()["data"]

        brickforce_rows = [row for row in data if "brickforce" in (row.get("description") or "").lower()]
        assert len(brickforce_rows) == 1, (
            f"Expected 1 deduplicated row, got {len(brickforce_rows)}: "
            f"{[r['description'] for r in data]}"
        )
        assert float(brickforce_rows[0]["boq_allocated_qty"]) == pytest.approx(39.0)

    def test_unit_case_mismatch_still_deduplicates(self, client, db, setup):
        """'Rolls' and 'rolls' normalise to the same key — should not create two rows."""
        s = setup

        _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Hoop Iron", unit="Rolls", qty=20.0,
            section_name="Foundation",
        )
        _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Hoop Iron", unit="rolls", qty=10.0,
            section_name="Walls",
        )
        db.commit()

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        data = r.json()["data"]

        hoop_rows = [row for row in data if "hoop iron" in (row.get("description") or "").lower()]
        assert len(hoop_rows) == 1, f"Expected 1 row after dedup, got {len(hoop_rows)}: {[r['description'] for r in data]}"
        assert float(hoop_rows[0]["boq_allocated_qty"]) == pytest.approx(30.0)

    def test_delivery_linked_to_alias_section_counted_for_canonical(self, client, db, setup):
        """Delivery linked to the alias (Section B) BOQ item is still reflected
        in the deduplicated canonical row's delivered_qty.

        Uses item_id=None so stock is tracked via boq_item_id path (the alias
        folding logic in lot_material_summary).
        """
        s = setup

        # Section A wins as canonical (higher qty)
        boq_a = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Brickforce", unit="rolls", qty=26.0,
            section_name="Section A",
        )
        # Section B becomes the alias (lower qty, discarded during dedup)
        boq_b = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,
            description="Brickforce", unit="rolls", qty=13.0,
            section_name="Section B",
        )
        db.commit()

        # Receive delivery linked to Section B (the alias boq_item_id)
        r = _receive(
            client, s["tok"],
            project_id=s["project_id"],
            site_id=s["site_id"],
            supplier_id=s["supplier_id"],
            lot_id=s["lot_id"],
            items=[{
                "description":       "Brickforce",
                "unit":              "rolls",
                "boq_item_id":       boq_b,   # alias section
                "quantity_received": 13,
                "quantity_rejected": 0,
            }],
        )
        assert r.status_code == 201, r.text

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200
        data = r.json()["data"]

        brickforce_rows = [row for row in data if "brickforce" in (row.get("description") or "").lower()]
        assert len(brickforce_rows) == 1, "Dedup must produce exactly one Brickforce row"
        row = brickforce_rows[0]
        assert float(row["boq_allocated_qty"]) == pytest.approx(39.0), "Total allocation must be 26+13"
        assert float(row["delivered_qty"])     == pytest.approx(13.0), "Alias delivery must be counted"


# ── Test 4: non-catalog items (no item_id) ────────────────────────────────────

class TestNonCatalogBOQ:

    def test_non_catalog_boq_item_tracks_delivered_qty(self, client, db, setup):
        """BOQ items without a catalog link (item_id=None) track delivered_qty
        via boq_item_id on the StockLedger row."""
        s = setup

        # BOQ item with NO catalog item_id
        boq_id = _make_boq_item_raw(
            db,
            project_id=s["project_id"], lot_id=s["lot_id"],
            item_id=None,          # non-catalog
            description="River Sand",
            unit="m3",
            qty=20.0,
        )
        db.commit()

        # Receive delivery: no item_id, only boq_item_id
        r = _receive(
            client, s["tok"],
            project_id=s["project_id"],
            site_id=s["site_id"],
            supplier_id=s["supplier_id"],
            lot_id=s["lot_id"],
            items=[{
                "description":       "River Sand",
                "unit":              "m3",
                "boq_item_id":       boq_id,
                "quantity_received": 8,
                "quantity_rejected": 0,
            }],
        )
        assert r.status_code == 201, r.text

        r = _summary(client, s["tok"], s["site_id"], s["lot_id"])
        assert r.status_code == 200

        sand_rows = [row for row in r.json()["data"]
                     if "sand" in (row.get("description") or "").lower()]
        assert len(sand_rows) >= 1
        sand = sand_rows[0]
        assert float(sand["boq_allocated_qty"]) == pytest.approx(20.0)
        assert float(sand["delivered_qty"])     == pytest.approx(8.0)
