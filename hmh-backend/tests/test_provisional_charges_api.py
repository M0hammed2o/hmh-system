"""
Pending supplier charges are reachable, and separate from Accounts Payable.

The separation is the point. A pro-forma must be findable, and must not be
reachable through any route that a caller could sum into what the business
owes. These tests assert both halves.
"""

import uuid

import pytest


def _owner(db, client):
    from tests.conftest import make_user

    user = make_user(db, role="OWNER")
    db.commit()
    res = client.post("/api/v1/auth/login", json={
        "email": user["email"], "password": "Test@1234",
    })
    assert res.status_code == 200, res.text
    return user, {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project_and_supplier(db, owner):
    from tests.conftest import make_project, make_supplier

    project = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db, name="Vantage Readymix")
    db.commit()
    return uuid.UUID(project["id"]), uuid.UUID(supplier["id"])


def _charge(db, project_id, supplier_id, actor_id, *, reference, total, paid=False):
    from app.services import provisional_charge_service as charges

    charge = charges.create_charge(
        db, project_id=project_id, supplier_id=supplier_id,
        reference=reference, total_amount=total, actor_id=actor_id,
        payment_evidence_detected=paid,
        payment_evidence_note=(
            "Payment evidence detected — verification required." if paid else None
        ),
    )
    db.commit()
    return charge


# ── Reachable ─────────────────────────────────────────────────────────────────

def test_pending_charges_are_listed(db, client):
    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
            reference="P77120", total=20360.89)

    res = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/", headers=headers,
    )
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert [r["reference"] for r in rows] == ["P77120"]
    assert rows[0]["status"] == "PENDING"
    assert rows[0]["supplier_name"] == "Vantage Readymix"


def test_the_summary_says_what_the_number_means(db, client):
    """
    A bare total on a screen invites being added to Accounts Payable. The
    endpoint states in words that it must not be.
    """
    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
            reference="P77120", total=20360.89)
    _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
            reference="QTE7410", total=14300.00, paid=True)

    data = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/summary", headers=headers,
    ).json()["data"]

    assert data["pending_count"] == 2
    assert data["pending_total"] == pytest.approx(34660.89)
    assert data["payment_evidence_count"] == 1
    assert "not owed" in data["meaning"]
    assert "Accounts Payable" in data["meaning"]


def test_a_closed_charge_leaves_the_pending_list(db, client):
    from datetime import datetime, timezone

    from app.models.enums import RecordStatus
    from app.models.invoice import Invoice
    from app.services import provisional_charge_service as charges

    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    charge = _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
                     reference="QTE7410", total=14300.00)

    invoice = Invoice(
        invoice_number="INV-7781", supplier_id=supplier_id, project_id=project_id,
        total_amount=14300.00, status=RecordStatus.DRAFT,
        captured_by=uuid.UUID(owner["id"]),
        captured_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    charges.settle_against_invoice(db, charge, invoice, uuid.UUID(owner["id"]))
    db.commit()

    pending = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/?status=PENDING",
        headers=headers,
    ).json()["data"]
    assert pending == []

    everything = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/", headers=headers,
    ).json()["data"]
    assert len(everything) == 1
    assert everything[0]["status"] == "INVOICED"
    assert everything[0]["settled_by_invoice_number"] == "INV-7781"


# ── Separate from Accounts Payable ────────────────────────────────────────────

def test_a_pending_charge_never_appears_among_invoices(db, client):
    """
    The guarantee stated from the other side: whatever a caller asks the
    invoice routes for, a pro-forma is not in the answer.
    """
    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
            reference="P77120", total=20360.89)

    res = client.get(f"/api/v1/projects/{project_id}/invoices/", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"] == []


# ── Cancelling ────────────────────────────────────────────────────────────────

def test_a_charge_can_be_withdrawn_with_a_reason(db, client):
    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    charge = _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
                     reference="QTE7410", total=14300.00)

    res = client.post(
        f"/api/v1/provisional-charges/{charge.id}/cancel",
        json={"reason": "Supplier withdrew the offer; no goods to be supplied."},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "CANCELLED"

    pending = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/?status=PENDING",
        headers=headers,
    ).json()["data"]
    assert pending == []


def test_cancelling_requires_a_reason(db, client):
    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    charge = _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
                     reference="QTE7410", total=14300.00)

    res = client.post(
        f"/api/v1/provisional-charges/{charge.id}/cancel",
        json={"reason": ""}, headers=headers,
    )
    assert res.status_code == 422


def test_an_invoiced_charge_cannot_be_cancelled(db, client):
    """Deal with the invoice instead; the liability is real by then."""
    from datetime import datetime, timezone

    from app.models.enums import RecordStatus
    from app.models.invoice import Invoice
    from app.services import provisional_charge_service as charges

    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)
    charge = _charge(db, project_id, supplier_id, uuid.UUID(owner["id"]),
                     reference="QTE7410", total=14300.00)
    invoice = Invoice(
        invoice_number="INV-7781", supplier_id=supplier_id, project_id=project_id,
        total_amount=14300.00, status=RecordStatus.DRAFT,
        captured_by=uuid.UUID(owner["id"]),
        captured_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    charges.settle_against_invoice(db, charge, invoice, uuid.UUID(owner["id"]))
    db.commit()

    res = client.post(
        f"/api/v1/provisional-charges/{charge.id}/cancel",
        json={"reason": "Changed our minds."}, headers=headers,
    )
    assert res.status_code == 409


# ── Access ────────────────────────────────────────────────────────────────────

def test_the_routes_require_authentication(db, client):
    owner, _ = _owner(db, client)
    project_id, _supplier = _project_and_supplier(db, owner)
    assert client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/"
    ).status_code in (401, 403)


def test_the_matched_order_is_named_not_just_referenced(db, client):
    """
    A screen showing a UUID for "matched order" has not told anybody which
    order it matched.
    """
    from datetime import date

    from app.models.enums import RecordStatus
    from app.models.purchase_order import PurchaseOrder

    owner, headers = _owner(db, client)
    project_id, supplier_id = _project_and_supplier(db, owner)

    po = PurchaseOrder(
        po_number="PO-122", project_id=project_id, supplier_id=supplier_id,
        po_date=date.today(), status=RecordStatus.DRAFT,
        created_by=uuid.UUID(owner["id"]),
    )
    db.add(po)
    db.flush()

    from app.services import provisional_charge_service as charges
    charges.create_charge(
        db, project_id=project_id, supplier_id=supplier_id,
        reference="QTE7410", total_amount=14300.00,
        actor_id=uuid.UUID(owner["id"]), purchase_order_id=po.id,
    )
    db.commit()

    row = client.get(
        f"/api/v1/projects/{project_id}/provisional-charges/", headers=headers,
    ).json()["data"][0]
    assert row["purchase_order_number"] == "PO-122"
