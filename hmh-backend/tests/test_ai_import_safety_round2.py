"""
AI Document Import — safety properties, second verification round.

One test per defect found in the second independent review. Each asserts the
property rather than the implementation, so it still fails if the guarantee
regresses after a refactor.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.ai_import import AIImportMatch, AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportMatchStatus,
    AIImportProcessingOutcome,
    DeliveryDestination,
    RecordStatus,
)
from app.schemas.ai_import import FieldCorrection
from app.services import ai_import_matching_service as matching
from app.services import ai_import_posting_service as posting
from app.services import ai_import_service
from tests.conftest import (
    auth, login, make_item, make_project, make_site, make_supplier, make_user,
    make_user_project_access,
)
from tests.ai_import_fixtures import (
    delivery_note, field, install_stub, make_import_document, supplier_invoice,
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


def _existing_invoice(db, project, supplier, number):
    from app.models.invoice import Invoice
    now = datetime.now(timezone.utc)
    inv = Invoice(
        invoice_number=number,
        supplier_id=uuid.UUID(supplier["id"]),
        project_id=uuid.UUID(project["id"]),
        total_amount=13800.00,
        status=RecordStatus.DRAFT,
        captured_at=now, created_at=now, updated_at=now,
    )
    db.add(inv)
    db.flush()
    return inv


# ── D1: machine-generated matches must not survive a rematch ─────────────────

def test_correcting_a_misread_invoice_number_clears_the_duplicate_block(db, monkeypatch):
    """
    A duplicate-invoice match is recorded CONFIRMED with decided_by NULL. If
    it survived the rematch, fixing the misread number would leave the
    document BLOCKED forever, and BLOCKED cannot be overridden by anyone.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    _existing_invoice(db, project, supplier, "INV-999")

    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", invoice_number="INV-999", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    assert "DUPLICATE_INVOICE_NUMBER" in [r["code"] for r in document.outcome_reasons]
    assert document.processing_outcome == AIImportProcessingOutcome.BLOCKED

    ai_import_service.apply_corrections(
        db, document,
        [FieldCorrection(field_path="document_number", value="INV-BRAND-NEW",
                         reason="misread digit")],
        actor,
    )

    codes = [r["code"] for r in document.outcome_reasons]
    assert "DUPLICATE_INVOICE_NUMBER" not in codes, document.outcome_reasons
    assert document.processing_outcome != AIImportProcessingOutcome.BLOCKED


