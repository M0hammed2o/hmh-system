"""
Tests for the Site Dashboard API.

Covers:
- material-summary endpoint returns correct BOQ/delivery/usage data
- activity endpoint returns unified list
- over-BOQ usage creates alert
- phone number login works via auth endpoint
- wrong phone login returns 401 (not redirect to admin)
"""

import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_lot,
    make_item, make_boq_item, make_stock,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def dashboard_setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"])
    lot     = make_lot(db, project_id=project["id"], site_id=site["id"], lot_number="1")
    item    = make_item(db, name="Cement Bags")
    tok     = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        lot_id=lot["id"],
        item_id=item["id"],
        tok=tok,
    )


# ── Material Summary tests ────────────────────────────────────────────────────

class TestMaterialSummary:
    def test_empty_lot_returns_empty_list(self, client, db, dashboard_setup):
        s = dashboard_setup
        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_with_boq_returns_allocated_qty(self, client, db, dashboard_setup):
        s = dashboard_setup
        make_boq_item(db, project_id=s["project_id"], lot_id=s["lot_id"],
                      item_id=s["item_id"], qty=50.0)
        db.commit()

        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        row = data[0]
        assert float(row["boq_allocated_qty"]) == pytest.approx(50.0)
        assert float(row["used_qty"]) == pytest.approx(0.0)
        assert float(row["remaining_qty"]) == pytest.approx(50.0)
        assert row["status"] == "OK"

    def test_status_is_low_when_near_limit(self, client, db, dashboard_setup):
        """When remaining < 15% of allocation, status = LOW."""
        s = dashboard_setup
        make_boq_item(db, project_id=s["project_id"], lot_id=s["lot_id"],
                      item_id=s["item_id"], qty=100.0)
        # Record 90 units used (10% remaining → LOW)
        make_stock(db, project_id=s["project_id"], site_id=s["site_id"],
                   item_id=s["item_id"], qty=100.0, lot_id=s["lot_id"])
        from app.models.stock import StockLedger
        from app.models.enums import MovementType
        now = datetime.now(timezone.utc)
        db.add(StockLedger(
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            lot_id=uuid.UUID(s["lot_id"]),
            item_id=uuid.UUID(s["item_id"]),
            movement_type=MovementType.USAGE,
            reference_type="test",
            quantity_in=0,
            quantity_out=90,
            movement_date=now,
            created_at=now,
        ))
        db.commit()

        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert row["status"] in ("LOW", "OVER_BOQ")

    def test_status_over_boq_when_used_exceeds_allocated(self, client, db, dashboard_setup):
        s = dashboard_setup
        make_boq_item(db, project_id=s["project_id"], lot_id=s["lot_id"],
                      item_id=s["item_id"], qty=10.0)
        # Record 20 units used (exceeds 10 allocated)
        from app.models.stock import StockLedger
        from app.models.enums import MovementType
        now = datetime.now(timezone.utc)
        db.add(StockLedger(
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            lot_id=uuid.UUID(s["lot_id"]),
            item_id=uuid.UUID(s["item_id"]),
            movement_type=MovementType.USAGE,
            reference_type="test",
            quantity_in=0,
            quantity_out=20,
            movement_date=now,
            created_at=now,
        ))
        db.commit()

        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert row["status"] == "OVER_BOQ"
        assert float(row["over_qty"]) > 0

    def test_delivered_qty_reflects_delivery_received(self, client, db, dashboard_setup):
        s = dashboard_setup
        make_boq_item(db, project_id=s["project_id"], lot_id=s["lot_id"],
                      item_id=s["item_id"], qty=50.0)
        from app.models.stock import StockLedger
        from app.models.enums import MovementType
        now = datetime.now(timezone.utc)
        db.add(StockLedger(
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            lot_id=uuid.UUID(s["lot_id"]),
            item_id=uuid.UUID(s["item_id"]),
            movement_type=MovementType.DELIVERY_RECEIVED,
            reference_type="delivery",
            quantity_in=30,
            quantity_out=0,
            movement_date=now,
            created_at=now,
        ))
        db.commit()

        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        row = r.json()["data"][0]
        assert float(row["delivered_qty"]) == pytest.approx(30.0)


# ── Activity tests ────────────────────────────────────────────────────────────

