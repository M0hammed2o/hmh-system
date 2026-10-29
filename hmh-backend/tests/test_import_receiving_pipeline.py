"""
From uploaded file to BOQ lot: where the materials actually are.

Rafiq uploaded delivery notes into production and could not find the
materials in stock or on a BOQ. Two separate things were wrong, and these
tests pin both plus the chain between them.

  * A failed upload stored nothing, so no document row existed at all —
    yet the screen reported success. Storage failures must be legible.
  * A posted goods receipt lands in the PROJECT WAREHOUSE. Putting it
    against a BOQ lot is a separate, deliberate step. Nothing said so, so a
    correctly posted delivery looked like a lost one.

The rule throughout: only delivery notes move stock, a receipt posts once,
and no lot is ever guessed.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.enums import MovementType
from app.services import ai_import_receiving_service as receiving
from tests.conftest import make_project, make_site, make_supplier, make_user


def _now():
    return datetime.now(timezone.utc)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _batch(db, owner_id, project_id=None):
    from app.models.ai_import import AIImportBatch

    b = AIImportBatch(
        reference=f"AUD-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project_id) if project_id else None,
        uploaded_by=uuid.UUID(owner_id),
        created_at=_now(), updated_at=_now(),
    )
    db.add(b)
    db.flush()
    return b


def _document(db, batch, owner_id, *, doc_type="DELIVERY_NOTE", status="POSTED",
              project_id=None, file_name="delivery-note.pdf"):
    from app.models.ai_import import AIImportDocument
    from app.models.enums import AIImportDocumentStatus, AIImportDocumentType

    d = AIImportDocument(
        batch_id=batch.id,
        file_name=file_name,
        stored_path=f"supabase://ai_import/{batch.id}/{uuid.uuid4().hex}_{file_name}",
        mime_type="application/pdf",
        file_size_bytes=2048,
        checksum_sha256=uuid.uuid4().hex * 2,
        page_count=1,
        status=AIImportDocumentStatus(status),
        document_type=AIImportDocumentType(doc_type),
        classification_confidence=0.95,
        project_id=uuid.UUID(project_id) if project_id else None,
        uploaded_by=uuid.UUID(owner_id),
        created_at=_now(), updated_at=_now(),
    )
    db.add(d)
    db.flush()
    return d


def _delivery(db, project_id, site_id, supplier_id, received_by):
    from app.models.delivery import Delivery
    from app.models.enums import RecordStatus

    d = Delivery(
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        supplier_id=uuid.UUID(supplier_id),
        delivery_number=f"DN-{uuid.uuid4().hex[:6].upper()}",
        supplier_delivery_note_number=f"SUP-{uuid.uuid4().hex[:5].upper()}",
        delivery_date=date(2026, 10, 20),
        delivery_status=RecordStatus.RECEIVED,
        received_by_user_id=uuid.UUID(received_by),
        created_at=_now(), updated_at=_now(),
    )
    db.add(d)
    db.flush()
    return d


def _posting(db, document, delivery, project_id, actor_id):
    from app.models.ai_import import AIImportPosting

    p = AIImportPosting(
        document_id=document.id,
        entity_type="delivery",
        entity_id=delivery.id,
        entity_label=delivery.delivery_number,
        project_id=uuid.UUID(project_id),
        idempotency_key=f"{document.id}:delivery",
        posted_by=uuid.UUID(actor_id),
        posted_at=_now(),
    )
    db.add(p)
    db.flush()
    return p


def _receipt(db, project_id, delivery, item_id, qty, *, lot_id=None):
    """A goods receipt, as delivery_service writes one."""
    from app.models.stock import StockLedger

    row = StockLedger(
        project_id=uuid.UUID(project_id),
        site_id=None,
        lot_id=uuid.UUID(lot_id) if lot_id else None,
        item_id=uuid.UUID(item_id),
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="delivery",
        reference_id=delivery.id,
        quantity_in=qty, quantity_out=0, unit="bag",
        movement_date=_now(), created_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


def _issue_to_lot(db, project_id, lot_id, item_id, qty):
    """Warehouse dispatch to a lot, as the transfer workflow writes it."""
    from app.models.stock import StockLedger

    db.add(StockLedger(
        project_id=uuid.UUID(project_id), site_id=None,
        lot_id=uuid.UUID(lot_id), item_id=uuid.UUID(item_id),
        movement_type=MovementType.TRANSFER_IN,
        reference_type="warehouse_transfer", reference_id=uuid.uuid4(),
        quantity_in=qty, quantity_out=0, unit="bag",
        movement_date=_now(), created_at=_now(),
    ))
    db.flush()


@pytest.fixture()
def world(db):
    from tests.conftest import make_item, make_lot

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    lot = make_lot(db, project["id"], site["id"], lot_number="7")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    supplier = make_supplier(db, name="Umhlanga Building Supplies CC")
    batch = _batch(db, owner["id"], project["id"])
    db.commit()
    return {"owner": owner, "project": project, "site": site, "lot": lot,
            "item": item, "supplier": supplier, "batch": batch}


def _post_receipt(db, world, qty=100, *, lot_id=None):
    """A delivery note posted as a goods receipt."""
    doc = _document(db, world["batch"], world["owner"]["id"],
                    project_id=world["project"]["id"])
    delivery = _delivery(db, world["project"]["id"], world["site"]["id"],
                         world["supplier"]["id"], world["owner"]["id"])
    _posting(db, doc, delivery, world["project"]["id"], world["owner"]["id"])
    _receipt(db, world["project"]["id"], delivery, world["item"]["id"], qty, lot_id=lot_id)
    db.commit()
    return doc, delivery


# ── A posted receipt sits in the project warehouse until it is allocated ─────

def test_a_posted_receipt_reports_itself_as_in_the_project_warehouse(db, world):
    """
    The heart of the confusion: the delivery posted correctly, the stock is
    real, and it is simply not on a lot yet.
    """
    doc, _ = _post_receipt(db, world, qty=100)

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.IN_PROJECT_WAREHOUSE
    assert p["received_qty"] == 100.0
    assert p["allocated_qty"] == 0.0
    assert p["awaiting_allocation_qty"] == 100.0
    assert p["next_action"], "no next step offered to the operator"


def test_the_detail_explains_why_it_is_not_on_the_boq(db, world):
    doc, _ = _post_receipt(db, world, qty=100)
    detail = receiving.receiving_progress(db, doc)["detail"].lower()
    assert "lot" in detail


def test_issuing_to_a_lot_moves_it_to_allocated(db, world):
    doc, _ = _post_receipt(db, world, qty=100)
    _issue_to_lot(db, world["project"]["id"], world["lot"]["id"], world["item"]["id"], 100)
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.ALLOCATED_TO_LOT
    assert p["awaiting_allocation_qty"] == 0.0
    assert p["next_action"] is None


def test_a_partial_issue_reads_as_partly_allocated(db, world):
    doc, _ = _post_receipt(db, world, qty=100)
    _issue_to_lot(db, world["project"]["id"], world["lot"]["id"], world["item"]["id"], 40)
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.PARTIALLY_ALLOCATED
    assert p["allocated_qty"] == 40.0
    assert p["awaiting_allocation_qty"] == 60.0


def test_a_receipt_delivered_straight_to_a_lot_is_already_allocated(db, world):
    doc, _ = _post_receipt(db, world, qty=100, lot_id=world["lot"]["id"])

    assert receiving.receiving_progress(db, doc)["stage"] == receiving.ALLOCATED_TO_LOT


def test_allocation_never_exceeds_what_this_receipt_brought_in(db, world):
    """Transfers are project-wide; they must not report more than was received."""
    doc, _ = _post_receipt(db, world, qty=100)
    _issue_to_lot(db, world["project"]["id"], world["lot"]["id"], world["item"]["id"], 500)
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["allocated_qty"] == 100.0
    assert p["awaiting_allocation_qty"] == 0.0


# ── Only delivery notes move stock ──────────────────────────────────────────

@pytest.mark.parametrize("doc_type", ["SUPPLIER_INVOICE", "PURCHASE_ORDER", "MATERIAL_REQUEST"])
def test_orders_and_invoices_are_never_treated_as_goods_receipts(db, world, doc_type):
    """A commitment is not physical evidence and must not imply stock."""
    doc = _document(db, world["batch"], world["owner"]["id"],
                    doc_type=doc_type, project_id=world["project"]["id"])
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.NOT_A_RECEIPT
    assert p["received_qty"] == 0.0


def test_an_unposted_delivery_note_reports_that_plainly(db, world):
    doc = _document(db, world["batch"], world["owner"]["id"],
                    status="AWAITING_REVIEW", project_id=world["project"]["id"])
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.NOT_POSTED
    assert "post" in (p["next_action"] or "").lower()


def test_a_reversed_posting_no_longer_counts_as_received(db, world):
    doc, delivery = _post_receipt(db, world, qty=100)

    from app.models.ai_import import AIImportPosting
    posting = db.query(AIImportPosting).filter(
        AIImportPosting.document_id == doc.id).one()
    posting.reversed_at = _now()
    posting.reversal_reason = "captured against the wrong project"
    db.commit()

    assert receiving.receiving_progress(db, doc)["stage"] == receiving.NOT_POSTED


# ── Stock is counted once, and other projects are untouched ─────────────────

def test_one_receipt_increases_stock_exactly_once(db, world):
    from app.models.stock import StockLedger

    _post_receipt(db, world, qty=100)

    rows = (db.query(StockLedger)
              .filter(StockLedger.project_id == uuid.UUID(world["project"]["id"]),
                      StockLedger.movement_type == MovementType.DELIVERY_RECEIVED)
              .all())
    assert len(rows) == 1
    assert float(rows[0].quantity_in) == 100.0


def test_a_second_document_posts_its_own_receipt_without_inflating_the_first(db, world):
    doc_a, _ = _post_receipt(db, world, qty=100)
    doc_b, _ = _post_receipt(db, world, qty=60)

    assert receiving.receiving_progress(db, doc_a)["received_qty"] == 100.0
    assert receiving.receiving_progress(db, doc_b)["received_qty"] == 60.0


def test_another_projects_stock_does_not_leak_in(db, world):
    from tests.conftest import make_item, make_lot

    doc, _ = _post_receipt(db, world, qty=100)

    other_owner = make_user(db, role="OWNER")
    other_project = make_project(db, other_owner["id"])
    other_site = make_site(db, other_project["id"])
    other_lot = make_lot(db, other_project["id"], other_site["id"], lot_number="1")
    db.commit()
    # A big issue on another project must not mark this receipt allocated.
    _issue_to_lot(db, other_project["id"], other_lot["id"], world["item"]["id"], 500)
    db.commit()

    p = receiving.receiving_progress(db, doc)
    assert p["stage"] == receiving.IN_PROJECT_WAREHOUSE
    assert p["allocated_qty"] == 0.0


# ── The end-to-end stage shown on screen ────────────────────────────────────

def test_the_pipeline_continues_past_posted(db, world):
    """
    The document status stops at POSTED. On its own that reads as finished,
    which is exactly the misunderstanding being fixed.
    """
    doc, _ = _post_receipt(db, world, qty=100)

    stage = receiving.pipeline_stage(db, doc)
    assert stage["stage"] == receiving.IN_PROJECT_WAREHOUSE
    assert stage["label"] == "In the project warehouse"
    assert stage["next_action"]
    assert stage["receiving"]["awaiting_allocation_qty"] == 100.0


@pytest.mark.parametrize("status,expected", [
    ("QUEUED", "QUEUED"),
    ("PROCESSING", "PROCESSING"),
    ("AWAITING_REVIEW", "AWAITING_REVIEW"),
    ("AWAITING_AUTHORISATION", "AWAITING_AUTHORISATION"),
    ("READY_TO_POST", "READY_TO_POST"),
    ("FAILED", "FAILED"),
    ("REJECTED", "REJECTED"),
])
def test_every_earlier_stage_is_reported(db, world, status, expected):
    doc = _document(db, world["batch"], world["owner"]["id"],
                    status=status, project_id=world["project"]["id"])
    db.commit()

    stage = receiving.pipeline_stage(db, doc)
    assert stage["stage"] == expected
    assert stage["label"]
    assert stage["detail"]


def test_a_failed_document_carries_its_reason(db, world):
    doc = _document(db, world["batch"], world["owner"]["id"],
                    status="FAILED", project_id=world["project"]["id"])
    doc.failure_reason = "Evidence upload to persistent storage failed."
    db.commit()

    assert "storage" in receiving.pipeline_stage(db, doc)["detail"].lower()


def test_the_api_exposes_the_pipeline(db, client, world):
    from tests.conftest import auth, login

    doc, _ = _post_receipt(db, world, qty=100)
    token = login(client, world["owner"]["email"], "Test@1234")

    r = client.get(f"/api/v1/ai-import/documents/{doc.id}", headers=auth(token))
    assert r.status_code == 200, r.text
    pipeline = r.json()["data"]["pipeline"]
    assert pipeline["stage"] == receiving.IN_PROJECT_WAREHOUSE
    assert pipeline["receiving"]["awaiting_allocation_qty"] == 100.0


# ── A refused upload must say why, and must leave nothing behind ────────────
#
# Production logged repeated HTTP 400s uploading PDFs to the private bucket.
# The log recorded only the status, because httpx raises without the response
# body and the body is where Supabase explains itself. That turned a
# diagnosable configuration problem into an opaque failure.

def test_a_supabase_rejection_names_its_reason():
    import httpx

    from app.core.storage import _supabase_error_detail

    request = httpx.Request(
        "PUT", "https://example.supabase.co/storage/v1/object/hmh-evidence-private/a.pdf")
    response = httpx.Response(400, request=request, json={
        "statusCode": "400",
        "error": "invalid_mime_type",
        "message": "mime type application/pdf is not supported",
    })
    detail = _supabase_error_detail(
        httpx.HTTPStatusError("400", request=request, response=response))

    assert "400" in detail
    assert "invalid_mime_type" in detail
    assert "application/pdf" in detail


def test_a_size_rejection_is_distinguishable_from_a_type_rejection():
    import httpx

    from app.core.storage import _supabase_error_detail

    request = httpx.Request("PUT", "https://example.supabase.co/x")
    too_big = httpx.Response(413, request=request, json={
        "statusCode": "413", "error": "Payload too large",
        "message": "The object exceeded the maximum allowed size"})
    missing = httpx.Response(404, request=request, json={
        "statusCode": "404", "error": "Bucket not found"})

    big = _supabase_error_detail(httpx.HTTPStatusError("413", request=request, response=too_big))
    gone = _supabase_error_detail(httpx.HTTPStatusError("404", request=request, response=missing))

    assert "Payload too large" in big
    assert "Bucket not found" in gone
    assert big != gone


def test_a_transport_failure_still_produces_a_description():
    from app.core.storage import _supabase_error_detail

    detail = _supabase_error_detail(RuntimeError("connection reset by peer"))
    assert "RuntimeError" in detail and "connection reset" in detail


def test_the_reason_never_carries_a_credential():
    """
    The service key travels in a request header. Nothing from the request is
    echoed into the message — only the response.
    """
    import httpx

    from app.core.storage import _supabase_error_detail

    request = httpx.Request(
        "PUT", "https://example.supabase.co/storage/v1/object/hmh-evidence-private/a.pdf",
        headers={"Authorization": "Bearer super-secret-service-key"})
    response = httpx.Response(400, request=request, json={"error": "invalid_mime_type"})

    detail = _supabase_error_detail(
        httpx.HTTPStatusError("400", request=request, response=response))
    assert "super-secret-service-key" not in detail
    assert "Bearer" not in detail


def test_a_storage_failure_records_no_document(db, client, monkeypatch):
    """
    The crucial property behind Rafiq's missing materials: when storage
    refuses the file, no document row may survive. A row without a retrievable
    file is a promise the system cannot keep.
    """
    from io import BytesIO

    from app.core.exceptions import StorageError
    from app.models.ai_import import AIImportDocument
    from tests.conftest import auth, login, make_user

    owner = make_user(db, role="OWNER")
    db.commit()
    token = login(client, owner["email"], "Test@1234")

    created = client.post("/api/v1/ai-import/batches", json={}, headers=auth(token))
    assert created.status_code == 201, created.text
    batch_id = created.json()["data"]["id"]

    def refuse(*args, **kwargs):
        raise StorageError(
            "Evidence upload to persistent storage failed. No file was recorded. "
            "Supabase returned HTTP 400: invalid_mime_type")

    monkeypatch.setattr("app.services.ai_import_service.save_upload", refuse)

    before = db.query(AIImportDocument).count()
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents",
        files=[("files", ("delivery-note.pdf", BytesIO(pdf), "application/pdf"))],
        headers=auth(token),
    )

    assert response.status_code in (200, 201), response.text
    data = response.json()["data"]
    assert data["accepted"] == [], "a document was accepted despite storage refusing the file"
    assert len(data["rejected"]) == 1
    assert "delivery-note.pdf" == data["rejected"][0]["file_name"]
    # The operator is told what went wrong, not merely that something did.
    assert "400" in data["rejected"][0]["reason"]

    db.expire_all()
    assert db.query(AIImportDocument).count() == before, \
        "a document row outlived the failed upload"
