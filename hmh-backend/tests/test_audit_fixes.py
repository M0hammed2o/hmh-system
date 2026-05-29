"""
Regression tests for audit-identified defects:

  1. link_delivery_item — NameError fix + site_id=None (Phase 3B)
  2. receive-with-document — LOT destination without lot_id now returns 422
  3. receive-with-document — invalid destination now returns 422
"""

import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import (
    auth, login,
    make_user, make_project, make_site, make_lot, make_supplier, make_item,
    make_stock, make_user_project_access,
)


@pytest.fixture()
def audit_setup(db: Session, client: TestClient):
    owner   = make_user(db, role="OWNER")
    office  = make_user(db, role="OFFICE_ADMIN")
    project = make_project(db, owner["id"])
    site    = make_site(db, project["id"], "Site A")
    lot     = make_lot(db, project["id"], site["id"], "A-1")
    item    = make_item(db, "Brick 220mm")
    supplier = make_supplier(db, "Best Bricks Ltd")
    make_user_project_access(db, office["id"], project["id"])
    db.flush()
    return {
        "owner": owner, "office": office,
        "project": project, "site": site, "lot": lot,
        "item": item, "supplier": supplier,
    }


# ── Defect 1: link_delivery_item ─────────────────────────────────────────────

def test_link_delivery_item_writes_stock_to_project_warehouse(
    db: Session, client: TestClient, audit_setup: dict
):
    """
    Regression: link_delivery_item previously crashed with NameError because
    the return value of get_and_check_project_resource was not captured.

    After the fix, the endpoint must:
      - succeed with 200
      - write a StockLedger row with site_id=NULL, lot_id=NULL (project warehouse)
    """
    tok = login(client, audit_setup["office"]["email"], audit_setup["office"]["password"])

    # 1. Create a delivery with an UNLINKED item (no item_id in the line)
    items_json = json.dumps([{
        "description":       "Brick 220mm",
        "quantity_received": 100.0,
        # No item_id — this creates an unlinked delivery item
    }])
    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  audit_setup["project"]["id"],
            "site_id":     audit_setup["site"]["id"],
            "supplier_id": audit_setup["supplier"]["id"],
            "destination": "SITE_STORE",
            "items_json":  items_json,
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text
    result = r.json()["data"]
    delivery_id    = result["delivery_id"]
    unlinked_count = result["unlinked_count"]
    assert unlinked_count == 1, "Expected 1 unlinked item"
    assert result["stock_updated_count"] == 0, "Unlinked item must not update stock"

    # 2. Get the delivery to find the delivery_item_id
    r2 = client.get(
        f"/api/v1/deliveries/{delivery_id}",
        headers=auth(tok),
    )
    assert r2.status_code == 200, r2.text
    d_items = r2.json()["data"]["items"]
    assert len(d_items) >= 1
    d_item_id = d_items[0]["id"]

    # 3. Link the delivery item — this was the crashing endpoint
    r3 = client.patch(
        f"/api/v1/deliveries/{delivery_id}/items/{d_item_id}/link",
        json={"item_id": audit_setup["item"]["id"]},
        headers=auth(tok),
    )
    assert r3.status_code == 200, f"link_delivery_item failed: {r3.text}"

    # 4. Verify StockLedger row: site_id=NULL, lot_id=NULL (project warehouse)
    row = db.execute(text("""
        SELECT site_id, lot_id, quantity_in
        FROM stock_ledger
        WHERE reference_id = :did
          AND movement_type = 'DELIVERY_RECEIVED'
          AND reference_type = 'delivery'
    """), {"did": delivery_id}).fetchone()

    assert row is not None, "No StockLedger row written after link"
    assert row[0] is None, f"site_id must be NULL (Phase 3B), got {row[0]}"
    assert row[1] is None, f"lot_id must be NULL, got {row[1]}"
    assert float(row[2]) == 100.0, f"Expected quantity_in=100, got {row[2]}"


