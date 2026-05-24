"""
Invoice Proof Pack tests.

Tests:
  - Proof pack with PO linked returns po_number
  - Proof pack with delivery linked returns delivery info
  - Proof pack flags missing_delivery_note correctly
  - Proof pack flags missing_signature correctly
  - Proof pack with full match returns is_matched=True
  - Proof pack with mismatch returns is_matched=False
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import (
    auth, login, make_item, make_lot, make_project,
    make_site, make_supplier, make_user, make_user_project_access,
)


@pytest.fixture()
def proof_setup(db: Session, client: TestClient):
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db)
    item = make_item(db)
    make_user_project_access(db, office["id"], project["id"])
    db.flush()
    tok = login(client, office["email"], office["password"])
    return {
        "owner": owner, "office": office, "project": project,
        "site": site, "supplier": supplier, "item": item, "tok": tok,
    }


def _create_invoice(client, setup, po_id=None, inv_number=None):
    inv_number = inv_number or f"INV-{uuid.uuid4().hex[:8].upper()}"
    body = {
        "invoice_number": inv_number,
        "supplier_id": setup["supplier"]["id"],
        "total_amount": 2400.00,
        "subtotal_amount": 2086.96,
        "vat_amount": 313.04,
    }
    if po_id:
        body["purchase_order_id"] = po_id
    r = client.post(
        f"/api/v1/projects/{setup['project']['id']}/invoices/",
        json=body,
        headers=auth(setup["tok"]),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_po(client, setup):
    r = client.post(
        f"/api/v1/projects/{setup['project']['id']}/purchase-orders/",
        json={
            "supplier_id": setup["supplier"]["id"],
            "items": [{"description": "Test Item", "quantity_ordered": 8, "rate": 300.0}],
        },
        headers=auth(setup["tok"]),
    )
    assert r.status_code == 201
    return r.json()["data"]["id"]


def test_proof_pack_no_po(client: TestClient, proof_setup: dict):
    """Invoice with no PO: po_number is None."""
    inv_id = _create_invoice(client, proof_setup)
    r = client.get(f"/api/v1/invoices/{inv_id}/proof", headers=auth(proof_setup["tok"]))
    assert r.status_code == 200
    proof = r.json()["data"]
    assert proof["po_number"] is None
    assert proof["missing_delivery_note"] is True
    assert proof["missing_signature"] is True
    assert proof["is_matched"] is False


def test_proof_pack_with_po(client: TestClient, proof_setup: dict):
    """Invoice linked to PO: po_number present, po_items populated."""
    po_id = _create_po(client, proof_setup)
    inv_id = _create_invoice(client, proof_setup, po_id=po_id)
    r = client.get(f"/api/v1/invoices/{inv_id}/proof", headers=auth(proof_setup["tok"]))
    assert r.status_code == 200
    proof = r.json()["data"]
    assert proof["po_number"] is not None
    assert len(proof["po_items"]) == 1
    assert proof["po_items"][0]["quantity_ordered"] == 8.0


def test_proof_pack_with_delivery_note_image(db: Session, client: TestClient, proof_setup: dict):
    """Proof pack correctly reports delivery note image present/absent."""
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.enums import RecordStatus
    from app.models.invoice import InvoiceMatchingResult
    from app.models.enums import InvoiceMatchStatus

    # Create PO + invoice
    po_id = _create_po(client, proof_setup)
    inv_id = _create_invoice(client, proof_setup, po_id=po_id)

    # Manually create delivery with image
    now = datetime.now(timezone.utc)
    delivery = Delivery(
        id=uuid.uuid4(),
        delivery_number="DEL-TEST-001",
        purchase_order_id=uuid.UUID(po_id),
        supplier_id=uuid.UUID(proof_setup["supplier"]["id"]),
        project_id=uuid.UUID(proof_setup["project"]["id"]),
        site_id=uuid.UUID(proof_setup["site"]["id"]),
        received_by_user_id=uuid.UUID(proof_setup["owner"]["id"]),
        delivery_date=now,
        delivery_status=RecordStatus.RECEIVED,
        delivery_note_image_url="/uploads/demo/note.jpg",
        signature_image_url="/uploads/demo/sig.jpg",
        receiver_name="Test Receiver",
        created_at=now, updated_at=now,
    )
    db.add(delivery)
    db.flush()

    # Create match result linking invoice to delivery
    db.add(InvoiceMatchingResult(
        id=uuid.uuid4(),
        invoice_id=uuid.UUID(inv_id),
        purchase_order_id=uuid.UUID(po_id),
        delivery_id=delivery.id,
        match_status=InvoiceMatchStatus.MATCHED,
        quantity_match=True,
        amount_match=True,
        supplier_match=True,
        created_at=now,
    ))
    db.flush()

    r = client.get(f"/api/v1/invoices/{inv_id}/proof", headers=auth(proof_setup["tok"]))
    assert r.status_code == 200
    proof = r.json()["data"]

    assert proof["missing_delivery_note"] is False
    assert proof["missing_signature"] is False
    assert proof["is_matched"] is True
    assert proof["delivery_note_image_url"] == "/uploads/demo/note.jpg"
    assert proof["signature_image_url"] == "/uploads/demo/sig.jpg"
    assert proof["receiver_name"] == "Test Receiver"
    assert proof["match_status"] == "MATCHED"


def test_proof_pack_quantity_mismatch(db: Session, client: TestClient, proof_setup: dict):
    """Proof pack with QUANTITY_MISMATCH match result returns is_matched=False."""
    from app.models.delivery import Delivery
    from app.models.enums import RecordStatus, InvoiceMatchStatus
    from app.models.invoice import InvoiceMatchingResult

    po_id = _create_po(client, proof_setup)
    inv_id = _create_invoice(client, proof_setup, po_id=po_id)

    now = datetime.now(timezone.utc)
    delivery = Delivery(
        id=uuid.uuid4(),
        delivery_number="DEL-MISMATCH",
        supplier_id=uuid.UUID(proof_setup["supplier"]["id"]),
        project_id=uuid.UUID(proof_setup["project"]["id"]),
        site_id=uuid.UUID(proof_setup["site"]["id"]),
        received_by_user_id=uuid.UUID(proof_setup["owner"]["id"]),
        delivery_date=now,
        delivery_status=RecordStatus.PARTIALLY_RECEIVED,
        created_at=now, updated_at=now,
    )
    db.add(delivery)
    db.flush()

    db.add(InvoiceMatchingResult(
        id=uuid.uuid4(),
        invoice_id=uuid.UUID(inv_id),
        purchase_order_id=uuid.UUID(po_id),
        delivery_id=delivery.id,
        match_status=InvoiceMatchStatus.QUANTITY_MISMATCH,
        quantity_match=False,
        amount_match=False,
        supplier_match=True,
        notes="Invoice for 8 bags, only 6 received.",
        created_at=now,
    ))
    db.flush()

    r = client.get(f"/api/v1/invoices/{inv_id}/proof", headers=auth(proof_setup["tok"]))
    assert r.status_code == 200
    proof = r.json()["data"]
    assert proof["is_matched"] is False
    assert proof["match_status"] == "QUANTITY_MISMATCH"
    assert proof["quantity_match"] is False


def test_proof_pack_email_log(db: Session, client: TestClient, proof_setup: dict):
    """Proof pack includes email log entries for the linked PO."""
    from app.models.purchase_order import PoEmailLog
    from app.models.enums import EmailStatus

    po_id = _create_po(client, proof_setup)
    inv_id = _create_invoice(client, proof_setup, po_id=po_id)

    # Add email log manually
    now = datetime.now(timezone.utc)
    db.add(PoEmailLog(
        id=uuid.uuid4(),
        purchase_order_id=uuid.UUID(po_id),
        sent_to_email="supplier@test.com",
        email_subject="PO Test",
        email_body="<p>Test email body</p>",
        status=EmailStatus.sent,
        sent_at=now,
        created_at=now,
    ))
    db.flush()

    r = client.get(f"/api/v1/invoices/{inv_id}/proof", headers=auth(proof_setup["tok"]))
    assert r.status_code == 200
    proof = r.json()["data"]
    assert len(proof["email_logs"]) >= 1
    assert proof["email_logs"][0]["sent_to"] == "supplier@test.com"
    assert proof["email_logs"][0]["has_body"] is True
