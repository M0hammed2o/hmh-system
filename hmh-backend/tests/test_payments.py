"""
Phase 3L — Payment system tests.

Tests:
  1.  Single full payment sets invoice to PAID
  2.  Partial payment sets invoice to PARTIALLY_PAID
  3.  Second payment completing full amount sets PAID
  4.  Overpayment sets invoice to OVERPAID
  5.  Cancelled payment does not count toward balance
  6.  Payment method stored and returned
  7.  lot_id on payment stored and returned
  8.  Invoice reconciliation endpoint returns correct totals
  9.  Invoice reconciliation shows all payments with captured_by_name
  10. Payment report endpoint returns by_month + by_supplier
  11. Site user cannot access reconciliation (office-only endpoint)
  12. READ_ONLY cannot create payment
  13. Freestanding lot payment works
"""

import pytest
import uuid
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_lot, make_project, make_site, make_supplier, make_user


@pytest.fixture()
def pay_setup(db: Session, client: TestClient):
    owner   = make_user(db, role="OWNER")
    office  = make_user(db, role="OFFICE_ADMIN")
    ro      = make_user(db, role="READ_ONLY")
    site_s  = make_user(db, role="SITE_STAFF")

    project  = make_project(db, owner["id"])
    site     = make_site(db, project["id"])
    lot      = make_lot(db, project["id"], site["id"], "5")
    lot_free = make_lot(db, project["id"], None, "FREESTANDING-PAY")
    supplier = make_supplier(db)
    db.flush()

    # Create an invoice directly in DB
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    from datetime import datetime, timezone, date
    inv = Invoice(
        invoice_number  = "INV-TEST-001",
        supplier_id     = uuid.UUID(supplier["id"]),
        project_id      = uuid.UUID(project["id"]),
        invoice_date    = date.today(),
        total_amount    = 100_000.00,
        status          = RecordStatus.MATCHED,
        captured_by     = uuid.UUID(owner["id"]),
        captured_at     = datetime.now(timezone.utc),
    )
    db.add(inv)
    db.flush()

    return {
        "owner": owner, "office": office, "ro": ro, "site_staff": site_s,
        "project": project, "site": site, "lot": lot, "lot_free": lot_free,
        "supplier": supplier, "invoice_id": str(inv.id),
    }


def _create_payment(client, tok, project_id, invoice_id, amount, method=None, lot_id=None):
    body = {
        "payment_type": "SUPPLIER",
        "amount_paid":  amount,
        "invoice_id":   invoice_id,
    }
    if method:    body["payment_method"] = method
    if lot_id:    body["lot_id"]         = lot_id
    return client.post(f"/api/v1/projects/{project_id}/payments/", json=body,
        headers={"Authorization": f"Bearer {tok}"})


def test_full_payment_sets_paid(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 100_000.00)
    assert r.status_code == 201, r.text

    # Check invoice status
    from sqlalchemy import text
    status = db.execute(text("SELECT status FROM invoices WHERE id = :id"),
        {"id": pay_setup["invoice_id"]}).scalar()
    assert status == "PAID", f"Expected PAID, got {status}"


def test_partial_payment_sets_partially_paid(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 40_000.00)
    assert r.status_code == 201, r.text

    from sqlalchemy import text
    status = db.execute(text("SELECT status FROM invoices WHERE id = :id"),
        {"id": pay_setup["invoice_id"]}).scalar()
    assert status == "PARTIALLY_PAID", f"Expected PARTIALLY_PAID, got {status}"


def test_two_payments_complete_invoice(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 60_000.00)
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 40_000.00)
    assert r.status_code == 201, r.text

    from sqlalchemy import text
    status = db.execute(text("SELECT status FROM invoices WHERE id = :id"),
        {"id": pay_setup["invoice_id"]}).scalar()
    assert status == "PAID"


def test_overpayment_sets_overpaid(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 110_000.00)
    assert r.status_code == 201, r.text

    from sqlalchemy import text
    status = db.execute(text("SELECT status FROM invoices WHERE id = :id"),
        {"id": pay_setup["invoice_id"]}).scalar()
    assert status == "OVERPAID", f"Expected OVERPAID, got {status}"


def test_cancelled_payment_excluded_from_balance(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])

    # Pay full amount
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 100_000.00)
    payment_id = r.json()["data"]["id"]

    # Cancel the payment
    client.patch(f"/api/v1/payments/{payment_id}",
        json={"status": "CANCELLED"}, headers={"Authorization": f"Bearer {tok}"})

    # Invoice should revert (no active payments → remain MATCHED or not PAID)
    from sqlalchemy import text
    status = db.execute(text("SELECT status FROM invoices WHERE id = :id"),
        {"id": pay_setup["invoice_id"]}).scalar()
    assert status != "PAID", "Cancelled payment must not count toward balance"


def test_payment_method_stored(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"],
        pay_setup["invoice_id"], 50_000.00, method="EFT")
    assert r.status_code == 201, r.text
    assert r.json()["data"]["payment_method"] == "EFT"


def test_lot_id_on_payment(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"],
        pay_setup["invoice_id"], 10_000.00, lot_id=pay_setup["lot"]["id"])
    assert r.status_code == 201, r.text
    assert r.json()["data"]["lot_id"] == pay_setup["lot"]["id"]


def test_invoice_reconciliation_endpoint(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 60_000.00)
    _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 20_000.00)

    r = client.get(f"/api/v1/invoices/{pay_setup['invoice_id']}/reconciliation",
        headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_amount"]  == 100_000.00
    assert data["total_paid"]    == 80_000.00
    assert data["outstanding"]   == 20_000.00
    assert data["is_overpaid"]   is False
    assert len(data["payments"]) == 2
    assert data["status"]        == "PARTIALLY_PAID"


def test_reconciliation_captured_by_name(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 50_000.00)

    r = client.get(f"/api/v1/invoices/{pay_setup['invoice_id']}/reconciliation",
        headers={"Authorization": f"Bearer {tok}"})
    data = r.json()["data"]
    p = data["payments"][0]
    # captured_by_name should be populated
    assert p["captured_by_name"] is not None


def test_payment_report_endpoint(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 30_000.00)

    r = client.get(f"/api/v1/projects/{pay_setup['project']['id']}/payments/report",
        headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_paid"]    >= 30_000.00
    assert data["payment_count"] >= 1
    assert isinstance(data["by_month"],    list)
    assert isinstance(data["by_supplier"], list)


def test_site_user_cannot_access_reconciliation(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["site_staff"]["email"], pay_setup["site_staff"]["password"])
    r = client.get(f"/api/v1/invoices/{pay_setup['invoice_id']}/reconciliation",
        headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_read_only_cannot_create_payment(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["ro"]["email"], pay_setup["ro"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"], pay_setup["invoice_id"], 1000.00)
    assert r.status_code == 403


def test_freestanding_lot_payment(db: Session, client: TestClient, pay_setup: dict):
    tok = login(client, pay_setup["office"]["email"], pay_setup["office"]["password"])
    r = _create_payment(client, tok, pay_setup["project"]["id"],
        pay_setup["invoice_id"], 5_000.00, lot_id=pay_setup["lot_free"]["id"])
    assert r.status_code == 201, r.text
    assert r.json()["data"]["lot_id"] == pay_setup["lot_free"]["id"]
