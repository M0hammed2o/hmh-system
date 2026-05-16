"""
Tests for site-scoped BOQ section deletion.

Covers:
- scope="lot"  deletes only the target section (single lot)
- scope="site" deletes matching sections across all lots in the same site
- scope="site" does NOT touch other sites or templates
- API endpoint returns correct SectionDeleteResult counts
- section name matching (not ID matching) drives site-scoped deletes
"""

import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import insert as _sa_insert

from tests.conftest import auth, login, make_user, make_project, make_site, make_lot


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _header(db, project_id, version_name="Test BOQ", is_template=False):
    from app.models.boq import BOQHeader
    from app.models.enums import BoqStatus
    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=version_name,
        source_type="manual",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=is_template,
        uploaded_at=_now(),
    )
    db.add(h)
    db.flush()
    return h


def _section(db, header_id, name="Foundations", seq=1):
    from app.models.boq import BOQSection
    s = BOQSection(
        boq_header_id=header_id,
        section_name=name,
        sequence_order=seq,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(s)
    db.flush()
    return s


def _item(db, section_id, project_id, lot_id=None, qty=10.0, rate=100.0):
    from app.models.boq import BOQItem
    new_id = uuid.uuid4()
    db.execute(_sa_insert(BOQItem).values(
        id=new_id,
        boq_section_id=section_id,
        project_id=uuid.UUID(project_id) if isinstance(project_id, str) else project_id,
        lot_id=uuid.UUID(lot_id) if isinstance(lot_id, str) else lot_id,
        raw_description="Test item",
        item_type="MATERIAL",
        unit="m²",
        planned_quantity=qty,
        planned_rate=rate,
        sort_order=1,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    ))
    db.flush()
    return new_id


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site_a  = make_site(db, project_id=project["id"], name="Site A")
    site_b  = make_site(db, project_id=project["id"], name="Site B")
    lot1    = make_lot(db, project_id=project["id"], site_id=site_a["id"], lot_number="1")
    lot2    = make_lot(db, project_id=project["id"], site_id=site_a["id"], lot_number="2")
    lot3    = make_lot(db, project_id=project["id"], site_id=site_b["id"], lot_number="3")
    tok     = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"], project_id=project["id"],
        site_a_id=site_a["id"], site_b_id=site_b["id"],
        lot1_id=lot1["id"], lot2_id=lot2["id"], lot3_id=lot3["id"],
        tok=tok,
    )


# ── scope="lot" ───────────────────────────────────────────────────────────────

