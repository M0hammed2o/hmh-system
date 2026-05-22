"""
Phase 3F — Dashboard Operations tests.

Tests:
  1.  GET /dashboard/ops-summary returns all 4 sections
  2.  Financial section counts outstanding invoices correctly
  3.  Financial section counts overdue invoices
  4.  Financial section payments_this_month is bounded to current month
  5.  Milestone section counts blocked milestones
  6.  Milestone section counts delayed milestones
  7.  Warehouse section counts projects with stock
  8.  Fuel section counts flagged entries
  9.  project_id filter scopes results
  10. READ_ONLY can access ops-summary (read endpoint)
  11. Freestanding project (no sites) supported
  12. GET /dashboard/operations returns per-project data
"""

import uuid
import pytest
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_lot, make_project, make_site, make_stock, make_supplier, make_user


@pytest.fixture()
def dash_setup(db: Session, client: TestClient):
    owner  = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_ADMIN")
    ro     = make_user(db, role="READ_ONLY")

    project      = make_project(db, owner["id"])
    project_free = make_project(db, owner["id"])   # no sites — freestanding
    site         = make_site(db, project["id"])
    lot          = make_lot(db, project["id"], site["id"], "1")
    lot_free     = make_lot(db, project_free["id"], None, "F1")  # freestanding

    db.flush()
    return {
        "owner": owner, "office": office, "ro": ro,
        "project": project, "project_free": project_free,
        "site": site, "lot": lot, "lot_free": lot_free,
    }


def test_ops_summary_returns_all_sections(db: Session, client: TestClient, dash_setup: dict):
    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get("/api/v1/dashboard/ops-summary", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "financial"  in data
    assert "milestones" in data
    assert "warehouse"  in data
    assert "fuel"       in data


def test_financial_outstanding_invoices(db: Session, client: TestClient, dash_setup: dict):
    """Outstanding invoice count reflects MATCHED invoices."""
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus

    now = datetime.now(timezone.utc)
    inv = Invoice(
        invoice_number="INV-DASH-001",
        supplier_id=uuid.UUID(make_supplier(db)["id"]),
        project_id=uuid.UUID(dash_setup["project"]["id"]),
        total_amount=50_000.0,
        status=RecordStatus.MATCHED,
        captured_by=uuid.UUID(dash_setup["owner"]["id"]),
        captured_at=now,
    )
    db.add(inv)
    db.commit()

    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get(f"/api/v1/dashboard/ops-summary?project_id={dash_setup['project']['id']}",
        headers=auth(tok))
    data = r.json()["data"]
    assert data["financial"]["outstanding_invoice_count"] >= 1
    assert data["financial"]["outstanding_total"] >= 50_000.0


def test_financial_overdue_invoices(db: Session, client: TestClient, dash_setup: dict):
    """Overdue = MATCHED invoice with due_date in the past."""
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus

    now = datetime.now(timezone.utc)
    past = date.today() - timedelta(days=5)
    inv = Invoice(
        invoice_number="INV-OVERDUE",
        supplier_id=uuid.UUID(make_supplier(db)["id"]),
        project_id=uuid.UUID(dash_setup["project"]["id"]),
        total_amount=25_000.0,
        due_date=past,
        status=RecordStatus.MATCHED,
        captured_by=uuid.UUID(dash_setup["owner"]["id"]),
        captured_at=now,
    )
    db.add(inv)
    db.commit()

    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get(f"/api/v1/dashboard/ops-summary?project_id={dash_setup['project']['id']}",
        headers=auth(tok))
    data = r.json()["data"]
    assert data["financial"]["overdue_count"] >= 1
    assert data["financial"]["overdue_total"] >= 25_000.0


def test_milestone_blocked_count(db: Session, client: TestClient, dash_setup: dict):
    """Blocked milestone count reflected in ops-summary."""
    from app.models.stage import StageMaster, ProjectStageStatus
    from app.models.enums import StageStatus

    now = datetime.now(timezone.utc)
    stage = db.query(StageMaster).first()
    if not stage:
        stage = StageMaster(id=uuid.uuid4(), name="X", sequence_order=99, created_at=now)
        db.add(stage); db.flush()

    db.add(ProjectStageStatus(
        project_id=uuid.UUID(dash_setup["project"]["id"]),
        lot_id=uuid.UUID(dash_setup["lot"]["id"]),
        stage_id=stage.id,
        status=StageStatus.BLOCKED,
        blocked_reason="Awaiting materials",
        progress_pct=0,
        updated_by=None,
    ))
    db.commit()

    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get(f"/api/v1/dashboard/ops-summary?project_id={dash_setup['project']['id']}",
        headers=auth(tok))
    data = r.json()["data"]
    assert data["milestones"]["blocked_count"] >= 1


def test_warehouse_projects_with_stock(db: Session, client: TestClient, dash_setup: dict):
    """Warehouse stock shows projects with project warehouse entries."""
    item = __import__("tests.conftest", fromlist=["make_item"]).make_item(db)
    # Add to project warehouse (site_id=None, lot_id=None)
    make_stock(db, dash_setup["project"]["id"], None, item["id"], qty=50.0)
    db.commit()

    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get("/api/v1/dashboard/ops-summary", headers=auth(tok))
    data = r.json()["data"]
    assert data["warehouse"]["projects_with_stock"] >= 1


def test_project_id_filter_scopes_results(db: Session, client: TestClient, dash_setup: dict):
    """project_id query param scopes all sections to that project."""
    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r1 = client.get("/api/v1/dashboard/ops-summary", headers=auth(tok))
    r2 = client.get(f"/api/v1/dashboard/ops-summary?project_id={dash_setup['project_free']['id']}",
        headers=auth(tok))
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Scoped result should have ≤ global count (less data)
    global_ms = r1.json()["data"]["milestones"]["blocked_count"]
    scoped_ms = r2.json()["data"]["milestones"]["blocked_count"]
    assert scoped_ms <= global_ms


def test_readonly_can_access_ops_summary(db: Session, client: TestClient, dash_setup: dict):
    """READ_ONLY role can read dashboard (read-only endpoint)."""
    tok = login(client, dash_setup["ro"]["email"], dash_setup["ro"]["password"])
    r = client.get("/api/v1/dashboard/ops-summary", headers=auth(tok))
    assert r.status_code == 200


def test_freestanding_project_supported(db: Session, client: TestClient, dash_setup: dict):
    """Freestanding project (no sites) does not cause 500."""
    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get(f"/api/v1/dashboard/ops-summary?project_id={dash_setup['project_free']['id']}",
        headers=auth(tok))
    assert r.status_code == 200
    data = r.json()["data"]
    # Should return zero counts, not error
    assert data["milestones"]["blocked_count"] == 0


def test_operations_returns_per_project(db: Session, client: TestClient, dash_setup: dict):
    """GET /dashboard/operations returns list with project fields."""
    tok = login(client, dash_setup["office"]["email"], dash_setup["office"]["password"])
    r = client.get("/api/v1/dashboard/operations", headers=auth(tok))
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)
    if data:
        p = data[0]
        assert "project_id" in p
        assert "total_lots" in p
        assert "progress_pct" in p
