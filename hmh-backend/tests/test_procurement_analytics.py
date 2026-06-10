"""Tests for Procurement Analytics API — Phase 5."""
import pytest
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def admin(db):
    from tests.conftest import make_user
    return make_user(db, role="OFFICE_ADMIN")


@pytest.fixture
def auth(client: TestClient, admin):
    resp = client.post("/api/v1/auth/login", json={"email": admin["email"], "password": admin["password"]})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def project(db, admin):
    from tests.conftest import make_project
    return make_project(db, owner_id=admin["id"])


@pytest.fixture
def supplier(db):
    from tests.conftest import make_supplier
    return make_supplier(db)


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_empty(client, auth):
    """Returns zero-value stats when no data exists."""
    resp = client.get("/api/v1/procurement-analytics/dashboard", headers=auth)
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert "total_spend" in d
    assert "open_pos" in d
    assert "pending_reconciliations" in d
    assert isinstance(d["total_spend"], float)


def test_dashboard_filter_params(client, auth, project, supplier):
    """Dashboard accepts project_id, supplier_id, date_from, date_to filters."""
    resp = client.get(
        "/api/v1/procurement-analytics/dashboard",
        params={
            "project_id":  project["id"],
            "supplier_id": supplier["id"],
            "date_from":   "2025-01-01",
            "date_to":     "2025-12-31",
        },
        headers=auth,
    )
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["total_spend"] == 0.0


# ── Supplier Performance ──────────────────────────────────────────────────────

def test_all_supplier_scores_list(client, auth):
    resp = client.get("/api/v1/procurement-analytics/supplier-performance", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_supplier_score_single(client, auth, supplier):
    resp = client.get(
        f"/api/v1/procurement-analytics/supplier-performance/{supplier['id']}",
        headers=auth,
    )
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert "score" in d
    assert 0 <= d["score"] <= 100
    assert "metrics" in d
    assert "stats" in d
    assert d["supplier_name"] == supplier["name"]


def test_supplier_score_not_found(client, auth):
    import uuid
    resp = client.get(
        f"/api/v1/procurement-analytics/supplier-performance/{uuid.uuid4()}",
        headers=auth,
    )
    assert resp.status_code == 404


# ── Supplier Spend ────────────────────────────────────────────────────────────

def test_supplier_spend(client, auth):
    resp = client.get("/api/v1/procurement-analytics/supplier-spend", headers=auth)
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert "top_suppliers" in d
    assert isinstance(d["top_suppliers"], list)


def test_supplier_spend_limit(client, auth):
    resp = client.get("/api/v1/procurement-analytics/supplier-spend?limit=5", headers=auth)
    assert resp.status_code == 200


# ── Project Analytics ─────────────────────────────────────────────────────────

def test_project_analytics_all(client, auth):
    resp = client.get("/api/v1/procurement-analytics/project-analytics", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_project_analytics_single(client, auth, project):
    resp = client.get(
        f"/api/v1/procurement-analytics/project-analytics?project_id={project['id']}",
        headers=auth,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    row = data[0]
    assert row["project_id"] == project["id"]
    assert "total_spend" in row
    assert "boq_budget" in row
    assert "open_pos" in row
    assert "outstanding_deliveries" in row
    assert row["total_spend"] == 0.0


# ── Price History ─────────────────────────────────────────────────────────────

def test_price_history_empty(client, auth):
    resp = client.get("/api/v1/procurement-analytics/price-history", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_price_history_search(client, auth):
    resp = client.get("/api/v1/procurement-analytics/price-history?search=cement", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


# ── Quotation Comparison ──────────────────────────────────────────────────────

def test_mrs_with_multiple_quotes_empty(client, auth):
    resp = client.get("/api/v1/procurement-analytics/quotation-comparison/mrs", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_quotation_comparison_mr_not_found(client, auth):
    import uuid
    resp = client.get(
        f"/api/v1/procurement-analytics/quotation-comparison/{uuid.uuid4()}",
        headers=auth,
    )
    assert resp.status_code == 404


# ── Savings Report ────────────────────────────────────────────────────────────

def test_savings_report_all(client, auth):
    resp = client.get("/api/v1/procurement-analytics/savings-report", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_savings_report_single_project(client, auth, project):
    resp = client.get(
        f"/api/v1/procurement-analytics/savings-report?project_id={project['id']}",
        headers=auth,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    row = data[0]
    assert row["project_id"] == project["id"]
    assert "boq_budget" in row
    assert "variance" in row
    assert row["status"] in ("under_budget", "over_budget")
    # New project with no spend → 0.0
    assert row["actual_spend"] == 0.0
    assert row["status"] == "under_budget"


# ── Export endpoints (Excel + PDF) ───────────────────────────────────────────

def test_export_supplier_spend_excel(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/supplier-spend/excel", headers=auth)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_supplier_spend_pdf(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/supplier-spend/pdf", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_export_outstanding_orders_excel(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/outstanding-orders/excel", headers=auth)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_outstanding_orders_pdf(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/outstanding-orders/pdf", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_export_savings_excel(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/savings/excel", headers=auth)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_savings_pdf(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/savings/pdf", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_export_reconciliation_excel(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/reconciliation/excel", headers=auth)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_reconciliation_pdf(client, auth):
    resp = client.get("/api/v1/procurement-analytics/reports/reconciliation/pdf", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
