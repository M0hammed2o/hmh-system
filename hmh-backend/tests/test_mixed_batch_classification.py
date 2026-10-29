"""
Classifying the paperwork that actually arrives.

The text in these tests is transcribed from a real batch of twenty documents
for Minerat Construction & Civils, Dassenhoek. It is deliberately verbatim —
including the misspellings, the handwriting and the stamps — because the
failures being guarded against all come from what the paper really says
rather than from what a clean example would say.

The central one: a pro-forma invoice prints the word "INVOICE" across the
top, carries an invoice number and a VAT registration number, and asks to be
paid. Every keyword that identifies a tax invoice is on it. The deterministic
classifier was written before the pro-forma type existed and scores exactly
those keywords, so left alone it files a pro-forma in Accounts Payable —
creating a liability that does not exist and paying the supplier twice when
the real tax invoice follows.
"""

import pytest

from app.models.enums import AIImportDocumentType as T
from app.services.ai_import_extraction_service import _classify_from_text


def classify(text: str) -> T:
    return _classify_from_text(text)[0]


# ── Pro-formas: the dangerous case ───────────────────────────────────────────

# Pinetown Build It, QTE254210, R3 699.50. Pairs with purchase order PO-01.
BUILD_IT_PROFORMA = """
    BUILD IT PINETOWN
    VAT Reg No: 4290116892
    PRO FORMA INVOICE
    Document No: QTE254210
    Date: 2026-08-14
    Customer: MINERAT CONSTRUCTION & CIVILS
    Total Due R 3 699.50
    Banking details for payment
"""

# Cretemix P89250. The scan is clean; the words are the whole problem.
CRETEMIX_PROFORMA = """
    CRETEMIX (PTY) LTD
    PROFORMA INVOICE
    Invoice No: P89250
    VAT Reg: 4150271234
    Delivery to: DASSENHOEK
    TOTAL 17 444.89
"""


@pytest.mark.parametrize("text", [BUILD_IT_PROFORMA, CRETEMIX_PROFORMA])
def test_a_proforma_is_not_filed_as_a_tax_invoice(text):
    """
    The regression that the merge of the two branches would otherwise
    introduce. "Pro forma" and "proforma" are both in the batch.
    """
    assert classify(text) is not T.SUPPLIER_INVOICE


@pytest.mark.parametrize("text", [BUILD_IT_PROFORMA, CRETEMIX_PROFORMA])
def test_a_proforma_is_recognised_as_a_proforma(text):
    assert classify(text) is T.PRO_FORMA_INVOICE


def test_proforma_beats_tax_invoice_even_when_both_phrases_appear():
    """
    Some suppliers print "This is not a tax invoice" on a pro-forma. The
    phrase "tax invoice" is then present on a document that is certainly not
    one, and the more specific signal has to win.
    """
    text = """
        PRO FORMA INVOICE
        Invoice No: QTE5895
        This document is not a tax invoice. A tax invoice will be issued on payment.
        VAT Reg No: 4030189234
        TOTAL 12 254.00
    """
    assert classify(text) is T.PRO_FORMA_INVOICE


# ── Quotations ───────────────────────────────────────────────────────────────

# Midlands, BR1-QUT/66689801, R26 600.38.
MIDLANDS_QUOTE = """
    MIDLANDS HARDWARE
    QUOTATION
    Quote No: BR1-QUT/66689801
    Valid for 30 days
    Site: A17 & A175 DASSENHOEK
    Total incl VAT 26 600.38
"""


def test_a_quotation_is_recognised():
    assert classify(MIDLANDS_QUOTE) is T.QUOTATION


def test_a_quotation_is_not_an_order():
    """
    A quotation commits nobody. Treating one as a purchase order would show
    committed spend against the project that was never authorised.
    """
    assert classify(MIDLANDS_QUOTE) is not T.PURCHASE_ORDER


