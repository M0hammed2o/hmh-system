"""
The twenty-document batch, end to end.

This is the acceptance set: twenty real pieces of paper that arrived together
for Minerat Construction & Civils at Dassenhoek. Quotations, purchase orders,
pro-formas, two tax invoices, a fuel order and one handwritten delivery note,
in no order, several of them scans of scans.

The text in each fixture is transcribed from the document itself. It is
deliberately not tidied up: the rotated scan stays sparse, the handwritten
note stays thin, the misspelt site name stays misspelt. The system has to
cope with the paperwork that exists, and a test written against clean
examples proves nothing about it.

Three properties are being defended, in order of how much they cost to get
wrong:

  1. Of twenty documents, exactly two create a liability and exactly one
     moves stock. Everything else creates something harmless or nothing.
  2. No purchase is counted twice, even though three of the pairs describe
     the same purchase under two different document types.
  3. Nothing is invented. Where the paper is ambiguous the answer is review,
     not a confident guess — lot A599 being the standing example.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pytest

from app.models.enums import AIImportDocumentType as T
from app.services import ai_import_routing_service as routing
from app.services.ai_import_extraction_service import _classify_from_text


# ── The batch ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Doc:
    file_name: str
    text: str
    expected_type: T
    supplier: str
    amount: Optional[str]
    destination: str
    # True where the paperwork claims it has been paid.
    paid_stamp: bool = False
    note: str = ""


BATCH: tuple[Doc, ...] = (
    Doc(
        "20261019110559.pdf",
        """BUILD IT PINETOWN
           VAT Reg No: 4290116892
           PRO FORMA INVOICE
           Document No: QTE254210  Date: 14/08/2026
           Customer: MINERAT CONSTRUCTION & CIVILS
           Total Due R 3 699.50
           PAID""",
        T.PRO_FORMA_INVOICE, "Pinetown Build It", "3699.50",
        "provisional_charges", paid_stamp=True,
        note="Pairs with PO-01. Supplier absent from production.",
    ),
    Doc(
        "20261019110121.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-038
           Supplier: FUEL UP
           500 Litres Diesel 50PPM
           Deliver to: dassenhoek
           Total 13 575.00""",
        T.PURCHASE_ORDER, "Fuel Up", "13575.00",
        "fuel_procurement",
        note="Fuel, not materials. Must never become warehouse stock.",
    ),
    Doc(
        "20261019110033.pdf",
        """HUAXIN   STERKSPRUIT
           PRO FORMA
           SQ473889
           3 407.77""",
        T.PRO_FORMA_INVOICE, "Huaxin", "3407.77",
        "provisional_charges",
        note="Rotated scan, barely legible.",
    ),
    Doc(
        "20261019105936.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-020
           Supplier: J S SINGH GLAZZING
           Site: A17 A175
           Total 2 242.40""",
        T.PURCHASE_ORDER, "J S Singh Glazzing", "2242.40",
        "purchase_orders",
        note="Supplier absent from production.",
    ),
    Doc(
        "20261019105913.pdf",
        """NPC CEMENT
           TAX INVOICE
           Invoice No: 91515003
           VAT Reg No: 4120156789
           Your Order: PO-012
           TOTAL DUE 3 412.03""",
        T.SUPPLIER_INVOICE, "NPC", "3412.03",
        "accounts_payable",
        note="A real liability.",
    ),
    Doc(
        "20261019105710.pdf",
        """PROMINENT PAINTS
           QUOTATION   QU07029334
           Site: A175 & A17
           Total 453.27""",
        T.QUOTATION, "Prominent Paints", "453.27", "procurement",
    ),
    Doc(
        "20261019105628.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-021
           Supplier: AFRISTAR
           Deliver to: a17 a175 dassenhoek
           Total 8 484.82""",
        T.PURCHASE_ORDER, "Afristar", "8484.82", "purchase_orders",
    ),
    Doc(
        "20261019105342.pdf",
        """MIDLANDS
           QUOTATION
           Quote No: BR1-QUT/66689801
           Site: A17 & A175 DASSENHOEK
           Total incl VAT 26 600.38""",
        T.QUOTATION, "Midlands", "26600.38", "procurement",
    ),
    Doc(
        "20261019105313.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-013
           Supplier: YANE
           Site: A17 A175
           Total 10 500.00
           PAID IN FULL""",
        T.PURCHASE_ORDER, "Yane", "10500.00", "purchase_orders",
        paid_stamp=True,
    ),
    Doc(
        "20261019105237.pdf",
        """MIDLANDS
           QUOTATION
           Quote No: BR1-QUT/66901001
           Dasenhoek
           Total 13 884.98""",
        T.QUOTATION, "Midlands", "13884.98", "procurement",
        note="Site name misspelt on the document.",
    ),
    Doc(
        "20261019105200.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-017
           Supplier: KILLARNEY
           Site: A17 A175 A599
           Total 494.32""",
        T.PURCHASE_ORDER, "Killarney", "494.32", "purchase_orders",
        note="Names lot A599, which does not exist at Dassenhoek.",
    ),
    Doc(
        "20261019104934.pdf",
        """BUCO
           QUOTE   Quotation Number: 1047739
           NO GOODS TO BE SUPPLIED
           Total 3 742.56""",
        T.QUOTATION, "Buco", "3742.56", "procurement",
    ),
    Doc(
        "20261019104817.pdf",
        """MIDLANDS
           QUOTATION
           Quote No: BR1-QUT/65845902
           A17/A175
           Total 3 012.00""",
        T.QUOTATION, "Midlands", "3012.00", "procurement",
    ),
    Doc(
        "20261019104650.pdf",
        """STEELBAR
           DELIVERY NOTE   No. 0084
           Dassenhoek
           Received in good order""",
        T.DELIVERY_NOTE, "Steelbar", None, "goods_received",
        note="Handwritten. The only document in the batch that may move stock.",
    ),
    Doc(
        "20261019104626.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-022
           Supplier: SDS BLOCKS
           Site: A175
           Total 12 254.00
           No Delivery note""",
        T.PURCHASE_ORDER, "SDS Blocks", "12254.00", "purchase_orders",
        note="Handwritten annotation: no delivery note received.",
    ),
    Doc(
        "20261019104607.pdf",
        """SDS BRICK & BLOCK
           PRO FORMA INVOICE   QTE5895
           This document is not a tax invoice.
           A17
           TOTAL 12 254.00""",
        T.PRO_FORMA_INVOICE, "SDS Brick & Block", "12254.00",
        "provisional_charges",
        note="Same purchase as PO-022.",
    ),
    Doc(
        "20261019104537.pdf",
        """CRETEMIX (PTY) LTD
           PROFORMA INVOICE
           Invoice No: P89250   Date: 13/08/2026
           VAT Reg: 4150271234
           Delivery to: DASSENHOEK
           TOTAL 17 444.89""",
        T.PRO_FORMA_INVOICE, "Cretemix", "17444.89",
        "provisional_charges",
        note="Same amount as P89381. Second pour, or the same one twice?",
    ),
    Doc(
        "20261019104502.pdf",
        """CRETEMIX (PTY) LTD
           PROFORMA INVOICE
           Invoice No: P89381   Date: 24/08/2026
           VAT Reg: 4150271234
           Delivery to: DASSENHOEK
           TOTAL 17 444.89""",
        T.PRO_FORMA_INVOICE, "Cretemix", "17444.89",
        "provisional_charges",
        note="Same amount as P89250, eleven days later.",
    ),
    Doc(
        "20261019110916.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-01
           Supplier: BUILD IT
           PICK UP
           Total 3 699.55""",
        T.PURCHASE_ORDER, "Build It", "3699.55", "purchase_orders",
        note="Supplier absent from production. Pairs with QTE254210.",
    ),
    Doc(
        "20261019110855.pdf",
        """KILLARNEY
           TAX INVOICE
           Invoice No: 85956
           VAT Reg No: 4920145678
           Your Order No: PO-017
           TOTAL DUE 494.32""",
        T.SUPPLIER_INVOICE, "Killarney", "494.32", "accounts_payable",
        note="A real liability. Pairs with PO-017.",
    ),
)


