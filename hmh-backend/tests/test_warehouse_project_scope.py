"""
Phase 3A Validation Tests — stock_ledger.site_id nullable

Tests:
  1. StockLedger rows with site_id=None can be created (project warehouse entries)
  2. Existing site-scoped rows are unaffected
  3. GET /projects/{id}/warehouse/ returns project-warehouse stock (site_id IS NULL)
  4. POST /projects/{id}/warehouse/transfer dispatches from project warehouse to site warehouse
  5. POST /projects/{id}/warehouse/return moves stock back to project warehouse
  6. GET /sites/{id}/warehouse/ still works for site-scoped stock
  7. READ_ONLY user cannot transfer

All tests share a single DB rollback — no permanent data written.
"""

import pytest
import uuid
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_item, make_lot, make_project, make_site, make_stock, make_user, make_user_project_access


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def wh_setup(db: Session, client: TestClient):
    """
    Creates:
      - project with one site and one lot
      - an item
      - 100 units in project warehouse  (site_id=None, lot_id=None)
      - 20  units in site warehouse     (site_id=site, lot_id=None)
    """
    owner   = make_user(db, role="OWNER")
    office  = make_user(db, role="OFFICE_ADMIN")
    ro_user = make_user(db, role="READ_ONLY")

    project = make_project(db, owner["id"])
    site    = make_site(db, project["id"], "Block A")
    lot     = make_lot(db, project["id"], site["id"], "1")
    item    = make_item(db, "Steel Rebar 12mm")

    # Project warehouse stock (site_id = None) — the fix we are validating
    make_stock(db, project["id"], None, item["id"], qty=100.0)

    # Site warehouse stock (site_id = site, lot_id = None)
    make_stock(db, project["id"], site["id"], item["id"], qty=20.0)
    make_user_project_access(db, office["id"], project["id"])
    make_user_project_access(db, ro_user["id"], project["id"])
    db.flush()

    return {
        "owner": owner, "office": office, "ro_user": ro_user,
        "project": project, "site": site, "lot": lot, "item": item,
    }


# ── ORM-level tests (no HTTP) ─────────────────────────────────────────────────

def test_stock_ledger_site_id_nullable(db: Session, wh_setup: dict):
    """StockLedger rows with site_id=None must exist in the DB (migration 0015)."""
    from sqlalchemy import text
    result = db.execute(text(
        "SELECT COUNT(*) FROM stock_ledger "
        "WHERE project_id = :pid AND site_id IS NULL AND lot_id IS NULL"
    ), {"pid": wh_setup["project"]["id"]}).scalar()
    assert result == 1, (
        "Expected exactly one project-warehouse row (site_id IS NULL). "
        "If this fails, migration 0015 has NOT been applied to the test DB."
    )


def test_site_scoped_stock_unaffected(db: Session, wh_setup: dict):
    """Existing site-scoped rows must still be present and queryable."""
    from sqlalchemy import text
    result = db.execute(text(
        "SELECT COUNT(*) FROM stock_ledger "
        "WHERE project_id = :pid AND site_id = :sid AND lot_id IS NULL"
    ), {"pid": wh_setup["project"]["id"], "sid": wh_setup["site"]["id"]}).scalar()
    assert result == 1


def test_project_warehouse_balance_correct(db: Session, wh_setup: dict):
    """Net balance in project warehouse = 100 (all quantity_in, no quantity_out)."""
    from sqlalchemy import text
    result = db.execute(text(
        "SELECT SUM(quantity_in) - SUM(quantity_out) "
        "FROM stock_ledger "
        "WHERE project_id = :pid AND site_id IS NULL AND lot_id IS NULL AND item_id = :iid"
    ), {"pid": wh_setup["project"]["id"], "iid": wh_setup["item"]["id"]}).scalar()
    assert float(result) == 100.0


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