def test_the_buco_quote_that_says_no_goods_to_be_supplied():
    """
    Buco, R3 742.56, with "NO GOODS TO BE SUPPLIED" written across it. It is
    still a quotation — the annotation is a reason not to act on it, which is
    a human decision, not a classification.
    """
    text = """
        BUCO
        QUOTE
        Quotation Number: 1047739
        NO GOODS TO BE SUPPLIED
        Total 3 742.56
    """
    assert classify(text) is T.QUOTATION


# ── The types that already worked must keep working ──────────────────────────

def test_a_real_tax_invoice_is_still_a_tax_invoice():
    """Killarney 85956, R494.32 — a genuine liability. #11's pair."""
    text = """
        KILLARNEY CIVILS
        TAX INVOICE
        Invoice No: 85956
        VAT Reg No: 4920145678
        Your Order No: PO-017
        TOTAL DUE 494.32
    """
    assert classify(text) is T.SUPPLIER_INVOICE


def test_a_purchase_order_is_still_a_purchase_order():
    """Minerat PO-021 to Afristar, R8 484.82."""
    text = """
        MINERAT CONSTRUCTION & CIVILS
        PURCHASE ORDER
        Order No: PO-021
        Supplier: AFRISTAR
        Deliver to: a17 a175 dassenhoek
        Total 8 484.82
    """
    assert classify(text) is T.PURCHASE_ORDER


def test_the_handwritten_steelbar_delivery_note():
    """
    Document 14, the only one in the batch that may move stock. Handwritten
    on a printed book page, so the text that survives OCR is sparse.
    """
    text = """
        STEELBAR
        DELIVERY NOTE
        No. 0084
        Dassenhoek
        Received in good order
    """
    assert classify(text) is T.DELIVERY_NOTE


# ── Nothing is guessed ───────────────────────────────────────────────────────

def test_an_unreadable_scan_stays_unknown():
    """
    Document 3 arrived rotated and barely legible. A confident wrong answer
    is worse than no answer, because classification picks the posting path.
    """
    assert classify("   ") is T.UNKNOWN
    assert classify("smudge 4471 ...") is T.UNKNOWN


def test_confidence_is_never_full_from_keywords_alone():
    """A keyword match is evidence, not a reading of the document."""
    _, confidence = _classify_from_text(MIDLANDS_QUOTE)
    assert 0.0 < confidence <= 0.75


# ── Headings versus references ───────────────────────────────────────────────
#
# Both of these were real failures. Documents name each other constantly: a
# delivery note cites the order it fulfils, an order is annotated about the
# delivery note that never came. Whichever way the marker list is ordered,
# one of the two breaks — so position decides, because a heading is at the
# top and a reference is in the body.

def test_an_order_annotated_about_a_missing_delivery_note_is_still_an_order():
    """
    PO-022 to SDS Blocks, R12 254.00, with "No Delivery note" written on it
    by hand. Read as a delivery note it receives 12 254 rands of block into
    stock — goods the annotation explicitly says never arrived.
    """
    text = """
        MINERAT CONSTRUCTION & CIVILS
        PURCHASE ORDER   Order No: PO-022
        Supplier: SDS BLOCKS
        Total 12 254.00
        No Delivery note
    """
    assert classify(text) is T.PURCHASE_ORDER


def test_a_delivery_note_citing_its_order_is_still_a_delivery_note():
    """
    The other direction, and the reason the marker list cannot simply be
    reordered: almost every real delivery note quotes the purchase order it
    is delivering against.
    """
    text = """
        AFRISTAR
        DELIVERY NOTE   No. 4471
        Your Purchase Order: PO-021
        Received in good order
    """
    assert classify(text) is T.DELIVERY_NOTE


def test_an_outstanding_tax_invoice_note_does_not_make_a_quote_an_invoice():
    text = """
        MIDLANDS
        QUOTATION   Quote No: BR1-QUT/65845902
        Tax invoice outstanding until payment is received.
        Total 3 012.00
    """
    assert classify(text) is T.QUOTATION
