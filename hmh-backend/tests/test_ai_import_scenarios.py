"""
AI Document Import — the remaining required document scenarios.

Covers the paperwork shapes that do not fit the single-document happy path:
multi-page documents, several invoices against one order, one invoice spanning
several orders, and an order that arrives before its material request.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.enums import AIImportDocumentType, AIImportMatchStatus, RecordStatus
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_matching_service as matching
from app.services import ai_import_posting_service as posting
from app.services import ai_import_service
from tests.conftest import make_item, make_project, make_site, make_supplier, make_user
from tests.ai_import_fixtures import (
    field,
    install_stub,
    line,
    make_import_document,
    raw_response,
    supplier_invoice,
)
from tests.test_ai_import_matching import _make_po


def _payload(response: dict):
    return extraction._finalise(
        extraction._normalise(response, "vision", "anthropic", "stub")
    )


def _user_obj(db, role="OFFICE_ADMIN"):
    from app.models.user import User
    row = make_user(db, role=role)
    return db.get(User, uuid.UUID(row["id"])), row


def _env(db):
    actor, actor_row = _user_obj(db)
    project = make_project(db, actor_row["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    return actor, actor_row, project, site, supplier, item


# ── Multi-page documents ──────────────────────────────────────────────────────

def multi_page_invoice(supplier_name: str, project_code: str) -> dict:
    """An invoice whose lines run across three pages, totalled on the last."""
    return raw_response(
        AIImportDocumentType.SUPPLIER_INVOICE,
        [
            field("document_number", "INV-MP-900", page=1),
            field("issue_date", "2026-03-20", page=1),
            field("supplier_name", supplier_name, page=1),
            field("project_number", project_code, page=1),
            field("subtotal_amount", "9000.00", page=3),
            field("vat_rate", "15", page=3),
            field("vat_amount", "1350.00", page=3),
            field("total_amount", "10350.00", page=3),
        ],
        [
            line("Cement 42.5N 50kg bag", 20, "bag", "120.00", "2400.00", page=1),
            line("River sand", 10, "m3", "300.00", "3000.00", page=2),
            line("Builders lime", 30, "bag", "120.00", "3600.00", page=3),
        ],
    )


def test_multi_page_invoice_keeps_page_provenance_and_totals_correctly(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, multi_page_invoice("Acme Supplies", project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    record = ai_import_service.current_extraction(db, document.id)
    assert record is not None

    # Each value knows which page it came from — that is what the reviewer
    # needs to find it again in a 3-page scan.
    assert record.fields["document_number"]["page"] == 1
    assert record.fields["total_amount"]["page"] == 3
    assert [i["page"] for i in record.line_items] == [1, 2, 3]

    # Lines across all three pages add up to the subtotal printed on page 3.
    assert all(c["passed"] for c in record.arithmetic_checks), record.arithmetic_checks
    assert "ARITHMETIC_INVALID" not in [r["code"] for r in document.outcome_reasons]


def test_multi_page_arithmetic_catches_a_page_that_was_missed(db, monkeypatch):
    """If a page fails to read, the totals stop adding up and that is reported."""
    response = multi_page_invoice("Acme Supplies", "X")
    response["line_items"] = response["line_items"][:2]   # page 3 lines lost

    actor, actor_row, project, site, supplier, item = _env(db)
    response["fields"] = [
        f if f["name"] != "project_number" else field("project_number", project["code"])
        for f in response["fields"]
    ]
    install_stub(monkeypatch, response)

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    check = next(
        c for c in (ai_import_service.current_extraction(db, document.id).arithmetic_checks)
        if c["name"] == "lines_sum_to_subtotal"
    )
    assert check["passed"] is False
    assert check["expected"] == pytest.approx(5400.00)   # only pages 1-2
    assert check["actual"] == pytest.approx(9000.00)


# ── Several invoices against one purchase order ───────────────────────────────

def test_two_invoices_against_one_po_both_match_and_both_post(db, monkeypatch):
    """
    A supplier billing one order in two instalments is ordinary. Both invoices
    must link to the same order and create two separate liabilities.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-SPLIT-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100, "item_id": item["id"]}],
    )

    first_doc = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    second_doc = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
        file_name="invoice-part-2.pdf",
    )

    first = _payload(supplier_invoice(
        "Acme Supplies", invoice_number="INV-A1", po_reference="PO-SPLIT-01",
        project_code=project["code"], quantity=60, unit_price="120.00",
        line_total="7200.00", subtotal="7200.00", vat="1080.00", total="8280.00",
    ))
    second = _payload(supplier_invoice(
        "Acme Supplies", invoice_number="INV-A2", po_reference="PO-SPLIT-01",
        project_code=project["code"], quantity=40, unit_price="120.00",
        line_total="4800.00", subtotal="4800.00", vat="720.00", total="5520.00",
    ))

    for doc, payload in ((first_doc, first), (second_doc, second)):
        matching.rematch_document(db, doc, payload)
        match = matching.best_match(db, doc.id, "purchase_order")
        assert match is not None and str(match.target_id) == str(po.id)
        assert match.status == AIImportMatchStatus.CONFIRMED

    posting.post_supplier_invoice(db, first_doc, first, actor)
    posting.post_supplier_invoice(db, second_doc, second, actor)

    from app.models.invoice import Invoice
    invoices = (
        db.query(Invoice)
        .filter(Invoice.purchase_order_id == po.id)
        .order_by(Invoice.invoice_number)
        .all()
    )
    assert [i.invoice_number for i in invoices] == ["INV-A1", "INV-A2"]
    assert sum(float(i.total_amount) for i in invoices) == pytest.approx(13800.00)


