"""
Regression tests for project-level (site_id IS NULL, lot_id IS NULL) BOQs in
the master summary.

A project-level master BOQ is a legitimate shape — copy_boq() and
generate_lot_boqs() derive site- and lot-level BOQs *from* it. But
get_project_master_summary() only emitted a null-site row when the project had
freestanding lots, so a project-level BOQ on a project with no lots (and no
non-warehouse site) vanished from the dashboard entirely: the endpoint returned
200 with an empty `sites` list and the UI rendered "No BOQ data yet".

That is the Cornubia shape — one warehouse site, zero lots, 22 sections and 79
items all carrying site_id = NULL and lot_id = NULL.

These tests pin the fixed behaviour and guard the existing site/lot aggregation
against regressions.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert

from tests.conftest import make_lot, make_project, make_site, make_user


def _now():
    return datetime.now(timezone.utc)


def _make_boq(db, project_id, *, site_id=None, lot_id=None, qty=1.0, rate=None,
              uploaded_at=None, n_items=1, version_name=None):
    """One BOQHeader + BOQSection + n_items BOQItems at the given tier.

    site_id=None and lot_id=None produces a project-level master BOQ.
    rate=None mirrors the Cornubia import: quantities but no commercial data.
    """
    from app.models.boq import BOQHeader, BOQItem, BOQSection
    from app.models.enums import BoqStatus

    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=version_name or f"BOQ {uuid.uuid4().hex[:6]}",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=uploaded_at or _now(),
    )
    db.add(h)
    db.flush()

    s = BOQSection(
        boq_header_id=h.id,
        section_name="Works",
        sequence_order=1,
        created_at=_now(), updated_at=_now(),
    )
    db.add(s)
    db.flush()

    for i in range(n_items):
        db.execute(insert(BOQItem).values(
            id=uuid.uuid4(),
            boq_section_id=s.id,
            project_id=uuid.UUID(project_id),
            site_id=uuid.UUID(site_id) if site_id else None,
            lot_id=uuid.UUID(lot_id) if lot_id else None,
            item_id=None,
            raw_description=f"Item {i + 1}",
            item_type="MATERIAL",
            unit=None,
            planned_quantity=qty,
            planned_rate=rate,
            sort_order=i + 1,
            is_active=True,
            created_at=_now(), updated_at=_now(),
        ))
    db.flush()
    return str(h.id)


def _make_warehouse_site(db, project_id, name="Project Warehouse"):
    """make_site() always builds a construction_site; the Cornubia project's
    only site is a warehouse, which the master summary deliberately skips."""
    from app.models.site import Site
    s = Site(
        project_id=uuid.UUID(project_id),
        name=name,
        site_type="warehouse",
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(s)
    db.flush()
    return str(s.id)


def _project_row(summary):
    """The null-site row, if the summary emitted one."""
    return next((r for r in summary["sites"] if r["site_id"] is None), None)


# ── The bug: project-level BOQ with nothing else ──────────────────────────────

def test_project_level_boq_with_zero_sites_and_zero_lots_is_visible(db):
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    header_id = _make_boq(db, proj["id"], qty=10, rate=50, n_items=3)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    row = _project_row(summary)

    assert row is not None, "project-level BOQ produced no row in the master summary"
    assert row["has_boq"] is True
    assert row["item_count"] == 3
    assert row["lot_count"] == 0
    assert row["is_project_level"] is True
    assert row["site_name"] == "Project BOQ"
    assert header_id in row["boq_header_ids"], "row must link to the BOQ header"
    # With no lots the project-level BOQ is itself the total, not zero.
    assert row["unit_total"] == pytest.approx(1500.0)
    assert row["site_total"] == pytest.approx(1500.0)
    assert summary["total_planned"] == pytest.approx(1500.0)


def test_project_level_boq_with_warehouse_only_site_is_visible(db):
    """The Cornubia shape: one warehouse site, no lots, project-level items."""
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    _make_warehouse_site(db, proj["id"])
    header_id = _make_boq(db, proj["id"], qty=1, rate=None, n_items=79)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    row = _project_row(summary)

    assert row is not None, "warehouse-only project hid its project-level BOQ"
    assert row["item_count"] == 79
    assert row["has_boq"] is True
    assert row["is_project_level"] is True
    assert header_id in row["boq_header_ids"]
    # The warehouse is still excluded from the site roll-up.
    assert summary["site_count"] == 0
    assert all(r["site_id"] is None for r in summary["sites"])


def test_project_level_boq_with_no_rates_still_has_boq_true(db):
    """Quantities but no rates totals R0.00 — presence must come from the
    items, never from site_total > 0."""
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    _make_boq(db, proj["id"], qty=680, rate=None, n_items=5)

    row = _project_row(get_project_master_summary(db, uuid.UUID(proj["id"])))

    assert row is not None
    assert row["site_total"] == pytest.approx(0.0)
    assert row["unit_total"] == pytest.approx(0.0)
    assert row["has_boq"] is True, "a zero-value BOQ must not be hidden"
    assert row["item_count"] == 5


# ── Header de-duplication must still hold at project level ────────────────────

def test_multiple_active_headers_do_not_double_count_project_level_items(db):
    """Two active headers with project-level items → only the most recently
    uploaded one counts, matching the site-level guard."""
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    older = _now() - timedelta(days=2)
    _make_boq(db, proj["id"], qty=10, rate=100, n_items=1, uploaded_at=older)
    newer_id = _make_boq(db, proj["id"], qty=10, rate=100, n_items=1, uploaded_at=_now())

    row = _project_row(get_project_master_summary(db, uuid.UUID(proj["id"])))

    assert row is not None
    assert row["item_count"] == 1, "both headers were counted — totals inflated"
    assert row["unit_total"] == pytest.approx(1000.0)
    assert row["site_total"] == pytest.approx(1000.0)
    assert row["boq_header_ids"] == [newer_id]


# ── Existing behaviour must not regress ───────────────────────────────────────

def test_site_level_aggregation_unchanged(db):
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site Alpha")
    for i in range(1, 4):
        make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number=str(i))
    _make_boq(db, proj["id"], site_id=site["id"], qty=10, rate=50)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    assert row["unit_total"] == pytest.approx(500.0)
    assert row["lot_count"] == 3
    assert row["site_total"] == pytest.approx(1500.0)
    assert summary["site_count"] == 1
    # No project-level items exist, so no null-site row should be invented.
    assert _project_row(summary) is None


def test_lot_level_aggregation_unchanged(db):
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site Beta")
    lots = [make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number=str(i))
            for i in range(1, 3)]
    for lot in lots:
        _make_boq(db, proj["id"], site_id=site["id"], lot_id=lot["id"], qty=2, rate=100)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    assert row["lot_count"] == 2
    assert row["site_total"] == pytest.approx(400.0)
    assert _project_row(summary) is None


def test_freestanding_lots_keep_their_label_and_totals(db):
    """Freestanding lots (lot.site_id IS NULL) still report as before, and are
    not relabelled as a project-level BOQ."""
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    make_lot(db, project_id=proj["id"], site_id=None, lot_number="F1")
    make_lot(db, project_id=proj["id"], site_id=None, lot_number="F2")
    _make_boq(db, proj["id"], qty=5, rate=20)   # project-level unit template

    row = _project_row(get_project_master_summary(db, uuid.UUID(proj["id"])))

    assert row is not None
    assert row["site_name"] == "Freestanding Units"
    assert row["is_project_level"] is False
    assert row["lot_count"] == 2
    assert row["unit_total"] == pytest.approx(100.0)
    assert row["site_total"] == pytest.approx(200.0), "unit_total × 2 freestanding lots"
