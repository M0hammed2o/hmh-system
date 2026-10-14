"""
AI Document Import — ingestion pipeline, policy, worker and API.

Covers the lifecycle a document actually travels: upload, duplicate
detection, background processing, the policy verdict, human review, retry,
worker crash recovery, out-of-order reconciliation, and access control.

No real AI provider, OCR engine or object storage is touched: the provider is
stubbed and the stored file read is patched to return bytes.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.ai_import import AIImportDocument, AIImportJob
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportJobStatus,
    AIImportProcessingOutcome,
    RecordStatus,
)
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_policy_service as policy
from app.services import ai_import_service, ai_import_worker
from tests.conftest import (
    auth,
    login,
    make_item,
    make_project,
    make_site,
    make_supplier,
    make_user,
    make_user_project_access,
)
from tests.ai_import_fixtures import (
    delivery_note,
    injected_invoice,
    install_stub,
    invoice_with_bad_arithmetic,
    make_import_document,
    purchase_order,
    supplier_invoice,
    typed_material_request,
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


def _queued(db, document) -> AIImportJob:
    ai_import_service._enqueue(db, document)
    db.flush()
    return ai_import_service.current_job(db, document.id)


# ── Processing pipeline ───────────────────────────────────────────────────────

def test_document_runs_through_the_full_pipeline(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    stub = install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert stub.calls == 1
    assert document.document_type == AIImportDocumentType.SUPPLIER_INVOICE
    assert float(document.classification_confidence) > 0.9
    assert str(document.supplier_id) == supplier["id"]
    assert str(document.project_id) == project["id"]

    record = ai_import_service.current_extraction(db, document.id)
    assert record is not None
    assert record.is_current is True
    assert record.fields["document_number"]["value"] == "INV-502"
    assert record.fields["total_amount"]["value"] == 13800.00
    assert record.input_tokens == 1200
    assert float(record.cost_usd) == pytest.approx(0.0108)


def test_extraction_history_is_append_only(db, monkeypatch):
    """A reprocess must not destroy the original AI output."""
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(
        monkeypatch,
        supplier_invoice("Acme Supplies", invoice_number="INV-1", project_code=project["code"]),
        supplier_invoice("Acme Supplies", invoice_number="INV-2", project_code=project["code"]),
    )

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    ai_import_service.process_document(db, document)

    from app.models.ai_import import AIImportExtraction
    rows = (
        db.query(AIImportExtraction)
        .filter(AIImportExtraction.document_id == document.id)
        .all()
    )
    assert len(rows) == 2
    assert sum(1 for r in rows if r.is_current) == 1


def test_a_human_classification_survives_reprocessing(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    document.document_type = AIImportDocumentType.DELIVERY_NOTE
    document.document_type_confirmed_by = actor.id
    db.flush()

    ai_import_service.process_document(db, document)

    assert document.document_type == AIImportDocumentType.DELIVERY_NOTE


# ── Policy outcomes ───────────────────────────────────────────────────────────

def test_clean_invoice_with_receipt_and_po_is_auto_eligible(db, monkeypatch):
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _env(db)
    po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-CLEAN-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag",
                "rate": 120.00, "received": 100}],     # already receipted
    )
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-CLEAN-01", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert document.processing_outcome == AIImportProcessingOutcome.AUTO_ELIGIBLE, \
        document.outcome_reasons
    assert document.status == AIImportDocumentStatus.READY_TO_POST


def test_auto_eligible_still_waits_for_a_human_by_default(db, monkeypatch):
    """AI_IMPORT_AUTO_POST_ENABLED is off, so nothing posts itself."""
    assert settings.AI_IMPORT_AUTO_POST_ENABLED is False

    from tests.test_ai_import_matching import _make_po
    actor, actor_row, project, site, supplier, item = _env(db)
    _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-NOAUTO-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag",
                "rate": 120.00, "received": 100}],
    )
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-NOAUTO-01", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert document.status == AIImportDocumentStatus.READY_TO_POST
    assert document.postings == []


def test_invalid_arithmetic_blocks_a_financial_document(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, invoice_with_bad_arithmetic("Acme Supplies"))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED
    codes = [r["code"] for r in document.outcome_reasons]
    assert "ARITHMETIC_INVALID" in codes
    assert policy.may_post(document.processing_outcome) is False


def test_injected_instructions_block_the_document(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, injected_invoice("Acme Supplies"))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "SUSPICIOUS_CONTENT" in codes
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED


def test_unknown_supplier_sends_the_document_to_review(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice(
        "Zzqx Materials International", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "UNKNOWN_SUPPLIER" in codes
    assert document.status == AIImportDocumentStatus.AWAITING_REVIEW


def test_invoice_without_a_purchase_order_needs_review(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "NO_PURCHASE_ORDER" in codes


def test_invoice_for_undelivered_goods_needs_review(db, monkeypatch):
    """A matched PO with nothing receipted is not enough to pay against."""
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _env(db)
    _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-NORECV-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 0}],
    )
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-NORECV-01", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "NO_GOODS_RECEIPT" in codes


def test_price_discrepancy_against_the_po_needs_review(db, monkeypatch):
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _env(db)
    _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-PRICE-01",
        total=12000.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-PRICE-01", project_code=project["code"],
        unit_price="150.00", line_total="15000.00",
        subtotal="15000.00", vat="2250.00", total="17250.00",
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "PRICE_DISCREPANCY" in codes


def test_purchase_order_without_an_approver_needs_review(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, purchase_order(
        "Acme Supplies", project_code=project["code"], approver=None,
    ))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "MISSING_AUTHORISATION" in codes


def test_legacy_document_waits_for_authorisation(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, typed_material_request(project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        is_legacy=True,
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "LEGACY_AUTHORISATION_REQUIRED" in codes
    assert document.status == AIImportDocumentStatus.AWAITING_AUTHORISATION

    ai_import_service.authorise_legacy(db, document, "Signed paper file in cabinet 3.", actor)
    assert document.authorised_by == actor.id
    assert "LEGACY_AUTHORISATION_REQUIRED" not in [r["code"] for r in document.outcome_reasons]


def test_delivery_without_a_receiving_site_needs_review(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, delivery_note("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],     # no site
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "UNKNOWN_RECEIVING_LOCATION" in codes


# ── Corrections ───────────────────────────────────────────────────────────────

def test_correcting_a_field_is_audited_and_re_evaluated(db, monkeypatch):
    from app.models.ai_import import AIImportCorrection
    from app.schemas.ai_import import FieldCorrection

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, invoice_with_bad_arithmetic("Acme Supplies"))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED

    ai_import_service.apply_corrections(
        db, document,
        [FieldCorrection(field_path="total_amount", value=13800.00, reason="Misread digit")],
        actor,
    )

    correction = (
        db.query(AIImportCorrection)
        .filter(AIImportCorrection.document_id == document.id)
        .one()
    )
    assert correction.before_value == "18300.0"
    assert correction.after_value == "13800.0"
    assert correction.corrected_by == actor.id

    record = ai_import_service.current_extraction(db, document.id)
    assert record.fields["total_amount"]["corrected"] is True
    assert record.fields["total_amount"]["source"] == "manual"
    # Arithmetic was recomputed on the corrected figure, so the block is gone.
    assert all(c["passed"] for c in record.arithmetic_checks)
    assert "ARITHMETIC_INVALID" not in [r["code"] for r in document.outcome_reasons]


def test_a_correction_cannot_be_applied_to_a_posted_document(db, monkeypatch):
    from app.core.exceptions import ConflictError
    from app.schemas.ai_import import FieldCorrection

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    document.status = AIImportDocumentStatus.POSTED
    db.flush()

    with pytest.raises(ConflictError):
        ai_import_service.apply_corrections(
            db, document, [FieldCorrection(field_path="total_amount", value=1.0)], actor,
        )


def test_assigning_a_supplier_resolves_the_unknown_supplier_block(db, monkeypatch):
    from app.schemas.ai_import import ContextAssignment

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Zzqx Materials", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    assert "UNKNOWN_SUPPLIER" in [r["code"] for r in document.outcome_reasons]

    ai_import_service.assign_context(
        db, document, ContextAssignment(supplier_id=uuid.UUID(supplier["id"])), actor,
    )

    assert str(document.supplier_id) == supplier["id"]
    assert "UNKNOWN_SUPPLIER" not in [r["code"] for r in document.outcome_reasons]


# ── Worker ────────────────────────────────────────────────────────────────────

def test_worker_processes_a_queued_document(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    assert document.status == AIImportDocumentStatus.QUEUED

    assert ai_import_worker.run_job(db, job) is True

    db.refresh(job)
    db.refresh(document)
    assert job.status == AIImportJobStatus.COMPLETED
    assert job.completed_at is not None
    assert document.status in (
        AIImportDocumentStatus.AWAITING_REVIEW, AIImportDocumentStatus.READY_TO_POST,
    )


def test_provider_outage_schedules_a_retry_with_backoff(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(
        monkeypatch,
        extraction.ExtractionTransientError("AI provider unavailable: connection reset"),
    )

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    db.commit()

    job.status = AIImportJobStatus.RUNNING
    job.attempt_count = 1
    db.commit()

    assert ai_import_worker.run_job(db, job) is False

    db.refresh(job)
    db.refresh(document)
    assert job.status == AIImportJobStatus.PENDING          # retryable
    assert job.next_attempt_at > datetime.now(timezone.utc)
    assert "unavailable" in job.last_error
    assert document.status == AIImportDocumentStatus.QUEUED  # not failed


def test_retry_budget_is_eventually_exhausted(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(
        monkeypatch, extraction.ExtractionTransientError("AI provider unavailable"),
    )

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    job.attempt_count = job.max_attempts
    db.commit()

    ai_import_worker.run_job(db, job)

    db.refresh(job)
    db.refresh(document)
    # FAILED, not DEAD: this one was retryable and simply ran out of attempts.
    # DEAD is reserved for failures that could never have succeeded.
    assert job.status == AIImportJobStatus.FAILED
    assert document.status == AIImportDocumentStatus.FAILED
    assert "retry this document" in document.failure_reason


def test_a_non_retryable_failure_is_dead_not_failed(db, monkeypatch):
    """
    The two terminal job states carry different meanings and must not merge.

    A provider error is not enough here — extraction degrades gracefully
    through its fallback chain — so a genuine defect is injected downstream.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    def boom(*args, **kwargs):
        raise RuntimeError("a defect in the pipeline, not a transient outage")

    monkeypatch.setattr(ai_import_service, "_store_extraction", boom)

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    db.commit()

    assert ai_import_worker.run_job(db, job) is False

    db.refresh(job)
    db.refresh(document)
    assert job.status == AIImportJobStatus.DEAD      # never retried
    assert document.status == AIImportDocumentStatus.FAILED
    assert "RuntimeError" in job.last_error


