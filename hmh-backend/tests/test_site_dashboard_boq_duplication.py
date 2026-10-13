"""
Staff dashboard — BOQ duplication against delivered stock.

The reported symptom (Dassenhoek) is duplicate BOQ quantities and costs on
the staff dashboard, appearing alongside delivery notes. These tests pin the
behaviour that produces it and the behaviour that must replace it.

The important property: one physical delivery must be reported once, however
many BOQ rows happen to describe the same material.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.enums import ItemType, MovementType
from tests.conftest import (
    auth, login, make_item, make_lot, make_project, make_site, make_user,
)


def _now():
    return datetime.now(timezone.utc)


def _boq_header_section(db, project_id):
    """A BOQ header + section to hang items from."""
    from app.models.boq import BOQHeader, BOQSection
    from app.models.enums import BoqStatus

    header = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name="Dashboard duplication fixture",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=_now(),
    )
    db.add(header)
    db.flush()
    section = BOQSection(
        boq_header_id=header.id,
        section_name="Section A",
        sequence_order=1,
        created_at=_now(), updated_at=_now(),
    )
    db.add(section)
    db.flush()
    return header, section


def _boq_item(db, project_id, section, *, description, unit, qty, item_id=None,
              lot_id=None, site_id=None, rate=100.0):
    """
    Core INSERT, not the ORM: BOQItem.planned_total is a GENERATED column and
    the ORM would try to write it.
    """
    from sqlalchemy import insert

    from app.models.boq import BOQItem

    new_id = uuid.uuid4()
    db.execute(
        insert(BOQItem).values(
            id=new_id,
            boq_section_id=section.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id) if lot_id else None,
            site_id=uuid.UUID(site_id) if site_id else None,
            item_id=uuid.UUID(item_id) if item_id else None,
            raw_description=description,
            item_type="MATERIAL",
            unit=unit,
            planned_quantity=qty,
            planned_rate=rate,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()
    return db.get(BOQItem, new_id)


def _deliver(db, project_id, lot_id, item_id, qty, boq_item_id=None):
    """One DELIVERY_RECEIVED movement into a lot — what a delivery note writes."""
    from app.models.stock import StockLedger

    row = StockLedger(
        project_id=uuid.UUID(project_id),
        site_id=None,
        lot_id=uuid.UUID(lot_id),
        item_id=uuid.UUID(item_id) if item_id else None,
        boq_item_id=boq_item_id,
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="delivery",
        reference_id=uuid.uuid4(),
        quantity_in=qty,
        quantity_out=0,
        unit="bag",
        movement_date=_now(),
        entered_by=None,
        created_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    lot = make_lot(db, project["id"], site["id"], lot_number="12")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    header, section = _boq_header_section(db, project["id"])
    return {
        "owner": owner, "project": project, "site": site,
        "lot": lot, "item": item, "section": section,
    }


def _summary(client, token, world):
    r = client.get(
        f"/api/v1/site-dashboard/{world['site']['id']}/lots/{world['lot']['id']}/material-summary",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── The defect ────────────────────────────────────────────────────────────────

def test_one_delivery_is_not_counted_twice_when_two_boq_rows_share_an_item(db, client, world):
    """
    Two BOQ rows for the SAME catalogue item, worded slightly differently.

    The dashboard collapses duplicates on (description, unit), so different
    wording keeps both rows. Delivered quantity is then looked up by item_id
    — which both rows share — so a single 100-bag delivery is reported on
    both rows as 100, showing 200 delivered against one physical delivery.
    """
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]

    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=item["id"], lot_id=lot["id"])
    # Same material, same catalogue item, different wording on the paper BOQ.
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bags",
              unit="bag", qty=40, item_id=item["id"], lot_id=lot["id"])

    _deliver(db, project["id"], lot["id"], item["id"], 100)
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    total_delivered = sum(float(r["delivered_qty"]) for r in rows)
    assert total_delivered == 100.0, (
        f"one 100-bag delivery reported as {total_delivered} across "
        f"{len(rows)} BOQ row(s): {[(r['description'], r['delivered_qty']) for r in rows]}"
    )


def test_three_boq_rows_sharing_an_item_still_report_the_delivery_once(db, client, world):
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]

    for desc in ("Cement 42.5N 50kg bag", "Cement 42.5N  50kg bag.", "CEMENT 42.5N 50KG BAGS"):
        _boq_item(db, project["id"], section, description=desc, unit="bag",
                  qty=30, item_id=item["id"], lot_id=lot["id"])

    _deliver(db, project["id"], lot["id"], item["id"], 90)
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    assert sum(float(r["delivered_qty"]) for r in rows) == 90.0


def test_usage_is_not_counted_twice_either(db, client, world):
    """The same attribution bug applies to quantity_out."""
    from app.models.stock import StockLedger

    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=item["id"], lot_id=lot["id"])
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bags",
              unit="bag", qty=40, item_id=item["id"], lot_id=lot["id"])

    _deliver(db, project["id"], lot["id"], item["id"], 100)
    db.add(StockLedger(
        project_id=uuid.UUID(project["id"]), site_id=None, lot_id=uuid.UUID(lot["id"]),
        item_id=uuid.UUID(item["id"]), movement_type=MovementType.USAGE,
        reference_type="usage_log", reference_id=uuid.uuid4(),
        quantity_in=0, quantity_out=25, unit="bag",
        movement_date=_now(), entered_by=None, created_at=_now(),
    ))
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    assert sum(float(r["used_qty"]) for r in rows) == 25.0


# ── Behaviour that must not regress ───────────────────────────────────────────

def test_genuinely_different_materials_are_reported_separately(db, client, world):
    """The fix must not collapse rows that are actually different materials."""
    project, lot, section = world["project"], world["lot"], world["section"]
    cement = world["item"]
    sand = make_item(db, name="River sand", unit="m3")

    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=cement["id"], lot_id=lot["id"])
    _boq_item(db, project["id"], section, description="River sand",
              unit="m3", qty=10, item_id=sand["id"], lot_id=lot["id"])

    _deliver(db, project["id"], lot["id"], cement["id"], 60)
    _deliver(db, project["id"], lot["id"], sand["id"], 10)
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    by_qty = {float(r["delivered_qty"]) for r in rows}
    assert len(rows) == 2, [r["description"] for r in rows]
    assert by_qty == {60.0, 10.0}


def test_allocation_across_sections_still_totals_correctly(db, client, world):
    """
    Collapsing duplicates must keep summing their planned quantities — the
    row should show the total allocation, not just one section's share.
    """
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=26, item_id=item["id"], lot_id=lot["id"])
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=13, item_id=item["id"], lot_id=lot["id"])
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    assert len(rows) == 1
    assert float(rows[0]["boq_allocated_qty"]) == 39.0


def test_non_catalog_boq_rows_are_unaffected(db, client, world):
    """
    A BOQ row with no catalogue link matches stock by boq_item_id instead.
    That path must keep working and must not merge with catalogue rows.

    The ledger row still carries an item_id (the column is NOT NULL); what
    makes this the boq_item_id path is the BOQ row having none.
    """
    project, lot, section = world["project"], world["lot"], world["section"]
    scaffold_item = make_item(db, name="Scaffold hire unit", unit="week")
    bi = _boq_item(db, project["id"], section, description="Scaffold hire",
                   unit="week", qty=4, item_id=None, lot_id=lot["id"])
    _deliver(db, project["id"], lot["id"], scaffold_item["id"], 4, boq_item_id=bi.id)
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)

    scaffold = [r for r in rows if "Scaffold" in r["description"]]
    assert len(scaffold) == 1
    assert float(scaffold[0]["delivered_qty"]) == 4.0


def test_a_lot_with_no_deliveries_reports_zero(db, client, world):
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=item["id"], lot_id=lot["id"])
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)
    assert sum(float(r["delivered_qty"]) for r in rows) == 0.0


def test_another_projects_delivery_does_not_leak_in(db, client, world):
    """Other projects must remain unaffected by anything done here."""
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    other_project = make_project(db, world["owner"]["id"])
    other_site = make_site(db, other_project["id"])
    other_lot = make_lot(db, other_project["id"], other_site["id"], lot_number="99")

    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=item["id"], lot_id=lot["id"])
    _deliver(db, project["id"], lot["id"], item["id"], 50)
    # A delivery of the same item into a different project's lot.
    _deliver(db, other_project["id"], other_lot["id"], item["id"], 500)
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _summary(client, token, world)
    assert sum(float(r["delivered_qty"]) for r in rows) == 50.0


# ── The same defect on the project-scoped endpoint ────────────────────────────

def _project_summary(client, token, world):
    r = client.get(
        f"/api/v1/projects/{world['project']['id']}/lots/{world['lot']['id']}/material-summary",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_project_lot_summary_does_not_duplicate_used_quantities(db, client, world):
    """
    `/projects/{id}/lots/{id}/material-summary` carries its own copy of the
    deduplication logic and had the same description-only key. Its per-row
    stock queries filter by item_id, so two rows sharing one would each
    report the material's full usage.
    """
    from app.models.stock import StockLedger

    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=60, item_id=item["id"], lot_id=lot["id"])
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bags",
              unit="bag", qty=40, item_id=item["id"], lot_id=lot["id"])

    db.add(StockLedger(
        project_id=uuid.UUID(project["id"]), site_id=None, lot_id=uuid.UUID(lot["id"]),
        item_id=uuid.UUID(item["id"]), movement_type=MovementType.USAGE,
        reference_type="usage_log", reference_id=uuid.uuid4(),
        quantity_in=0, quantity_out=30, unit="bag",
        movement_date=_now(), entered_by=None, created_at=_now(),
    ))
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _project_summary(client, token, world)

    assert sum(float(r["used_qty"]) for r in rows) == 30.0, (
        f"30 bags of usage reported as "
        f"{sum(float(r['used_qty']) for r in rows)} across {len(rows)} row(s)"
    )


def test_project_lot_summary_still_totals_allocation_across_sections(db, client, world):
    project, lot, item, section = world["project"], world["lot"], world["item"], world["section"]
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=26, item_id=item["id"], lot_id=lot["id"])
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=13, item_id=item["id"], lot_id=lot["id"])
    db.commit()

    token = login(client, world["owner"]["email"], world["owner"]["password"])
    rows = _project_summary(client, token, world)

    assert len(rows) == 1
    assert float(rows[0]["boq_allocated_qty"]) == 39.0