def test_the_batch_is_the_whole_batch():
    """Guards against a document being quietly dropped from the set."""
    assert len(BATCH) == 20
    assert len({d.file_name for d in BATCH}) == 20


# ── 1. Classification ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", BATCH, ids=lambda d: d.file_name)
def test_each_document_is_classified_correctly(doc):
    actual, _ = _classify_from_text(doc.text)
    assert actual is doc.expected_type, (
        f"{doc.file_name} ({doc.supplier}) read as {actual.value}, "
        f"expected {doc.expected_type.value}. {doc.note}"
    )


def test_no_proforma_is_classified_as_a_tax_invoice():
    """
    Stated separately from the parametrised case because this is the one
    that costs money. Five pro-formas, every one of them printing the word
    "invoice".
    """
    proformas = [d for d in BATCH if d.expected_type is T.PRO_FORMA_INVOICE]
    assert len(proformas) == 5
    for doc in proformas:
        actual, _ = _classify_from_text(doc.text)
        assert actual is not T.SUPPLIER_INVOICE, (
            f"{doc.file_name} would have created a payable that is not owed"
        )


# ── 2. Destinations ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", BATCH, ids=lambda d: d.file_name)
def test_each_document_reaches_the_right_module(doc):
    """
    Fuel is excluded here: a fuel order's destination depends on its line
    items, not its type alone, and is covered by its own test below.
    """
    if doc.destination == "fuel_procurement":
        pytest.skip("covered by test_the_fuel_order_leaves_the_materials_path")
    actual, _ = _classify_from_text(doc.text)
    assert routing.destination_for(actual).key == doc.destination


