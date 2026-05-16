"""
Tests that planned_total (GENERATED ALWAYS AS STORED) is never written by application code.

These tests catch the production bug where ORM inserts include planned_total=NULL
and PostgreSQL rejects them with "cannot insert into column 'planned_total'".
"""

import uuid
import pytest
from datetime import datetime, timezone

from sqlalchemy import inspect as _sa_inspect, insert as _sa_insert, text

from tests.conftest import make_user, make_project, make_site, make_lot, login, auth


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_boq_header(db, project_id: str, is_template: bool = False):
    from app.models.boq import BOQHeader
    from app.models.enums import BoqStatus
    h = BOQHeader(
        project_id    = uuid.UUID(project_id),
        version_name  = "Test BOQ",
        source_type   = "test",
        status        = BoqStatus.ACTIVE,
        is_template   = is_template,
        template_name = "Test Template" if is_template else None,
        uploaded_at   = _now(),
    )
    db.add(h)
    db.flush()
    return h


def _make_boq_section(db, header_id, name: str = "Section 1"):
    from app.models.boq import BOQSection
    s = BOQSection(
        boq_header_id  = header_id,
        section_name   = name,
        sequence_order = 1,
        created_at     = _now(),
        updated_at     = _now(),
    )
    db.add(s)
    db.flush()
    return s


def _insert_boq_item_core(db, section_id, project_id, lot_id=None, qty=10.0, rate=100.0):
    """Insert a BOQItem via Core INSERT — the correct production approach."""
    from app.models.boq import BOQItem
    new_id = uuid.uuid4()
    stmt = _sa_insert(BOQItem).values(
        id             = new_id,
        boq_section_id = section_id,
        project_id     = project_id,
        lot_id         = lot_id,
        raw_description = "Test material",
        item_type      = "MATERIAL",
        unit           = "m²",
        planned_quantity = qty,
        planned_rate   = rate,
        sort_order     = 1,
        is_active      = True,
        created_at     = _now(),
        updated_at     = _now(),
    )
    db.execute(stmt)
    db.flush()
    return new_id


# ── Test 1: planned_total is declared as Computed in the ORM model ─────────────

def test_planned_total_is_computed_in_orm_model():
    """
    BOQItem.planned_total must have Computed(persisted=True) so that SQLAlchemy
    NEVER includes it in INSERT or UPDATE statements automatically.
    """
    from app.models.boq import BOQItem
    col = BOQItem.__table__.columns.get("planned_total")
    assert col is not None, "planned_total column must exist in ORM model"
    assert hasattr(col, "computed") and col.computed is not None, (
        "planned_total must be declared with Computed(persisted=True) in the ORM model. "
        "Without this, SQLAlchemy includes planned_total=NULL in every INSERT, which "
        "PostgreSQL rejects for GENERATED ALWAYS columns."
    )


# ── Test 2: Core INSERT does NOT include planned_total in SQL ─────────────────

def test_core_insert_excludes_planned_total(db):
    """
    _sa_insert(BOQItem).values(...) must NOT include planned_total in the generated SQL.
    This is the safe insertion pattern used throughout the codebase.
    """
    from app.models.boq import BOQItem
    import sqlalchemy as sa
    user    = make_user(db)
    project = make_project(db, user["id"])
    header  = _make_boq_header(db, project["id"])
    section = _make_boq_section(db, header.id)

    # Build the INSERT statement without executing it
    stmt = _sa_insert(BOQItem).values(
        id              = uuid.uuid4(),
        boq_section_id  = section.id,
        project_id      = uuid.UUID(project["id"]),
        raw_description = "Cement",
        item_type       = "MATERIAL",
        unit            = "bag",
        planned_quantity = 10.0,
        planned_rate    = 250.0,
        sort_order      = 1,
        is_active       = True,
        created_at      = _now(),
        updated_at      = _now(),
    )
    compiled = stmt.compile(dialect=sa.dialects.postgresql.dialect())
    sql_text = str(compiled)

    assert "planned_total" not in sql_text, (
        f"Core INSERT must NOT include planned_total in SQL. Found it in:\n{sql_text}"
    )


# ── Test 3: BOQ item can be inserted and planned_total is computed ─────────────

def test_boq_item_insert_computes_planned_total(db):
    """
    After a valid Core INSERT, planned_total should be auto-computed by the DB
    as planned_quantity * planned_rate.
    """
    from app.models.boq import BOQItem
    user    = make_user(db)
    project = make_project(db, user["id"])
    header  = _make_boq_header(db, project["id"])
    section = _make_boq_section(db, header.id)

    item_id = _insert_boq_item_core(
        db, section.id, uuid.UUID(project["id"]), qty=10.0, rate=250.0
    )
    db.commit()

    item = db.get(BOQItem, item_id)
    assert item is not None, "BOQItem should be retrievable after Core INSERT"
    # planned_total may be None if DB is SQLite (no computed columns) — only check on PostgreSQL
    if item.planned_total is not None:
        assert abs(float(item.planned_total) - 2500.0) < 0.01, (
            f"planned_total should be qty*rate=2500, got {item.planned_total}"
        )


# ── Test 4: boq_service.create_item uses Core INSERT ──────────────────────────