def test_get_project_warehouse_stock(db: Session, client: TestClient, wh_setup: dict):
    """GET /projects/{id}/warehouse/ returns only project-warehouse stock."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])
    r = client.get(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/",
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list)
    items = {i["item_id"]: i for i in data}
    item_id = wh_setup["item"]["id"]
    assert item_id in items, f"Item not found in project warehouse. Got: {list(items.keys())}"
    assert items[item_id]["on_hand"] == 100.0


def test_get_site_warehouse_stock_unaffected(db: Session, client: TestClient, wh_setup: dict):
    """GET /sites/{id}/warehouse/ still returns site-scoped stock independently."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])
    r = client.get(
        f"/api/v1/sites/{wh_setup['site']['id']}/warehouse/",
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    items = {i["item_id"]: i for i in data}
    item_id = wh_setup["item"]["id"]
    assert item_id in items
    assert items[item_id]["on_hand"] == 20.0


def test_transfer_project_warehouse_to_site(db: Session, client: TestClient, wh_setup: dict):
    """POST /projects/{id}/warehouse/transfer dispatches stock from project warehouse to site."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.post(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/transfer",
        json={
            "item_id": wh_setup["item"]["id"],
            "site_id": wh_setup["site"]["id"],
            "quantity": 30.0,
            "notes": "Phase 3A test dispatch",
        },
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["quantity"] == 30.0
    assert result["new_balance"] == 70.0   # 100 - 30


def test_return_from_site_to_project_warehouse(db: Session, client: TestClient, wh_setup: dict):
    """POST /projects/{id}/warehouse/return moves stock back to project warehouse."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.post(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/return",
        json={
            "item_id": wh_setup["item"]["id"],
            "site_id": wh_setup["site"]["id"],
            "quantity": 10.0,
            "notes": "Excess from site returned",
        },
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["quantity"] == 10.0


def test_read_only_cannot_transfer(db: Session, client: TestClient, wh_setup: dict):
    """READ_ONLY role must be blocked from warehouse transfers (403)."""
    tok = login(client, wh_setup["ro_user"]["email"], wh_setup["ro_user"]["password"])

    r = client.post(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/transfer",
        json={
            "item_id": wh_setup["item"]["id"],
            "site_id": wh_setup["site"]["id"],
            "quantity": 5.0,
        },
        headers=auth(tok),
    )
    assert r.status_code == 403


def test_transfer_rejects_insufficient_stock(db: Session, client: TestClient, wh_setup: dict):
    """Transferring more than available project warehouse balance returns 422."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.post(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/transfer",
        json={
            "item_id": wh_setup["item"]["id"],
            "site_id": wh_setup["site"]["id"],
            "quantity": 9999.0,
        },
        headers=auth(tok),
    )
    assert r.status_code == 422


def test_project_warehouse_history(db: Session, client: TestClient, wh_setup: dict):
    """GET /projects/{id}/warehouse/history returns project-warehouse movements."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.get(
        f"/api/v1/projects/{wh_setup['project']['id']}/warehouse/history",
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # The opening balance row should appear
    assert isinstance(data, list)
    assert len(data) >= 1


# ── Phase 3B tests — delivery routing to project warehouse ────────────────────

def test_site_store_delivery_routes_to_project_warehouse(
    db: Session, client: TestClient, wh_setup: dict
):
    """
    Phase 3B: SITE_STORE deliveries must write stock to site_id=NULL (project
    warehouse) rather than site_id=X (legacy per-site store).
    """
    import json as _json
    from tests.conftest import make_supplier

    supplier  = make_supplier(db, "Test Cement Co")
    tok       = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    items_json = _json.dumps([{
        "description":       "Cement 50kg",
        "quantity_received": 20.0,
        "item_id":           wh_setup["item"]["id"],
    }])

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  wh_setup["project"]["id"],
            "site_id":     wh_setup["site"]["id"],
            "supplier_id": supplier["id"],
            "destination": "SITE_STORE",
            "items_json":  items_json,
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text
    result = r.json()["data"]
    assert result["stock_updated_count"] >= 1

    # Verify stock landed in project warehouse (site_id IS NULL)
    from sqlalchemy import text
    count = db.execute(text(
        "SELECT SUM(quantity_in) FROM stock_ledger "
        "WHERE project_id = :pid AND site_id IS NULL "
        "  AND item_id = :iid AND movement_type = 'DELIVERY_RECEIVED'"
    ), {"pid": wh_setup["project"]["id"], "iid": wh_setup["item"]["id"]}).scalar()
    assert float(count or 0) == 20.0, (
        f"Expected 20 units in project warehouse (site_id IS NULL), got {count}. "
        "Phase 3B delivery routing fix may not have been applied."
    )


def test_lot_delivery_routes_to_lot_stock(
    db: Session, client: TestClient, wh_setup: dict
):
    """
    Deliveries with destination=LOT must write to lot-level stock (lot_id=Y).
    Lot deliveries should never bypass warehouse (site_id=NULL, lot_id=Y).
    """
    import json as _json
    from tests.conftest import make_supplier

    supplier = make_supplier(db, "Rebar Supplier")
    tok      = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    items_json = _json.dumps([{
        "description":       "Rebar 12mm",
        "quantity_received": 15.0,
        "item_id":           wh_setup["item"]["id"],
    }])

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  wh_setup["project"]["id"],
            "site_id":     wh_setup["site"]["id"],
            "supplier_id": supplier["id"],
            "destination": "LOT",
            "lot_id":      wh_setup["lot"]["id"],
            "items_json":  items_json,
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text

    from sqlalchemy import text
    count = db.execute(text(
        "SELECT SUM(quantity_in) FROM stock_ledger "
        "WHERE project_id = :pid AND lot_id = :lid "
        "  AND item_id = :iid AND movement_type = 'DELIVERY_RECEIVED'"
    ), {
        "pid": wh_setup["project"]["id"],
        "lid": wh_setup["lot"]["id"],
        "iid": wh_setup["item"]["id"],
    }).scalar()
    assert float(count or 0) == 15.0


def test_legacy_site_warehouse_endpoint_still_works(
    db: Session, client: TestClient, wh_setup: dict
):
    """
    Phase 3B: Legacy /sites/{id}/warehouse/ endpoint must remain accessible.
    Backward compatibility guarantee.
    """
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.get(
        f"/api/v1/sites/{wh_setup['site']['id']}/warehouse/",
        headers=auth(tok),
    )
    # The endpoint must respond 200 (may return empty if no per-site stock)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["data"], list)


# ── Global Main Warehouse tests ───────────────────────────────────────────────

def test_global_main_warehouse_returns_stock_without_project_filter(
    db: Session, client: TestClient, wh_setup: dict
):
    """GET /warehouse/main/ must return stock across ALL projects (no project selector)."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.get("/api/v1/warehouse/main/", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list)

    # The item we put in wh_setup (100 units, site_id=None) must appear
    item_id = wh_setup["item"]["id"]
    project_id = wh_setup["project"]["id"]
    matches = [row for row in data if row["item_id"] == item_id and row["project_id"] == project_id]
    assert len(matches) == 1, f"Expected 1 match for item={item_id}, got {len(matches)}"
    assert matches[0]["on_hand"] == 100.0
    # Must include project_name
    assert "project_name" in matches[0]
    assert "project_code" in matches[0]


def test_global_main_warehouse_includes_project_info(
    db: Session, client: TestClient, wh_setup: dict
):
    """Every row in GET /warehouse/main/ must carry project_id and project_name."""
    tok = login(client, wh_setup["owner"]["email"], wh_setup["owner"]["password"])

    r = client.get("/api/v1/warehouse/main/", headers=auth(tok))
    assert r.status_code == 200, r.text
    for row in r.json()["data"]:
        assert "project_id"   in row, "project_id missing from global warehouse row"
        assert "project_name" in row, "project_name missing from global warehouse row"
        assert "item_id"      in row
        assert "on_hand"      in row


def test_global_main_warehouse_shows_multi_project_stock(
    db: Session, client: TestClient, wh_setup: dict
):
    """When two projects have main warehouse stock, both appear in the global view."""
    from tests.conftest import make_project, make_item, make_stock

    owner = wh_setup["owner"]
    # Second project + second item
    project2 = make_project(db, owner["id"])
    item2     = make_item(db, "Cement Bags 50kg")
    make_stock(db, project2["id"], None, item2["id"], qty=50.0)
    db.flush()

    tok = login(client, owner["email"], owner["password"])
    r = client.get("/api/v1/warehouse/main/", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    project_ids = {row["project_id"] for row in data}
    assert wh_setup["project"]["id"] in project_ids, "First project missing from global view"
    assert project2["id"] in project_ids, "Second project missing from global view"


def test_global_main_warehouse_excludes_site_stock(
    db: Session, client: TestClient, wh_setup: dict
):
    """Site-scoped stock (site_id IS NOT NULL) must NOT appear in /warehouse/main/."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.get("/api/v1/warehouse/main/", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # Site-scoped stock: project + site = wh_setup has 20 units at site level
    # These must NOT be in the global main view
    item_id = wh_setup["item"]["id"]
    project_id = wh_setup["project"]["id"]

    # The global view should show 100 (main warehouse), not 120 (main + site)
    matches = [row for row in data if row["item_id"] == item_id and row["project_id"] == project_id]
    assert len(matches) == 1
    assert matches[0]["on_hand"] == 100.0, (
        f"Expected 100 (main only), got {matches[0]['on_hand']} — "
        "site-scoped stock is leaking into /warehouse/main/"
    )


def test_global_main_warehouse_history(
    db: Session, client: TestClient, wh_setup: dict
):
    """GET /warehouse/main/history must return movements with project_name."""
    tok = login(client, wh_setup["office"]["email"], wh_setup["office"]["password"])

    r = client.get("/api/v1/warehouse/main/history", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list)
    # The opening-balance row from wh_setup must be present
    assert len(data) >= 1
    for row in data:
        assert "project_name" in row
        assert "movement_type" in row
