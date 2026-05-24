"""
Flow B + C — Stock Issue to Lot + BOQ Overrun + Warehouse → Site → Lot

Tests:
  - Issue within BOQ → 201 success, ledger entry created
  - Issue exceeding BOQ without reason → 422 with overrun detail
  - Issue exceeding BOQ with reason → 201, alert created
  - Audit event written on overrun
  - Site-to-site transfer creates two ledger entries
  - Stock balances update (checked via ledger query, not materialized view)
"""
import uuid
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import (
    auth, login, make_boq_item, make_item, make_lot, make_project,
    make_site, make_stock, make_user, make_user_project_access,
)


@pytest.fixture()
def stock_setup(db: Session, client: TestClient):
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    project = make_project(db, owner["id"])
    warehouse = make_site(db, project["id"], "Main Warehouse")
    site_store = make_site(db, project["id"], "Site Store")
    lot = make_lot(db, project["id"], site_store["id"], "T1")
    item = make_item(db, "Test Cement Bags")

    # Put 50 bags in warehouse
    make_stock(db, project["id"], warehouse["id"], item["id"], qty=50.0)
    # BOQ allocation: 10 bags for lot
    make_boq_item(db, project["id"], lot["id"], item["id"], qty=10.0)
    make_user_project_access(db, office["id"], project["id"])
    db.flush()

    return {
        "owner": owner, "office": office,
        "project": project, "warehouse": warehouse,
        "site_store": site_store, "lot": lot, "item": item,
    }


def test_issue_to_lot_within_boq(db: Session, client: TestClient, stock_setup: dict):
    """Issuing within BOQ allocation returns 201 and creates ledger entry."""
    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    r = client.post(
        "/api/v1/stock/issue-to-lot",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "lot_id": stock_setup["lot"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 5.0,
            "notes": "Test issue within BOQ",
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert "ledger_id" in data
    assert data["quantity"] == 5.0


def test_issue_to_lot_over_boq_requires_reason(db: Session, client: TestClient, stock_setup: dict):
    """Issuing beyond BOQ without reason must return 422 with overrun detail."""
    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    r = client.post(
        "/api/v1/stock/issue-to-lot",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "lot_id": stock_setup["lot"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 15.0,  # exceeds 10 bag allocation
        },
        headers=auth(tok),
    )
    assert r.status_code == 422, r.text
    # The error detail should contain overrun flag
    body = r.json()
    # FastAPI 422 wraps in detail or HMH wraps in message
    assert "overrun" in str(body).lower() or "allocation" in str(body).lower()


def test_issue_to_lot_over_boq_with_reason_succeeds(db: Session, client: TestClient, stock_setup: dict):
    """Issuing beyond BOQ WITH reason must return 201 and create alert."""
    from app.models.alert import SystemAlert
    from app.models.enums import AlertType

    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    r = client.post(
        "/api/v1/stock/issue-to-lot",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "lot_id": stock_setup["lot"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 15.0,
            "overrun_reason": "Foundation correction required extra bags",
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text

    # Alert should have been created
    alerts = db.query(SystemAlert).filter(
        SystemAlert.lot_id == uuid.UUID(stock_setup["lot"]["id"]),
        SystemAlert.alert_type == AlertType.MATERIAL_OVERUSE,
    ).all()
    assert len(alerts) >= 1, "Expected MATERIAL_OVERUSE alert to be created"


def test_site_transfer_creates_two_ledger_entries(db: Session, client: TestClient, stock_setup: dict):
    """Transfer from warehouse to site store creates TRANSFER_OUT and TRANSFER_IN entries."""
    from app.models.stock import StockLedger
    from app.models.enums import MovementType

    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    r = client.post(
        "/api/v1/stock/site-transfer",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "to_site_id": stock_setup["site_store"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 20.0,
            "notes": "Transfer for site operations",
        },
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert "out_ledger_id" in data
    assert "in_ledger_id" in data

    # Verify two ledger entries exist
    out_entry = db.get(StockLedger, uuid.UUID(data["out_ledger_id"]))
    in_entry = db.get(StockLedger, uuid.UUID(data["in_ledger_id"]))
    assert out_entry is not None
    assert in_entry is not None
    assert out_entry.movement_type == MovementType.TRANSFER_OUT
    assert in_entry.movement_type == MovementType.TRANSFER_IN
    assert float(out_entry.quantity_out) == 20.0
    assert float(in_entry.quantity_in) == 20.0


def test_stock_ledger_records_issue(db: Session, client: TestClient, stock_setup: dict):
    """After issuing to lot, a TRANSFER_IN ledger entry exists with correct lot_id."""
    from app.models.stock import StockLedger
    from app.models.enums import MovementType

    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    r = client.post(
        "/api/v1/stock/issue-to-lot",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "lot_id": stock_setup["lot"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 3.0,
        },
        headers=auth(tok),
    )
    assert r.status_code == 201

    ledger_id = uuid.UUID(r.json()["data"]["ledger_id"])
    entry = db.get(StockLedger, ledger_id)
    assert entry is not None
    assert entry.lot_id == uuid.UUID(stock_setup["lot"]["id"])
    assert entry.movement_type == MovementType.TRANSFER_IN
    assert float(entry.quantity_in) == 3.0


def test_audit_event_written_on_overrun(db: Session, client: TestClient, stock_setup: dict):
    """An audit event with OVERRUN_ACCEPTED is written when overrun_reason is provided."""
    from app.models.audit import AuditEvent

    tok = login(client, stock_setup["office"]["email"], stock_setup["office"]["password"])

    before_count = db.query(AuditEvent).count()

    client.post(
        "/api/v1/stock/issue-to-lot",
        json={
            "project_id": stock_setup["project"]["id"],
            "from_site_id": stock_setup["warehouse"]["id"],
            "lot_id": stock_setup["lot"]["id"],
            "item_id": stock_setup["item"]["id"],
            "quantity": 20.0,
            "overrun_reason": "Test overrun reason",
        },
        headers=auth(tok),
    )

    after_count = db.query(AuditEvent).count()
    assert after_count > before_count, "Expected at least one audit event"
