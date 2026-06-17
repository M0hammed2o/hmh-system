"""
BOQ sync tests.

Covers:
- _BI NameError fix: apply_item_to_all_site_lots no longer crashes
- Lot→site propagation: "apply to all lots" also updates the site-level template item
- Site→lot push: new push-to-lots endpoint propagates rate/supplier to lot copies
- Quantity aggregation: get_site_boq_summary sums lot quantities, not template × lot_count
"""

import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import insert

from tests.conftest import auth, login, make_user, make_project, make_site, make_lot, make_supplier


def _now():
    return datetime.now(timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_boq_header(db, project_id: str, site_id: str = None):
    from app.models.boq import BOQHeader, BOQSection
    from app.models.enums import BoqStatus

    now = _now()
    header = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name=f"Test BOQ {uuid.uuid4().hex[:6]}",
        source_type="manual",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        uploaded_at=now,
    )
    db.add(header)
    db.flush()

    section = BOQSection(
        boq_header_id=header.id,
        section_name="Works",
        sequence_order=1,
        created_at=now, updated_at=now,
    )
    db.add(section)
    db.flush()
    return header, section


def _make_site_item(db, section, project_id: str, site_id: str,
                    description="Cement Bags", unit="bag", qty=10.0, rate=50.0,
                    supplier_id=None):
    """Create a site-level BOQ item (lot_id=NULL)."""
    from app.models.boq import BOQItem
    item = BOQItem(
        boq_section_id=section.id,
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        lot_id=None,
        raw_description=description,
        item_type="MATERIAL",
        unit=unit,
        planned_quantity=qty,
        planned_rate=rate,
        sort_order=1,
        supplier_id=uuid.UUID(supplier_id) if supplier_id else None,
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(item)
    db.flush()
    return item


def _make_lot_item(db, section, project_id: str, site_id: str, lot_id: str,
                   description="Cement Bags", unit="bag", qty=10.0, rate=50.0,
                   supplier_id=None):
    """Create a lot-level BOQ item (lot_id set)."""
    from app.models.boq import BOQItem
    item = BOQItem(
        boq_section_id=section.id,
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        lot_id=uuid.UUID(lot_id),
        raw_description=description,
        item_type="MATERIAL",
        unit=unit,
        planned_quantity=qty,
        planned_rate=rate,
        sort_order=1,
        supplier_id=uuid.UUID(supplier_id) if supplier_id else None,
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(item)
    db.flush()
    return item


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sync_setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"], name="Site BOQ Sync")
    lot1    = make_lot(db, project_id=project["id"], site_id=site["id"], lot_number="S1")
    lot2    = make_lot(db, project_id=project["id"], site_id=site["id"], lot_number="S2")
    lot3    = make_lot(db, project_id=project["id"], site_id=site["id"], lot_number="S3")
    supplier = make_supplier(db)
    tok     = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        lot1_id=lot1["id"],
        lot2_id=lot2["id"],
        lot3_id=lot3["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


# ── _BI fix: apply_item_to_all_site_lots works without NameError ──────────────

class TestApplyToAllSiteLotsNoBug:
    def test_apply_updates_peer_lot_items(self, client, db, sync_setup):
        """
        apply_item_to_all_site_lots should update peer lot items.
        Previously crashed with NameError: _BI not defined.
        """
        s = sync_setup
        header, section = _make_boq_header(db, s["project_id"], s["site_id"])
        _make_site_item(db, section, s["project_id"], s["site_id"],
                        description="Cement Bags", unit="bag", qty=10, rate=50)
        lot1_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot1_id"],
                                   description="Cement Bags", unit="bag", qty=10, rate=50)
        lot2_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot2_id"],
                                   description="Cement Bags", unit="bag", qty=10, rate=50)
        db.commit()

        # Edit lot1 item and apply to all lots — must NOT crash
        r = client.post(
            f"/api/v1/boq/items/{lot1_item.id}/apply-to-all-site-lots",
            json={"planned_rate": 75.0, "planned_quantity": 10.0},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["lots_affected"] >= 1

        # lot2_item should now have rate=75
        db.expire(lot2_item)
        assert float(lot2_item.planned_rate) == pytest.approx(75.0)

    def test_apply_also_updates_site_template_item(self, client, db, sync_setup):
        """
        When a lot item is edited and applied to all lots, the site-level
        template item should also be updated (rate, supplier — not quantity).
        """
        s = sync_setup
        supplier2 = make_supplier(db)
        header, section = _make_boq_header(db, s["project_id"], s["site_id"])
        site_item = _make_site_item(db, section, s["project_id"], s["site_id"],
                                    description="Sand", unit="m3", qty=5, rate=100)
        lot1_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot1_id"],
                                   description="Sand", unit="m3", qty=5, rate=100)
        _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot2_id"],
                       description="Sand", unit="m3", qty=5, rate=100)
        db.commit()

        # Edit lot1 item with new rate + supplier
        r = client.post(
            f"/api/v1/boq/items/{lot1_item.id}/apply-to-all-site-lots",
            json={
                "planned_rate":    150.0,
                "planned_quantity": 5.0,
                "supplier_id":      supplier2["id"],
            },
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text

        # Site template item should now have rate=150 and supplier=supplier2
        db.expire(site_item)
        assert float(site_item.planned_rate) == pytest.approx(150.0)
        assert str(site_item.supplier_id) == supplier2["id"]

        # Site template item quantity must NOT be changed (preserve template qty)
        assert float(site_item.planned_quantity) == pytest.approx(5.0)


# ── Site→lot push via new endpoint ───────────────────────────────────────────

class TestPushSiteItemToLots:
    def test_push_propagates_rate_to_lots(self, client, db, sync_setup):
        """
        POST /boq/items/{id}/push-to-lots on a site-level item should propagate
        rate and supplier changes to all lot copies, but NOT change lot quantities.
        """
        s = sync_setup
        header, section = _make_boq_header(db, s["project_id"], s["site_id"])
        site_item = _make_site_item(db, section, s["project_id"], s["site_id"],
                                    description="Bricks", unit="each", qty=200, rate=5.0)
        # Lots with different quantities
        lot1_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot1_id"],
                                   description="Bricks", unit="each", qty=180, rate=5.0)
        lot2_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot2_id"],
                                   description="Bricks", unit="each", qty=220, rate=5.0)
        db.commit()

        r = client.post(
            f"/api/v1/boq/items/{site_item.id}/push-to-lots",
            json={"planned_rate": 7.5},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["lots_affected"] >= 2

        # Lot rates updated
        db.expire(lot1_item)
        db.expire(lot2_item)
        assert float(lot1_item.planned_rate) == pytest.approx(7.5)
        assert float(lot2_item.planned_rate) == pytest.approx(7.5)

        # Lot quantities NOT changed
        assert float(lot1_item.planned_quantity) == pytest.approx(180.0)
        assert float(lot2_item.planned_quantity) == pytest.approx(220.0)

    def test_push_from_lot_item_returns_warning(self, client, db, sync_setup):
        """push-to-lots on a lot-level item should return a warning, not crash."""
        s = sync_setup
        header, section = _make_boq_header(db, s["project_id"], s["site_id"])
        lot1_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot1_id"],
                                   description="Pipes", unit="m", qty=50, rate=30)
        db.commit()

        r = client.post(
            f"/api/v1/boq/items/{lot1_item.id}/push-to-lots",
            json={"planned_rate": 40.0},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["lots_affected"] == 0

    def test_push_supplier_to_lots(self, client, db, sync_setup):
        """Supplier change on site item propagates to lot copies."""
        s = sync_setup
        supplier2 = make_supplier(db)
        header, section = _make_boq_header(db, s["project_id"], s["site_id"])
        site_item = _make_site_item(db, section, s["project_id"], s["site_id"],
                                    description="Tiles", unit="m2", qty=100, rate=80,
                                    supplier_id=s["supplier_id"])
        lot1_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot1_id"],
                                   description="Tiles", unit="m2", qty=90, rate=80,
                                   supplier_id=s["supplier_id"])
        lot2_item = _make_lot_item(db, section, s["project_id"], s["site_id"], s["lot2_id"],
                                   description="Tiles", unit="m2", qty=110, rate=80,
                                   supplier_id=s["supplier_id"])
        db.commit()

        r = client.post(
            f"/api/v1/boq/items/{site_item.id}/push-to-lots",
            json={"supplier_id": supplier2["id"]},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["lots_affected"] == 2

        db.expire(lot1_item)
        db.expire(lot2_item)
        assert str(lot1_item.supplier_id) == supplier2["id"]
        assert str(lot2_item.supplier_id) == supplier2["id"]


# ── Quantity aggregation in site BOQ summary ──────────────────────────────────

class TestSiteBoqQuantityAggregation:
    def test_site_summary_aggregates_lot_quantities(self, db):
        """
        get_site_boq_summary shows the SUM of all lot quantities for each item,
        not the site template quantity × lot_count.

        Scenario: 10 lots × 10 bags cement, but the last lot needs 12.
        Expected aggregated quantity = 9×10 + 1×12 = 102.
        """
        from app.services.boq_service import get_site_boq_summary

        owner   = make_user(db)
        project = make_project(db, owner_id=owner["id"])
        site    = make_site(db, project_id=project["id"])
        lots    = [
            make_lot(db, project_id=project["id"], site_id=site["id"], lot_number=str(i))
            for i in range(1, 11)
        ]

        header, section = _make_boq_header(db, project["id"], site["id"])
        _make_site_item(db, section, project["id"], site["id"],
                        description="Cement Bags", unit="bag", qty=10, rate=50)

        # Generate lot items: first 9 lots × 10 bags, last lot × 12 bags
        for i, lot in enumerate(lots):
            qty = 10 if i < 9 else 12
            _make_lot_item(db, section, project["id"], site["id"], lot["id"],
                           description="Cement Bags", unit="bag", qty=qty, rate=50)
        db.commit()

        summary = get_site_boq_summary(db, uuid.UUID(site["id"]))

        # Find the cement item in sections
        all_items = [
            item
            for sec in summary["sections"]
            for item in sec["items"]
            if "Cement" in item["description"]
        ]
        assert len(all_items) == 1
        cement = all_items[0]

        # Aggregated quantity should be 9×10 + 12 = 102 (not 10)
        assert cement["planned_quantity"] == pytest.approx(102.0, rel=1e-4), (
            f"Expected 102 bags (aggregated from lots), got {cement['planned_quantity']}"
        )
        assert cement["line_total"] == pytest.approx(102 * 50, rel=1e-4)

    def test_site_total_aggregated_from_lots(self, db):
        """site_total reflects the actual sum of all lot totals, including overrides."""
        from app.services.boq_service import get_site_boq_summary

        owner   = make_user(db)
        project = make_project(db, owner_id=owner["id"])
        site    = make_site(db, project_id=project["id"])
        # 3 lots: quantities 10, 10, 15 at rate=100 → total = 3500
        lots = [
            make_lot(db, project_id=project["id"], site_id=site["id"], lot_number=str(i))
            for i in range(1, 4)
        ]

        header, section = _make_boq_header(db, project["id"], site["id"])
        _make_site_item(db, section, project["id"], site["id"],
                        description="Steel Bars", unit="kg", qty=10, rate=100)

        for i, lot in enumerate(lots):
            qty = 15 if i == 2 else 10
            _make_lot_item(db, section, project["id"], site["id"], lot["id"],
                           description="Steel Bars", unit="kg", qty=qty, rate=100)
        db.commit()

        summary = get_site_boq_summary(db, uuid.UUID(site["id"]))

        # site_total = (10 + 10 + 15) × 100 = 3500
        assert summary["site_total"] == pytest.approx(3500.0, rel=1e-4), (
            f"Expected 3500.0 (aggregated lot totals), got {summary['site_total']}"
        )

    def test_fallback_when_no_lot_items(self, db):
        """When no lot BOQ items exist, site_total falls back to template_qty × lot_count."""
        from app.services.boq_service import get_site_boq_summary

        owner   = make_user(db)
        project = make_project(db, owner_id=owner["id"])
        site    = make_site(db, project_id=project["id"])
        for i in range(1, 4):
            make_lot(db, project_id=project["id"], site_id=site["id"], lot_number=str(i))

        header, section = _make_boq_header(db, project["id"], site["id"])
        _make_site_item(db, section, project["id"], site["id"],
                        description="Paint", unit="L", qty=20, rate=25)
        db.commit()

        summary = get_site_boq_summary(db, uuid.UUID(site["id"]))

        # Fallback: 20 × 25 × 3 lots = 1500
        assert summary["site_total"] == pytest.approx(1500.0, rel=1e-4)
        # Template quantity shown when no lot items
        all_items = [i for sec in summary["sections"] for i in sec["items"]]
        assert all_items[0]["planned_quantity"] == pytest.approx(20.0)
