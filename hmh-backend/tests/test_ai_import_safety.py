"""
AI Document Import — the safety properties, tested adversarially.

Every test here corresponds to a defect found during independent verification.
They assert the property directly rather than the implementation's shape, so
they fail if the guarantee regresses regardless of how the code is rearranged.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ValidationError
from app.models.ai_import import AIImportMatch, AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportJobStatus,
    AIImportProcessingOutcome,
    DeliveryDestination,
)
from app.services import ai_import_posting_service as posting
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
    install_stub,
    make_import_document,
    supplier_invoice,
)
from tests.test_ai_import_matching import _make_po
from tests.test_ai_import_posting import _ledger_total, _payload


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


# ── A failure after the domain service commits must block any retry ──────────

def test_a_failure_after_the_domain_service_commits_blocks_any_retry(db, monkeypatch):
    """
    create_delivery commits the stock ledger and then keeps working. If it
    raises after that commit, the claim must stand — otherwise a retry
    receives the same delivery a second time.
    """
    from app.services import delivery_service

    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=100, project_code=project["code"]))

    real_create = delivery_service.create_delivery

    def commit_then_explode(*args, **kwargs):
        real_create(*args, **kwargs)                      # commits the ledger
        raise RuntimeError("connection reset after commit")

    monkeypatch.setattr(delivery_service, "create_delivery", commit_then_explode)

    with pytest.raises(RuntimeError):
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )

    after_first = _ledger_total(db, project["id"], item["id"])
    assert after_first == 100.0, "the domain service did commit the stock"

    claim = (
        db.query(AIImportPosting)
        .filter(AIImportPosting.document_id == document.id)
        .one()
    )
    assert claim.reversed_at is None
    assert claim.entity_id is None            # unfinished, needs verification

    monkeypatch.setattr(delivery_service, "create_delivery", real_create)
    with pytest.raises(posting.AlreadyPosted) as exc:
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )
    # The claim was taken seconds ago, so it reads as in flight. What matters
    # is that the retry is refused and the ledger is untouched.
    assert "right now" in str(exc.value)

    assert _ledger_total(db, project["id"], item["id"]) == after_first, \
        "a retry must not create a second stock movement"


def test_an_unfinished_claim_is_surfaced_for_verification(db, monkeypatch):
    from app.services import invoice_service

    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    real_create = invoice_service.create_invoice

    def commit_then_explode(*args, **kwargs):
        real_create(*args, **kwargs)
        raise RuntimeError("timed out after commit")

    monkeypatch.setattr(invoice_service, "create_invoice", commit_then_explode)
    with pytest.raises(RuntimeError):
        posting.post_supplier_invoice(
            db, document,
            _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
            actor,
        )

    unfinished = posting.incomplete_postings(db)
    assert any(p.document_id == document.id for p in unfinished)


# ── The idempotency key must never be varied ─────────────────────────────────

def test_a_reversed_posting_does_not_mint_a_new_key(db):
    """
    Minting a fresh key after a reversal would let two concurrent requests
    both insert. One posting per document per entity type, permanently.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    result = posting.post_supplier_invoice(
        db, document,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )
    result.reversed_at = datetime.now(timezone.utc)
    db.commit()

    with pytest.raises(posting.AlreadyPosted) as exc:
        posting._claim(db, document, "invoice", actor.id)
    assert "reversed" in str(exc.value)

    assert db.query(AIImportPosting).filter(
        AIImportPosting.document_id == document.id,
        AIImportPosting.entity_type == "invoice",
    ).count() == 1


# ── Manual matching must not cross the project boundary ──────────────────────

def test_manual_match_rejects_an_unknown_target_type(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    with pytest.raises(ValidationError) as exc:
        ai_import_service.add_manual_match(
            db, document, "not_a_real_type", uuid.uuid4(), actor,
        )
    assert "cannot be linked by hand" in str(exc.value)


def test_manual_match_cannot_move_a_document_into_another_project(db, client):
    """
    target_type="project" previously relocated the document, bypassing the
    access check that PATCH /context performs.
    """
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_a["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/matches",
        json={"target_type": "project", "target_id": project_b["id"]},
        headers=auth(token),
    )

    assert response.status_code == 422
    db.refresh(document)
    assert str(document.project_id) == project_a["id"]


def test_manual_match_to_another_projects_purchase_order_is_refused(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])
    supplier = make_supplier(db)

    foreign_po = _make_po(db, project_b["id"], supplier["id"], owner_row["id"])
    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/matches",
        json={"target_type": "purchase_order", "target_id": str(foreign_po.id)},
        headers=auth(token),
    )

    assert response.status_code == 422
    # HMHException responses use the app's {success, message, code} envelope,
    # not FastAPI's "detail".
    assert "different project" in response.json()["message"]