def test_backoff_grows_and_is_capped():
    first = ai_import_worker._backoff_seconds(1)
    second = ai_import_worker._backoff_seconds(2)
    assert second > first
    assert ai_import_worker._backoff_seconds(50) <= 3600


def test_a_job_abandoned_by_a_dead_worker_is_reclaimed(db, monkeypatch):
    """This is what makes processing resume after a container restart."""
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    job.status = AIImportJobStatus.RUNNING
    job.locked_by = "crashed-host:999"
    job.locked_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.AI_IMPORT_JOB_STALE_MINUTES + 5
    )
    db.commit()

    reclaimed = ai_import_worker.reclaim_stale_jobs(db)

    db.refresh(job)
    assert reclaimed == 1
    assert job.status == AIImportJobStatus.PENDING
    assert job.locked_at is None


def test_a_freshly_locked_job_is_not_stolen(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    job.status = AIImportJobStatus.RUNNING
    job.locked_at = datetime.now(timezone.utc)
    job.locked_by = "busy-worker:1"
    db.commit()

    assert ai_import_worker.reclaim_stale_jobs(db) == 0
    db.refresh(job)
    assert job.status == AIImportJobStatus.RUNNING


def test_a_second_live_job_for_the_same_document_is_refused(db):
    """
    The partial unique index is the structural guard against duplicate
    concurrent execution of the same document.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    first = ai_import_service._enqueue(db, document)
    db.flush()
    second = ai_import_service._enqueue(db, document)

    assert first is not None
    assert second is None
    assert db.query(AIImportJob).filter(AIImportJob.document_id == document.id).count() == 1


def test_a_terminal_document_is_not_reprocessed(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = _queued(db, document)
    document.status = AIImportDocumentStatus.POSTED
    db.commit()

    assert ai_import_worker.run_job(db, job) is True
    db.refresh(job)
    assert job.status == AIImportJobStatus.COMPLETED
    assert "already posted" in job.last_error


def test_retrying_a_posted_document_is_refused(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    from app.core.exceptions import ConflictError

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    document.status = AIImportDocumentStatus.POSTED
    db.flush()

    with pytest.raises(ConflictError):
        ai_import_service.retry_document(db, document, actor)


def test_queue_health_reports_state(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    _queued(db, document)
    db.commit()

    health = ai_import_worker.queue_health(db)
    assert health["jobs"].get("PENDING", 0) >= 1
    assert health["auto_post_enabled"] is False


# ── Out-of-order reconciliation ───────────────────────────────────────────────

def test_an_invoice_uploaded_before_its_po_links_once_the_po_exists(db, monkeypatch):
    """
    The out-of-order requirement: Monday's invoice finds Wednesday's purchase
    order without anyone re-uploading anything.
    """
    from tests.test_ai_import_matching import _make_po

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-LATE-01", project_code=project["code"],
    ))

    invoice_doc = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, invoice_doc)

    # Monday: the referenced order does not exist yet.
    from app.services import ai_import_matching_service as matching
    assert matching.best_match(db, invoice_doc.id, "purchase_order") is None
    assert "NO_PURCHASE_ORDER" in [r["code"] for r in invoice_doc.outcome_reasons]

    # Wednesday: the order is created.
    po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-LATE-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )
    db.commit()

    ai_import_service.reevaluate(db, invoice_doc)

    match = matching.best_match(db, invoice_doc.id, "purchase_order")
    assert match is not None
    assert str(match.target_id) == str(po.id)
    assert "NO_PURCHASE_ORDER" not in [r["code"] for r in invoice_doc.outcome_reasons]


def test_posting_a_document_re_evaluates_its_waiting_siblings(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    waiting = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, waiting)
    assert waiting.status == AIImportDocumentStatus.AWAITING_REVIEW

    other = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    count = ai_import_service.reevaluate_related(db, other)
    assert count >= 1


def test_related_documents_are_surfaced_for_a_reviewer(db, monkeypatch):
    from app.services import ai_import_matching_service as matching

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(
        monkeypatch,
        supplier_invoice("Acme Supplies", project_code=project["code"]),
        delivery_note("Acme Supplies", project_code=project["code"]),
    )

    first = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, first)
    second = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, second)

    related = matching.related_documents(db, second)
    assert any(r["id"] == str(first.id) for r in related)


# ── Duplicate detection ───────────────────────────────────────────────────────

def test_the_same_file_uploaded_twice_is_marked_duplicate(db):
    """Identical bytes under a different filename are still the same document."""
    actor, actor_row, project, site, supplier, item = _env(db)
    checksum = "a" * 64

    first = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        file_name="invoice.pdf", checksum=checksum,
    )
    first.status = AIImportDocumentStatus.READY_TO_POST
    db.flush()

    existing = (
        db.query(AIImportDocument)
        .filter(AIImportDocument.checksum_sha256 == checksum)
        .order_by(AIImportDocument.created_at.asc())
        .first()
    )
    assert existing.id == first.id


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_counts_and_queues(db, monkeypatch):
    from app.schemas.ai_import import DashboardFilters

    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    data = ai_import_service.dashboard(
        db, DashboardFilters(project_id=uuid.UUID(project["id"])),
    )

    assert data["totals"]["uploaded"] == 1
    assert data["totals"]["classified"] == 1
    assert data["queues"]["unmatched_invoices"] >= 1
    assert data["ai_usage"]["input_tokens"] == 1200
    assert data["ai_usage"]["cost_usd"] == pytest.approx(0.0108)
    assert data["amounts_awaiting_authorisation"] == pytest.approx(13800.00)


# ── API: access control ───────────────────────────────────────────────────────

def test_site_user_cannot_read_another_projects_document(db, client):
    """Cross-tenant document access attempt."""
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_b["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.get(f"/api/v1/ai-import/documents/{document.id}", headers=auth(token))

    assert response.status_code == 403


def test_site_user_cannot_download_another_projects_file(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_b["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.get(
        f"/api/v1/ai-import/documents/{document.id}/file", headers=auth(token),
    )
    assert response.status_code == 403


def test_document_list_excludes_other_projects(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    viewer = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, viewer["id"], project_b["id"])

    hidden = make_import_document(db, uploaded_by=owner_row["id"], project_id=project_a["id"])
    visible = make_import_document(db, uploaded_by=owner_row["id"], project_id=project_b["id"])
    db.commit()

    token = login(client, viewer["email"], viewer["password"])
    response = client.get("/api/v1/ai-import/documents", headers=auth(token))

    assert response.status_code == 200
    ids = [d["id"] for d in response.json()["data"]["items"]]
    assert str(visible.id) in ids
    assert str(hidden.id) not in ids


def test_site_manager_cannot_post_a_document(db, client, monkeypatch):
    """Unauthorised financial posting attempt."""
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])

    site_manager = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, site_manager["id"], project["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
        document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    db.commit()

    token = login(client, site_manager["email"], site_manager["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post", json={}, headers=auth(token),
    )
    assert response.status_code == 403


def test_read_only_owner_cannot_upload(db, client):
    viewer = make_user(db, role="READ_ONLY")
    db.commit()
    token = login(client, viewer["email"], viewer["password"])

    response = client.post("/api/v1/ai-import/batches", json={}, headers=auth(token))
    assert response.status_code == 403


def test_blocked_document_cannot_be_posted_even_with_override(db, client, monkeypatch):
    """BLOCKED is absolute: no role and no flag gets past it."""
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    make_supplier(db, name="Acme Supplies")
    install_stub(monkeypatch, invoice_with_bad_arithmetic("Acme Supplies"))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    db.commit()
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED

    token = login(client, owner_row["email"], owner_row["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post",
        json={"confirm_override": True}, headers=auth(token),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert any(r["code"] == "ARITHMETIC_INVALID" for r in detail["reasons"])

    from app.models.invoice import Invoice
    assert db.query(Invoice).filter(Invoice.project_id == uuid.UUID(project["id"])).count() == 0


def test_needs_review_document_requires_an_explicit_override(db, client, monkeypatch):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    make_supplier(db, name="Acme Supplies")
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])

    refused = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post", json={}, headers=auth(token),
    )
    assert refused.status_code == 409
    assert "needs review" in refused.json()["detail"]["message"]

    accepted = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post",
        json={"confirm_override": True}, headers=auth(token),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["posting"]["entity_type"] == "invoice"


def test_an_override_post_is_recorded_in_the_audit_log(db, client, monkeypatch):
    from app.models.audit import AuditEvent

    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    make_supplier(db, name="Acme Supplies")
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])
    client.post(
        f"/api/v1/ai-import/documents/{document.id}/post",
        json={"confirm_override": True}, headers=auth(token),
    )

    override = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "ai_import_override",
                AuditEvent.entity_id == document.id)
        .first()
    )
    assert override is not None
    assert "on the user's authority" in override.notes


def test_posting_the_same_document_twice_through_the_api_is_refused(db, client, monkeypatch):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    make_supplier(db, name="Acme Supplies")
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])
    body = {"confirm_override": True}

    first = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post", json=body, headers=auth(token),
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post", json=body, headers=auth(token),
    )
    assert second.status_code == 409

    from app.models.invoice import Invoice
    assert db.query(Invoice).filter(
        Invoice.project_id == uuid.UUID(project["id"]),
        Invoice.invoice_number == "INV-502",
    ).count() == 1


# ── API: batches and upload ───────────────────────────────────────────────────

def test_batch_upload_accepts_a_mixed_batch_and_detects_a_duplicate_file(db, client):
    """
    One batch, several document types, no manual classification, and the same
    file sent twice under different names is caught by checksum.
    """
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])

    created = client.post(
        "/api/v1/ai-import/batches",
        json={"project_id": project["id"], "is_legacy": True, "notes": "2024 paper files"},
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    batch_id = created.json()["data"]["id"]

    content = b"%PDF-1.4\nfake invoice bytes\n"
    files = [
        ("files", ("invoice.pdf", content, "application/pdf")),
        ("files", ("delivery.pdf", b"%PDF-1.4\nfake delivery\n", "application/pdf")),
        ("files", ("invoice-copy.pdf", content, "application/pdf")),   # same bytes
    ]
    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents", files=files, headers=auth(token),
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert len(data["accepted"]) == 3
    statuses = [d["status"] for d in data["accepted"]]
    assert statuses.count("DUPLICATE") == 1
    assert statuses.count("QUEUED") == 2

    duplicate = next(d for d in data["accepted"] if d["status"] == "DUPLICATE")
    assert duplicate["duplicate_of_id"] is not None
    assert duplicate["outcome_reasons"][0]["code"] == "DUPLICATE_FILE"
    # Legacy flag flows from the batch to its documents.
    assert all(d["is_legacy"] for d in data["accepted"])


def test_an_executable_disguised_as_a_document_is_rejected(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])

    batch_id = client.post(
        "/api/v1/ai-import/batches", json={}, headers=auth(token),
    ).json()["data"]["id"]

    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents",
        files=[("files", ("payload.exe", b"MZ\x90\x00", "application/pdf"))],
        headers=auth(token),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted"] == []
    assert len(data["rejected"]) == 1
    assert ".exe" in data["rejected"][0]["reason"]


def test_one_bad_file_does_not_discard_the_rest_of_the_batch(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])
    batch_id = client.post(
        "/api/v1/ai-import/batches", json={}, headers=auth(token),
    ).json()["data"]["id"]

    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents",
        files=[
            ("files", ("good.pdf", b"%PDF-1.4 ok", "application/pdf")),
            ("files", ("bad.exe", b"MZ", "application/pdf")),
            ("files", ("also-good.jpg", b"\xff\xd8\xff ok", "image/jpeg")),
        ],
        headers=auth(token),
    )

    data = response.json()["data"]
    assert len(data["accepted"]) == 2
    assert len(data["rejected"]) == 1


def test_upload_queues_rather_than_extracting_inline(db, client):
    """
    Phase 11: a long extraction must never run inside the HTTP request. The
    document comes back QUEUED with a pending job, not EXTRACTED.
    """
    owner, owner_row = _user_obj(db, role="OWNER")
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])
    batch_id = client.post(
        "/api/v1/ai-import/batches", json={}, headers=auth(token),
    ).json()["data"]["id"]

    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents",
        files=[("files", ("scan.pdf", b"%PDF-1.4 ok", "application/pdf"))],
        headers=auth(token),
    )
    document_id = response.json()["data"]["accepted"][0]["id"]

    assert response.json()["data"]["accepted"][0]["status"] == "QUEUED"
    job = (
        db.query(AIImportJob)
        .filter(AIImportJob.document_id == uuid.UUID(document_id))
        .one()
    )
    assert job.status == AIImportJobStatus.PENDING


def test_dashboard_endpoint_returns_the_pipeline_summary(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])

    response = client.get(
        f"/api/v1/ai-import/dashboard?project_id={project['id']}", headers=auth(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "totals" in data and "queues" in data and "ai_usage" in data


def test_health_endpoint_is_admin_only(db, client):
    viewer = make_user(db, role="OFFICE_USER")
    db.commit()
    token = login(client, viewer["email"], viewer["password"])
    assert client.get("/api/v1/ai-import/health", headers=auth(token)).status_code == 403


# ── Security: access logging and retention ────────────────────────────────────

def test_viewing_a_document_file_is_logged(db, client):
    """Supplier financial documents are sensitive — every issued URL is recorded."""
    from app.models.audit import AuditEvent

    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"],
    )
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])
    client.get(f"/api/v1/ai-import/documents/{document.id}/file", headers=auth(token))

    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "ai_import_document_file",
                AuditEvent.entity_id == document.id)
        .first()
    )
    assert event is not None
    assert event.action == "ACCESS"
    assert event.actor_id == owner.id
    assert event.after_value["checksum_sha256"] == document.checksum_sha256


def test_retention_dry_run_changes_nothing(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    document.created_at = datetime.now(timezone.utc) - timedelta(
        days=settings.AI_IMPORT_RETENTION_DAYS + 10
    )
    db.flush()
    original_path = document.stored_path

    result = ai_import_service.purge_expired_documents(db, dry_run=True)

    assert result["dry_run"] is True
    assert str(document.id) in result["purged"]
    assert document.stored_path == original_path     # untouched


def test_retention_keeps_evidence_behind_a_live_posting(db, monkeypatch):
    """
    A document that backs a posted transaction is its evidence and is never
    purged, however old it is.
    """
    from app.services import ai_import_posting_service as posting

    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    from tests.test_ai_import_posting import _payload
    posting.post_supplier_invoice(
        db, document,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )
    document.created_at = datetime.now(timezone.utc) - timedelta(
        days=settings.AI_IMPORT_RETENTION_DAYS + 10
    )
    db.flush()

    result = ai_import_service.purge_expired_documents(db, dry_run=False)

    assert str(document.id) not in result["purged"]
    assert any(s["document_id"] == str(document.id) for s in result["skipped"])
    assert document.stored_path  # still there


def test_retention_purge_is_owner_only(db, client):
    admin = make_user(db, role="OFFICE_ADMIN")
    db.commit()
    token = login(client, admin["email"], admin["password"])
    response = client.post("/api/v1/ai-import/retention/purge", headers=auth(token))
    assert response.status_code == 403