def test_boq_service_create_item_succeeds(db):
    """
    boq_service.create_item() must succeed without errors.
    This fails on production if planned_total is not Computed() in the model.
    """
    from app.services import boq_service
    from app.schemas.boq import BOQItemCreate
    user    = make_user(db)
    project = make_project(db, user["id"])
    header  = _make_boq_header(db, project["id"])
    section = _make_boq_section(db, header.id)

    data = BOQItemCreate(
        raw_description  = "IBR Sheeting",
        item_type        = "MATERIAL",
        unit             = "m²",
        planned_quantity = 120.0,
        planned_rate     = 185.0,
        sort_order       = 1,
    )
    # Should not raise any exception about planned_total
    item = boq_service.create_item(db, section.id, data)
    assert item is not None
    assert item.raw_description == "IBR Sheeting"


# ── Test 5: boq_template_service clone uses Core INSERT ───────────────────────

def test_boq_template_clone_does_not_insert_planned_total(db):
    """
    clone_template_to_lots() must NOT send planned_total to the database.
    This was the production bug: ORM INSERT sent planned_total=NULL, PostgreSQL rejected it.
    """
    from app.services.boq_template_service import clone_template_to_lots
    from app.models.boq import BOQItem

    user    = make_user(db, role="OWNER")
    project = make_project(db, user["id"])
    site    = make_site(db, project["id"])
    lot     = make_lot(db, project["id"], site["id"], lot_number="1")

    # Build a minimal template header + section + item
    template = _make_boq_header(db, project["id"], is_template=True)
    section  = _make_boq_section(db, template.id, "Foundations")
    _insert_boq_item_core(
        db, section.id, uuid.UUID(project["id"]),
        qty=13.0, rate=190.0,
    )
    db.commit()

    # Clone the template to one lot — this is the operation that was broken
    # It must not raise "cannot insert into column 'planned_total'"
    created_headers = clone_template_to_lots(
        db,
        template_boq_id = template.id,
        project_id      = uuid.UUID(project["id"]),
        lot_ids         = [uuid.UUID(lot["id"])],
        actor_id        = uuid.UUID(user["id"]),
    )
    db.commit()

    assert len(created_headers) == 1, "One header should be created for one lot"

    # Verify the cloned item exists and has correct data
    cloned_items = (
        db.query(BOQItem)
        .filter(BOQItem.lot_id == uuid.UUID(lot["id"]))
        .all()
    )
    assert len(cloned_items) == 1, "Cloned lot should have one BOQ item"
    assert cloned_items[0].planned_quantity == 13.0
    assert cloned_items[0].planned_rate == 190.0
    # planned_total computed by DB (may be None on SQLite)
    if cloned_items[0].planned_total is not None:
        assert abs(float(cloned_items[0].planned_total) - 2470.0) < 0.01


# ── Test 6: boq_service.generate_lot_boqs uses Core INSERT ────────────────────

def test_generate_lot_boqs_does_not_insert_planned_total(db):
    """
    boq_service.generate_lot_boqs() must succeed without inserting planned_total.
    """
    from app.services import boq_service
    from app.models.boq import BOQItem

    user    = make_user(db, role="OWNER")
    project = make_project(db, user["id"])
    site    = make_site(db, project["id"])
    lot     = make_lot(db, project["id"], site["id"], lot_number="2")

    # Create a site-level BOQ (lot_id=None)
    header  = _make_boq_header(db, project["id"])
    section = _make_boq_section(db, header.id, "Brickwork")
    _insert_boq_item_core(
        db, section.id, uuid.UUID(project["id"]),
        lot_id=None, qty=5500.0, rate=1.85
    )
    db.commit()

    # generate_lot_boqs should not raise any exception
    count = boq_service.generate_lot_boqs(
        db,
        source_header_id = header.id,
        lot_ids          = [uuid.UUID(lot["id"])],
    )
    assert count == 1, "Should create 1 lot-specific BOQ item"

    # Verify
    items = (
        db.query(BOQItem)
        .filter(BOQItem.lot_id == uuid.UUID(lot["id"]))
        .all()
    )
    assert len(items) == 1
    assert abs(float(items[0].planned_rate) - 1.85) < 0.001


# ── Test 7: API endpoint for Apply BOQ Template works end-to-end ───────────────

def test_apply_boq_template_api(db, client):
    """
    POST /boq-templates/clone-to-lots must succeed without planned_total errors.
    """
    user    = make_user(db, role="OWNER")
    token   = login(client, user["email"], user["password"])
    project = make_project(db, user["id"])
    site    = make_site(db, project["id"])
    lot     = make_lot(db, project["id"], site["id"], lot_number="3")

    # Create template
    template = _make_boq_header(db, project["id"], is_template=True)
    section  = _make_boq_section(db, template.id, "Roofing")
    _insert_boq_item_core(
        db, section.id, uuid.UUID(project["id"]),
        qty=14.0, rate=3200.0
    )
    db.commit()

    resp = client.post(
        "/api/v1/boq-templates/clone-to-lots",
        json={
            "template_boq_id": str(template.id),
            "project_id":      project["id"],
            "lot_ids":         [lot["id"]],
        },
        headers=auth(token),
    )
    assert resp.status_code == 201, (
        f"Expected 201, got {resp.status_code}: {resp.text}\n"
        "If 'cannot insert into column planned_total': Computed() fix was not applied."
    )
    data = resp.json()["data"]
    # Main assertion: no 500 / planned_total error; response confirms one lot cloned
    assert data.get("created_count") == 1, f"Expected created_count=1, got: {data}"
