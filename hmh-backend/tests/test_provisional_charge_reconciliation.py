"""
Pending charges, Accounts Payable, and the line between them.

The sequence this file is about, taken from the real batch:

    PO-122 is raised with Maswell Blocks for R14 300.00
    SDS sends pro-forma QTE7410 for R14 300.00 and asks to be paid up front
    the blocks are delivered
    SDS sends a tax invoice for the same R14 300.00

A business holding all four documents owes R14 300.00, once. The ways to get
that wrong are to book the pro-forma as a payable (owed twice), to pay the
pro-forma and lose the record (paid, then invoiced again), or to discard the
pro-forma entirely (no record of what was asked for, and the advance payment
reconciles against nothing).

So the pro-forma is held outside Accounts Payable as a pending charge, and
the tax invoice closes it.
"""

import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.models.enums import ProvisionalChargeStatus
from app.services import provisional_charge_service as charges


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _setup(db):
    from tests.conftest import make_project, make_supplier, make_user

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db, name="Maswell Brick and Block")
    db.commit()
    return (
        uuid.UUID(owner["id"]),
        uuid.UUID(project["id"]),
        uuid.UUID(supplier["id"]),
    )


def _invoice(db, project_id, supplier_id, actor_id, *, number, total, po_id=None):
    from datetime import datetime, timezone

    from app.models.enums import RecordStatus
    from app.models.invoice import Invoice

    invoice = Invoice(
        invoice_number=number,
        supplier_id=supplier_id,
        project_id=project_id,
        purchase_order_id=po_id,
        total_amount=total,
        status=RecordStatus.DRAFT,
        captured_by=actor_id,
        captured_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    return invoice


def _purchase_order(db, project_id, supplier_id, actor_id, number="PO-122"):
    from datetime import date

    from app.models.enums import RecordStatus
    from app.models.purchase_order import PurchaseOrder

    po = PurchaseOrder(
        po_number=number,
        project_id=project_id,
        supplier_id=supplier_id,
        po_date=date.today(),
        status=RecordStatus.DRAFT,
        created_by=actor_id,
    )
    db.add(po)
    db.flush()
    return po


# ── A pending charge is not a payable ─────────────────────────────────────────

def test_a_pending_charge_does_not_appear_in_accounts_payable(db):
    from app.models.invoice import Invoice

    actor, project, supplier = _setup(db)
    before = db.query(Invoice).count()

    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
    )
    db.commit()

    assert db.query(Invoice).count() == before


def test_outstanding_total_is_reported_separately(db):
    actor, project, supplier = _setup(db)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
    )
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="P77120", total_amount=20360.89, actor_id=actor,
    )
    db.commit()

    assert charges.outstanding_total(db, project) == pytest.approx(34660.89)


def test_a_closed_charge_leaves_the_outstanding_total(db):
    """Otherwise the same money is reported as pending and as owed."""
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    db.commit()
    assert charges.outstanding_total(db, project) == pytest.approx(14300.00)

    invoice = _invoice(db, project, supplier, actor,
                       number="INV-7781", total=14300.00, po_id=po.id)
    charges.settle_against_invoice(db, charge, invoice, actor)
    db.commit()

    assert charges.outstanding_total(db, project) == 0.0


# ── The reconciliation ────────────────────────────────────────────────────────

def test_the_tax_invoice_closes_the_pro_forma(db):
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    invoice = _invoice(db, project, supplier, actor,
                       number="INV-7781", total=14300.00, po_id=po.id)
    db.commit()

    found = charges.find_pending_for_invoice(db, invoice)
    assert found is not None and found.id == charge.id

    charges.settle_against_invoice(db, found, invoice, actor)
    db.commit()
    db.refresh(charge)

    assert charge.status is ProvisionalChargeStatus.INVOICED
    assert charge.settled_by_invoice_id == invoice.id


def test_a_charge_is_matched_on_the_order_not_the_amount(db):
    """
    A pro-forma and the tax invoice that follows it routinely differ —
    delivery charges, part supply, a price change between quote and supply.
    Matching on the amount would leave the charge open whenever they did.
    """
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    invoice = _invoice(db, project, supplier, actor,
                       number="INV-7781", total=12980.50, po_id=po.id)
    db.commit()

    assert charges.find_pending_for_invoice(db, invoice) is not None


def test_an_invoice_without_an_order_closes_nothing(db):
    """
    Supplier alone is not a safe key: a supplier with two open pro-formas
    would have an arbitrary one of them closed by an unrelated invoice.
    """
    actor, project, supplier = _setup(db)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
    )
    invoice = _invoice(db, project, supplier, actor,
                       number="INV-9999", total=14300.00)
    db.commit()

    assert charges.find_pending_for_invoice(db, invoice) is None


def test_a_charge_is_not_closed_twice(db):
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    first = _invoice(db, project, supplier, actor,
                     number="INV-1", total=14300.00, po_id=po.id)
    second = _invoice(db, project, supplier, actor,
                      number="INV-2", total=14300.00, po_id=po.id)
    db.commit()

    charges.settle_against_invoice(db, charge, first, actor)
    db.commit()

    with pytest.raises(ConflictError):
        charges.settle_against_invoice(db, charge, second, actor)


