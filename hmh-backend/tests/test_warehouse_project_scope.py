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

from tests.conftest import auth, login, make_item, make_lot, make_project, make_site, make_stock, make_user


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
