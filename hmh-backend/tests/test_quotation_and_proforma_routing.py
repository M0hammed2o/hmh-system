"""
Quotations and pro-forma invoices must not become liabilities.

Drawn from a real batch of 20 HMH documents for Minerat Construction &
Civils, Dassenhoek. Half of them are quotations or pro-formas, and the engine
had a type for neither — so both were headed for SUPPLIER_INVOICE or UNKNOWN.

SUPPLIER_INVOICE is the dangerous one. A pro-forma says "Invoice" across the
top while being a request for payment in advance. Booking one as a supplier
invoice creates an Accounts Payable entry that does not exist, and when the
real tax invoice arrives for the same goods the business owes it twice.

The batch contains exactly that chain three times over:

    PO-101  LAKESIDE MERCHANT        R4 120.55  ->  Lakeside Builders Merchant pro-forma QTE880114
    PO-122 MASWELL BLOCKS      R14 300.00 ->  Maswell pro-forma QTE7410
    PO-117 QUARRYSIDE       R577.32    ->  Quarryside TAX INVOICE 85956

One purchase each. One liability each — and only when the tax invoice comes.

An earlier pass refused to post either type at all, because the system had
nowhere to put them. They now have destinations of their own: a quotation
becomes a Quotation in Procurement, a pro-forma becomes a pending charge
outside Accounts Payable. The property these tests defend is unchanged, and
is the one the business cares about — neither type may create a payable or
move stock. What changed is that the document is no longer thrown away in
order to achieve it.
"""

import uuid
from decimal import Decimal

import pytest

from app.models.enums import AIImportDocumentType as T
from app.models.enums import ProvisionalChargeStatus
from app.services import ai_import_posting_service as posting
from app.services import ai_import_routing_service as routing


# ── The types exist at all ───────────────────────────────────────────────────

def test_a_quotation_has_its_own_type():
    """Without this the classifier can only call it an invoice or unknown."""
    assert T.QUOTATION.value == "QUOTATION"


def test_a_proforma_has_its_own_type_distinct_from_a_tax_invoice():
    assert T.PRO_FORMA_INVOICE.value == "PRO_FORMA_INVOICE"
    assert T.PRO_FORMA_INVOICE is not T.SUPPLIER_INVOICE


# ── Each goes somewhere, and somewhere different ─────────────────────────────

def test_a_quotation_is_routed_to_procurement():
    assert routing.destination_for(T.QUOTATION) is routing.PROCUREMENT


def test_a_proforma_is_routed_outside_accounts_payable():
    """
    The whole point. A pro-forma is a pending charge, and Accounts Payable
    must not be able to see it.
    """
    destination = routing.destination_for(T.PRO_FORMA_INVOICE)
    assert destination is routing.PROVISIONAL_CHARGES
    assert destination is not routing.ACCOUNTS_PAYABLE


def test_only_a_tax_invoice_reaches_accounts_payable():
    payable_types = [
        t for t in T if routing.destination_for(t) is routing.ACCOUNTS_PAYABLE
    ]
    assert payable_types == [T.SUPPLIER_INVOICE]


def test_only_receipts_reach_stock():
    stock_types = {
        t for t in T if routing.destination_for(t) is routing.GOODS_RECEIVED
    }
    assert stock_types == {T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE}


# ── Posting a quotation ──────────────────────────────────────────────────────

def _context(db):
    """An owner, a project and a supplier factory, from conftest's helpers."""
    from tests.conftest import make_project, make_supplier, make_user

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    db.commit()

    def supplier(name):
        record = make_supplier(db, name=name)
        db.commit()
        return uuid.UUID(record["id"])

    return owner, uuid.UUID(project["id"]), supplier


def _document(db, owner, doc_type, *, project_id=None, supplier_id=None,
              file_name="doc.pdf"):
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus

    batch = AIImportBatch(reference=f"T-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    doc = AIImportDocument(
        batch_id=batch.id, file_name=file_name,
        stored_path=f"supabase://ai_import/x/{uuid.uuid4().hex}.pdf",
        mime_type="application/pdf", file_size_bytes=1000,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.READY_TO_POST,
        document_type=doc_type,
        project_id=project_id,
        supplier_id=supplier_id,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(doc)
    db.commit()
    return doc


def _payload(**fields):
    """An extraction payload carrying the named fields at full confidence."""
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedField

    payload = DocumentExtractionPayload()
    payload.fields = {
        name: ExtractedField(value=str(value), page=1, confidence=0.95)
        for name, value in fields.items()
    }
    return payload


def test_a_quotation_is_recorded_as_a_price_offer(db):
    """Riverside BR1-QUT/70110801, R31 050.38 — document 8 of the batch."""
    from app.models.quotation import Quotation
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Riverside Hardware")
    doc = _document(db, owner_user, T.QUOTATION,
                    project_id=project_id, supplier_id=supplier_id)
    payload = _payload(
        document_number="BR1-QUT/70110801",
        total_amount="31050.38",
        subtotal_amount="23130.77",
        vat_amount="3469.61",
        issue_date="2026-08-12",
    )

    actor = db.get(User, uuid.UUID(owner_user["id"]))
    posting.post_document(db, doc, payload, actor)

    quote = (
        db.query(Quotation)
        .filter(Quotation.quote_number == "BR1-QUT/70110801")
        .one()
    )
    assert quote.supplier_id == supplier_id
    assert Decimal(str(quote.gross_amount)) == Decimal("31050.38")


def test_a_quotation_creates_no_liability_and_no_stock(db):
    """The property the business cares about, stated directly."""
    from app.models.invoice import Invoice
    from app.models.stock import StockLedger
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Pinnacle Paints")
    doc = _document(db, owner_user, T.QUOTATION,
                    project_id=project_id, supplier_id=supplier_id)
    payload = _payload(document_number="QU08810220", total_amount="528.27")

    invoices_before = db.query(Invoice).count()
    stock_before = db.query(StockLedger).count()

    actor = db.get(User, uuid.UUID(owner_user["id"]))
    posting.post_document(db, doc, payload, actor)

    assert db.query(Invoice).count() == invoices_before, "a liability was created"
    assert db.query(StockLedger).count() == stock_before, "stock moved"


def test_the_same_quotation_is_not_recorded_twice(db):
    from app.models.quotation import Quotation
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Timberline Supply")
    actor = db.get(User, uuid.UUID(owner_user["id"]))

    first = _document(db, owner_user, T.QUOTATION, project_id=project_id,
                      supplier_id=supplier_id, file_name="a.pdf")
    posting.post_document(db, first, _payload(
        document_number="1098220", total_amount="4370.56"), actor)

    second = _document(db, owner_user, T.QUOTATION, project_id=project_id,
                       supplier_id=supplier_id, file_name="b.pdf")
    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, second, _payload(
            document_number="1098220", total_amount="4370.56"), actor)

    assert db.query(Quotation).filter(Quotation.quote_number == "1098220").count() == 1


