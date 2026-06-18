"""
Tests for project warehouse add-material and adjust-stock endpoints.

Coverage:
 1. Add material → StockLedger entry created in project warehouse
 2. Add material auto-creates a catalog Item when name is new
 3. Add material reuses existing catalog Item when normalized_name matches (no duplicate)
 4. Add material with no name → 422
 5. Add material with qty <= 0 → 422
 6. Adjust stock CORRECTION_ADD → quantity_in written
 7. Adjust stock DAMAGED → quantity_out written
 8. Adjust stock invalid type → 422
 9. Adjust stock invalid item_id → 404
10. History endpoint shows PROJECT_WAREHOUSE_ADD and ADJUSTMENT movements
"""

import json
import uuid
import pytest

from tests.conftest import auth, login, make_user, make_project, make_site, make_item


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"])
    tok     = login(client, owner["email"], owner["password"])
    return dict(project_id=project["id"], site_id=site["id"], tok=tok)


def _add(client, tok, project_id, name, quantity, unit=None, notes=None):
    body = {"name": name, "quantity": quantity}
    if unit:  body["unit"]  = unit
    if notes: body["notes"] = notes
    return client.post(
        f"/api/v1/projects/{project_id}/warehouse/add-material",
        json=body,
        headers=auth(tok),
    )


def _adjust(client, tok, project_id, item_id, adj_type, quantity, notes=None):
    body = {"item_id": item_id, "adjustment_type": adj_type, "quantity": quantity}
    if notes: body["notes"] = notes
    return client.post(
        f"/api/v1/projects/{project_id}/warehouse/adjust",
        json=body,
        headers=auth(tok),
    )


# ── add-material tests ────────────────────────────────────────────────────────

