"""
Procurement Scenario Tests — Supplier Selection A/B/C

Scenario A: BOQ item + supplier assigned → preferred_supplier_id auto-set
Scenario B: BOQ item + no supplier       → preferred_supplier_id required (user picks)
Scenario C: Not in BOQ                   → Outside BOQ, supplier required

All tested at the API level.
"""
import uuid
import pytest
from sqlalchemy import insert
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import (
    make_user, make_project, make_site, make_lot, make_item,
    make_supplier, login, auth,
)
from app.models.boq import BOQHeader, BOQSection, BOQItem
from app.models.enums import BoqStatus


def _now():
    return datetime.now(timezone.utc)


def _make_boq_with_supplier(db, project_id, lot_id, item_id, supplier_id=None, description="Test Door"):
    """Create a BOQ item, optionally with a linked supplier."""
    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=f"BOQ {uuid.uuid4().hex[:6]}",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=_now(),
    )
    db.add(h)
    db.flush()
    s = BOQSection(
        boq_header_id=h.id,
        section_name="Section",
        sequence_order=1,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(s)
    db.flush()
    boq_item_id = uuid.uuid4()
    db.execute(
        insert(BOQItem).values(
            id=boq_item_id,
            boq_section_id=s.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id),
            item_id=uuid.UUID(item_id) if item_id else None,
            supplier_id=uuid.UUID(supplier_id) if supplier_id else None,
            raw_description=description,
            item_type="MATERIAL",
            unit="each",
            planned_quantity=5.0,
            planned_rate=1000.0,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()
    return str(boq_item_id)


# ── Scenario A: BOQ item + assigned supplier ──────────────────────────────────

def test_scenario_a_mr_with_preferred_supplier(client, db):
    """Scenario A: MR can be created with preferred_supplier_id from BOQ."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Solid Door", unit="each")
    supplier = make_supplier(db, name="ABC Doors")

    boq_id = _make_boq_with_supplier(
        db, proj["id"], lot["id"], item["id"],
        supplier_id=supplier["id"], description="Solid Door"
    )

    token = login(client, owner["email"], owner["password"])
    r = client.post(
        f"/api/v1/projects/{proj['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "preferred_supplier_id": supplier["id"],
            "items": [{
                "description": "Solid Door",
                "requested_quantity": 5,
                "unit": "each",
                "boq_item_id": boq_id,
            }],
        },
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["preferred_supplier_id"] == supplier["id"], \
        "MR must store preferred_supplier_id from BOQ"
    assert mr["items"][0]["boq_item_id"] == boq_id, \
        "MR item must link back to BOQ item"


def test_scenario_a_boq_search_returns_supplier(client, db):
    """Scenario A: BOQ search result includes supplier_name when BOQ has supplier."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Steel Window", unit="each")
    supplier = make_supplier(db, name="Premium Windows Ltd")

    _make_boq_with_supplier(
        db, proj["id"], lot["id"], item["id"],
        supplier_id=supplier["id"], description="Steel Window"
    )

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search?q=window",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    matches = [d for d in data if "Steel Window" in d["description"]]
    assert len(matches) == 1, "Should find the window item"
    assert matches[0]["supplier_name"] == "Premium Windows Ltd", \
        f"Supplier name must be returned. Got: {matches[0].get('supplier_name')}"
    assert matches[0]["preferred_supplier_id"] == supplier["id"], \
        "preferred_supplier_id must be returned in search result"


# ── Scenario B: BOQ item + no supplier ───────────────────────────────────────

def test_scenario_b_boq_search_no_supplier(client, db):
    """Scenario B: BOQ search result has null supplier when BOQ has no supplier."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Floor Tile", unit="m2")

    _make_boq_with_supplier(
        db, proj["id"], lot["id"], item["id"],
        supplier_id=None, description="Floor Tile"  # No supplier
    )

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search?q=tile",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    matches = [d for d in data if "Floor Tile" in d["description"]]
    assert len(matches) == 1, "Should find the tile item"
    assert matches[0]["supplier_name"] is None, \
        "supplier_name must be None when no supplier assigned"
    assert matches[0]["preferred_supplier_id"] is None, \
        "preferred_supplier_id must be None when no supplier assigned"


def test_scenario_b_mr_with_manual_supplier(client, db):
    """Scenario B: MR can be created with a manually selected supplier (no BOQ supplier)."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Gravel", unit="m3")
    supplier = make_supplier(db, name="SA Quarry")  # user manually selects this

    boq_id = _make_boq_with_supplier(
        db, proj["id"], lot["id"], item["id"],
        supplier_id=None, description="Gravel"  # No BOQ supplier
    )

    token = login(client, owner["email"], owner["password"])
    r = client.post(
        f"/api/v1/projects/{proj['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "preferred_supplier_id": supplier["id"],  # manually selected
            "items": [{
                "description": "Gravel",
                "requested_quantity": 10,
                "unit": "m3",
                "boq_item_id": boq_id,
            }],
        },
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["preferred_supplier_id"] == supplier["id"]


# ── Scenario C: Not in BOQ ────────────────────────────────────────────────────

def test_scenario_c_outside_boq_mr(client, db):
    """Scenario C: MR for item not in BOQ — must include supplier and remarks."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    supplier = make_supplier(db, name="Ad Hoc Supplier")

    token = login(client, owner["email"], owner["password"])
    r = client.post(
        f"/api/v1/projects/{proj['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "preferred_supplier_id": supplier["id"],
            "items": [{
                "description": "Emergency Pump Rental",  # NOT in BOQ
                "requested_quantity": 1,
                "unit": "day",
                "remarks": "Outside BOQ — one-time purchase",
            }],
        },
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["preferred_supplier_id"] == supplier["id"]
    assert mr["items"][0]["remarks"] == "Outside BOQ — one-time purchase"


def test_scenario_c_mr_without_supplier_still_creates(client, db):
    """
    Backend allows MR without preferred_supplier_id (supplier is optional at MR creation).
    Supplier is required at PO conversion stage, not MR stage.
    """
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])

    token = login(client, owner["email"], owner["password"])
    r = client.post(
        f"/api/v1/projects/{proj['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "items": [{"description": "Sand", "requested_quantity": 2, "unit": "m3"}],
        },
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["preferred_supplier_id"] is None


# ── Supplier override: office role can change BOQ supplier ────────────────────

def test_supplier_override_by_office_user(client, db):
    """Office users can override the BOQ-assigned supplier on an MR."""
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_ADMIN")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Brick", unit="each")

    supplier_a = make_supplier(db, name="Original Supplier")
    supplier_b = make_supplier(db, name="Override Supplier")

    from tests.conftest import make_user_project_access
    make_user_project_access(db, office["id"], proj["id"])

    _make_boq_with_supplier(
        db, proj["id"], lot["id"], item["id"],
        supplier_id=supplier_a["id"], description="Brick"
    )

    # Office user overrides to supplier_b
    token = login(client, office["email"], office["password"])
    r = client.post(
        f"/api/v1/projects/{proj['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "preferred_supplier_id": supplier_b["id"],  # Override!
            "items": [{"description": "Brick", "requested_quantity": 100, "unit": "each"}],
        },
    )
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["preferred_supplier_id"] == supplier_b["id"], \
        "Office user must be able to override BOQ supplier"
