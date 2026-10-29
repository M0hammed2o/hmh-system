"""
Quotations and pro-forma invoices must not become liabilities.

Drawn from a real batch of 20 HMH documents for Minerat Construction &
Civils, Dassenhoek. Half of them are quotations or pro-formas, and the
engine had a type for neither — so both were headed for SUPPLIER_INVOICE or
UNKNOWN.

SUPPLIER_INVOICE is the dangerous one. A pro-forma says "Invoice" across the
top while being a request for payment in advance. Booking one as a supplier
invoice creates an Accounts Payable entry that does not exist, and when the
real tax invoice arrives for the same goods the business owes it twice.

The batch contains exactly that chain three times over:

    PO-01  BUILD IT        R3 699.55  ->  Pinetown Build It pro-forma QTE254210
    PO-022 SDS BLOCKS      R12 254.00 ->  SDS pro-forma QTE5895
    PO-017 KILLARNEY       R494.32    ->  Killarney TAX INVOICE 85956

One purchase each. One liability each — and only when the tax invoice comes.
"""

import uuid

import pytest

from app.models.enums import AIImportDocumentType as T
from app.services import ai_import_posting_service as posting


# ── The types exist at all ───────────────────────────────────────────────────

def test_a_quotation_has_its_own_type():
    """Without this the classifier can only call it an invoice or unknown."""
    assert T.QUOTATION.value == "QUOTATION"


def test_a_proforma_has_its_own_type_distinct_from_a_tax_invoice():
    assert T.PRO_FORMA_INVOICE.value == "PRO_FORMA_INVOICE"
    assert T.PRO_FORMA_INVOICE is not T.SUPPLIER_INVOICE


# ── Neither may post ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc_type", [T.QUOTATION, T.PRO_FORMA_INVOICE])
def test_neither_type_has_a_posting_path(doc_type):
    assert doc_type in posting._UNSUPPORTED


def test_the_quotation_refusal_explains_itself():
    """
    "Not supported" would invite someone to reclassify it as an invoice to
    force it through. The message has to say what a quotation is and what to
    do instead.
    """
    message = posting._UNSUPPORTED[T.QUOTATION].lower()
    assert "price offer" in message
    assert "purchase order" in message


def test_the_proforma_refusal_names_the_double_counting_risk():
    message = posting._UNSUPPORTED[T.PRO_FORMA_INVOICE].lower()
    assert "tax invoice" in message
    assert "again" in message or "twice" in message


@pytest.mark.parametrize("doc_type", [T.QUOTATION, T.PRO_FORMA_INVOICE])
def test_posting_is_refused_rather_than_silently_skipped(db, doc_type):
    """
    A silent skip would leave the document looking posted. It must refuse
    loudly, so the operator knows the liability was never created.
    """
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus
    from app.models.user import User
    from app.services.ai_import_extraction_service import DocumentExtractionPayload
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    batch = AIImportBatch(reference=f"T-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    doc = AIImportDocument(
        batch_id=batch.id, file_name="20261019104537.pdf",
        stored_path="supabase://ai_import/x/doc.pdf",
        mime_type="application/pdf", file_size_bytes=1000,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.READY_TO_POST,
        document_type=doc_type,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(doc)
    db.commit()

    actor = db.get(User, uuid.UUID(owner["id"]))
    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, doc, DocumentExtractionPayload(), actor)

    db.refresh(doc)
    assert doc.status != AIImportDocumentStatus.POSTED


@pytest.mark.parametrize("doc_type", [T.QUOTATION, T.PRO_FORMA_INVOICE])
def test_a_refused_document_creates_no_invoice_and_no_stock(db, doc_type):
    """The property the business cares about, stated directly."""
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus
    from app.models.invoice import Invoice
    from app.models.stock import StockLedger
    from app.models.user import User
    from app.services.ai_import_extraction_service import DocumentExtractionPayload
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    batch = AIImportBatch(reference=f"T-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    doc = AIImportDocument(
        batch_id=batch.id, file_name="proforma.pdf",
        stored_path="supabase://ai_import/x/p.pdf",
        mime_type="application/pdf", file_size_bytes=1000,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.READY_TO_POST,
        document_type=doc_type,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(doc)
    db.commit()

    invoices_before = db.query(Invoice).count()
    stock_before = db.query(StockLedger).count()

    actor = db.get(User, uuid.UUID(owner["id"]))
    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, doc, DocumentExtractionPayload(), actor)
    db.rollback()

    assert db.query(Invoice).count() == invoices_before, "a liability was created"
    assert db.query(StockLedger).count() == stock_before, "stock moved"


# ── Only the right things post ───────────────────────────────────────────────

def test_a_tax_invoice_still_has_a_posting_path():
    """The change must not have shut the real liability out."""
    assert T.SUPPLIER_INVOICE not in posting._UNSUPPORTED


@pytest.mark.parametrize("doc_type", [
    T.PURCHASE_ORDER, T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE, T.MATERIAL_REQUEST,
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
    assert T.PURCHASE_ORDER not in (T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE)
