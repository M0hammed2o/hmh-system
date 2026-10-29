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
        """LAKESIDE BUILDERS MERCHANT
           VAT Reg No: 4990000011
           PRO FORMA INVOICE
           Document No: QTE880114  Date: 14/08/2026
           Customer: MINERAT CONSTRUCTION & CIVILS
           Total Due R 4 120.50
           PAID""",
        T.PRO_FORMA_INVOICE, "Lakeside Builders Merchant", "4120.50",
        "provisional_charges", paid_stamp=True,
        note="Pairs with PO-101. Supplier absent from production.",
    ),
    Doc(
        "20261019110121.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-108
           Supplier: TRACKSIDE FUELS
           500 Litres Diesel 50PPM
           Deliver to: dassenhoek
           Total 15 880.00""",
        T.PURCHASE_ORDER, "Trackside Fuels", "15880.00",
        "fuel_procurement",
        note="Fuel, not materials. Must never become warehouse stock.",
    ),
    Doc(
        "20261019110033.pdf",
        """COASTAL CEMENT   HILLCREST
           PRO FORMA
           SQ441020
           3 990.77""",
        T.PRO_FORMA_INVOICE, "Coastal Cement", "3990.77",
        "provisional_charges",
        note="Rotated scan, barely legible.",
    ),
    Doc(
        "20261019105936.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-120
           Supplier: CLEARVIEW GLAZING
           Site: A17 A175
           Total 2 615.40""",
        T.PURCHASE_ORDER, "Clearview Glazing", "2615.40",
        "purchase_orders",
        note="Supplier absent from production.",
    ),
    Doc(
        "20261019105913.pdf",
        """NPC CEMENT
           TAX INVOICE
           Invoice No: 90220114
           VAT Reg No: 4990000044
           Your Order: PO-112
           TOTAL DUE 3 995.03""",
        T.SUPPLIER_INVOICE, "NPC", "3995.03",
        "accounts_payable",
        note="A real liability.",
    ),
    Doc(
        "20261019105710.pdf",
        """PINNACLE PAINTS
           QUOTATION   QU08810220
           Site: A175 & A17
           Total 528.27""",
        T.QUOTATION, "Pinnacle Paints", "528.27", "procurement",
    ),
    Doc(
        "20261019105628.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-121
           Supplier: IRONWORKS TRADING
           Deliver to: a17 a175 dassenhoek
           Total 9 910.82""",
        T.PURCHASE_ORDER, "Ironworks Trading", "9910.82", "purchase_orders",
    ),
    Doc(
        "20261019105342.pdf",
        """RIVERSIDE
           QUOTATION
           Quote No: BR1-QUT/70110801
           Site: A17 & A175 DASSENHOEK
           Total incl VAT 31 050.38""",
        T.QUOTATION, "Riverside", "31050.38", "procurement",
    ),
    Doc(
        "20261019105313.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-113
           Supplier: NORTHGATE PLUMBING
           Site: A17 A175
           Total 12 260.00
           PAID IN FULL""",
        T.PURCHASE_ORDER, "Northgate Plumbing", "12260.00", "purchase_orders",
        paid_stamp=True,
    ),
    Doc(
        "20261019105237.pdf",
        """RIVERSIDE
           QUOTATION
           Quote No: BR1-QUT/70220901
           Dasenhoek
           Total 16 210.98""",
        T.QUOTATION, "Riverside", "16210.98", "procurement",
        note="Site name misspelt on the document.",
    ),
    Doc(
        "20261019105200.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-117
           Supplier: QUARRYSIDE
           Site: A17 A175 A599
           Total 577.32""",
        T.PURCHASE_ORDER, "Quarryside", "577.32", "purchase_orders",
        note="Names lot A599, which does not exist at Dassenhoek.",
    ),
    Doc(
        "20261019104934.pdf",
        """TIMBERLINE SUPPLY
           QUOTE   Quotation Number: 1098220
           NO GOODS TO BE SUPPLIED
           Total 4 370.56""",
        T.QUOTATION, "Timberline Supply", "4370.56", "procurement",
    ),
    Doc(
        "20261019104817.pdf",
        """RIVERSIDE
           QUOTATION
           Quote No: BR1-QUT/70330902
           A17/A175
           Total 3 516.00""",
        T.QUOTATION, "Riverside", "3516.00", "procurement",
    ),
    Doc(
        "20261019104650.pdf",
        """REDLINE STEEL
           DELIVERY NOTE   No. 0151
           Dassenhoek
           Received in good order""",
        T.DELIVERY_NOTE, "Redline Steel", None, "goods_received",
        note="Handwritten. The only document in the batch that may move stock.",
    ),
    Doc(
        "20261019104626.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-122
           Supplier: MASWELL BLOCKS
           Site: A175
           Total 14 300.00
           No Delivery note""",
        T.PURCHASE_ORDER, "Maswell Blocks", "14300.00", "purchase_orders",
        note="Handwritten annotation: no delivery note received.",
    ),
    Doc(
        "20261019104607.pdf",
        """MASWELL BRICK & BLOCK
           PRO FORMA INVOICE   QTE7410
           This document is not a tax invoice.
           A17
           TOTAL 14 300.00""",
        T.PRO_FORMA_INVOICE, "Maswell Brick & Block", "14300.00",
        "provisional_charges",
        note="Same purchase as PO-122.",
    ),
    Doc(
        "20261019104537.pdf",
        """VANTAGE READYMIX (PTY) LTD
           PROFORMA INVOICE
           Invoice No: P77120   Date: 13/08/2026
           VAT Reg: 4990000022
           Delivery to: DASSENHOEK
           TOTAL 20 360.89""",
        T.PRO_FORMA_INVOICE, "Vantage Readymix", "20360.89",
        "provisional_charges",
        note="Same amount as P77255. Second pour, or the same one twice?",
    ),
    Doc(
        "20261019104502.pdf",
        """VANTAGE READYMIX (PTY) LTD
           PROFORMA INVOICE
           Invoice No: P77255   Date: 24/08/2026
           VAT Reg: 4990000022
           Delivery to: DASSENHOEK
           TOTAL 20 360.89""",
        T.PRO_FORMA_INVOICE, "Vantage Readymix", "20360.89",
        "provisional_charges",
        note="Same amount as P77120, eleven days later.",
    ),
    Doc(
        "20261019110916.pdf",
        """MINERAT CONSTRUCTION & CIVILS
           PURCHASE ORDER   Order No: PO-101
           Supplier: LAKESIDE MERCHANT
           PICK UP
           Total 4 120.55""",
        T.PURCHASE_ORDER, "Lakeside Merchant", "4120.55", "purchase_orders",
        note="Supplier absent from production. Pairs with QTE880114.",
    ),
    Doc(
        "20261019110855.pdf",
        """QUARRYSIDE
           TAX INVOICE
           Invoice No: 85956
           VAT Reg No: 4990000033
           Your Order No: PO-117
           TOTAL DUE 577.32""",
        T.SUPPLIER_INVOICE, "Quarryside", "577.32", "accounts_payable",
        note="A real liability. Pairs with PO-117.",
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
    Twenty documents, two payables: NPC 90220114 and Quarryside 85956. If this
    number ever rises, something that is not a tax invoice has been let into
    Accounts Payable.
    """
    payables = [d for d in BATCH if d.destination == "accounts_payable"]
    assert [d.supplier for d in payables] == ["NPC", "Quarryside"]
    assert sum(Decimal(d.amount) for d in payables) == Decimal("4572.35")


def test_exactly_one_document_moves_stock():
    """
    The handwritten Redline Steel note. Eight purchase orders describe goods that
    were ordered; only this one is evidence that anything arrived.
    """
    movers = [d for d in BATCH if d.destination == "goods_received"]
    assert len(movers) == 1
    assert movers[0].supplier == "Redline Steel"


def test_no_purchase_order_moves_stock():
    for doc in BATCH:
        if doc.expected_type is T.PURCHASE_ORDER:
            assert doc.destination != "goods_received", (
                f"{doc.file_name} would receive goods that were only ordered"
            )


def test_the_fuel_order_leaves_the_materials_path(db):
    """
    PO-108, 500 litres of 50PPM diesel. Routed as an ordinary purchase order
    it becomes a materials order, and the delivery that follows tries to put
    diesel into the warehouse as though it were cement.
    """
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedField, ExtractedLineItem

    payload = DocumentExtractionPayload()
    payload.fields = {
        "document_number": ExtractedField(value="PO-108", confidence=0.9),
        "total_amount": ExtractedField(value="15880.00", confidence=0.9),
        "supplier_name": ExtractedField(value="TRACKSIDE FUELS", confidence=0.9),
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
    assert {d.supplier for d in stamped} == {"Lakeside Builders Merchant", "Northgate Plumbing"}


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
        ("20261019110916.pdf", "20261019110559.pdf"),  # PO-101    -> Lakeside Merchant pro-forma
        ("20261019104626.pdf", "20261019104607.pdf"),  # PO-122   -> Maswell pro-forma
        ("20261019105200.pdf", "20261019110855.pdf"),  # PO-117   -> Quarryside tax invoice
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
    Of the three pairs, only Quarryside produced an actual tax invoice. The
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
    cretemix = [d for d in BATCH if d.supplier == "Vantage Readymix"]
    assert len(cretemix) == 2
    assert cretemix[0].amount == cretemix[1].amount == "20360.89"
    assert cretemix[0].text != cretemix[1].text


# ── 5. Nothing is invented ────────────────────────────────────────────────────

def test_lot_a599_is_named_by_a_document_and_does_not_exist():
    """
    PO-117 names three lots: A17, A175 and A599. Dassenhoek has the first
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


# ── 6. Stock waits for a person ───────────────────────────────────────────────

def _receipt_document(db, *, reviewed: bool, confidence: float = 0.4):
    """The Redline Steel note: handwritten, with a supplier and project set."""
    from datetime import datetime, timezone

    from app.models.ai_import import AIImportDocument
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedLineItem
    from tests.conftest import make_project, make_supplier, make_user

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db, name="Redline Steel")
    db.commit()

    document = _stub_document(db, T.DELIVERY_NOTE, "20261019104650.pdf")
    document.project_id = uuid.UUID(project["id"])
    document.supplier_id = uuid.UUID(supplier["id"])
    if reviewed:
        document.reviewed_by = uuid.UUID(owner["id"])
        document.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    payload = DocumentExtractionPayload()
    payload.line_items = [
        ExtractedLineItem(description="Rebar Y12", quantity="40", unit="ea",
                          confidence=confidence),
    ]
    return document, payload