def test_a_second_invoice_billing_more_than_remains_is_flagged(db):
    """Two part-invoices that together exceed the order are not silently accepted."""
    actor, actor_row, project, site, supplier, item = _env(db)
    po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-OVER-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )

    # Billing 140 bags against an order for 100.
    payload = _payload(supplier_invoice(
        "Acme Supplies", po_reference="PO-OVER-01", project_code=project["code"],
        quantity=140, unit_price="120.00", line_total="16800.00",
        subtotal="16800.00", vat="2520.00", total="19320.00",
    ))
    comparison = matching.compare_against_purchase_order(db, payload, po.id, mode="billing")

    assert any(d["status"] == "OVER_SUPPLY" for d in comparison["discrepancies"])


# ── One invoice covering several purchase orders ──────────────────────────────

def test_one_invoice_covering_two_pos_is_not_silently_attached_to_one(db):
    """
    A consolidated invoice spanning two orders must not be posted against
    whichever order happened to score highest. It reports lines that are not
    on the matched order, which sends it to review.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    po_a = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-MULTI-A",
        total=2400.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 20,
                "unit": "bag", "rate": 120.00, "received": 20}],
    )
    _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-MULTI-B",
        total=3000.00,
        items=[{"description": "River sand", "quantity": 10,
                "unit": "m3", "rate": 300.00, "received": 10}],
    )

    consolidated = _payload(raw_response(
        AIImportDocumentType.SUPPLIER_INVOICE,
        [
            field("document_number", "INV-CONSOL-1"),
            field("issue_date", "2026-03-25"),
            field("supplier_name", "Acme Supplies"),
            field("project_number", project["code"]),
            field("purchase_order_reference", "PO-MULTI-A"),
            field("subtotal_amount", "5400.00"),
            field("vat_rate", "15"),
            field("vat_amount", "810.00"),
            field("total_amount", "6210.00"),
        ],
        [
            line("Cement 42.5N 50kg bag", 20, "bag", "120.00", "2400.00"),
            line("River sand", 10, "m3", "300.00", "3000.00"),
        ],
    ))

    comparison = matching.compare_against_purchase_order(
        db, consolidated, po_a.id, mode="billing",
    )

    # The sand line belongs to the other order, so it is reported, not absorbed.
    not_on_order = [d for d in comparison["discrepancies"] if d["status"] == "NOT_ON_ORDER"]
    assert len(not_on_order) == 1
    assert "River sand" in not_on_order[0]["message"]
    # The invoice total also exceeds the single order it was matched to.
    assert comparison["total_check"]["within_tolerance"] is False


def test_a_consolidated_invoice_is_sent_to_review_not_auto_posted(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-MULTI-C",
        total=2400.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 20,
                "unit": "bag", "rate": 120.00, "received": 20}],
    )
    install_stub(monkeypatch, raw_response(
        AIImportDocumentType.SUPPLIER_INVOICE,
        [
            field("document_number", "INV-CONSOL-2"),
            field("issue_date", "2026-03-25"),
            field("supplier_name", "Acme Supplies"),
            field("project_number", project["code"]),
            field("purchase_order_reference", "PO-MULTI-C"),
            field("subtotal_amount", "5400.00"),
            field("vat_rate", "15"),
            field("vat_amount", "810.00"),
            field("total_amount", "6210.00"),
        ],
        [
            line("Cement 42.5N 50kg bag", 20, "bag", "120.00", "2400.00"),
            line("Generator hire", 1, "ea", "3000.00", "3000.00"),
        ],
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "ITEM_NOT_ORDERED" in codes
    assert document.processing_outcome.value == "NEEDS_REVIEW"


# ── Purchase order arriving before its material request ───────────────────────

def test_a_po_uploaded_before_its_mr_links_once_the_mr_exists(db, monkeypatch):
    """
    The mirror of the invoice-before-PO case: an order scanned before the
    request it came from picks that request up once it is in the system.
    """
    from tests.ai_import_fixtures import purchase_order

    actor, actor_row, project, site, supplier, item = _env(db)

    response = purchase_order("Acme Supplies", project_code=project["code"])
    response["fields"].append(field("material_request_reference", "MR-EARLY-01"))
    install_stub(monkeypatch, response)

    po_doc = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, po_doc)

    # The request does not exist yet, so nothing is matched to it.
    assert matching.best_match(db, po_doc.id, "material_request") is None

    # The material request is created later.
    from app.models.material_request import MaterialRequest
    now = datetime.now(timezone.utc)
    mr = MaterialRequest(
        request_number="MR-EARLY-01",
        project_id=uuid.UUID(project["id"]),
        requested_by=uuid.UUID(actor_row["id"]),
        status=RecordStatus.APPROVED,
        requested_date=now,
        created_at=now, updated_at=now,
    )
    db.add(mr)
    db.flush()

    ai_import_service.reevaluate(db, po_doc)

    match = matching.best_match(db, po_doc.id, "material_request")
    assert match is not None
    assert str(match.target_id) == str(mr.id)
    assert match.status == AIImportMatchStatus.CONFIRMED


def test_an_imported_po_carries_its_material_request_link_into_the_record(db, monkeypatch):
    from app.models.material_request import MaterialRequest
    from tests.ai_import_fixtures import purchase_order

    actor, actor_row, project, site, supplier, item = _env(db)
    now = datetime.now(timezone.utc)
    mr = MaterialRequest(
        request_number="MR-LINKED-02",
        project_id=uuid.UUID(project["id"]),
        requested_by=uuid.UUID(actor_row["id"]),
        status=RecordStatus.APPROVED,
        requested_date=now,
        created_at=now, updated_at=now,
    )
    db.add(mr)
    db.flush()

    response = purchase_order("Acme Supplies", project_code=project["code"])
    response["fields"].append(field("material_request_reference", "MR-LINKED-02"))
    install_stub(monkeypatch, response)

    po_doc = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, po_doc)
    result = posting.post_purchase_order(
        db, po_doc, ai_import_service.working_payload(db, po_doc), actor,
    )

    from app.models.purchase_order import PurchaseOrder
    po = db.get(PurchaseOrder, result.entity_id)
    assert po.material_request_id == mr.id


# ── Historical import against existing stock ──────────────────────────────────

def test_historical_receipt_adds_to_existing_stock_rather_than_replacing_it(db, monkeypatch):
    """
    Importing old paperwork must not reset a balance that a stocktake already
    established — the ledger is append-only, so the opening balance stands and
    the historical receipt is added on top.
    """
    from tests.conftest import make_stock
    from app.models.enums import DeliveryDestination
    from tests.ai_import_fixtures import delivery_note
    from tests.test_ai_import_posting import _ledger_total

    actor, actor_row, project, site, supplier, item = _env(db)

    # A stocktake has already put 500 bags on the books.
    make_stock(db, project["id"], None, item["id"], qty=500.0)
    assert _ledger_total(db, project["id"], item["id"]) == 500.0

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
        is_legacy=True,
    )
    document.authorised_by = actor.id
    document.authorised_at = datetime.now(timezone.utc)
    db.flush()

    payload = _payload(delivery_note(
        "Acme Supplies", quantity=100, project_code=project["code"],
    ))
    posting.post_goods_receipt(
        db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
    )

    # 500 opening + 100 historical receipt. The opening balance is untouched.
    assert _ledger_total(db, project["id"], item["id"]) == 600.0

    from app.models.stock import StockLedger
    from app.models.enums import MovementType
    opening = (
        db.query(StockLedger)
        .filter(StockLedger.project_id == uuid.UUID(project["id"]),
                StockLedger.movement_type == MovementType.OPENING_BALANCE)
        .one()
    )
    assert float(opening.quantity_in) == 500.0


# ── Internal cron endpoint ────────────────────────────────────────────────────

def test_cron_endpoint_is_disabled_when_no_secret_is_configured(db, client, monkeypatch):
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "CRON_SECRET", "")
    response = client.post("/api/v1/internal/process-ai-import")
    assert response.status_code == 404


def test_cron_endpoint_rejects_a_wrong_secret(db, client, monkeypatch):
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "CRON_SECRET", "the-real-secret")
    response = client.post(
        "/api/v1/internal/process-ai-import",
        headers={"X-Cron-Secret": "not-the-secret"},
    )
    assert response.status_code == 403


def test_cron_endpoint_accepts_the_configured_secret(db, client, monkeypatch):
    """
    The cron endpoint opens its own session (it runs outside a request), so the
    session factory is pointed at the test session for this test. Closing is
    suppressed because the fixture owns that session's lifetime.
    """
    import app.db.session as _session_module
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "CRON_SECRET", "the-real-secret")

    class _BorrowedSession:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass  # the db fixture owns this session

    monkeypatch.setattr(_session_module, "SessionLocal", lambda: _BorrowedSession(db))

    response = client.post(
        "/api/v1/internal/process-ai-import",
        headers={"X-Cron-Secret": "the-real-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "processed" in body and "failed" in body and "reclaimed" in body


# ── Company filtering (Phase 8) ───────────────────────────────────────────────

def _make_company(db, name=None):
    from app.models.company import Company
    now = datetime.now(timezone.utc)
    company = Company(
        name=name or f"HMH Division {uuid.uuid4().hex[:6]}",
        created_at=now, updated_at=now,
    )
    db.add(company)
    db.flush()
    return company


def test_documents_can_be_filtered_by_company_through_their_project(db, client):
    """
    Documents carry no company of their own — company ownership lives on the
    project — so the filter resolves through it.
    """
    from app.models.project import Project

    actor, actor_row = _user_obj(db, role="OWNER")
    company_a = _make_company(db, "Division A")
    company_b = _make_company(db, "Division B")

    project_a = make_project(db, actor_row["id"])
    project_b = make_project(db, actor_row["id"])
    db.get(Project, uuid.UUID(project_a["id"])).company_id = company_a.id
    db.get(Project, uuid.UUID(project_b["id"])).company_id = company_b.id
    db.flush()

    doc_a = make_import_document(db, uploaded_by=actor_row["id"], project_id=project_a["id"])
    doc_b = make_import_document(db, uploaded_by=actor_row["id"], project_id=project_b["id"])
    db.commit()

    from tests.conftest import auth, login
    token = login(client, actor_row["email"], actor_row["password"])

    response = client.get(
        f"/api/v1/ai-import/documents?company_id={company_a.id}", headers=auth(token),
    )
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()["data"]["items"]]
    assert str(doc_a.id) in ids
    assert str(doc_b.id) not in ids


def test_a_company_with_no_projects_matches_nothing_not_everything(db, client):
    """An empty project list must filter everything out, never fall through."""
    actor, actor_row = _user_obj(db, role="OWNER")
    empty_company = _make_company(db, "Division With No Projects")
    project = make_project(db, actor_row["id"])
    make_import_document(db, uploaded_by=actor_row["id"], project_id=project["id"])
    db.commit()

    from tests.conftest import auth, login
    token = login(client, actor_row["email"], actor_row["password"])

    response = client.get(
        f"/api/v1/ai-import/documents?company_id={empty_company.id}", headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_dashboard_can_be_scoped_to_a_company(db, client):
    from app.models.project import Project

    actor, actor_row = _user_obj(db, role="OWNER")
    company = _make_company(db)
    project = make_project(db, actor_row["id"])
    db.get(Project, uuid.UUID(project["id"])).company_id = company.id
    db.flush()
    make_import_document(db, uploaded_by=actor_row["id"], project_id=project["id"])

    other_project = make_project(db, actor_row["id"])
    make_import_document(db, uploaded_by=actor_row["id"], project_id=other_project["id"])
    db.commit()

    from tests.conftest import auth, login
    token = login(client, actor_row["email"], actor_row["password"])

    response = client.get(
        f"/api/v1/ai-import/dashboard?company_id={company.id}", headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["totals"]["uploaded"] == 1
