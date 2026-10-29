"""
An imported supplier liability starts unpaid, and stays that way until
somebody records a payment.

Two documents in the batch of twenty arrived stamped PAID — a Pinetown Build
It pro-forma and Minerat's own PO-113 to Northgate Plumbing. A stamp is a claim made by
whoever held it. It may mean the money left the bank, or that somebody
intended to pay, or that a stamp and a pile of paper ended up on the same
desk. Only the bank knows, and the system's record of the bank is a Payment
row.

So payment status is derived from Payment rows and from nothing else. That
rule already held for invoices captured by hand; these tests fix it in place
for invoices that arrive through document import, where the temptation to
believe the paperwork is strongest.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.enums import AIImportDocumentType as T
from app.models.enums import RecordStatus
from app.services import ai_import_posting_service as posting


def _setup(db):
    from tests.conftest import make_project, make_supplier, make_user

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db, name="Quarryside Aggregates")
    db.commit()
    return (
        owner,
        uuid.UUID(project["id"]),
        uuid.UUID(supplier["id"]),
    )


def _payload(**fields):
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedField

    payload = DocumentExtractionPayload()
    payload.fields = {
        name: ExtractedField(value=str(value), page=1, confidence=0.95)
        for name, value in fields.items()
    }
    return payload


def _document(db, owner, project_id, supplier_id, *, paid_stamp=False):
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus

    batch = AIImportBatch(reference=f"U-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    document = AIImportDocument(
        batch_id=batch.id, file_name="20261019110855.pdf",
        stored_path=f"supabase://ai_import/x/{uuid.uuid4().hex}.pdf",
        mime_type="application/pdf", file_size_bytes=2048,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.READY_TO_POST,
        document_type=T.SUPPLIER_INVOICE,
        project_id=project_id, supplier_id=supplier_id,
        payment_evidence_detected=paid_stamp,
        payment_evidence_note=(
            "Payment evidence detected — verification required."
            if paid_stamp else None
        ),
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(document)
    db.commit()
    return document


def _post_invoice(db, owner, project_id, supplier_id, *, paid_stamp=False,
                  number="85956", total="577.32"):
    from app.models.invoice import Invoice
    from app.models.user import User

    document = _document(db, owner, project_id, supplier_id, paid_stamp=paid_stamp)
    actor = db.get(User, uuid.UUID(owner["id"]))
    posting.post_document(db, document, _payload(
        document_number=number, total_amount=total,
        issue_date="2026-08-20",
    ), actor)
    return db.query(Invoice).filter(Invoice.invoice_number == number).one()


# ── Unpaid on arrival ─────────────────────────────────────────────────────────

def test_an_imported_invoice_starts_unpaid(db):
    """Quarryside 85956, R577.32 — a real liability from the batch."""
    owner, project_id, supplier_id = _setup(db)
    invoice = _post_invoice(db, owner, project_id, supplier_id)

    assert invoice.status not in (
        RecordStatus.PAID, RecordStatus.PARTIALLY_PAID, RecordStatus.OVERPAID,
    )


def test_an_invoice_stamped_paid_still_starts_unpaid(db):
    """
    The one that matters. The paperwork says paid; the bank has not been
    consulted; nothing is marked as settled.
    """
    from app.models.payment import Payment

    owner, project_id, supplier_id = _setup(db)
    payments_before = db.query(Payment).count()

    invoice = _post_invoice(db, owner, project_id, supplier_id, paid_stamp=True)

    assert invoice.status is not RecordStatus.PAID
    assert db.query(Payment).count() == payments_before, (
        "importing a stamped document created a payment record"
    )


def test_importing_creates_no_payment_rows_at_all(db):
    from app.models.payment import Payment

    owner, project_id, supplier_id = _setup(db)
    before = db.query(Payment).count()
    _post_invoice(db, owner, project_id, supplier_id)
    assert db.query(Payment).count() == before


# ── Payments recorded afterwards ──────────────────────────────────────────────

def _pay(db, invoice, project_id, supplier_id, owner, amount, *,
         method="EFT", reference="FNB-0001", when=None):
    from app.schemas.payment import PaymentCreate
    from app.services import payment_service

    return payment_service.create_payment(
        db, project_id,
        PaymentCreate(
            invoice_id=invoice.id,
            supplier_id=supplier_id,
            payment_type="SUPPLIER",
            amount_paid=amount,
            payment_date=when or date(2026, 8, 25),
            payment_method=method,
            payment_reference=reference,
        ),
        uuid.UUID(owner["id"]),
    )


def test_a_partial_payment_is_recorded_as_partial(db):
    """
    Suppliers are paid in instalments all the time. A part payment must not
    read as settled, and must not read as unpaid either.
    """
    owner, project_id, supplier_id = _setup(db)
    invoice = _post_invoice(db, owner, project_id, supplier_id,
                            number="90220114", total="3995.03")

    _pay(db, invoice, project_id, supplier_id, owner, 1500.00)
    db.commit()
    db.refresh(invoice)

    assert invoice.status is RecordStatus.PARTIALLY_PAID


def test_the_balance_settles_the_invoice(db):
    owner, project_id, supplier_id = _setup(db)
    invoice = _post_invoice(db, owner, project_id, supplier_id,
                            number="90220114", total="3995.03")

    _pay(db, invoice, project_id, supplier_id, owner, 1500.00, reference="FNB-1")
    _pay(db, invoice, project_id, supplier_id, owner, 2495.03, reference="FNB-2")
    db.commit()
    db.refresh(invoice)

    assert invoice.status is RecordStatus.PAID


def test_a_payment_keeps_its_date_method_and_reference(db):
    """
    What the business needs to find the payment again in the bank statement.
    """
    owner, project_id, supplier_id = _setup(db)
    invoice = _post_invoice(db, owner, project_id, supplier_id)

    payment = _pay(
        db, invoice, project_id, supplier_id, owner, 577.32,
        method="EFT", reference="FNB-884213", when=date(2026, 8, 22),
    )
    db.commit()

    assert payment.payment_method == "EFT"
    assert payment.payment_reference == "FNB-884213"
    assert payment.payment_date == date(2026, 8, 22)
    assert float(payment.amount_paid) == pytest.approx(577.32)


def test_status_follows_the_payments_not_the_document(db):
    """
    The rule stated directly: a stamped invoice becomes paid when, and only
    when, a payment row covers it.
    """
    owner, project_id, supplier_id = _setup(db)
    invoice = _post_invoice(db, owner, project_id, supplier_id, paid_stamp=True)
    assert invoice.status is not RecordStatus.PAID

    _pay(db, invoice, project_id, supplier_id, owner, 577.32)
    db.commit()
    db.refresh(invoice)
    assert invoice.status is RecordStatus.PAID


# ── A liability is created once ───────────────────────────────────────────────

def test_the_same_invoice_number_is_refused(db):
    """
    Two scans of one tax invoice are one liability. invoice_service owns the
    rule; posting surfaces it as a refusal rather than an integrity error.
    """
    from app.models.invoice import Invoice

    owner, project_id, supplier_id = _setup(db)
    _post_invoice(db, owner, project_id, supplier_id)

    with pytest.raises(posting.PostingRefused):
        _post_invoice(db, owner, project_id, supplier_id)

    assert db.query(Invoice).filter(Invoice.invoice_number == "85956").count() == 1


def test_an_invoice_with_an_unreadable_total_is_refused(db):
    """No liability is recorded from a figure nobody could read."""
    from app.models.user import User

    owner, project_id, supplier_id = _setup(db)
    document = _document(db, owner, project_id, supplier_id)
    actor = db.get(User, uuid.UUID(owner["id"]))

    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, document, _payload(document_number="85956"), actor)


@pytest.mark.parametrize("total", ["0", "0.00", "-577.32"])
def test_a_zero_or_negative_total_is_refused(db, total):
    from app.models.user import User

    owner, project_id, supplier_id = _setup(db)
    document = _document(db, owner, project_id, supplier_id)
    actor = db.get(User, uuid.UUID(owner["id"]))

    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, document, _payload(
            document_number="85956", total_amount=total), actor)