def test_a_site_user_cannot_link_to_a_record_they_cannot_see(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])
    supplier = make_supplier(db)
    foreign_po = _make_po(db, project_b["id"], supplier["id"], owner_row["id"])

    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_a["id"])
    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/matches",
        json={"target_type": "purchase_order", "target_id": str(foreign_po.id)},
        headers=auth(token),
    )
    assert response.status_code in (403, 422)


def test_a_document_without_a_project_cannot_be_linked(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    po = _make_po(db, project["id"], supplier["id"], actor_row["id"])
    document = make_import_document(db, uploaded_by=actor_row["id"])   # no project

    with pytest.raises(ValidationError) as exc:
        ai_import_service.add_manual_match(db, document, "purchase_order", po.id, actor)
    assert "project" in str(exc.value).lower()


# ── The dashboard must be scoped to the caller ───────────────────────────────

def test_dashboard_without_a_project_filter_is_still_scoped_to_the_caller(db, client):
    """
    Omitting project_id previously returned company-wide counts, including the
    total invoice value awaiting authorisation, to any viewer.
    """
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    viewer = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, viewer["id"], project_a["id"])

    make_import_document(db, uploaded_by=owner_row["id"], project_id=project_b["id"])
    db.commit()

    token = login(client, viewer["email"], viewer["password"])
    response = client.get("/api/v1/ai-import/dashboard", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["totals"]["uploaded"] == 0


def test_dashboard_shows_a_site_user_their_own_projects(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    viewer = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, viewer["id"], project["id"])
    make_import_document(db, uploaded_by=owner_row["id"], project_id=project["id"])
    db.commit()

    token = login(client, viewer["email"], viewer["password"])
    response = client.get("/api/v1/ai-import/dashboard", headers=auth(token))
    assert response.json()["data"]["totals"]["uploaded"] == 1


def test_batch_list_is_filtered_in_sql_not_truncated_afterwards(db, client):
    """A short page must mean "no more", not "the rest were filtered out"."""
    owner, owner_row = _user_obj(db, role="OWNER")
    mine = make_project(db, owner_row["id"])
    theirs = make_project(db, owner_row["id"])

    viewer = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, viewer["id"], mine["id"])

    for _ in range(6):
        make_import_document(db, uploaded_by=owner_row["id"], project_id=theirs["id"])
    for _ in range(3):
        make_import_document(db, uploaded_by=owner_row["id"], project_id=mine["id"])
    db.commit()

    token = login(client, viewer["email"], viewer["password"])
    response = client.get("/api/v1/ai-import/batches?limit=3", headers=auth(token))

    assert response.status_code == 200
    batches = response.json()["data"]
    assert len(batches) == 3                      # a full page of visible batches
    assert {b["project_id"] for b in batches} == {mine["id"]}


# ── A failed job must not leave half-processed state ─────────────────────────

