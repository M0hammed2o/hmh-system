"""
AI Document Import — posting through the real domain services.

These are integration tests: they create genuine material requests, purchase
orders, deliveries, stock ledger movements and supplier invoices via
mr_service, po_service, delivery_service and invoice_service. The `db` fixture
rolls its transaction back, so nothing survives the test.

The properties under test are the ones that protect the books:
  * stock only moves on receipt evidence, never on an invoice;
  * a repeated post never creates a second record;
  * an invoice is never marked paid by a document;
  * an imported legacy record never claims approvals that did not happen.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.exceptions import ConflictError
from app.models.ai_import import AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    DeliveryDestination,
    MovementType,
    RecordStatus,
)
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_matching_service as matching
from app.services import ai_import_posting_service as posting
from tests.conftest import make_item, make_project, make_site, make_supplier, make_user
from tests.ai_import_fixtures import (
    credit_note,
    delivery_note,
    make_import_document,
    payment_proof,
    purchase_order,
    supplier_invoice,
    typed_material_request,
)


def _payload(response: dict):
    return extraction._finalise(
        extraction._normalise(response, "vision", "anthropic", "stub")
    )


def _user(db, role="OFFICE_ADMIN"):
    from app.models.user import User
    row = make_user(db, role=role)
    return db.get(User, uuid.UUID(row["id"])), row


def _ledger_total(db, project_id, item_id) -> float:
    from app.models.stock import StockLedger
    rows = (
        db.query(StockLedger)
        .filter(
            StockLedger.project_id == uuid.UUID(project_id),
            StockLedger.item_id == uuid.UUID(item_id),
        )
        .all()
    )
    return sum(float(r.quantity_in or 0) - float(r.quantity_out or 0) for r in rows)


def _setup(db, *, with_site=True):
    actor, actor_row = _user(db)
    project = make_project(db, actor_row["id"])
    site = make_site(db, project["id"]) if with_site else None
    supplier = make_supplier(db, name="Acme Supplies")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    return actor, actor_row, project, site, supplier, item


# ── Phase 4: material request ─────────────────────────────────────────────────

def test_material_request_import_creates_a_draft_request(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        document_type=AIImportDocumentType.MATERIAL_REQUEST,
    )
    payload = _payload(typed_material_request(project_code=project["code"]))

    result = posting.post_material_request(db, document, payload, actor)

    from app.models.material_request import MaterialRequest
    mr = db.get(MaterialRequest, result.entity_id)
    assert mr is not None
    assert mr.status == RecordStatus.DRAFT        # approvals are never simulated
    assert mr.project_id == uuid.UUID(project["id"])
    assert len(mr.items) == 2
    assert result.entity_type == "material_request"


def test_material_request_import_moves_no_stock(db):
    """A request is not a receipt. Nothing may touch the ledger here."""
    actor, actor_row, project, site, supplier, item = _setup(db)
    before = _ledger_total(db, project["id"], item["id"])

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        document_type=AIImportDocumentType.MATERIAL_REQUEST,
    )
    posting.post_material_request(
        db, document, _payload(typed_material_request(project_code=project["code"])), actor,
    )

    assert _ledger_total(db, project["id"], item["id"]) == before


def test_legacy_import_is_labelled_rather_than_shown_as_approved(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        document_type=AIImportDocumentType.MATERIAL_REQUEST, is_legacy=True,
    )
    document.authorised_by = actor.id
    document.authorised_at = datetime.now(timezone.utc)
    db.flush()

    result = posting.post_material_request(
        db, document, _payload(typed_material_request(project_code=project["code"])), actor,
    )

    from app.models.material_request import MaterialRequest
    mr = db.get(MaterialRequest, result.entity_id)
    assert "LEGACY IMPORT" in mr.notes
    assert "did not go through the digital approval workflow" in mr.notes
    assert mr.status == RecordStatus.DRAFT


def test_material_request_with_an_unreadable_quantity_is_refused(db):
    """Rather than post a guess, the import stops and says which line is wrong."""
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        document_type=AIImportDocumentType.MATERIAL_REQUEST,
    )
    from tests.ai_import_fixtures import handwritten_material_request
    payload = _payload(handwritten_material_request(project_code=project["code"]))

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_material_request(db, document, payload, actor)
    assert "quantity" in str(exc.value).lower()


# ── Phase 5: purchase order ───────────────────────────────────────────────────

def test_purchase_order_import_creates_a_draft_order(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.PURCHASE_ORDER,
    )
    payload = _payload(purchase_order("Acme Supplies", project_code=project["code"]))

    result = posting.post_purchase_order(db, document, payload, actor)

    from app.models.purchase_order import PurchaseOrder
    po = db.get(PurchaseOrder, result.entity_id)
    assert po is not None
    assert po.status == RecordStatus.DRAFT        # never silently approved
    assert po.approved_by is None
    assert po.supplier_id == uuid.UUID(supplier["id"])
    assert len(po.order_items) == 1
    assert float(po.order_items[0].quantity_ordered) == 100.0
    assert float(po.order_items[0].rate) == 120.00


def test_purchase_order_import_requires_a_resolved_supplier(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        document_type=AIImportDocumentType.PURCHASE_ORDER,     # no supplier_id
    )
    payload = _payload(purchase_order("Acme Supplies", project_code=project["code"]))

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_purchase_order(db, document, payload, actor)
    assert "supplier" in str(exc.value).lower()


# ── Phase 6: goods receipt and stock ──────────────────────────────────────────

def test_delivery_note_import_creates_the_delivery_and_moves_stock(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    before = _ledger_total(db, project["id"], item["id"])

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=100, project_code=project["code"]))

    result = posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )

    from app.models.delivery import Delivery
    delivery = db.get(Delivery, result.entity_id)
    assert delivery is not None
    assert delivery.supplier_delivery_note_number == "DN-7781"
    assert _ledger_total(db, project["id"], item["id"]) == before + 100.0

    from app.models.stock import StockLedger
    movement = (
        db.query(StockLedger)
        .filter(StockLedger.reference_type == "delivery",
                StockLedger.reference_id == delivery.id)
        .one()
    )
    assert movement.movement_type == MovementType.DELIVERY_RECEIVED
    assert float(movement.quantity_in) == 100.0


def test_the_same_delivery_note_posted_twice_increases_stock_once(db):
    """
    The headline guarantee of Phase 6. The second attempt is refused by the
    idempotency key, and the ledger is unchanged.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=100, project_code=project["code"]))

    posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )
    after_first = _ledger_total(db, project["id"], item["id"])

    with pytest.raises(posting.AlreadyPosted):
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )

    assert _ledger_total(db, project["id"], item["id"]) == after_first