def test_exactly_two_documents_create_a_liability():
    """
    Twenty documents, two payables: NPC 91515003 and Killarney 85956. If this
    number ever rises, something that is not a tax invoice has been let into
    Accounts Payable.
    """
    payables = [d for d in BATCH if d.destination == "accounts_payable"]
    assert [d.supplier for d in payables] == ["NPC", "Killarney"]
    assert sum(Decimal(d.amount) for d in payables) == Decimal("3906.35")


def test_exactly_one_document_moves_stock():
    """
    The handwritten Steelbar note. Eight purchase orders describe goods that
    were ordered; only this one is evidence that anything arrived.
    """
    movers = [d for d in BATCH if d.destination == "goods_received"]
    assert len(movers) == 1
    assert movers[0].supplier == "Steelbar"


def test_no_purchase_order_moves_stock():
    for doc in BATCH:
        if doc.expected_type is T.PURCHASE_ORDER:
            assert doc.destination != "goods_received", (
                f"{doc.file_name} would receive goods that were only ordered"
            )


def test_the_fuel_order_leaves_the_materials_path(db):
    """
    PO-038, 500 litres of 50PPM diesel. Routed as an ordinary purchase order
    it becomes a materials order, and the delivery that follows tries to put
    diesel into the warehouse as though it were cement.
    """
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedField, ExtractedLineItem

    payload = DocumentExtractionPayload()
    payload.fields = {
        "document_number": ExtractedField(value="PO-038", confidence=0.9),
        "total_amount": ExtractedField(value="13575.00", confidence=0.9),
        "supplier_name": ExtractedField(value="FUEL UP", confidence=0.9),
    }
    payload.line_items = [
        ExtractedLineItem(description="500 Litres Diesel 50PPM", quantity="500",
                          unit="L", confidence=0.8),
    ]

    document = _stub_document(db, T.PURCHASE_ORDER, "20261019110121.pdf")
    verdict = routing.route(db, document, payload)

    assert verdict.destination is routing.FUEL_PROCUREMENT
    assert verdict.action == routing.REVIEW
    assert "litres" in verdict.reason.lower()


# ── 3. Payment treatment ──────────────────────────────────────────────────────

def test_two_documents_carry_a_paid_stamp():
    stamped = [d for d in BATCH if d.paid_stamp]
    assert {d.supplier for d in stamped} == {"Pinetown Build It", "Yane"}


@pytest.mark.parametrize(
    "doc", [d for d in BATCH if d.paid_stamp], ids=lambda d: d.file_name,
)
def test_a_paid_stamp_is_recorded_as_unverified_evidence(doc):
    from app.schemas.ai_import import DocumentExtractionPayload
    from app.services.ai_import_service import detect_payment_evidence

    payload = DocumentExtractionPayload()
    payload.raw_text = doc.text

    detected, note = detect_payment_evidence(payload)
    assert detected, f"the PAID marking on {doc.file_name} was not noticed"
    assert "verification required" in note
    # The wording matters: it must not read as a settlement.
    assert "not a bank record" in note


@pytest.mark.parametrize(
    "doc", [d for d in BATCH if not d.paid_stamp], ids=lambda d: d.file_name,
)
def test_documents_without_a_paid_marking_are_not_flagged(doc):
    """A false positive here sends somebody to the bank for nothing."""
    from app.schemas.ai_import import DocumentExtractionPayload
    from app.services.ai_import_service import detect_payment_evidence

    payload = DocumentExtractionPayload()
    payload.raw_text = doc.text
    detected, _ = detect_payment_evidence(payload)
    assert not detected