def test_a_failed_job_does_not_destroy_the_documents_existing_matches(db, monkeypatch):
    """
    rematch_document deletes the proposed matches before rebuilding them. A
    failure after that point must roll back, not commit the deletion.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    matches_before = (
        db.query(AIImportMatch).filter(AIImportMatch.document_id == document.id).count()
    )
    assert matches_before > 0

    def boom(*args, **kwargs):
        raise RuntimeError("policy blew up after the matches were rebuilt")

    monkeypatch.setattr(ai_import_service.policy, "evaluate", boom)

    job = ai_import_service._enqueue(db, document)
    db.commit()
    ai_import_worker.run_job(db, job)

    matches_after = (
        db.query(AIImportMatch).filter(AIImportMatch.document_id == document.id).count()
    )
    assert matches_after == matches_before, \
        "a failed run must not leave the document with its matches deleted"


# ── The cross-project and supplier-conflict rules must actually fire ─────────

def test_a_reference_to_another_projects_po_blocks_the_document(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    other_project = make_project(db, actor_row["id"])
    _make_po(
        db, other_project["id"], supplier["id"], actor_row["id"], po_number="PO-FOREIGN-01",
    )

    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-FOREIGN-01", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "CROSS_TENANT_REFERENCE" in codes, document.outcome_reasons
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED


def test_a_reference_to_another_suppliers_po_blocks_the_document(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    other_supplier = make_supplier(db, name="Beta Trading")
    _make_po(
        db, project["id"], other_supplier["id"], actor_row["id"], po_number="PO-OTHERSUP-01",
    )

    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-OTHERSUP-01", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    codes = [r["code"] for r in document.outcome_reasons]
    assert "CONFLICTING_SUPPLIER" in codes, document.outcome_reasons
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED


def test_correcting_a_bad_reference_clears_the_conflict_block(db, monkeypatch):
    """
    Conflict rows are stored as REJECTED, which the normal rematch cleanup
    skips. If they were not cleared explicitly, fixing the reference would
    leave the document blocked forever.
    """
    from app.schemas.ai_import import FieldCorrection

    actor, actor_row, project, site, supplier, item = _env(db)
    other_project = make_project(db, actor_row["id"])
    _make_po(
        db, other_project["id"], supplier["id"], actor_row["id"], po_number="PO-TYPO-01",
    )
    good_po = _make_po(
        db, project["id"], supplier["id"], actor_row["id"], po_number="PO-CORRECT-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )

    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-TYPO-01", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    assert "CROSS_TENANT_REFERENCE" in [r["code"] for r in document.outcome_reasons]

    ai_import_service.apply_corrections(
        db, document,
        [FieldCorrection(field_path="purchase_order_reference", value="PO-CORRECT-01",
                         reason="misread digit")],
        actor,
    )

    codes = [r["code"] for r in document.outcome_reasons]
    assert "CROSS_TENANT_REFERENCE" not in codes, document.outcome_reasons
    assert db.query(AIImportMatch).filter(
        AIImportMatch.document_id == document.id,
        AIImportMatch.target_type == "purchase_order_conflict",
    ).count() == 0

    from app.services import ai_import_matching_service as matching
    match = matching.best_match(db, document.id, "purchase_order")
    assert match is not None and str(match.target_id) == str(good_po.id)


# ── Auto-post must respect the posting role ──────────────────────────────────

def test_auto_post_will_not_post_for_a_user_who_may_not_post(db, monkeypatch):
    from app.core.config import settings as _settings

    uploader = make_user(db, role="SITE_MANAGER")
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    _make_po(
        db, project["id"], supplier["id"], owner_row["id"], po_number="PO-AUTO-01",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )

    monkeypatch.setattr(_settings, "AI_IMPORT_AUTO_POST_ENABLED", True)
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-AUTO-01", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=uploader["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert document.postings == []
    assert document.status != AIImportDocumentStatus.POSTED
    assert "AUTO_POST_ROLE_REQUIRED" in [r["code"] for r in document.outcome_reasons]


def test_auto_post_proceeds_for_a_user_who_may_post(db, monkeypatch):
    """The role gate must not block the case it is meant to allow."""
    from app.core.config import settings as _settings

    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    _make_po(
        db, project["id"], supplier["id"], owner_row["id"], po_number="PO-AUTO-02",
        total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 100}],
    )

    monkeypatch.setattr(_settings, "AI_IMPORT_AUTO_POST_ENABLED", True)
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-AUTO-02", project_code=project["code"],
    ))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    assert document.status == AIImportDocumentStatus.POSTED
    assert len(document.postings) == 1


# ── The legacy authorisation note must be recorded ───────────────────────────

def test_posting_a_legacy_document_requires_the_authorisation_note(db, client, monkeypatch):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    site = make_site(db, project["id"])
    make_supplier(db, name="Acme Supplies")
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"], site_id=site["id"],
        is_legacy=True,
    )
    ai_import_service.process_document(db, document)
    db.commit()

    token = login(client, owner_row["email"], owner_row["password"])

    refused = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post",
        json={"confirm_override": True}, headers=auth(token),
    )
    assert refused.status_code == 422
    assert "legacy_authorisation_note" in str(refused.json()["detail"])

    accepted = client.post(
        f"/api/v1/ai-import/documents/{document.id}/post",
        json={
            "confirm_override": True,
            "legacy_authorisation_note": "Signed original in the 2024 invoice file, box 3.",
        },
        headers=auth(token),
    )
    assert accepted.status_code == 200, accepted.text

    db.refresh(document)
    assert document.authorised_by == owner.id

    from app.models.audit import AuditEvent
    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "ai_import_document",
                AuditEvent.entity_id == document.id,
                AuditEvent.action == "APPROVE")
        .first()
    )
    assert event is not None
    assert "box 3" in event.after_value["legacy_authorisation_note"]


# ── Reclaim must preserve the dead worker's identity ─────────────────────────

def test_reclaiming_a_job_records_which_worker_died(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    job = ai_import_service._enqueue(db, document)
    job.status = AIImportJobStatus.RUNNING
    job.locked_by = "dead-host:1234"
    job.locked_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()

    ai_import_worker.reclaim_stale_jobs(db)

    db.refresh(job)
    assert "dead-host:1234" in job.last_error