def test_correcting_a_po_reference_does_not_leave_the_old_order_matched(db, monkeypatch):
    """
    Two CONFIRMED order matches would let best_match return the superseded
    one, booking the receipt against the wrong purchase order.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    wrong = _make_po(db, project["id"], supplier["id"], actor_row["id"], po_number="PO-WRONG-0001")
    right = _make_po(db, project["id"], supplier["id"], actor_row["id"], po_number="PO-RIGHT-0002")

    install_stub(monkeypatch, delivery_note(
        "Acme Supplies", po_reference="PO-WRONG-0001", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    ai_import_service.apply_corrections(
        db, document,
        [FieldCorrection(field_path="purchase_order_reference", value="PO-RIGHT-0002")],
        actor,
    )

    rows = (
        db.query(AIImportMatch)
        .filter(AIImportMatch.document_id == document.id,
                AIImportMatch.target_type == "purchase_order")
        .all()
    )
    assert len(rows) == 1, [(r.status.value, r.target_label) for r in rows]
    assert str(matching.best_match(db, document.id, "purchase_order").target_id) == str(right.id)
    assert str(rows[0].target_id) != str(wrong.id)


def test_repeated_re_evaluation_does_not_accumulate_matches(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    _make_po(db, project["id"], supplier["id"], actor_row["id"], po_number="PO-STABLE-01")
    install_stub(monkeypatch, supplier_invoice(
        "Acme Supplies", po_reference="PO-STABLE-01", project_code=project["code"],
    ))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    first = db.query(AIImportMatch).filter(AIImportMatch.document_id == document.id).count()

    for _ in range(3):
        ai_import_service.reevaluate(db, document)

    after = db.query(AIImportMatch).filter(AIImportMatch.document_id == document.id).count()
    assert after == first, "match rows accumulated across re-evaluations"


def test_a_human_decision_still_survives_the_rematch(db, monkeypatch):
    """The broader cleanup must not start discarding human decisions."""
    actor, actor_row, project, site, supplier, item = _env(db)
    chosen = make_supplier(db, name="Chosen By A Person")
    install_stub(monkeypatch, supplier_invoice("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)

    from app.schemas.ai_import import ContextAssignment
    ai_import_service.assign_context(
        db, document, ContextAssignment(supplier_id=uuid.UUID(chosen["id"])), actor,
    )
    ai_import_service.reevaluate(db, document)

    assert str(document.supplier_id) == chosen["id"]


# ── D2: an interrupted posting must be resolvable ────────────────────────────

def _interrupt_invoice_post(db, monkeypatch, document, project, actor):
    from app.services import invoice_service
    real = invoice_service.create_invoice

    def explode(*args, **kwargs):
        raise RuntimeError("process died after the claim was taken")

    monkeypatch.setattr(invoice_service, "create_invoice", explode)
    with pytest.raises(RuntimeError):
        posting.post_supplier_invoice(
            db, document,
            _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
            actor,
        )
    monkeypatch.setattr(invoice_service, "create_invoice", real)
    return db.query(AIImportPosting).filter(
        AIImportPosting.document_id == document.id
    ).one()


def test_an_interrupted_posting_can_be_discarded_and_then_posted_properly(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    claim = _interrupt_invoice_post(db, monkeypatch, document, project, actor)
    assert claim.entity_id is None

    # Blocked until resolved.
    with pytest.raises(posting.AlreadyPosted):
        posting.post_supplier_invoice(
            db, document,
            _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
            actor,
        )

    posting.resolve_incomplete_posting(
        db, claim.id, "discard", actor,
        note="Checked the invoice list for this project; nothing was created.",
    )

    # The claim is gone and a proper post now succeeds exactly once.
    assert db.query(AIImportPosting).filter(
        AIImportPosting.document_id == document.id
    ).count() == 0

    result = posting.post_supplier_invoice(
        db, document,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )
    assert result.entity_id is not None

    from app.models.invoice import Invoice
    assert db.query(Invoice).filter(
        Invoice.supplier_id == uuid.UUID(supplier["id"]),
        Invoice.invoice_number == "INV-502",
    ).count() == 1


def test_an_interrupted_posting_can_be_linked_to_the_record_that_was_created(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    claim = _interrupt_invoice_post(db, monkeypatch, document, project, actor)

    # The operator finds the record really was created.
    existing = _existing_invoice(db, project, supplier, "INV-502")

    resolved = posting.resolve_incomplete_posting(
        db, claim.id, "link", actor,
        note="Found INV-502 in the invoice list; it was created.",
        entity_id=existing.id,
    )

    assert resolved.entity_id == existing.id
    assert resolved.entity_label == "INV-502"
    db.refresh(document)
    assert document.status == AIImportDocumentStatus.POSTED


def test_resolution_refuses_to_claim_a_record_another_document_already_owns(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)

    first = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    posted = posting.post_supplier_invoice(
        db, first,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )

    second = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
        file_name="another-scan.pdf",
    )
    claim = _interrupt_invoice_post(db, monkeypatch, second, project, actor)

    with pytest.raises(ConflictError) as exc:
        posting.resolve_incomplete_posting(
            db, claim.id, "link", actor, note="trying to reuse it",
            entity_id=posted.entity_id,
        )
    assert "already recorded against" in str(exc.value)


def test_resolution_requires_a_note_and_rejects_a_missing_record(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    claim = _interrupt_invoice_post(db, monkeypatch, document, project, actor)

    with pytest.raises(ValidationError):
        posting.resolve_incomplete_posting(db, claim.id, "discard", actor, note="")

    with pytest.raises(NotFoundError):
        posting.resolve_incomplete_posting(
            db, claim.id, "link", actor, note="pointing at nothing",
            entity_id=uuid.uuid4(),
        )


def test_incomplete_postings_are_listed_with_what_to_do(db, monkeypatch, client):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    _interrupt_invoice_post(db, monkeypatch, document, project, actor)
    db.commit()

    token = login(client, actor_row["email"], actor_row["password"])
    response = client.get("/api/v1/ai-import/postings/incomplete", headers=auth(token))

    assert response.status_code == 200
    rows = response.json()["data"]
    mine = next(r for r in rows if r["document_id"] == str(document.id))
    assert mine["entity_type"] == "invoice"
    assert "resolve as" in mine["what_to_do"]


# ── D3: no claim may be released after a domain service has committed ────────

def test_create_delivery_never_raises_after_committing(db):
    """
    The claim is released only for exceptions a domain service raises before
    writing. create_delivery used to re-query after commit and could raise
    NotFoundError — a pre-write error type — which would have released the
    claim with the stock already moved.
    """
    import inspect

    from app.services import delivery_service

    source = inspect.getsource(delivery_service.create_delivery)
    after_commit = source.rsplit("db.commit()", 1)[1]
    assert "_get_delivery_or_404" not in after_commit, (
        "create_delivery re-queries with a raising helper after committing"
    )


def test_a_pre_write_error_raised_after_commit_still_blocks_a_retry(db, monkeypatch):
    """
    Belt and braces: even if a domain service were changed to raise a
    pre-write error type after committing, the ledger must not be doubled by
    a retry. This documents the invariant the posting layer depends on.
    """
    from app.services import delivery_service

    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.DELIVERY_NOTE,
    )
    payload = _payload(delivery_note("Acme Supplies", quantity=100, project_code=project["code"]))

    real = delivery_service.create_delivery

    def commit_then_raise_pre_write(*args, **kwargs):
        real(*args, **kwargs)
        raise NotFoundError("a pre-write error type raised after the commit")

    monkeypatch.setattr(delivery_service, "create_delivery", commit_then_raise_pre_write)
    with pytest.raises(NotFoundError):
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )
    after_first = _ledger_total(db, project["id"], item["id"])
    assert after_first == 100.0

    monkeypatch.setattr(delivery_service, "create_delivery", real)
    try:
        posting.post_goods_receipt(
            db, document, payload, actor, destination=DeliveryDestination.SITE_STORE,
        )
    except posting.AlreadyPosted:
        pass
    assert _ledger_total(db, project["id"], item["id"]) == after_first, (
        "a retry doubled the stock after a post-commit failure"
    )


# ── D4: accepting a match must not move a document out of reach ──────────────

def test_accepting_a_cross_project_match_is_refused(db, client):
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])

    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_a["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    match = AIImportMatch(
        document_id=document.id, target_type="project",
        target_id=uuid.UUID(project_b["id"]), target_label="Project B",
        status=AIImportMatchStatus.PROPOSED, method="project_fuzzy",
        created_at=datetime.now(timezone.utc),
    )
    db.add(match)
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/matches/decide",
        json={"match_id": str(match.id), "accept": True},
        headers=auth(token),
    )

    assert response.status_code == 403
    db.refresh(document)
    assert str(document.project_id) == project_a["id"]


def test_rejecting_a_cross_project_match_is_still_allowed(db, client):
    """Rejecting moves nothing, so it must not be blocked."""
    owner, owner_row = _user_obj(db, role="OWNER")
    project_a = make_project(db, owner_row["id"])
    project_b = make_project(db, owner_row["id"])
    intruder = make_user(db, role="SITE_MANAGER")
    make_user_project_access(db, intruder["id"], project_a["id"])

    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project_a["id"],
    )
    match = AIImportMatch(
        document_id=document.id, target_type="project",
        target_id=uuid.UUID(project_b["id"]), status=AIImportMatchStatus.PROPOSED,
        method="project_fuzzy", created_at=datetime.now(timezone.utc),
    )
    db.add(match)
    db.commit()

    token = login(client, intruder["email"], intruder["password"])
    response = client.post(
        f"/api/v1/ai-import/documents/{document.id}/matches/decide",
        json={"match_id": str(match.id), "accept": False},
        headers=auth(token),
    )
    assert response.status_code == 200


# ── D5: an unclassified document must not list other projects' files ─────────

def test_related_documents_does_not_leak_across_projects_without_a_project(db):
    owner, owner_row = _user_obj(db, role="OWNER")
    other_project = make_project(db, owner_row["id"])
    supplier = make_supplier(db, name="Shared Supplier")
    other_uploader = make_user(db, role="OFFICE_USER")

    secret = make_import_document(
        db, uploaded_by=other_uploader["id"], project_id=other_project["id"],
        supplier_id=supplier["id"], file_name="other_project_invoice.pdf",
    )
    unclassified = make_import_document(
        db, uploaded_by=owner_row["id"], supplier_id=supplier["id"],
        file_name="unclassified.pdf",
    )
    db.flush()

    related = matching.related_documents(db, unclassified)
    assert all(r["id"] != str(secret.id) for r in related), related


# ── D6: a legacy stock import must warn about double counting ────────────────

def test_a_legacy_delivery_warns_that_stock_may_already_be_counted(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, delivery_note("Acme Supplies", project_code=project["code"]))

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        is_legacy=True,
    )
    ai_import_service.process_document(db, document)

    reasons = {r["code"]: r["message"] for r in document.outcome_reasons}
    assert "LEGACY_STOCK_DOUBLE_COUNT_RISK" in reasons
    assert "opening balance" in reasons["LEGACY_STOCK_DOUBLE_COUNT_RISK"]


def test_a_current_delivery_carries_no_legacy_stock_warning(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    install_stub(monkeypatch, delivery_note("Acme Supplies", project_code=project["code"]))
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.process_document(db, document)
    assert "LEGACY_STOCK_DOUBLE_COUNT_RISK" not in [r["code"] for r in document.outcome_reasons]


# ── D7: rejection is guarded like every other mutating path ──────────────────

def test_an_already_rejected_document_cannot_be_rejected_again(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
    )
    ai_import_service.reject_document(db, document, "not ours", actor)

    with pytest.raises(ConflictError):
        ai_import_service.reject_document(db, document, "again", actor)


def test_rejecting_every_copy_cannot_hide_a_posted_original(db, monkeypatch):
    """
    A rejected document stops anchoring duplicate detection, which is correct
    only while nothing was posted. A posted original must keep anchoring.
    """
    actor, actor_row, project, site, supplier, item = _env(db)
    checksum = "c" * 64

    original = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
        checksum=checksum,
    )
    posting.post_document(
        db, original,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )
    assert original.status == AIImportDocumentStatus.POSTED

    # A posted document can never be rejected, so it still anchors.
    with pytest.raises(ConflictError):
        ai_import_service.reject_document(db, original, "trying to clear the anchor", actor)

    from app.models.ai_import import AIImportDocument
    anchor = (
        db.query(AIImportDocument)
        .filter(AIImportDocument.checksum_sha256 == checksum,
                AIImportDocument.status != AIImportDocumentStatus.REJECTED)
        .first()
    )
    assert anchor is not None and anchor.id == original.id


# ── D8: a stale site must not reach another project's records ────────────────

def test_a_site_from_another_project_is_dropped_before_posting(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    other_project = make_project(db, actor_row["id"])
    foreign_site = make_site(db, other_project["id"], name="Foreign Site")

    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    # Simulate the stranded-site case: project changed, site left behind.
    document.site_id = uuid.UUID(foreign_site["id"])
    db.flush()

    result = posting.post_supplier_invoice(
        db, document,
        _payload(supplier_invoice("Acme Supplies", project_code=project["code"])),
        actor,
    )

    from app.models.invoice import Invoice
    invoice = db.get(Invoice, result.entity_id)
    assert invoice.project_id == uuid.UUID(project["id"])
    assert invoice.site_id is None, "a site from another project was written onto the invoice"


def test_a_site_in_the_same_project_is_kept(db):
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
    from app.models.invoice import Invoice
    assert db.get(Invoice, result.entity_id).site_id == uuid.UUID(site["id"])


# ── D9: a post in flight is described as such ────────────────────────────────

def test_a_claim_taken_moments_ago_reads_as_in_flight(db, monkeypatch):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    posting._claim(db, document, "invoice", actor.id)

    with pytest.raises(posting.AlreadyPosted) as exc:
        posting._claim(db, document, "invoice", actor.id)
    assert "right now" in str(exc.value)


def test_an_old_unfinished_claim_reads_as_abandoned(db):
    actor, actor_row, project, site, supplier, item = _env(db)
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"], site_id=site["id"],
        supplier_id=supplier["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    claim = posting._claim(db, document, "invoice", actor.id)
    claim.posted_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db.commit()

    with pytest.raises(posting.AlreadyPosted) as exc:
        posting._claim(db, document, "invoice", actor.id)
    message = str(exc.value)
    assert "did not finish" in message
    assert "incomplete postings" in message