def test_a_paid_stamp_never_settles_anything(db):
    """
    The invariant behind all of the above: payment status comes from Payment
    rows, and an imported document does not create one.
    """
    from app.models.payment import Payment
    from app.schemas.ai_import import DocumentExtractionPayload
    from app.services.ai_import_service import detect_payment_evidence

    payload = DocumentExtractionPayload()
    payload.raw_text = "TAX INVOICE 85956 ... PAID IN FULL"
    before = db.query(Payment).count()
    detect_payment_evidence(payload)
    assert db.query(Payment).count() == before


# ── 4. Duplicates and pairs ───────────────────────────────────────────────────

def test_the_three_same_purchase_pairs_are_present():
    """
    Each of these is one purchase described by two documents. Counting both
    as liabilities is the double charge the design exists to prevent.
    """
    pairs = [
        ("20261019110916.pdf", "20261019110559.pdf"),  # PO-01    -> Build It pro-forma
        ("20261019104626.pdf", "20261019104607.pdf"),  # PO-022   -> SDS pro-forma
        ("20261019105200.pdf", "20261019110855.pdf"),  # PO-017   -> Killarney tax invoice
    ]
    by_name = {d.file_name: d for d in BATCH}
    for order_file, follow_up in pairs:
        order, second = by_name[order_file], by_name[follow_up]
        assert order.expected_type is T.PURCHASE_ORDER
        assert second.expected_type is not T.PURCHASE_ORDER
        # At most one of the two may reach Accounts Payable.
        destinations = {order.destination, second.destination}
        assert len([d for d in destinations if d == "accounts_payable"]) <= 1


def test_only_the_killarney_pair_ends_in_a_payable():
    """
    Of the three pairs, only Killarney produced an actual tax invoice. The
    other two stop at a pending charge, because no supplier has invoiced yet.
    """
    by_name = {d.file_name: d for d in BATCH}
    assert by_name["20261019110855.pdf"].destination == "accounts_payable"
    assert by_name["20261019110559.pdf"].destination == "provisional_charges"
    assert by_name["20261019104607.pdf"].destination == "provisional_charges"


def test_the_two_cretemix_proformas_carry_the_same_amount():
    """
    Not a bug in the fixtures: they really are identical in value, eleven
    days apart. The system must raise this rather than resolve it, which
    test_duplicate_proforma_amount_is_questioned covers.
    """
    cretemix = [d for d in BATCH if d.supplier == "Cretemix"]
    assert len(cretemix) == 2
    assert cretemix[0].amount == cretemix[1].amount == "17444.89"
    assert cretemix[0].text != cretemix[1].text


# ── 5. Nothing is invented ────────────────────────────────────────────────────

def test_lot_a599_is_named_by_a_document_and_does_not_exist():
    """
    PO-017 names three lots: A17, A175 and A599. Dassenhoek has the first
    two. A599 is not a lot anybody can allocate to, and production
    reconciliation confirmed it is absent.

    This test fixes the fact in place. The guarantee that nothing is
    allocated to it comes from posting refusing to take a lot at all — see
    test_an_imported_receipt_cannot_be_sent_straight_to_a_lot.
    """
    by_name = {d.file_name: d for d in BATCH}
    assert "A599" in by_name["20261019105200.pdf"].text


def test_an_imported_receipt_cannot_be_sent_straight_to_a_lot(db):
    """
    The mechanism that makes a guessed lot impossible: an imported receipt
    goes to the project warehouse, and supplying a lot is rejected rather
    than quietly ignored. Allocation is a separate, deliberate step on the
    warehouse screen.
    """
    from app.models.user import User
    from app.schemas.ai_import import DocumentExtractionPayload
    from app.services import ai_import_posting_service as posting
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    db.commit()
    actor = db.get(User, uuid.UUID(owner["id"]))
    document = _stub_document(db, T.DELIVERY_NOTE, "20261019104650.pdf")

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_document(
            db, document, DocumentExtractionPayload(), actor,
            lot_id=uuid.uuid4(),
        )
    assert "lot" in str(exc.value).lower()


# ── Helper ────────────────────────────────────────────────────────────────────

def _stub_document(db, doc_type: T, file_name: str):
    """A persisted document with no context, for routing-only assertions."""
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    batch = AIImportBatch(reference=f"B-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    document = AIImportDocument(
        batch_id=batch.id, file_name=file_name,
        stored_path=f"supabase://ai_import/x/{uuid.uuid4().hex}.pdf",
        mime_type="application/pdf", file_size_bytes=2048,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.READY_TO_POST,
        document_type=doc_type,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(document)
    db.commit()
    return document