def test_a_second_invoice_on_the_same_order_finds_no_open_charge(db):
    """
    The guarantee stated from the invoice's side: once the charge is closed,
    nothing else can close it, so a second invoice cannot re-consume it.
    """
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    first = _invoice(db, project, supplier, actor,
                     number="INV-1", total=14300.00, po_id=po.id)
    db.commit()
    charges.settle_against_invoice(db, charge, first, actor)
    db.commit()

    second = _invoice(db, project, supplier, actor,
                      number="INV-2", total=14300.00, po_id=po.id)
    db.commit()
    assert charges.find_pending_for_invoice(db, second) is None


# ── Duplicates ────────────────────────────────────────────────────────────────

def test_the_same_pro_forma_number_is_refused(db):
    actor, project, supplier = _setup(db)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
    )
    db.commit()

    with pytest.raises(ConflictError):
        charges.create_charge(
            db, project_id=project, supplier_id=supplier,
            reference="QTE7410", total_amount=14300.00, actor_id=actor,
        )


def test_the_same_number_from_a_different_supplier_is_fine(db):
    """Suppliers number their own documents; collisions mean nothing."""
    from tests.conftest import make_supplier

    actor, project, supplier = _setup(db)
    other = uuid.UUID(make_supplier(db, name="Vantage Readymix")["id"])
    db.commit()

    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="P77120", total_amount=14300.00, actor_id=actor,
    )
    charges.create_charge(
        db, project_id=project, supplier_id=other,
        reference="P77120", total_amount=20360.89, actor_id=actor,
    )
    db.commit()

    assert len(charges.list_charges(db, project)) == 2


def test_the_database_refuses_a_duplicate_even_without_the_service(db):
    """
    The uniqueness rule belongs to the table, not to whichever code path
    happens to be inserting.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.provisional_charge import ProvisionalCharge

    actor, project, supplier = _setup(db)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
    )
    db.commit()

    db.add(ProvisionalCharge(
        reference="QTE7410", supplier_id=supplier, project_id=project,
        total_amount=Decimal("14300.00"), created_by=actor,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ── Refusals ──────────────────────────────────────────────────────────────────

def test_a_charge_without_a_reference_is_refused(db):
    actor, project, supplier = _setup(db)
    with pytest.raises(ValidationError):
        charges.create_charge(
            db, project_id=project, supplier_id=supplier,
            reference="   ", total_amount=14300.00, actor_id=actor,
        )


@pytest.mark.parametrize("amount", [0, -1, -14300.00])
def test_a_charge_of_zero_or_less_is_refused(db, amount):
    actor, project, supplier = _setup(db)
    with pytest.raises(ValidationError):
        charges.create_charge(
            db, project_id=project, supplier_id=supplier,
            reference="QTE7410", total_amount=amount, actor_id=actor,
        )


# ── Payment evidence travels with the charge ──────────────────────────────────

def test_a_paid_stamp_is_carried_but_settles_nothing(db):
    """
    Document 1 of the batch: a Lakeside Builders Merchant pro-forma stamped PAID. The
    claim is recorded; the charge stays pending, because a stamp is not a
    bank record.
    """
    actor, project, supplier = _setup(db)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE880114", total_amount=4120.50, actor_id=actor,
        payment_evidence_detected=True,
        payment_evidence_note="Payment evidence detected — verification required.",
    )
    db.commit()

    assert charge.payment_evidence_detected is True
    assert charge.status is ProvisionalChargeStatus.PENDING
    assert charge.settled_by_invoice_id is None


def test_two_pending_charges_on_one_order_close_neither(db):
    """
    A supplier can send two pro-formas against the same order — a deposit
    and a balance, or a revised request. When the tax invoice arrives there
    is no way to tell which it settles.

    Closing an arbitrary one would mark a request as invoiced that was not,
    and leave the real one pending. Both stay open instead: under-closing is
    visible and recoverable, a wrong closure hides itself.
    """
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410-A", total_amount=7000.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410-B", total_amount=7300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    invoice = _invoice(db, project, supplier, actor,
                       number="INV-7781", total=14300.00, po_id=po.id)
    db.commit()

    assert charges.find_pending_for_invoice(db, invoice) is None
    assert len(charges.list_charges(
        db, project, status=ProvisionalChargeStatus.PENDING)) == 2


def test_one_pending_charge_on_an_order_still_closes(db):
    """The unambiguous case must keep working."""
    actor, project, supplier = _setup(db)
    po = _purchase_order(db, project, supplier, actor)
    charge = charges.create_charge(
        db, project_id=project, supplier_id=supplier,
        reference="QTE7410", total_amount=14300.00, actor_id=actor,
        purchase_order_id=po.id,
    )
    invoice = _invoice(db, project, supplier, actor,
                       number="INV-7781", total=14300.00, po_id=po.id)
    db.commit()

    found = charges.find_pending_for_invoice(db, invoice)
    assert found is not None and found.id == charge.id
