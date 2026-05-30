"""
BOQ aggregation regression tests.

Covers the double-counting bug where multiple active BOQ headers for the same
site caused unit_total and site_total to be multiplied by the number of headers.

Scenarios:
- 1 lot: site_total == unit_total × 1
- 20 lots: site_total == R570,085 × 20 == R11,401,700 (was R22,803,400 before fix)
- Multiple sites: project total == sum of individual site totals
- Double-header guard: 2 active headers for the same site → single correct total
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import insert

from tests.conftest import make_user, make_project, make_site, make_lot


def _now():
    return datetime.now(timezone.utc)


def _make_site_boq(db, project_id: str, site_id: str, qty: float, rate: float,
                   uploaded_at=None):
    """Create one BOQHeader + BOQSection + one site-level BOQItem (lot_id=NULL)."""
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus

    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=f"Site BOQ {uuid.uuid4().hex[:6]}",
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

    db.execute(
        insert(BOQItem).values(
            id=uuid.uuid4(),
            boq_section_id=s.id,
            project_id=uuid.UUID(project_id),
            site_id=uuid.UUID(site_id),
            lot_id=None,
            item_id=None,
            raw_description="Site-level item",
            item_type="MATERIAL",
            unit="m2",
            planned_quantity=qty,
            planned_rate=rate,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()
    return str(h.id)


# ── 1-lot baseline ────────────────────────────────────────────────────────────

def test_one_lot_site_total(db):
    """site_total == unit_total × 1 for a site with exactly one lot."""
    from app.services.boq_service import get_project_master_summary, get_site_boq_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site Alpha")
    make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number="1")

    # qty=10, rate=50 → unit_total = 500
    _make_site_boq(db, proj["id"], site["id"], qty=10, rate=50)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    site_row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    assert site_row["unit_total"] == pytest.approx(500.0, rel=1e-4)
    assert site_row["lot_count"] == 1
    assert site_row["site_total"] == pytest.approx(500.0, rel=1e-4)
    assert summary["total_planned"] == pytest.approx(500.0, rel=1e-4)


# ── 20-lot proof: R570,085 × 20 = R11,401,700 ────────────────────────────────

def test_twenty_lots_correct_total(db):
    """With 20 identical lots the project total is unit_total × 20, not × 40."""
    from app.services.boq_service import get_project_master_summary, get_site_boq_summary

    UNIT_TOTAL = 570_085.00  # R570,085 per unit

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site 20-Lots")
    for i in range(1, 21):
        make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number=str(i))

    _make_site_boq(db, proj["id"], site["id"], qty=1, rate=UNIT_TOTAL)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    site_row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    assert site_row["unit_total"] == pytest.approx(UNIT_TOTAL, rel=1e-4)
    assert site_row["lot_count"] == 20
    assert site_row["site_total"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4), (
        f"Expected R{UNIT_TOTAL * 20:,.2f} but got R{site_row['site_total']:,.2f}"
    )
    assert summary["total_planned"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4)

    # Also verify via get_site_boq_summary
    site_summary = get_site_boq_summary(db, uuid.UUID(site["id"]))
    assert site_summary["unit_total"] == pytest.approx(UNIT_TOTAL, rel=1e-4)
    assert site_summary["site_total"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4)


# ── Multiple sites: project total = sum of site totals ───────────────────────

def test_multiple_sites_project_total(db):
    """Project total_planned equals the arithmetic sum of all site_totals."""
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])

    # Site A: 5 lots × R100,000 = R500,000  (lot numbers 1-5)
    site_a = make_site(db, project_id=proj["id"], name="Site A")
    for i in range(1, 6):
        make_lot(db, project_id=proj["id"], site_id=site_a["id"], lot_number=f"A{i}")
    _make_site_boq(db, proj["id"], site_a["id"], qty=1, rate=100_000)

    # Site B: 3 lots × R200,000 = R600,000  (lot numbers B1-B3, unique per project)
    site_b = make_site(db, project_id=proj["id"], name="Site B")
    for i in range(1, 4):
        make_lot(db, project_id=proj["id"], site_id=site_b["id"], lot_number=f"B{i}")
    _make_site_boq(db, proj["id"], site_b["id"], qty=1, rate=200_000)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))

    row_a = next(r for r in summary["sites"] if r["site_id"] == site_a["id"])
    row_b = next(r for r in summary["sites"] if r["site_id"] == site_b["id"])

    assert row_a["site_total"] == pytest.approx(500_000.0, rel=1e-4)
    assert row_b["site_total"] == pytest.approx(600_000.0, rel=1e-4)
    assert summary["total_planned"] == pytest.approx(1_100_000.0, rel=1e-4)


# ── Double-header guard: 2 active headers → single correct total ──────────────

def test_double_header_no_double_counting(db):
    """
    When two active BOQ headers both have site-level items for the same site
    (e.g. a manual BOQ plus a template-clone site master), the service must
    return the unit_total from the most-recently-uploaded header ONLY, not
    the sum of both.

    Pre-fix behaviour:  unit_total = R570,085 × 2 = R1,140,170
    Post-fix behaviour: unit_total = R570,085
    """
    from app.services.boq_service import get_project_master_summary, get_site_boq_summary

    UNIT_TOTAL = 570_085.00

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site Dup")
    for i in range(1, 21):
        make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number=str(i))

    # Older header (uploaded 1 hour ago)
    old_ts = _now() - timedelta(hours=1)
    _make_site_boq(db, proj["id"], site["id"], qty=1, rate=UNIT_TOTAL, uploaded_at=old_ts)

    # Newer header (uploaded now) — same items, same rate
    new_ts = _now()
    _make_site_boq(db, proj["id"], site["id"], qty=1, rate=UNIT_TOTAL, uploaded_at=new_ts)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    site_row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    # unit_total must NOT be doubled
    assert site_row["unit_total"] == pytest.approx(UNIT_TOTAL, rel=1e-4), (
        f"Double-counting detected: unit_total={site_row['unit_total']:.2f} "
        f"(expected {UNIT_TOTAL:.2f}, got {site_row['unit_total'] / UNIT_TOTAL:.1f}×)"
    )
    assert site_row["site_total"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4)
    assert summary["total_planned"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4)

    # get_site_boq_summary must also be clean
    site_summary = get_site_boq_summary(db, uuid.UUID(site["id"]))
    assert site_summary["unit_total"] == pytest.approx(UNIT_TOTAL, rel=1e-4)
    assert site_summary["site_total"] == pytest.approx(UNIT_TOTAL * 20, rel=1e-4)


def test_double_header_uses_latest_header(db):
    """
    When two active headers have different rates, the service picks the
    most-recently-uploaded header's items, not the older ones.
    """
    from app.services.boq_service import get_project_master_summary

    owner = make_user(db)
    proj = make_project(db, owner_id=owner["id"])
    site = make_site(db, project_id=proj["id"], name="Site Version")
    make_lot(db, project_id=proj["id"], site_id=site["id"], lot_number="1")

    # Old header: rate=100
    old_ts = _now() - timedelta(hours=2)
    _make_site_boq(db, proj["id"], site["id"], qty=1, rate=100, uploaded_at=old_ts)

    # New header: rate=250
    new_ts = _now()
    _make_site_boq(db, proj["id"], site["id"], qty=1, rate=250, uploaded_at=new_ts)

    summary = get_project_master_summary(db, uuid.UUID(proj["id"]))
    site_row = next(r for r in summary["sites"] if r["site_id"] == site["id"])

    # Should use rate=250 (newer), not rate=100 (older) or 350 (sum of both)
    assert site_row["unit_total"] == pytest.approx(250.0, rel=1e-4)
    assert site_row["site_total"] == pytest.approx(250.0, rel=1e-4)