class TestLotScopeDelete:

    def test_lot_scope_deletes_single_section(self, db, setup):
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection, BOQItem

        h = _header(db, setup["project_id"])
        s = _section(db, h.id, "Foundations")
        _item(db, s.id, setup["project_id"], lot_id=setup["lot1_id"])
        db.commit()

        result = delete_section_scoped(db, s.id, scope="lot")

        assert result["scope"] == "lot"
        assert result["sections_deleted"] == 1
        assert result["lots_affected"] == 1
        assert result["items_deleted"] == 1

        # Section is gone
        assert db.get(BOQSection, s.id) is None

    def test_lot_scope_leaves_other_sections_untouched(self, db, setup):
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        h = _header(db, setup["project_id"])
        s1 = _section(db, h.id, "Foundations", seq=1)
        s2 = _section(db, h.id, "Roofing", seq=2)
        _item(db, s1.id, setup["project_id"], lot_id=setup["lot1_id"])
        _item(db, s2.id, setup["project_id"], lot_id=setup["lot1_id"])
        db.commit()

        delete_section_scoped(db, s1.id, scope="lot")

        assert db.get(BOQSection, s1.id) is None
        assert db.get(BOQSection, s2.id) is not None  # untouched

    def test_lot_scope_via_api(self, client, db, setup):
        h = _header(db, setup["project_id"])
        s = _section(db, h.id, "Brickwork")
        _item(db, s.id, setup["project_id"], lot_id=setup["lot1_id"])
        db.commit()

        resp = client.delete(
            f"/api/v1/boq/{h.id}/sections/{s.id}?scope=lot",
            headers=auth(setup["tok"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["scope"] == "lot"
        assert data["sections_deleted"] == 1
        assert data["lots_affected"] == 1


# ── scope="site" ──────────────────────────────────────────────────────────────

class TestSiteScopeDelete:

    def _build_site_boq(self, db, setup, section_name="Foundations"):
        """
        Create two lot BOQs (lot1, lot2) under site_a, each with a section
        named `section_name`.  Returns (header1, section1, header2, section2).
        """
        h1 = _header(db, setup["project_id"], f"BOQ — Lot 1")
        s1 = _section(db, h1.id, section_name, seq=1)
        _item(db, s1.id, setup["project_id"], lot_id=setup["lot1_id"])

        h2 = _header(db, setup["project_id"], f"BOQ — Lot 2")
        s2 = _section(db, h2.id, section_name, seq=1)
        _item(db, s2.id, setup["project_id"], lot_id=setup["lot2_id"])

        db.commit()
        return h1, s1, h2, s2

    def test_site_scope_deletes_all_matching_sections(self, db, setup):
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        _, s1, _, s2 = self._build_site_boq(db, setup, "Foundations")

        result = delete_section_scoped(db, s1.id, scope="site")

        assert result["scope"] == "site"
        assert result["sections_deleted"] == 2
        assert result["lots_affected"] == 2
        assert result["items_deleted"] == 2
        # Both sections gone
        assert db.get(BOQSection, s1.id) is None
        assert db.get(BOQSection, s2.id) is None

    def test_site_scope_matches_by_name_not_id(self, db, setup):
        """
        s1 and s2 are completely different DB rows (different IDs) but share
        section_name="Roofing".  Deleting s1 with scope=site must remove s2.
        """
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        _, s1, _, s2 = self._build_site_boq(db, setup, "Roofing")
        assert s1.id != s2.id  # sanity

        delete_section_scoped(db, s1.id, scope="site")

        assert db.get(BOQSection, s2.id) is None

    def test_site_scope_does_not_touch_other_site(self, db, setup):
        """
        lot3 belongs to site_b.  Deleting a section in site_a with scope=site
        must NOT affect site_b.
        """
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        # site_a: lot1 + lot2, section "Foundations"
        _, s1, _, s2 = self._build_site_boq(db, setup, "Foundations")

        # site_b: lot3, same section name
        h3 = _header(db, setup["project_id"], "BOQ — Lot 3")
        s3 = _section(db, h3.id, "Foundations", seq=1)
        _item(db, s3.id, setup["project_id"], lot_id=setup["lot3_id"])
        db.commit()

        delete_section_scoped(db, s1.id, scope="site")

        # site_a sections gone
        assert db.get(BOQSection, s1.id) is None
        assert db.get(BOQSection, s2.id) is None
        # site_b section untouched
        assert db.get(BOQSection, s3.id) is not None

    def test_site_scope_does_not_touch_templates(self, db, setup):
        """
        A template BOQHeader with the same section name must not be touched.
        """
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        _, s1, _, _ = self._build_site_boq(db, setup, "Plastering")

        # Template with same section name — no lot_id on items
        tmpl = _header(db, setup["project_id"], "Standard Template", is_template=True)
        st   = _section(db, tmpl.id, "Plastering", seq=1)
        _item(db, st.id, setup["project_id"], lot_id=None)  # no lot
        db.commit()

        delete_section_scoped(db, s1.id, scope="site")

        # Template section untouched (no lot_id → not in site's lots)
        assert db.get(BOQSection, st.id) is not None

    def test_site_scope_leaves_other_section_names_alone(self, db, setup):
        """
        Only sections whose name matches the target are deleted.
        """
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        h1 = _header(db, setup["project_id"], "BOQ — Lot 1 v2")
        s_found = _section(db, h1.id, "Electrical", seq=1)
        s_keep  = _section(db, h1.id, "Plumbing",   seq=2)
        _item(db, s_found.id, setup["project_id"], lot_id=setup["lot1_id"])
        _item(db, s_keep.id,  setup["project_id"], lot_id=setup["lot1_id"])
        db.commit()

        delete_section_scoped(db, s_found.id, scope="site")

        assert db.get(BOQSection, s_found.id) is None
        assert db.get(BOQSection, s_keep.id)  is not None

    def test_site_scope_via_api_returns_correct_counts(self, client, db, setup):
        h1 = _header(db, setup["project_id"], "BOQ — Lot 1 api")
        s1 = _section(db, h1.id, "Concrete & Slab", seq=1)
        _item(db, s1.id, setup["project_id"], lot_id=setup["lot1_id"])

        h2 = _header(db, setup["project_id"], "BOQ — Lot 2 api")
        s2 = _section(db, h2.id, "Concrete & Slab", seq=1)
        _item(db, s2.id, setup["project_id"], lot_id=setup["lot2_id"])
        db.commit()

        resp = client.delete(
            f"/api/v1/boq/{h1.id}/sections/{s1.id}?scope=site",
            headers=auth(setup["tok"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["scope"] == "site"
        assert data["sections_deleted"] == 2
        assert data["lots_affected"] == 2
        assert data["items_deleted"] == 2
        assert "2 lot" in data["message"]

    def test_site_scope_no_items_falls_back_to_lot(self, db, setup):
        """
        If the section has no items (can't infer lot → site), fall back to
        single-section (lot-scope) delete gracefully.
        """
        from app.services.boq_service import delete_section_scoped
        from app.models.boq import BOQSection

        h = _header(db, setup["project_id"])
        s = _section(db, h.id, "Empty Section")
        # No items added
        db.commit()

        result = delete_section_scoped(db, s.id, scope="site")

        # Falls back gracefully — section is gone
        assert db.get(BOQSection, s.id) is None
        assert result["sections_deleted"] >= 1