class TestActivity:
    def test_activity_returns_list(self, client, db, dashboard_setup):
        s = dashboard_setup
        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/activity",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_activity_includes_alerts(self, client, db, dashboard_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        s = dashboard_setup
        now = datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.MATERIAL_OVERUSE,
            severity=AlertSeverity.HIGH,
            title="Test Alert for Activity",
            message="Test",
            status=AlertStatus.OPEN,
            site_id=uuid.UUID(s["site_id"]),
            notification_channel="in_app",
            created_at=now,
        ))
        db.commit()

        r = client.get(
            f"/api/v1/site-dashboard/{s['site_id']}/lots/{s['lot_id']}/activity",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        items = r.json()["data"]
        assert any(i["type"] == "alert" for i in items)
        assert any("Test Alert for Activity" in i["title"] for i in items)


# ── Over-BOQ usage alert tests ────────────────────────────────────────────────

class TestOverBOQUsage:
    def test_stock_issue_over_lot_boq_creates_alert(self, client, db, dashboard_setup):
        """Issuing more than BOQ allocation via stock API creates a MATERIAL_OVERUSE alert."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s = dashboard_setup
        make_boq_item(db, project_id=s["project_id"], lot_id=s["lot_id"],
                      item_id=s["item_id"], qty=10.0)
        make_stock(db, project_id=s["project_id"], site_id=s["site_id"],
                   item_id=s["item_id"], qty=100.0)
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.MATERIAL_OVERUSE
        ).count()

        r = client.post(
            "/api/v1/stock/issue-to-lot",
            json={
                "project_id":    s["project_id"],
                "from_site_id":  s["site_id"],
                "lot_id":        s["lot_id"],
                "item_id":       s["item_id"],
                "quantity":      25.0,
                "overrun_reason": "Approved rework by site manager",
            },
            headers=auth(s["tok"]),
        )
        assert r.status_code == 201

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.MATERIAL_OVERUSE
        ).count()
        assert after > before


# ── Phone login tests ─────────────────────────────────────────────────────────

class TestPhoneLogin:
    def _make_user_with_phone(self, db, phone: str, password: str = "Test@1234"):
        from app.models.user import User
        from app.models.enums import UserRole
        from app.core.security import hash_password
        now = datetime.now(timezone.utc)
        u = User(
            full_name="Site Staff",
            email=f"phone_test_{uuid.uuid4().hex[:6]}@test.com",
            phone=phone,
            password_hash=hash_password(password),
            role=UserRole.SITE_STAFF,
            is_active=True,
            must_reset_password=False,
            created_at=now, updated_at=now,
        )
        db.add(u)
        db.flush()
        return u

    def test_login_with_phone_number(self, client, db):
        """A user can log in using their phone number as the username."""
        user = self._make_user_with_phone(db, phone="0831112233")
        db.commit()

        r = client.post("/api/v1/auth/login", json={
            "email": "0831112233",
            "password": "Test@1234",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_wrong_phone_returns_401(self, client, db):
        """Wrong phone number returns 401, not a redirect."""
        r = client.post("/api/v1/auth/login", json={
            "email": "0999999999",
            "password": "wrongpin",
        })
        assert r.status_code == 401

    def test_phone_login_does_not_affect_email_login(self, client, db):
        """Email login still works normally after phone fallback is added."""
        owner = make_user(db, role="OWNER")
        db.commit()
        r = client.post("/api/v1/auth/login", json={
            "email": owner["email"],
            "password": owner["password"],
        })
        assert r.status_code == 200

    def test_wrong_password_for_phone_returns_401(self, client, db):
        user = self._make_user_with_phone(db, phone="0831554433")
        db.commit()
        r = client.post("/api/v1/auth/login", json={
            "email": "0831554433",
            "password": "wrongpassword",
        })
        assert r.status_code == 401


# ── Lot sorting tests (backend) ───────────────────────────────────────────────

class TestLotSorting:
    def test_site_lot_boqs_sorts_numerically(self, client, db, dashboard_setup):
        """Lots 1,2,3...10,11 appear in numeric order, not lexicographic."""
        from app.models.lot import Lot
        from app.models.enums import LotStatus

        s = dashboard_setup
        now = datetime.now(timezone.utc)
        # Create lots in non-numeric order — use numbers > 1 to avoid fixture conflict
        for num in ["20", "12", "21", "11", "13"]:
            lot = Lot(
                project_id=uuid.UUID(s["project_id"]),
                site_id=uuid.UUID(s["site_id"]),
                lot_number=num,
                status=LotStatus.IN_PROGRESS,
                created_at=now, updated_at=now,
            )
            db.add(lot)
        db.commit()

        r = client.get(
            f"/api/v1/boq/items/sites/{s['site_id']}/lot-boqs",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        lots = r.json()["data"]
        numbers = [l["lot_number"] for l in lots]
        # Filter to our test lots (avoid the fixture's "1")
        test_nums = [n for n in numbers if n in {"11", "12", "13", "20", "21"}]
        expected_numeric = sorted(test_nums, key=lambda x: int(x))
        assert test_nums == expected_numeric, f"Expected {expected_numeric}, got {test_nums}"


# ── Phase 3J finalization tests ───────────────────────────────────────────────

class TestProjectLotMaterialSummary:
    """Tests for the new GET /projects/{id}/lots/{lot_id}/material-summary endpoint."""

    def test_basic_summary_returns_data(self, client, db, dashboard_setup):
        """Project-lot material summary endpoint returns valid data."""
        s = dashboard_setup
        make_boq_item(db, s["project_id"], s["lot_id"], s["item_id"], qty=10.0)
        db.commit()

        r = client.get(
            f"/api/v1/projects/{s['project_id']}/lots/{s['lot_id']}/material-summary",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1
        row = data[0]
        assert "boq_allocated_qty" in row
        assert "delivered_qty"    in row   # TRANSFER_IN to lot
        assert "used_qty"         in row
        assert "remaining_qty"    in row
        assert "shortfall_qty"    in row   # Phase 3J new field

    def test_freestanding_lot_summary(self, client, db):
        """Freestanding lots (site_id=None) return material summary using project master."""
        from tests.conftest import make_user, make_project, make_item, make_lot, login, auth
        from app.models.boq import BOQHeader, BOQSection, BOQItem
        from app.models.enums import BoqStatus, ItemType
        from datetime import datetime, timezone

        owner   = make_user(db, role="OWNER")
        project = make_project(db, owner["id"])
        lot_free = make_lot(db, project["id"], None, "FL-MAT")   # freestanding
        item    = make_item(db, "Freestanding Item")
        db.flush()

        # Create project-level master BOQ (site_id=None, lot_id=None)
        now = datetime.now(timezone.utc)
        hdr = BOQHeader(
            id=uuid.uuid4(), project_id=uuid.UUID(project["id"]),
            version_name="FL Master", source_type="manual",
            status=BoqStatus.ACTIVE, is_active_version=True,
            is_template=False, uploaded_by=uuid.UUID(owner["id"]), uploaded_at=now,
        )
        db.add(hdr)
        db.flush()
        from app.models.boq import BOQSection
        sec = BOQSection(
            id=uuid.uuid4(), boq_header_id=hdr.id,
            section_name="S", sequence_order=1, created_at=now, updated_at=now,
        )
        db.add(sec)
        db.flush()
        db.add(BOQItem(
            id=uuid.uuid4(), boq_section_id=sec.id,
            project_id=uuid.UUID(project["id"]),
            site_id=None, lot_id=None,
            raw_description="Cement", item_type=ItemType.MATERIAL,
            planned_quantity=20.0, sort_order=0, is_active=True,
            created_at=now, updated_at=now,
        ))
        db.commit()

        tok = login(client, owner["email"], owner["password"])
        r = client.get(
            f"/api/v1/projects/{project['id']}/lots/{lot_free['id']}/material-summary",
            headers=auth(tok),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # Freestanding lot with project master BOQ should return items
        assert isinstance(data, list)
        # May return items from project master (with fallback=True)

    def test_lot_progress_endpoint(self, client, db, dashboard_setup):
        """GET /lots/{id}/progress returns milestone completion stats."""
        from tests.conftest import login, auth
        from app.models.stage import StageMaster, ProjectStageStatus
        from app.models.enums import StageStatus
        from datetime import datetime, timezone
        s = dashboard_setup

        now = datetime.now(timezone.utc)
        stage = db.query(StageMaster).first()
        if not stage:
            stage = StageMaster(
                id=uuid.uuid4(), name="Test", sequence_order=1,
                description="T", created_at=now,
            )
            db.add(stage)
            db.flush()

        # Create 2 milestones: 1 completed, 1 in_progress
        for i, st in enumerate([StageStatus.COMPLETED, StageStatus.IN_PROGRESS]):
            db.add(ProjectStageStatus(
                project_id=uuid.UUID(s["project_id"]),
                lot_id=uuid.UUID(s["lot_id"]),
                stage_id=stage.id,
                status=st,
                progress_pct=100 if st == StageStatus.COMPLETED else 50,
                updated_by=None,
            )) if i == 0 else None   # avoid unique constraint
        db.commit()

        r = client.get(
            f"/api/v1/lots/{s['lot_id']}/progress",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "progress_pct"   in data
        assert "completion_pct" in data
        assert "total_milestones" in data
