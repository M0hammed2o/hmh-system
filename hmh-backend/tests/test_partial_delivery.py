"""
Tests for partial delivery and back-order tracking.

Verifies:
- A delivery with fewer items than the PO qty records correct quantities
- Outstanding quantities endpoint reflects remaining back-order
- A DELIVERY_DISCREPANCY alert is created when received < expected
- Two partial deliveries can together complete a PO
"""

import pytest
from datetime import datetime, timezone

from tests.conftest import auth, login, make_item, make_project, make_site, make_supplier, make_user


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def pd_setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    item     = make_item(db)
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        tok=tok,
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        item_id=item["id"],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_po(client, tok, project_id, site_id, supplier_id, qty=30):
    r = client.post(
        f"/api/v1/projects/{project_id}/purchase-orders/",
        json={
            "supplier_id": str(supplier_id),
            "site_id":     str(site_id),
            "notes":       "Partial delivery test PO",
            "items": [{
                "description":      "Test material",
                "quantity_ordered": qty,
                "unit":             "bags",
                "rate":             100.00,
                "vat_mode":         "INCLUSIVE",
                "vat_rate":         15.0,
            }],
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _create_delivery(client, tok, project_id, site_id, po_id, supplier_id,
                     qty_expected, qty_received, discrepancy_reason=None):
    item_payload = {
        "description":       "Test material",
        "quantity_expected": qty_expected,
        "quantity_received": qty_received,
        "unit":              "bags",
    }
    if discrepancy_reason:
        item_payload["discrepancy_reason"] = discrepancy_reason

    r = client.post(
        f"/api/v1/projects/{project_id}/deliveries/",
        json={
            "purchase_order_id": str(po_id),
            "supplier_id":       str(supplier_id),
            "site_id":           str(site_id),
            "delivery_date":     datetime.now(timezone.utc).isoformat(),
            "items":             [item_payload],
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_full_delivery_no_shortfall(client, db, pd_setup):
    """Full delivery matching PO quantity — items and quantities recorded correctly."""
    s   = pd_setup
    tok = s["tok"]
    po  = _create_po(client, tok, s["project_id"], s["site_id"], s["supplier_id"], qty=30)

    delivery = _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=30, qty_received=30,
    )

    assert delivery["id"] is not None
    items = delivery.get("items", [])
    if items:
        assert float(items[0]["quantity_received"]) == 30.0


def test_partial_delivery_records_shortfall(client, db, pd_setup):
    """Delivery of 20/30 bags records correct received and expected quantities."""
    s   = pd_setup
    tok = s["tok"]
    po  = _create_po(client, tok, s["project_id"], s["site_id"], s["supplier_id"], qty=30)

    delivery = _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=30, qty_received=20,
        discrepancy_reason="Supplier short-shipped. Back-order of 10 bags.",
    )

    assert delivery["id"] is not None
    items = delivery.get("items", [])
    if items:
        received = float(items[0]["quantity_received"])
        expected = float(items[0]["quantity_expected"])
        assert received == 20.0
        assert expected == 30.0
        assert expected - received == 10.0


def test_partial_delivery_po_outstanding(client, db, pd_setup):
    """Outstanding endpoint shows remaining quantity after a partial delivery."""
    s   = pd_setup
    tok = s["tok"]
    po  = _create_po(client, tok, s["project_id"], s["site_id"], s["supplier_id"], qty=30)

    _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=30, qty_received=20,
        discrepancy_reason="Short-shipped.",
    )

    r = client.get(
        f"/api/v1/purchase-orders/{po['id']}/outstanding",
        headers=auth(tok),
    )
    assert r.status_code == 200
    data = r.json()["data"]

    # get_po_outstanding returns: {items: [{quantity_outstanding, ...}], is_fully_received, ...}
    assert data["is_fully_received"] is False, "PO should not be fully received"
    items = data.get("items", [])
    assert len(items) > 0
    total_outstanding = sum(float(i["quantity_outstanding"]) for i in items)
    assert total_outstanding > 0, f"Outstanding qty should be > 0, got {total_outstanding}"


def test_partial_delivery_creates_discrepancy_alert(client, db, pd_setup):
    """Delivery where received < expected creates a DELIVERY_DISCREPANCY alert."""
    from app.models.alert import SystemAlert
    from app.models.enums import AlertType

    s   = pd_setup
    tok = s["tok"]
    po  = _create_po(client, tok, s["project_id"], s["site_id"], s["supplier_id"], qty=50)

    before = (
        db.query(SystemAlert)
        .filter(SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY)
        .count()
    )

    _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=50, qty_received=30,
        discrepancy_reason="20 bags missing.",
    )

    after = (
        db.query(SystemAlert)
        .filter(SystemAlert.alert_type == AlertType.DELIVERY_DISCREPANCY)
        .count()
    )

    assert after > before, (
        "A DELIVERY_DISCREPANCY alert should be created when received < expected"
    )


def test_second_delivery_clears_backorder(client, db, pd_setup):
    """Two partial deliveries summing to PO quantity leave zero outstanding."""
    s   = pd_setup
    tok = s["tok"]
    po  = _create_po(client, tok, s["project_id"], s["site_id"], s["supplier_id"], qty=30)

    _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=30, qty_received=20,
        discrepancy_reason="Short-shipped first batch.",
    )

    _create_delivery(
        client, tok, s["project_id"], s["site_id"], po["id"], s["supplier_id"],
        qty_expected=10, qty_received=10,
    )

    r = client.get(
        f"/api/v1/purchase-orders/{po['id']}/outstanding",
        headers=auth(tok),
    )
    assert r.status_code == 200
    data = r.json()["data"]

    assert data["is_fully_received"] is True, "PO should be fully received after two deliveries"
    items = data.get("items", [])
    total_outstanding = sum(float(i["quantity_outstanding"]) for i in items)
    assert total_outstanding == 0.0, f"Outstanding should be 0, got {total_outstanding}"
