"""
BOQ validation tests — verify MATERIAL/LABOUR separation, math correctness,
and no duplication across the warehouse BOQ summary and search endpoints.
"""
import uuid
import pytest
from sqlalchemy import insert
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import (
    make_user, make_project, make_site, make_lot, make_item,
    login, auth,
)
from app.models.boq import BOQHeader, BOQSection, BOQItem
from app.models.enums import BoqStatus


def _now():
    return datetime.now(timezone.utc)


def _make_boq(
    db,
    project_id: str,
    lot_id: str,
    item_id: str = None,
    description: str = "Test Material Item",
    item_type: str = "MATERIAL",
    unit: str = "each",
    qty: float = 5.0,
) -> None:
    """Insert a BOQ item with configurable description and type (skips GENERATED column)."""
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
        section_name="Test Section",
        sequence_order=1,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(s)
    db.flush()
    db.execute(
        insert(BOQItem).values(
            id=uuid.uuid4(),
            boq_section_id=s.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id),
            item_id=uuid.UUID(item_id) if item_id else None,
            raw_description=description,
            item_type=item_type,
            unit=unit,
            planned_quantity=qty,
            planned_rate=100.0,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()


# ── Warehouse BOQ summary: MATERIAL/LABOUR separation ─────────────────────────

def test_warehouse_boq_summary_excludes_labour(client, db):
    """GET /projects/{id}/warehouse/boq-summary must not include LABOUR items."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    door_item = make_item(db, name="External Door", unit="each", item_type="MATERIAL")

    _make_boq(db, proj["id"], lot["id"], item_id=door_item["id"],
              description="External Door", unit="each", qty=5.0, item_type="MATERIAL")
    _make_boq(db, proj["id"], lot["id"], description="Bricklayer Labour",
              unit="day", qty=5.0, item_type="LABOUR")

    token = login(client, owner["email"], owner["password"])
    r = client.get(f"/api/v1/projects/{proj['id']}/warehouse/boq-summary", headers=auth(token))
    assert r.status_code == 200, r.text

    descriptions = [d["description"] for d in r.json()["data"]]
    assert any("External Door" in d for d in descriptions), f"MATERIAL item must appear. Got: {descriptions}"
    assert not any("Labour" in d for d in descriptions), f"LABOUR item must NOT appear. Got: {descriptions}"


def test_warehouse_boq_summary_math_across_lots(client, db):
    """BOQ summary must correctly sum planned_quantity across multiple lots."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot1 = make_lot(db, proj["id"], site["id"], lot_number="1")
    lot2 = make_lot(db, proj["id"], site["id"], lot_number="2")
    item = make_item(db, name="Steel Door", unit="each", item_type="MATERIAL")

    _make_boq(db, proj["id"], lot1["id"], item_id=item["id"],
              description="Steel Door", unit="each", qty=3.0)
    _make_boq(db, proj["id"], lot2["id"], item_id=item["id"],
              description="Steel Door", unit="each", qty=7.0)

    token = login(client, owner["email"], owner["password"])
    r = client.get(f"/api/v1/projects/{proj['id']}/warehouse/boq-summary", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # Groups by item_id → single row with total 3+7=10
    matching = [d for d in data if "Steel Door" in d.get("description", "")]
    assert len(matching) > 0, f"Steel Door must appear. Got: {[d['description'] for d in data]}"
    total_qty = sum(d["total_boq_qty"] for d in matching)
    assert total_qty == pytest.approx(10.0, rel=0.01), f"Expected 10.0, got {total_qty}"


def test_warehouse_boq_summary_no_double_count_same_lot(client, db):
    """Two BOQ entries for same item_id in same lot → must sum, not drop one."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])
    item = make_item(db, name="Plywood Sheet", unit="sheet", item_type="MATERIAL")

    _make_boq(db, proj["id"], lot["id"], item_id=item["id"],
              description="Plywood Sheet", unit="sheet", qty=4.0)
    _make_boq(db, proj["id"], lot["id"], item_id=item["id"],
              description="Plywood Sheet", unit="sheet", qty=6.0)

    token = login(client, owner["email"], owner["password"])
    r = client.get(f"/api/v1/projects/{proj['id']}/warehouse/boq-summary", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    matching = [d for d in data if "Plywood Sheet" in d.get("description", "")]
    total_qty = sum(d["total_boq_qty"] for d in matching)
    assert total_qty == pytest.approx(10.0, rel=0.01), f"Expected 4+6=10.0, got {total_qty}"


def test_warehouse_boq_summary_lot_count(client, db):
    """lots_count must reflect distinct lots for each aggregated item."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot1 = make_lot(db, proj["id"], site["id"], lot_number="A")
    lot2 = make_lot(db, proj["id"], site["id"], lot_number="B")
    lot3 = make_lot(db, proj["id"], site["id"], lot_number="C")
    item = make_item(db, name="Window Frame", unit="each", item_type="MATERIAL")

    for lot in [lot1, lot2, lot3]:
        _make_boq(db, proj["id"], lot["id"], item_id=item["id"],
                  description="Window Frame", unit="each", qty=2.0)

    token = login(client, owner["email"], owner["password"])
    r = client.get(f"/api/v1/projects/{proj['id']}/warehouse/boq-summary", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    matching = [d for d in data if "Window Frame" in d.get("description", "")]
    assert len(matching) > 0, "Window Frame must appear"
    assert matching[0]["lots_count"] >= 3, f"Expected lots_count >= 3, got {matching[0]['lots_count']}"


# ── BOQ search: MATERIAL/LABOUR separation ─────────────────────────────────────

def test_boq_search_excludes_labour(client, db):
    """GET /projects/{id}/boq/items/search must not return LABOUR items."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])

    _make_boq(db, proj["id"], lot["id"], description="Timber Beam", unit="m", qty=10.0)
    _make_boq(db, proj["id"], lot["id"], description="Site Foreman Labour",
              unit="day", qty=5.0, item_type="LABOUR")

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert any("Timber Beam" in d["description"] for d in data), \
        f"MATERIAL item must appear. Got: {[d['description'] for d in data]}"
    assert not any("Labour" in d["description"] for d in data), \
        f"LABOUR item must NOT appear. Got: {[d['description'] for d in data]}"


def test_boq_search_filters_by_query(client, db):
    """GET /projects/{id}/boq/items/search?q=door only returns matching descriptions."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])

    _make_boq(db, proj["id"], lot["id"], description="Solid Timber Door", unit="each", qty=5.0)
    _make_boq(db, proj["id"], lot["id"], description="Aluminium Window", unit="each", qty=8.0)

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search?q=door",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    descriptions = [d["description"] for d in data]
    assert any("Door" in d for d in descriptions), f"Door must match. Got: {descriptions}"
    assert not any("Window" in d for d in descriptions), f"Window must NOT match 'door'. Got: {descriptions}"


def test_boq_search_deduplicates_by_description_unit(client, db):
    """Same description+unit across multiple lots appears only once in search results."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot1 = make_lot(db, proj["id"], site["id"], lot_number="X")
    lot2 = make_lot(db, proj["id"], site["id"], lot_number="Y")

    _make_boq(db, proj["id"], lot1["id"], description="Roof Tile", unit="m2", qty=20.0)
    _make_boq(db, proj["id"], lot2["id"], description="Roof Tile", unit="m2", qty=30.0)

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search?q=roof",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    roof_entries = [d for d in data if "Roof Tile" in d["description"]]
    assert len(roof_entries) == 1, f"Deduplicated: expected 1 entry, got {len(roof_entries)}"


def test_boq_search_empty_query_returns_all_materials(client, db):
    """Empty query returns all MATERIAL items (up to 20)."""
    owner = make_user(db, role="OWNER")
    proj = make_project(db, owner["id"])
    site = make_site(db, proj["id"])
    lot = make_lot(db, proj["id"], site["id"])

    _make_boq(db, proj["id"], lot["id"], description="Cement Bag", unit="bag", qty=50.0)
    _make_boq(db, proj["id"], lot["id"], description="Sand m3", unit="m3", qty=10.0)
    _make_boq(db, proj["id"], lot["id"], description="Brick Labour",
              unit="day", qty=3.0, item_type="LABOUR")

    token = login(client, owner["email"], owner["password"])
    r = client.get(
        f"/api/v1/projects/{proj['id']}/boq/items/search",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    descriptions = [d["description"] for d in data]
    assert any("Cement Bag" in d for d in descriptions)
    assert any("Sand m3" in d for d in descriptions)
    assert not any("Labour" in d for d in descriptions)