class TestAddProjectMaterial:

    def test_creates_stock_ledger_entry(self, client, db, setup):
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = setup
        r = _add(client, s["tok"], s["project_id"], "Bag of Screws", 5, unit="bags")
        assert r.status_code == 201, r.text

        entry_id = uuid.UUID(r.json()["data"]["id"])
        ledger = db.get(StockLedger, entry_id)
        assert ledger is not None
        assert float(ledger.quantity_in)  == pytest.approx(5.0)
        assert float(ledger.quantity_out) == pytest.approx(0.0)
        assert str(ledger.project_id)     == s["project_id"]
        assert ledger.site_id  is None
        assert ledger.lot_id   is None
        assert ledger.movement_type == MovementType.DELIVERY_RECEIVED
        assert ledger.reference_type == "PROJECT_WAREHOUSE_ADD"

    def test_auto_creates_catalog_item(self, client, db, setup):
        from app.models.item import Item

        s = setup
        r = _add(client, s["tok"], s["project_id"], "Copper Nails", 100, unit="pcs")
        assert r.status_code == 201, r.text
        assert r.json()["data"]["created_item"] is True

        item = db.query(Item).filter(Item.normalized_name == "copper nails").first()
        assert item is not None
        assert item.default_unit == "pcs"

    def test_reuses_existing_catalog_item(self, client, db, setup):
        from app.models.item import Item

        s = setup
        existing = make_item(db, name="Masking Tape")
        existing_obj = db.get(Item, uuid.UUID(existing["id"]))
        existing_obj.normalized_name = "masking tape"
        db.flush()

        r = _add(client, s["tok"], s["project_id"], "Masking Tape", 20, unit="rolls")
        assert r.status_code == 201, r.text
        assert r.json()["data"]["created_item"] is False
        assert r.json()["data"]["item_id"] == existing["id"]

        count = db.query(Item).filter(Item.normalized_name == "masking tape").count()
        assert count == 1, "Should not create a duplicate catalog item"

    def test_missing_name_returns_422(self, client, db, setup):
        s = setup
        r = _add(client, s["tok"], s["project_id"], "  ", 5)
        assert r.status_code == 422

    def test_zero_quantity_returns_422(self, client, db, setup):
        s = setup
        r = _add(client, s["tok"], s["project_id"], "Sand", 0)
        assert r.status_code == 422

    def test_negative_quantity_returns_422(self, client, db, setup):
        s = setup
        r = _add(client, s["tok"], s["project_id"], "Sand", -5)
        assert r.status_code == 422

    def test_stock_appears_in_warehouse_get(self, client, db, setup):
        s = setup
        _add(client, s["tok"], s["project_id"], "Yellow Rope", 30, unit="m")

        r = client.get(
            f"/api/v1/projects/{s['project_id']}/warehouse/",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        names = [item["item_name"] for item in r.json()["data"]]
        assert "Yellow Rope" in names


# ── adjust-stock tests ────────────────────────────────────────────────────────

class TestAdjustProjectWarehouseStock:

    def _seed_stock(self, client, tok, project_id, name, qty, unit="pcs"):
        r = _add(client, tok, project_id, name, qty, unit=unit)
        assert r.status_code == 201, r.text
        return r.json()["data"]["item_id"]

    def test_correction_add_writes_quantity_in(self, client, db, setup):
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Steel Pins", 10)

        r = _adjust(client, s["tok"], s["project_id"], item_id, "CORRECTION_ADD", 5,
                    notes="Found extra box")
        assert r.status_code == 201, r.text

        entry_id = uuid.UUID(r.json()["data"]["id"])
        ledger = db.get(StockLedger, entry_id)
        assert float(ledger.quantity_in)  == pytest.approx(5.0)
        assert float(ledger.quantity_out) == pytest.approx(0.0)
        assert ledger.movement_type == MovementType.ADJUSTMENT_ADD
        assert ledger.reference_type == "ADJUSTMENT_CORRECTION_ADD"
        assert str(ledger.project_id) == s["project_id"]
        assert ledger.site_id is None
        assert ledger.lot_id  is None

    def test_damaged_writes_quantity_out(self, client, db, setup):
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Glass Pane", 20)

        r = _adjust(client, s["tok"], s["project_id"], item_id, "DAMAGED", 3)
        assert r.status_code == 201, r.text

        entry_id = uuid.UUID(r.json()["data"]["id"])
        ledger = db.get(StockLedger, entry_id)
        assert float(ledger.quantity_out) == pytest.approx(3.0)
        assert float(ledger.quantity_in)  == pytest.approx(0.0)
        assert ledger.movement_type == MovementType.ADJUSTMENT_SUBTRACT

    def test_invalid_adjustment_type_returns_422(self, client, db, setup):
        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Wire", 50)
        r = _adjust(client, s["tok"], s["project_id"], item_id, "INVALID_TYPE", 1)
        assert r.status_code == 422

    def test_unknown_item_id_returns_404(self, client, db, setup):
        s = setup
        r = _adjust(client, s["tok"], s["project_id"], str(uuid.uuid4()), "CORRECTION_ADD", 1)
        assert r.status_code == 404

    def test_net_stock_reflects_adjustment(self, client, db, setup):
        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Tile Adhesive", 100, "bags")

        # Remove 15 damaged
        _adjust(client, s["tok"], s["project_id"], item_id, "DAMAGED", 15)
        # Add 5 correction
        _adjust(client, s["tok"], s["project_id"], item_id, "CORRECTION_ADD", 5)

        # Expected net: 100 - 15 + 5 = 90
        r = client.get(
            f"/api/v1/projects/{s['project_id']}/warehouse/",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        items = r.json()["data"]
        tile = next((i for i in items if i["item_name"] == "Tile Adhesive"), None)
        assert tile is not None
        assert float(tile["on_hand"]) == pytest.approx(90.0)

    def test_all_adjustment_types_accepted(self, client, db, setup):
        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Cable Ties", 200)
        for adj_type in ["CORRECTION_ADD", "RETURNED", "OTHER_ADD",
                         "CORRECTION_SUB", "DAMAGED", "LOST", "OTHER_SUB"]:
            r = _adjust(client, s["tok"], s["project_id"], item_id, adj_type, 1)
            assert r.status_code == 201, f"{adj_type} failed: {r.text}"

    def test_history_shows_add_and_adjust_movements(self, client, db, setup):
        s = setup
        item_id = self._seed_stock(client, s["tok"], s["project_id"], "Rivets", 50)
        _adjust(client, s["tok"], s["project_id"], item_id, "DAMAGED", 5)

        r = client.get(
            f"/api/v1/projects/{s['project_id']}/warehouse/history",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        ref_types = {m["reference_type"] for m in r.json()["data"]}
        assert "PROJECT_WAREHOUSE_ADD"      in ref_types
        assert "ADJUSTMENT_DAMAGED"         in ref_types