def test_the_handwritten_delivery_note_waits_for_a_person(db):
    """
    Item under test: a receipt may not import itself. Stock is the one thing
    here that is physically wrong if it is wrong — materials on the system
    that are not on site, surfacing weeks later as an unexplained shortage.
    """
    document, payload = _receipt_document(db, reviewed=False)
    verdict = routing.route(db, document, payload)

    assert verdict.action == routing.REVIEW
    assert "confirmed by a person" in verdict.reason


def test_a_badly_read_quantity_is_named(db):
    """
    "Needs review" without saying why invites a rubber stamp. The line whose
    quantity could not be read confidently is named.
    """
    document, payload = _receipt_document(db, reviewed=False, confidence=0.4)
    verdict = routing.route(db, document, payload)

    assert any("not read confidently" in n for n in verdict.review_notes)
    assert any("Rebar Y12" in n for n in verdict.review_notes)


def test_a_confidently_read_receipt_still_waits(db):
    """
    A clean scan is not a confirmation. Only a person is.
    """
    document, payload = _receipt_document(db, reviewed=False, confidence=0.98)
    verdict = routing.route(db, document, payload)

    assert verdict.action == routing.REVIEW
    # ...but it does not invent a quantity problem that is not there.
    assert not any("not read confidently" in n for n in verdict.review_notes)


def test_once_a_person_has_reviewed_it_the_receipt_may_import(db):
    """The hold is a gate, not a wall: confirming it opens the path."""
    document, payload = _receipt_document(db, reviewed=True, confidence=0.98)
    verdict = routing.route(db, document, payload)

    assert verdict.action in (routing.CREATE, routing.LINK_EXISTING)
    assert verdict.destination is routing.GOODS_RECEIVED


def test_no_other_type_is_held_merely_for_being_unreviewed(db):
    """
    The hold is specific to stock. Holding everything would make review
    meaningless and nothing would ever import.
    """
    from app.schemas.ai_import import DocumentExtractionPayload, ExtractedField

    from tests.conftest import make_project, make_supplier, make_user

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db, name="Riverside")
    db.commit()

    document = _stub_document(db, T.QUOTATION, "quote.pdf")
    document.project_id = uuid.UUID(project["id"])
    document.supplier_id = uuid.UUID(supplier["id"])
    db.commit()

    payload = DocumentExtractionPayload()
    payload.fields = {
        "document_number": ExtractedField(value="BR1-QUT/1", confidence=0.9),
        "total_amount": ExtractedField(value="31050.38", confidence=0.9),
    }
    assert routing.route(db, document, payload).action == routing.CREATE