def test_an_invoice_can_never_post_a_goods_receipt(db):
    """
    An invoice is a demand for payment, not proof of delivery. Even called
    directly, the receipt path refuses it.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice("Acme Supplies", project_code=project["code"]))

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )
    assert "not evidence that goods were received" in str(exc.value)
    assert _ledger_total(db, project["id"], item["id"]) == 0


def test_receipt_without_a_receiving_site_is_refused(db):
    """Material must not be booked into stock with no stated destination."""
    actor, actor_row, project, site, supplier, item = _setup(db, with_site=False)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", project_code=project["code"]))

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )
    assert "receiving site" in str(exc.value).lower()


def test_direct_to_lot_receipt_is_refused_rather_than_improvised(db):
    """
    create_delivery routes every receipt to the project warehouse. Rather than
    build a direct-to-lot path the manual screens do not have, the import
    refuses and points at the existing issue-to-lot workflow.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", project_code=project["code"]))

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.LOT,
        )
    assert "project warehouse" in str(exc.value)
    assert _ledger_total(db, project["id"], item["id"]) == 0


def test_a_lot_id_supplied_at_posting_is_rejected_not_ignored(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", project_code=project["code"]))

    with pytest.raises(posting.PostingRefused):
        posting.post_document(
            db, document, payload, actor,
            destination=DeliveryDestination.SITE_STORE, lot_id=uuid.uuid4(),
        )


def test_received_stock_is_scoped_to_the_receiving_project(db):
    """
    Material received for one project must not become stock available to
    another. The ledger row carries the project and no global pool exists.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    other_project = make_project(db, actor_row["id"])

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=25, project_code=project["code"]))

    result = posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )

    from app.models.stock import StockLedger
    movement = (
        db.query(StockLedger)
        .filter(StockLedger.reference_type == "delivery",
                StockLedger.reference_id == result.entity_id)
        .one()
    )
    assert movement.project_id == uuid.UUID(project["id"])
    assert _ledger_total(db, other_project["id"], item["id"]) == 0


def test_partial_delivery_updates_only_the_delivered_quantity(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=40, project_code=project["code"]))

    posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )

    assert _ledger_total(db, project["id"], item["id"]) == 40.0


def test_goods_receipt_updates_the_purchase_order_received_quantity(db):
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _setup(db)
    po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-RECV-01",
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "item_id": item["id"]}],
    )

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note(
        "Acme Supplies", quantity=60, po_reference="PO-RECV-01", project_code=project["code"],
    ))
    matching.rematch_document(db, document, payload)

    posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )

    db.refresh(po)
    assert float(po.order_items[0].quantity_received) == 60.0
    assert po.status == RecordStatus.PARTIALLY_RECEIVED


# ── Phase 7: supplier invoices ────────────────────────────────────────────────

def test_invoice_import_records_the_liability_unpaid(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice("Acme Supplies", project_code=project["code"]))

    result = posting.post_supplier_invoice(db, document, payload, actor)

    from app.models.invoice import Invoice
    invoice = db.get(Invoice, result.entity_id)
    assert invoice is not None
    assert invoice.invoice_number == "INV-502"
    assert float(invoice.total_amount) == 13800.00
    assert float(invoice.vat_amount) == 1800.00
    # Never paid on the strength of a document.
    assert invoice.status != RecordStatus.PAID


def test_duplicate_invoice_number_is_refused_by_the_domain_service(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    payload = _payload(supplier_invoice("Acme Supplies", project_code=project["code"]))

    first = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    posting.post_supplier_invoice(db, first, payload, actor)

    # Same invoice, different scanned file — a new document, same number.
    second = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
        file_name="rescan-of-same-invoice.pdf",
    )
    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_supplier_invoice(db, second, payload, actor)
    assert "already exists" in str(exc.value)

    from app.models.invoice import Invoice
    count = (
        db.query(Invoice)
        .filter(Invoice.supplier_id == uuid.UUID(supplier["id"]),
                Invoice.invoice_number == "INV-502")
        .count()
    )
    assert count == 1


def test_invoice_with_an_unreadable_total_is_refused(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    response = supplier_invoice("Acme Supplies", project_code=project["code"])
    response["fields"] = [f for f in response["fields"] if f["name"] != "total_amount"]

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_supplier_invoice(db, document, _payload(response), actor)
    assert "total" in str(exc.value).lower()


def test_invoice_links_to_its_purchase_order_when_one_was_matched(db):
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _setup(db)
    po = _make_po(db, project["id"], supplier["id"], actor_row["id"], po_number="PO-LINK-01")

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice(
        "Acme Supplies", po_reference="PO-LINK-01", project_code=project["code"],
    ))
    matching.rematch_document(db, document, payload)

    result = posting.post_supplier_invoice(db, document, payload, actor)

    from app.models.invoice import Invoice
    invoice = db.get(Invoice, result.entity_id)
    assert invoice.purchase_order_id == po.id


def test_existing_partially_paid_invoice_keeps_its_derived_status(db):
    """
    Importing a document must never overwrite a payment-derived status.
    The status comes from Payment rows and nothing else.
    """
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus, PaymentType
    from app.services import payment_service

    actor, actor_row, project, site, supplier, item = _setup(db)
    now = datetime.now(timezone.utc)
    invoice = Invoice(
        invoice_number="INV-PAID-1",
        supplier_id=uuid.UUID(supplier["id"]),
        project_id=uuid.UUID(project["id"]),
        total_amount=1000.00,
        status=RecordStatus.DRAFT,
        captured_at=now, created_at=now, updated_at=now,
    )
    db.add(invoice)
    db.flush()
    db.add(Payment(
        invoice_id=invoice.id,
        supplier_id=uuid.UUID(supplier["id"]),
        project_id=uuid.UUID(project["id"]),
        payment_type=PaymentType.SUPPLIER,
        amount_paid=400.00,
        status=PaymentStatus.PAID,
        payment_date=now.date(),
        created_at=now, updated_at=now,
    ))
    db.flush()
    payment_service._recalculate_invoice_status(db, invoice.id)
    db.flush()
    db.refresh(invoice)

    status_after_payment = invoice.status
    assert status_after_payment != RecordStatus.PAID    # only 400 of 1000

    # Re-importing the same invoice number is refused, so the status stands.
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice(
        "Acme Supplies", invoice_number="INV-PAID-1", project_code=project["code"],
    ))
    with pytest.raises(posting.PostingRefused):
        posting.post_supplier_invoice(db, document, payload, actor)

    db.refresh(invoice)
    assert invoice.status == status_after_payment


# ── Unsupported document types ────────────────────────────────────────────────

def test_credit_note_is_refused_with_the_gap_explained(db):
    """There is no credit note record in this system; we say so rather than improvise."""
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_CREDIT_NOTE,
    )

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_document(db, document, _payload(credit_note("Acme Supplies")), actor)
    assert "credit note record" in str(exc.value)
    assert "known gap" in str(exc.value)


def test_payment_proof_does_not_create_a_payment(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.PAYMENT_PROOF,
    )

    from app.models.payment import Payment
    before = db.query(Payment).count()

    with pytest.raises(posting.PostingRefused) as exc:
        posting.post_document(db, document, _payload(payment_proof("Acme Supplies")), actor)
    assert "payments screen" in str(exc.value)
    assert db.query(Payment).count() == before


def test_unknown_document_type_has_no_posting_path(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        document_type=AIImportDocumentType.UNKNOWN,
    )
    with pytest.raises(posting.PostingRefused):
        posting.post_document(db, document, _payload(supplier_invoice("Acme")), actor)


# ── Idempotency and crash safety ──────────────────────────────────────────────

def test_the_claim_is_committed_before_the_domain_service_runs(db):
    """
    A posting row exists the moment the attempt starts, so a crash mid-post
    blocks a retry instead of allowing a duplicate.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    claim = posting._claim(db, document, "invoice", actor.id, {"test": True})

    assert claim.entity_id is None            # in flight
    assert claim.idempotency_key.endswith(":invoice")

    # A claim taken moments ago is a post still in flight, and says so. The
    # wording differs from an abandoned claim; both refuse the second attempt.
    with pytest.raises(posting.AlreadyPosted) as exc:
        posting._claim(db, document, "invoice", actor.id)
    assert "right now" in str(exc.value)


def test_an_unfinished_claim_is_reported_for_manual_verification(db):
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    posting._claim(db, document, "invoice", actor.id)

    incomplete = posting.incomplete_postings(db)
    assert any(p.document_id == document.id for p in incomplete)


def test_a_failed_domain_call_releases_the_claim(db):
    """
    When the domain service rejects the request from its own validation —
    before writing anything — the claim row is deleted, freeing the
    idempotency key so a corrected retry can proceed.
    """
    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice("Acme Supplies", project_code=project["code"]))

    first = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    posting.post_supplier_invoice(db, first, payload, actor)

    with pytest.raises(posting.PostingRefused):
        posting.post_supplier_invoice(db, document, payload, actor)

    # The claim is gone, not flagged: the key must be reusable, and a
    # reversed-but-present row would force a new key and defeat the unique index.
    assert (
        db.query(AIImportPosting)
        .filter(AIImportPosting.document_id == document.id)
        .count()
    ) == 0

    # And the document can genuinely be posted once the clash is resolved.
    corrected = _payload(supplier_invoice(
        "Acme Supplies", invoice_number="INV-CORRECTED", project_code=project["code"],
    ))
    result = posting.post_supplier_invoice(db, document, corrected, actor)
    assert result.entity_id is not None


def test_posting_records_a_full_audit_trail(db):
    from app.models.audit import AuditEvent

    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    result = posting.post_supplier_invoice(
        db, document, _payload(supplier_invoice("Acme Supplies", project_code=project["code"])), actor,
    )

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "ai_import_invoice",
                AuditEvent.entity_id == result.entity_id)
        .all()
    )
    assert events
    assert events[0].after_value["source_document"] == str(document.id)
    assert "Payment status remains" in events[0].notes


def test_the_original_scan_is_attached_to_the_record_it_produced(db):
    from app.models.attachment import Attachment
    from app.models.enums import AttachmentEntity

    actor, actor_row, project, site, supplier, item = _setup(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    result = posting.post_supplier_invoice(
        db, document, _payload(supplier_invoice("Acme Supplies", project_code=project["code"])), actor,
    )

    attachment = (
        db.query(Attachment)
        .filter(Attachment.entity_type == AttachmentEntity.INVOICE,
                Attachment.entity_id == result.entity_id)
        .one()
    )
    assert attachment.stored_path == document.stored_path
    assert attachment.file_name == document.file_name