def test_link_delivery_item_cannot_relink(
    db: Session, client: TestClient, audit_setup: dict
):
    """Linking an already-linked delivery item must return 422."""
    tok = login(client, audit_setup["office"]["email"], audit_setup["office"]["password"])

    # Create delivery with LINKED item (item_id provided)
    items_json = json.dumps([{
        "description":       "Brick 220mm",
        "quantity_received": 50.0,
        "item_id":           audit_setup["item"]["id"],
    }])
    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  audit_setup["project"]["id"],
            "site_id":     audit_setup["site"]["id"],
            "supplier_id": audit_setup["supplier"]["id"],
            "destination": "SITE_STORE",
            "items_json":  items_json,
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text
    delivery_id = r.json()["data"]["delivery_id"]

    r2 = client.get(f"/api/v1/deliveries/{delivery_id}", headers=auth(tok))
    d_item_id = r2.json()["data"]["items"][0]["id"]

    item2 = make_item(db, "Cement Bag")
    db.flush()

    # Try to re-link to a different item — must reject
    r3 = client.patch(
        f"/api/v1/deliveries/{delivery_id}/items/{d_item_id}/link",
        json={"item_id": item2["id"]},
        headers=auth(tok),
    )
    assert r3.status_code == 422, f"Expected 422 for re-link, got {r3.status_code}: {r3.text}"


# ── Defect 2: LOT destination without lot_id ─────────────────────────────────

def test_receive_lot_destination_without_lot_id_returns_422(
    db: Session, client: TestClient, audit_setup: dict
):
    """destination=LOT without lot_id must return 422, not silently go to project warehouse."""
    tok = login(client, audit_setup["office"]["email"], audit_setup["office"]["password"])

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  audit_setup["project"]["id"],
            "site_id":     audit_setup["site"]["id"],
            "supplier_id": audit_setup["supplier"]["id"],
            "destination": "LOT",
            # lot_id intentionally omitted
            "items_json":  json.dumps([{"description": "Steel bar", "quantity_received": 10.0}]),
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    assert "lot_id" in r.json().get("detail", "").lower() or \
           "lot_id" in str(r.json()).lower(), \
        "Error message should mention lot_id"


def test_receive_invalid_destination_returns_422(
    db: Session, client: TestClient, audit_setup: dict
):
    """An invalid destination string must return 422."""
    tok = login(client, audit_setup["office"]["email"], audit_setup["office"]["password"])

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  audit_setup["project"]["id"],
            "site_id":     audit_setup["site"]["id"],
            "supplier_id": audit_setup["supplier"]["id"],
            "destination": "SITE_WAREHOUSE",  # invalid value
            "items_json":  json.dumps([{"description": "Steel bar", "quantity_received": 10.0}]),
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 422, f"Expected 422 for invalid destination, got {r.status_code}"


def test_receive_lot_destination_with_lot_id_succeeds(
    db: Session, client: TestClient, audit_setup: dict
):
    """destination=LOT with a valid lot_id must succeed and route stock to lot."""
    tok = login(client, audit_setup["office"]["email"], audit_setup["office"]["password"])

    items_json = json.dumps([{
        "description":       "Brick 220mm",
        "quantity_received": 25.0,
        "item_id":           audit_setup["item"]["id"],
    }])
    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        data={
            "project_id":  audit_setup["project"]["id"],
            "site_id":     audit_setup["site"]["id"],
            "supplier_id": audit_setup["supplier"]["id"],
            "destination": "LOT",
            "lot_id":      audit_setup["lot"]["id"],
            "items_json":  items_json,
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text
    delivery_id = r.json()["data"]["delivery_id"]

    # Verify stock went to lot level
    row = db.execute(text("""
        SELECT lot_id, quantity_in
        FROM stock_ledger
        WHERE reference_id = :did
          AND movement_type = 'DELIVERY_RECEIVED'
    """), {"did": delivery_id}).fetchone()

    assert row is not None, "No StockLedger row for LOT delivery"
    assert str(row[0]) == audit_setup["lot"]["id"], \
        f"Expected lot_id={audit_setup['lot']['id']}, got {row[0]}"
    assert float(row[1]) == 25.0
