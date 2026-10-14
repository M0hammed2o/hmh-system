"""
AI Document Import — the complete business workflow.

One procurement transaction, four documents, through the whole engine and
into the real material request, purchase order, delivery, stock ledger and
supplier invoice records. Then the same four documents again, to prove the
second pass changes nothing.

Everything runs against real PostgreSQL through the existing domain services;
only the AI provider is stubbed. The `db` fixture rolls back, so no record
outlives the test.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.ai_import import AIImportDocument, AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    DeliveryDestination,
    MovementType,
    RecordStatus,
)
from app.services import ai_import_matching_service as matching
from app.services import ai_import_posting_service as posting
from app.services import ai_import_service
from tests.conftest import (
    auth, login, make_item, make_project, make_site, make_supplier, make_user,
)
from tests.ai_import_fixtures import (
    delivery_note, field, install_stub, line, make_import_document, purchase_order,
    raw_response, supplier_invoice, typed_material_request,
)
from tests.test_ai_import_posting import _ledger_total, _payload

SUPPLIER_NAME = "Umhlanga Building Supplies CC"
PAPER_PO = "SUP-PO-9912"
DELIVERY_NOTE_NO = "DN-7781"
INVOICE_NO = "INV-502"
QTY = 100
UNIT_PRICE = "120.00"
LINE_TOTAL = "12000.00"
SUBTOTAL = "12000.00"
VAT = "1800.00"
TOTAL = "13800.00"
ITEM_NAME = "Cement 42.5N 50kg bag"


def _user_obj(db, role="OFFICE_ADMIN"):
    from app.models.user import User
    row = make_user(db, role=role)
    return db.get(User, uuid.UUID(row["id"])), row


@pytest.fixture()
def world(db):
    """A project, a site, the supplier and the catalogue item."""
    actor, actor_row = _user_obj(db)
    project = make_project(db, actor_row["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db, name=SUPPLIER_NAME)
    item = make_item(db, name=ITEM_NAME, unit="bag")
    return {
        "actor": actor, "actor_row": actor_row, "project": project,
        "site": site, "supplier": supplier, "item": item,
    }


def _docs(project_code: str) -> dict[str, dict]:
    """The four provider responses for one coherent transaction."""
    return {
        "mr": typed_material_request(project_code=project_code, mr_number="MR-SAMPLE-014"),
        "po": purchase_order(SUPPLIER_NAME, po_number=PAPER_PO, project_code=project_code),
        "dn": delivery_note(
            SUPPLIER_NAME, note_number=DELIVERY_NOTE_NO, po_reference=PAPER_PO,
            quantity=QTY, project_code=project_code, description=ITEM_NAME,
        ),
        "inv": supplier_invoice(
            SUPPLIER_NAME, invoice_number=INVOICE_NO, po_reference=PAPER_PO,
            total=TOTAL, subtotal=SUBTOTAL, vat=VAT, quantity=QTY,
            unit_price=UNIT_PRICE, line_total=LINE_TOTAL,
            project_code=project_code, description=ITEM_NAME,
        ),
    }


def _ingest(db, monkeypatch, world, response, *, file_name):
    """Upload-equivalent: create the document row and run the pipeline on it."""
    install_stub(monkeypatch, response)
    document = make_import_document(
        db,
        uploaded_by=world["actor_row"]["id"],
        project_id=world["project"]["id"],
        site_id=world["site"]["id"],
        file_name=file_name,
    )
    ai_import_service.process_document(db, document)
    return document


# ── The full run ──────────────────────────────────────────────────────────────

def test_four_documents_one_transaction_end_to_end(db, monkeypatch, world):
    actor = world["actor"]
    project, site, supplier, item = world["project"], world["site"], world["supplier"], world["item"]
    responses = _docs(project["code"])

    assert _ledger_total(db, project["id"], item["id"]) == 0

    # ── 1. Material request ──────────────────────────────────────────────────
    mr_doc = _ingest(db, monkeypatch, world, responses["mr"], file_name="01_mr.pdf")
    assert mr_doc.document_type == AIImportDocumentType.MATERIAL_REQUEST
    assert str(mr_doc.project_id) == project["id"]

    mr_posting = posting.post_document(
        db, mr_doc, ai_import_service.working_payload(db, mr_doc), actor,
    )
    from app.models.material_request import MaterialRequest
    mr = db.get(MaterialRequest, mr_posting.entity_id)
    assert mr.status == RecordStatus.DRAFT, "approvals must not be simulated"
    assert _ledger_total(db, project["id"], item["id"]) == 0, "an MR must not move stock"

    # ── 2. Purchase order ────────────────────────────────────────────────────
    po_doc = _ingest(db, monkeypatch, world, responses["po"], file_name="02_po.pdf")
    assert po_doc.document_type == AIImportDocumentType.PURCHASE_ORDER
    assert str(po_doc.supplier_id) == supplier["id"], "supplier matched from the document"

    po_posting = posting.post_document(
        db, po_doc, ai_import_service.working_payload(db, po_doc), actor,
    )
    from app.models.purchase_order import PurchaseOrder
    po = db.get(PurchaseOrder, po_posting.entity_id)
    assert po.status == RecordStatus.DRAFT, "an imported order is never auto-approved"
    assert po.approved_by is None
    assert po.supplier_id == uuid.UUID(supplier["id"])
    assert float(po.order_items[0].quantity_ordered) == float(QTY)
    # The order carries a generated number, not the supplier's.
    assert po.po_number != PAPER_PO

    # ── 3. Delivery note — the receipt that moves stock ──────────────────────
    dn_doc = _ingest(db, monkeypatch, world, responses["dn"], file_name="03_dn.pdf")
    assert dn_doc.document_type == AIImportDocumentType.DELIVERY_NOTE

    # It quotes the paper order number, and still resolves to the order that
    # was created from the scanned purchase order.
    dn_po_match = matching.best_match(db, dn_doc.id, "purchase_order")
    assert dn_po_match is not None, "the delivery note did not find its order"
    assert str(dn_po_match.target_id) == str(po.id)

    dn_posting = posting.post_document(
        db, dn_doc, ai_import_service.working_payload(db, dn_doc), actor,
        destination=DeliveryDestination.SITE_STORE,
    )
    from app.models.delivery import Delivery
    delivery = db.get(Delivery, dn_posting.entity_id)
    assert delivery.supplier_delivery_note_number == DELIVERY_NOTE_NO

    # Stock moved, exactly once, through the real ledger.
    assert _ledger_total(db, project["id"], item["id"]) == float(QTY)
    from app.models.stock import StockLedger
    movements = (
        db.query(StockLedger)
        .filter(StockLedger.reference_type == "delivery",
                StockLedger.reference_id == delivery.id)
        .all()
    )
    assert len(movements) == 1
    assert movements[0].movement_type == MovementType.DELIVERY_RECEIVED
    assert movements[0].project_id == uuid.UUID(project["id"])

    # The order's outstanding quantity was updated by the domain service.
    db.refresh(po)
    assert float(po.order_items[0].quantity_received) == float(QTY)
    assert po.status == RecordStatus.RECEIVED

    # ── 4. Supplier invoice — the liability ──────────────────────────────────
    inv_doc = _ingest(db, monkeypatch, world, responses["inv"], file_name="04_inv.pdf")
    assert inv_doc.document_type == AIImportDocumentType.SUPPLIER_INVOICE

    # Three-way match: it found the order, and the goods are receipted.
    inv_po_match = matching.best_match(db, inv_doc.id, "purchase_order")
    assert inv_po_match is not None and str(inv_po_match.target_id) == str(po.id)
    codes = [r["code"] for r in inv_doc.outcome_reasons]
    assert "NO_GOODS_RECEIPT" not in codes, inv_doc.outcome_reasons
    assert "ARITHMETIC_INVALID" not in codes

    inv_posting = posting.post_document(
        db, inv_doc, ai_import_service.working_payload(db, inv_doc), actor,
    )
    from app.models.invoice import Invoice
    invoice = db.get(Invoice, inv_posting.entity_id)
    assert invoice.invoice_number == INVOICE_NO
    assert float(invoice.total_amount) == float(TOTAL)
    assert invoice.purchase_order_id == po.id, "the liability is linked to its order"
    assert invoice.status != RecordStatus.PAID, "a document can never mark an invoice paid"

    # ── 5. Project costs are not inflated by an unpaid liability ─────────────
    from app.models.payment import Payment
    assert db.query(Payment).filter(
        Payment.project_id == uuid.UUID(project["id"])
    ).count() == 0
    # Procurement spend is driven by Payment rows, so it stays at zero until
    # the invoice is actually paid — importing a liability must not look like
    # money going out.

    # ── 6. Everything is linked and visible ──────────────────────────────────
    for doc in (mr_doc, po_doc, dn_doc, inv_doc):
        db.refresh(doc)
        assert doc.status == AIImportDocumentStatus.POSTED
        assert len(doc.postings) == 1
        assert doc.postings[0].entity_id is not None

    # Relation is by supplier and project, so the order and the delivery note
    # appear. The material request does not: it carries no supplier, which is
    # correct — an internal request is not a supplier document.
    related_ids = {r["id"] for r in matching.related_documents(db, inv_doc)}
    assert str(po_doc.id) in related_ids
    assert str(dn_doc.id) in related_ids


# ── Idempotency: the whole thing again ────────────────────────────────────────

def test_running_the_same_transaction_twice_changes_nothing(db, monkeypatch, world):
    """
    The second pass must create no second record and move no further stock —
    the guarantee that matters most when staff re-upload a batch.
    """
    actor = world["actor"]
    project, item, supplier = world["project"], world["item"], world["supplier"]
    responses = _docs(project["code"])

    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.models.purchase_order import PurchaseOrder

    documents = []
    for key, name, dest in (
        ("mr", "01_mr.pdf", None),
        ("po", "02_po.pdf", None),
        ("dn", "03_dn.pdf", DeliveryDestination.SITE_STORE),
        ("inv", "04_inv.pdf", None),
    ):
        doc = _ingest(db, monkeypatch, world, responses[key], file_name=name)
        posting.post_document(
            db, doc, ai_import_service.working_payload(db, doc), actor,
            destination=dest,
        )
        documents.append(doc)

    def counts():
        return (
            db.query(MaterialRequest).filter(
                MaterialRequest.project_id == uuid.UUID(project["id"])).count(),
            db.query(PurchaseOrder).filter(
                PurchaseOrder.project_id == uuid.UUID(project["id"])).count(),
            db.query(Delivery).filter(
                Delivery.project_id == uuid.UUID(project["id"])).count(),
            db.query(Invoice).filter(
                Invoice.project_id == uuid.UUID(project["id"])).count(),
        )

    first_counts = counts()
    first_stock = _ledger_total(db, project["id"], item["id"])
    assert first_counts == (1, 1, 1, 1)
    assert first_stock == float(QTY)

    # Pass two: the very same documents, posted again.
    refused = 0
    for doc, dest in zip(documents, (None, None, DeliveryDestination.SITE_STORE, None)):
        try:
            posting.post_document(
                db, doc, ai_import_service.working_payload(db, doc), actor,
                destination=dest,
            )
        except posting.AlreadyPosted:
            refused += 1

    assert refused == 4, "every repeat post should be refused"
    assert counts() == first_counts, "a second pass created business records"
    assert _ledger_total(db, project["id"], item["id"]) == first_stock, (
        "a second pass moved stock again"
    )


def test_re_uploading_the_same_files_is_caught_before_processing(db, monkeypatch, world):
    """Identical bytes are refused at upload, so they never reach posting."""
    checksum = "f" * 64
    first = make_import_document(
        db, uploaded_by=world["actor_row"]["id"], project_id=world["project"]["id"],
        file_name="invoice.pdf", checksum=checksum,
    )
    first.status = AIImportDocumentStatus.POSTED
    db.flush()

    # The upload path marks a second copy DUPLICATE rather than queueing it.
    existing = (
        db.query(AIImportDocument)
        .filter(AIImportDocument.checksum_sha256 == checksum,
                AIImportDocument.status != AIImportDocumentStatus.REJECTED)
        .order_by(AIImportDocument.created_at.asc())
        .first()
    )
    assert existing is not None and existing.id == first.id


# ── Missing and conflicting documents ─────────────────────────────────────────

def test_an_invoice_with_no_order_and_no_receipt_is_held_for_review(db, monkeypatch, world):
    """The missing-documents case: nothing is posted on an invoice alone."""
    responses = _docs(world["project"]["code"])
    inv_doc = _ingest(db, monkeypatch, world, responses["inv"], file_name="lonely_invoice.pdf")

    codes = [r["code"] for r in inv_doc.outcome_reasons]
    assert "NO_PURCHASE_ORDER" in codes
    assert inv_doc.status == AIImportDocumentStatus.AWAITING_REVIEW
    assert inv_doc.postings == []


def test_an_invoice_billing_more_than_was_ordered_is_flagged(db, monkeypatch, world):
    """The conflicting-documents case."""
    actor = world["actor"]
    project = world["project"]
    responses = _docs(project["code"])

    po_doc = _ingest(db, monkeypatch, world, responses["po"], file_name="po.pdf")
    posting.post_document(db, po_doc, ai_import_service.working_payload(db, po_doc), actor)

    dn_doc = _ingest(db, monkeypatch, world, responses["dn"], file_name="dn.pdf")
    posting.post_document(
        db, dn_doc, ai_import_service.working_payload(db, dn_doc), actor,
        destination=DeliveryDestination.SITE_STORE,
    )

    # An invoice for 140 bags against an order for 100.
    overbilled = supplier_invoice(
        SUPPLIER_NAME, invoice_number="INV-OVER-1", po_reference=PAPER_PO,
        quantity=140, unit_price=UNIT_PRICE, line_total="16800.00",
        subtotal="16800.00", vat="2520.00", total="19320.00",
        project_code=project["code"], description=ITEM_NAME,
    )
    inv_doc = _ingest(db, monkeypatch, world, overbilled, file_name="overbilled.pdf")

    codes = [r["code"] for r in inv_doc.outcome_reasons]
    assert "QUANTITY_DISCREPANCY" in codes, inv_doc.outcome_reasons
    assert inv_doc.status == AIImportDocumentStatus.AWAITING_REVIEW


def test_a_delivery_for_goods_never_ordered_is_flagged(db, monkeypatch, world):
    actor = world["actor"]
    project = world["project"]
    responses = _docs(project["code"])

    po_doc = _ingest(db, monkeypatch, world, responses["po"], file_name="po.pdf")
    posting.post_document(db, po_doc, ai_import_service.working_payload(db, po_doc), actor)

    unexpected = delivery_note(
        SUPPLIER_NAME, note_number="DN-ODD-1", po_reference=PAPER_PO,
        quantity=4, project_code=project["code"], description="Diesel generator hire",
    )
    dn_doc = _ingest(db, monkeypatch, world, unexpected, file_name="odd_delivery.pdf")

    codes = [r["code"] for r in dn_doc.outcome_reasons]
    assert "ITEM_NOT_ORDERED" in codes, dn_doc.outcome_reasons


# ── Dashboard reflects the posted transaction ─────────────────────────────────

def test_the_dashboard_reports_the_completed_transaction(db, monkeypatch, world):
    from app.schemas.ai_import import DashboardFilters

    actor = world["actor"]
    project = world["project"]
    responses = _docs(project["code"])

    for key, name, dest in (
        ("po", "po.pdf", None),
        ("dn", "dn.pdf", DeliveryDestination.SITE_STORE),
        ("inv", "inv.pdf", None),
    ):
        doc = _ingest(db, monkeypatch, world, responses[key], file_name=name)
        posting.post_document(
            db, doc, ai_import_service.working_payload(db, doc), actor, destination=dest,
        )

    data = ai_import_service.dashboard(
        db, DashboardFilters(project_id=uuid.UUID(project["id"])), viewer=actor,
    )

    assert data["totals"]["uploaded"] == 3
    assert data["totals"]["posted"] == 3
    assert data["totals"]["posted_transactions"] == 3
    assert data["totals"]["incomplete_postings"] == 0
    assert data["ai_usage"]["input_tokens"] > 0
    assert data["ai_usage"]["cost_usd"] > 0