# ── Posting a pro-forma ──────────────────────────────────────────────────────

def test_a_proforma_becomes_a_pending_charge_not_a_payable(db):
    """Vantage Readymix P77120, R20 360.89 — document 17 of the batch."""
    from app.models.invoice import Invoice
    from app.models.provisional_charge import ProvisionalCharge
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Vantage Readymix")
    doc = _document(db, owner_user, T.PRO_FORMA_INVOICE,
                    project_id=project_id, supplier_id=supplier_id)
    payload = _payload(document_number="P77120", total_amount="20360.89")

    invoices_before = db.query(Invoice).count()

    actor = db.get(User, uuid.UUID(owner_user["id"]))
    posting.post_document(db, doc, payload, actor)

    charge = db.query(ProvisionalCharge).filter(
        ProvisionalCharge.reference == "P77120").one()
    assert charge.status is ProvisionalChargeStatus.PENDING
    assert Decimal(str(charge.total_amount)) == Decimal("20360.89")

    assert db.query(Invoice).count() == invoices_before, (
        "a pro-forma created an Accounts Payable entry"
    )


def test_a_proforma_moves_no_stock(db):
    from app.models.stock import StockLedger
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Maswell Brick and Block")
    doc = _document(db, owner_user, T.PRO_FORMA_INVOICE,
                    project_id=project_id, supplier_id=supplier_id)
    payload = _payload(document_number="QTE7410", total_amount="14300.00")

    stock_before = db.query(StockLedger).count()
    actor = db.get(User, uuid.UUID(owner_user["id"]))
    posting.post_document(db, doc, payload, actor)
    assert db.query(StockLedger).count() == stock_before


def test_the_same_proforma_is_not_recorded_twice(db):
    """
    Two scans of the same request for payment are one request for payment.
    """
    from app.models.provisional_charge import ProvisionalCharge
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Lakeside Builders Merchant")
    actor = db.get(User, uuid.UUID(owner_user["id"]))

    first = _document(db, owner_user, T.PRO_FORMA_INVOICE, project_id=project_id,
                      supplier_id=supplier_id, file_name="a.pdf")
    posting.post_document(db, first, _payload(
        document_number="QTE880114", total_amount="4120.50"), actor)

    second = _document(db, owner_user, T.PRO_FORMA_INVOICE, project_id=project_id,
                       supplier_id=supplier_id, file_name="b.pdf")
    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, second, _payload(
            document_number="QTE880114", total_amount="4120.50"), actor)

    assert db.query(ProvisionalCharge).filter(
        ProvisionalCharge.reference == "QTE880114").count() == 1


def test_a_proforma_without_a_number_is_refused(db):
    """
    Without the supplier's own reference the same request cannot be
    recognised on its second scan, so there is no duplicate protection left.
    """
    from app.models.user import User

    owner_user, project_id, make_sup = _context(db)
    supplier_id = make_sup("Coastal Cement")
    doc = _document(db, owner_user, T.PRO_FORMA_INVOICE,
                    project_id=project_id, supplier_id=supplier_id)
    actor = db.get(User, uuid.UUID(owner_user["id"]))

    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, doc, _payload(total_amount="3990.77"), actor)


# ── Nothing else changed ─────────────────────────────────────────────────────

def test_a_tax_invoice_still_has_a_posting_path():
    """The change must not have shut the real liability out."""
    assert T.SUPPLIER_INVOICE not in posting._UNSUPPORTED


@pytest.mark.parametrize("doc_type", [
    T.PURCHASE_ORDER, T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE, T.MATERIAL_REQUEST,
    T.QUOTATION, T.PRO_FORMA_INVOICE,
])
def test_the_working_types_are_untouched(doc_type):
    assert doc_type not in posting._UNSUPPORTED


def test_a_purchase_order_is_not_treated_as_a_receipt():
    """
    Eight of the twenty documents are Minerat purchase orders. An order
    records intent to buy; it is not evidence that anything arrived, and
    must never move stock.
    """
    assert T.PURCHASE_ORDER is not T.DELIVERY_NOTE
    assert routing.destination_for(T.PURCHASE_ORDER) is not routing.GOODS_RECEIVED
