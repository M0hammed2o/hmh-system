"""
AI Document Import API.

Upload scanned or digital procurement paperwork, let the engine read and
reconcile it, review what it found, and post the authorised result through
the existing domain services.

Access control:
  * Uploading and reviewing: office roles and site managers.
  * Posting, authorising legacy imports and rejecting: office admin and above.
  * Every project-scoped read and write re-checks `check_project_access`, so a
    site user never sees or posts another project's documents.
  * Original files are private; they are only reachable through
    GET /ai-import/documents/{id}/file, which issues a short-lived signed URL
    after the access check.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import false as sa_false

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.dependencies import (
    OFFICE_ADMIN_AND_ABOVE,
    OWNER_ONLY,
    CurrentUser,
    DbSession,
    check_project_access,
    require_roles,
)
from app.models.ai_import import AIImportBatch, AIImportDocument
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    DeliveryDestination,
    UserRole,
)
from app.schemas.ai_import import (
    BatchCreate,
    ContextAssignment,
    CorrectionRequest,
    DashboardFilters,
    ManualMatchCreate,
    MatchDecision,
    PostRequest,
    PostingResolution,
    RejectRequest,
)
from app.schemas.common import ApiSuccess
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_receiving_service
from app.services import ai_import_matching_service as matching
from app.services import ai_import_routing_service as routing
from app.services import ai_import_policy_service as policy
from app.services import ai_import_posting_service as posting_service
from app.services import ai_import_posting_service as ai_import_posting_service
from app.services import ai_import_service, ai_import_worker

router = APIRouter(prefix="/ai-import", tags=["ai-document-import"])

# Who may work in the module at all. READ_ONLY and view-only site managers are
# excluded from writes but may read via IMPORT_VIEWERS below.
IMPORT_USERS = require_roles(
    UserRole.OWNER,
    UserRole.OFFICE_ADMIN,
    UserRole.OFFICE_USER,
    UserRole.PROCUREMENT_LEAD,
    UserRole.SITE_MANAGER,
)
IMPORT_VIEWERS = require_roles(
    UserRole.OWNER,
    UserRole.OFFICE_ADMIN,
    UserRole.OFFICE_USER,
    UserRole.PROCUREMENT_LEAD,
    UserRole.SITE_MANAGER,
    UserRole.SITE_MANAGER_VIEW,
    UserRole.READ_ONLY,
)


# ── Access helpers ────────────────────────────────────────────────────────────

def _assert_document_access(db, user, document: AIImportDocument) -> None:
    """
    Enforce project isolation on a document.

    A document whose project is not yet resolved is visible only to the
    uploader and to office-level roles, so an unclassified upload cannot leak
    across projects before it is identified.
    """
    if document.project_id:
        check_project_access(db, user, document.project_id)
        return
    office_roles = {
        UserRole.OWNER, UserRole.OFFICE_ADMIN, UserRole.OFFICE_USER,
        UserRole.PROCUREMENT_LEAD, UserRole.READ_ONLY,
    }
    if user.role in office_roles or document.uploaded_by == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This document has not been assigned to a project you have access to.",
    )


def _assert_batch_access(db, user, batch: AIImportBatch) -> None:
    if batch.project_id:
        check_project_access(db, user, batch.project_id)
        return
    office_roles = {
        UserRole.OWNER, UserRole.OFFICE_ADMIN, UserRole.OFFICE_USER,
        UserRole.PROCUREMENT_LEAD, UserRole.READ_ONLY,
    }
    if user.role in office_roles or batch.uploaded_by == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this import batch.",
    )


def _visible_documents(db, user):
    """
    Base query restricted to the projects this user may see.

    Shares `visible_project_ids` with the dashboard so the two can never drift
    apart — which is exactly how an unscoped dashboard happens.
    """
    query = db.query(AIImportDocument)
    allowed = ai_import_service.visible_project_ids(db, user)
    if allowed is None:
        return query
    project_clause = (
        AIImportDocument.project_id.in_(allowed) if allowed else sa_false()
    )
    return query.filter(project_clause | (AIImportDocument.uploaded_by == user.id))


# ── Serialisation ─────────────────────────────────────────────────────────────

def _routing_dict(db, document: AIImportDocument) -> dict:
    """
    The routing verdict for one document, tolerant of an unprocessed one.

    A document that has not been extracted yet has no payload to reason over.
    That is an ordinary state right after upload, not an error, so it reports
    the destination its type implies and no action rather than failing the
    whole listing.
    """
    record = ai_import_service.current_extraction(db, document.id)
    if record is None:
        destination = routing.destination_for(document.document_type)
        return {
            "destination": destination.key,
            "destination_label": destination.label,
            "effect": destination.effect,
            "action": None,
            "reason": "Not yet extracted, so there is nothing to route.",
            "linked_label": None,
            "linked_type": None,
            "linked_id": None,
            "review_notes": [],
        }
    payload = ai_import_service.working_payload(db, document)
    return routing.route(db, document, payload).as_dict()


def _document_dict(db, document: AIImportDocument, *, detail: bool = False) -> dict:
    data = {
        "id": str(document.id),
        "batch_id": str(document.batch_id),
        "batch_reference": document.batch.reference if document.batch else None,
        "file_name": document.file_name,
        "mime_type": document.mime_type,
        "file_size_bytes": document.file_size_bytes,
        "checksum_sha256": document.checksum_sha256,
        "page_count": document.page_count,
        "status": document.status.value,
        "processing_outcome": document.processing_outcome.value if document.processing_outcome else None,
        "outcome_reasons": document.outcome_reasons or [],
        "document_type": document.document_type.value,
        "classification_confidence": float(document.classification_confidence or 0),
        "document_type_confirmed": document.document_type_confirmed_by is not None,
        "project_id": str(document.project_id) if document.project_id else None,
        "site_id": str(document.site_id) if document.site_id else None,
        "supplier_id": str(document.supplier_id) if document.supplier_id else None,
        "is_legacy": document.is_legacy,
        "duplicate_of_id": str(document.duplicate_of_id) if document.duplicate_of_id else None,
        "failure_reason": document.failure_reason,
        "retry_count": document.retry_count,
        "reviewed_by": str(document.reviewed_by) if document.reviewed_by else None,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "authorised_by": str(document.authorised_by) if document.authorised_by else None,
        "authorised_at": document.authorised_at.isoformat() if document.authorised_at else None,
        "rejection_reason": document.rejection_reason,
        "uploaded_by": str(document.uploaded_by),
        "created_at": document.created_at.isoformat() if document.created_at else None,
        # Where this document actually stands, end to end. The status above
        # stops at POSTED, which is where the confusion starts: a delivery can
        # be posted and still be sitting in the project warehouse, nowhere
        # near a BOQ lot.
        "pipeline": ai_import_receiving_service.pipeline_stage(db, document),
        # Where this document is headed and what importing it would do. The
        # review screen and the manifest both read this, so the two can never
        # tell the operator different stories about the same document.
        "routing": _routing_dict(db, document),
        # A PAID stamp is a claim, never a settlement. Surfaced so it can be
        # verified against the bank rather than silently discarded.
        "payment_evidence_detected": document.payment_evidence_detected,
        "payment_evidence_note": document.payment_evidence_note,
        "can_post": bool(
            document.processing_outcome is not None
            and document.status == AIImportDocumentStatus.READY_TO_POST
            and policy.may_post(document.processing_outcome)
        ),
    }
    if not detail:
        return data

    record = ai_import_service.current_extraction(db, document.id)
    job = ai_import_service.current_job(db, document.id)

    data["extraction"] = None if record is None else {
        "id": str(record.id),
        "schema_version": record.schema_version,
        "prompt_version": record.prompt_version,
        "provider": record.provider,
        "model": record.model,
        "extraction_mode": record.extraction_mode,
        "fields": record.fields or {},
        "line_items": record.line_items or [],
        "arithmetic_checks": record.arithmetic_checks or [],
        "warnings": record.warnings or [],
        "overall_confidence": float(record.overall_confidence or 0),
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost_usd": float(record.cost_usd) if record.cost_usd is not None else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
    data["matches"] = [
        {
            "id": str(m.id),
            "target_type": m.target_type,
            "target_id": str(m.target_id) if m.target_id else None,
            "target_label": m.target_label,
            "status": m.status.value,
            "method": m.method,
            "score": float(m.score) if m.score is not None else None,
            "explanation": m.explanation,
            "evidence": m.evidence or {},
            "decided_by": str(m.decided_by) if m.decided_by else None,
        }
        for m in document.matches
    ]
    data["postings"] = [
        {
            "id": str(p.id),
            "entity_type": p.entity_type,
            "entity_id": str(p.entity_id) if p.entity_id else None,
            "entity_label": p.entity_label,
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "reversed_at": p.reversed_at.isoformat() if p.reversed_at else None,
            "complete": p.entity_id is not None,
        }
        for p in document.postings
    ]
    data["corrections"] = [
        {
            "field_path": c.field_path,
            "before_value": c.before_value,
            "after_value": c.after_value,
            "reason": c.reason,
            "corrected_by": str(c.corrected_by),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in (
            db.query(ai_import_service.AIImportCorrection)
            .filter(ai_import_service.AIImportCorrection.document_id == document.id)
            .order_by(ai_import_service.AIImportCorrection.created_at.desc())
            .limit(100)
            .all()
        )
    ]
    data["job_status"] = job.status.value if job else None
    data["job"] = None if job is None else {
        "status": job.status.value,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "next_attempt_at": job.next_attempt_at.isoformat() if job.next_attempt_at else None,
        "last_error": job.last_error,
    }
    data["related_documents"] = matching.related_documents(db, document)

    if record is not None:
        payload = ai_import_service.working_payload(db, document)
        data["line_item_matches"] = matching.match_line_items(db, payload)
    else:
        data["line_item_matches"] = []

    return data


def _batch_dict(db, batch: AIImportBatch) -> dict:
    return {
        "id": str(batch.id),
        "reference": batch.reference,
        "project_id": str(batch.project_id) if batch.project_id else None,
        "site_id": str(batch.site_id) if batch.site_id else None,
        "is_legacy": batch.is_legacy,
        "status": batch.status.value,
        "notes": batch.notes,
        "uploaded_by": str(batch.uploaded_by),
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "document_count": len(batch.documents),
        "documents": [_document_dict(db, d) for d in
                      sorted(batch.documents, key=lambda d: d.created_at or batch.created_at)],
    }


# ── Batches and upload ────────────────────────────────────────────────────────

@router.post("/batches", response_model=ApiSuccess[dict], status_code=201, dependencies=[IMPORT_USERS])
def create_batch(body: BatchCreate, db: DbSession, current_user: CurrentUser):
    """Open an upload batch. Documents of any type and order may be added to it."""
    if body.project_id:
        check_project_access(db, current_user, body.project_id)
    batch = ai_import_service.create_batch(
        db, current_user.id,
        project_id=body.project_id,
        site_id=body.site_id,
        is_legacy=body.is_legacy,
        notes=body.notes,
    )
    return ApiSuccess(data=_batch_dict(db, batch), message=f"Batch {batch.reference} created.")


@router.post(
    "/batches/{batch_id}/documents",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[IMPORT_USERS],
)
async def upload_documents(
    batch_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    files: list[UploadFile] = File(...),
    is_legacy: Optional[bool] = Form(None),
):
    """
    Add one or more documents to a batch.

    Each file is validated, stored privately, hashed and queued. Extraction
    runs in the background: this endpoint never waits on a model call.
    Per-file failures are reported individually so one bad file does not
    discard the rest of the upload.
    """
    if not settings.AI_IMPORT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bypass Orders is switched off.",
        )

    batch = ai_import_service.get_batch(db, batch_id)
    _assert_batch_access(db, current_user, batch)

    accepted: list[dict] = []
    rejected: list[dict] = []

    for upload in files:
        try:
            document = ai_import_service.upload_document(
                db, batch, upload, current_user.id, is_legacy=is_legacy,
            )
            accepted.append(_document_dict(db, document))
        except (HTTPException, ValidationError) as exc:
            # upload_document validates the file before it writes anything, so
            # these are rejected with nothing to undo — rolling back here would
            # throw away the documents already accepted in this batch.
            reason = exc.detail if isinstance(exc, HTTPException) else str(exc)
            rejected.append({"file_name": upload.filename, "reason": reason})
        except Exception as exc:                    # noqa: BLE001 - reported per file
            db.rollback()
            rejected.append({"file_name": upload.filename, "reason": f"Upload failed: {exc}"})

    batch = ai_import_service.get_batch(db, batch_id)
    duplicates = [d for d in accepted if d["status"] == AIImportDocumentStatus.DUPLICATE.value]
    message = f"{len(accepted)} document(s) received."
    if duplicates:
        message += f" {len(duplicates)} already existed and were not reprocessed."
    if rejected:
        message += f" {len(rejected)} could not be accepted."

    return ApiSuccess(
        data={"batch": _batch_dict(db, batch), "accepted": accepted, "rejected": rejected},
        message=message,
    )


@router.get("/batches", response_model=ApiSuccess[list[dict]], dependencies=[IMPORT_VIEWERS])
def list_batches(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
):
    query = db.query(AIImportBatch)

    # Filter in SQL rather than fetching a guessed multiple of `limit` and
    # discarding rows afterwards, which silently returned short pages.
    allowed = ai_import_service.visible_project_ids(db, current_user)
    if allowed is not None:
        project_clause = (
            AIImportBatch.project_id.in_(allowed) if allowed else sa_false()
        )
        query = query.filter(project_clause | (AIImportBatch.uploaded_by == current_user.id))

    batches = query.order_by(AIImportBatch.created_at.desc()).limit(limit).all()
    return ApiSuccess(data=[
        {k: v for k, v in _batch_dict(db, b).items() if k != "documents"} for b in batches
    ])


@router.get("/batches/{batch_id}", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_batch(batch_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    batch = ai_import_service.get_batch(db, batch_id)
    _assert_batch_access(db, current_user, batch)
    return ApiSuccess(data=_batch_dict(db, batch))


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/batches/{batch_id}/manifest", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_batch_manifest(batch_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    What importing this batch would actually do, document by document.

    The point of the manifest is that it is readable before anything is
    written. Twenty mixed documents produce twenty different consequences —
    one moves stock, two create a liability, the rest create nothing — and
    approving them one screen at a time gives nobody a view of the whole.

    Read-only: it decides nothing and writes nothing.
    """
    batch = ai_import_service.get_batch(db, batch_id)
    _assert_batch_access(db, current_user, batch)

    documents = sorted(batch.documents, key=lambda d: d.file_name)

    rows: list[dict] = []
    for document in documents:
        record = ai_import_service.current_extraction(db, document.id)
        payload = (
            ai_import_service.working_payload(db, document) if record is not None else None
        )
        verdict = _routing_dict(db, document)
        rows.append({
            "document_id": str(document.id),
            "file_name": document.file_name,
            "document_type": document.document_type.value,
            "document_type_confirmed": document.document_type_confirmed_by is not None,
            "classification_confidence": float(document.classification_confidence or 0),
            "status": document.status.value,
            "supplier_id": str(document.supplier_id) if document.supplier_id else None,
            "supplier_name": (payload.value("supplier_name") if payload else None),
            "project_id": str(document.project_id) if document.project_id else None,
            "reference": (payload.value("document_number") if payload else None),
            "total_amount": (payload.value("total_amount") if payload else None),
            "payment_evidence_detected": document.payment_evidence_detected,
            "payment_evidence_note": document.payment_evidence_note,
            "routing": verdict,
            "can_post": bool(
                document.processing_outcome is not None
                and document.status == AIImportDocumentStatus.READY_TO_POST
                and policy.may_post(document.processing_outcome)
            ),
        })

    # Counts by action and by destination, so the header can say "3 will
    # create a liability" without the operator counting rows themselves.
    by_action: dict[str, int] = {}
    by_destination: dict[str, int] = {}
    for row in rows:
        action = row["routing"]["action"] or "PENDING"
        by_action[action] = by_action.get(action, 0) + 1
        label = row["routing"]["destination_label"]
        by_destination[label] = by_destination.get(label, 0) + 1

    return ApiSuccess(data={
        "batch": {
            "id": str(batch.id),
            "reference": batch.reference,
            "status": batch.status.value,
            "document_count": len(documents),
        },
        "rows": rows,
        "summary": {
            "by_action": by_action,
            "by_destination": by_destination,
            "payment_evidence_count": sum(
                1 for r in rows if r["payment_evidence_detected"]
            ),
            "needs_review_count": by_action.get("REVIEW", 0),
            "duplicate_count": by_action.get("SKIP_DUPLICATE", 0),
        },
    })


@router.get("/documents", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def list_documents(
    db: DbSession,
    current_user: CurrentUser,
    company_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    site_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    document_type: Optional[AIImportDocumentType] = None,
    doc_status: Optional[AIImportDocumentStatus] = Query(None, alias="status"),
    uploaded_by: Optional[uuid.UUID] = None,
    reason_code: Optional[str] = Query(
        None,
        description="Only documents carrying this policy reason, e.g. NO_PURCHASE_ORDER. "
                    "Turns a dashboard count into a worklist.",
    ),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
):
    """Filterable document list. Results are limited to the caller's projects."""
    query = _visible_documents(db, current_user)

    if company_id:
        query = query.filter(
            AIImportDocument.project_id.in_(
                ai_import_service._company_project_ids(db, company_id)
            )
        )
    if project_id:
        check_project_access(db, current_user, project_id)
        query = query.filter(AIImportDocument.project_id == project_id)
    if site_id:
        query = query.filter(AIImportDocument.site_id == site_id)
    if supplier_id:
        query = query.filter(AIImportDocument.supplier_id == supplier_id)
    if document_type:
        query = query.filter(AIImportDocument.document_type == document_type)
    if doc_status:
        query = query.filter(AIImportDocument.status == doc_status)
    if uploaded_by:
        query = query.filter(AIImportDocument.uploaded_by == uploaded_by)
    if date_from:
        query = query.filter(AIImportDocument.created_at >= date_from)
    if date_to:
        from datetime import datetime as _dt, timezone as _tz
        query = query.filter(
            AIImportDocument.created_at < _dt.combine(date_to, _dt.max.time(), tzinfo=_tz.utc)
        )

    if reason_code:
        # Reasons are a JSONB array of an open set of codes, so the filter is
        # applied after the query and the page is cut from the result.
        matched = ai_import_service.filter_by_reason_code(
            query.order_by(AIImportDocument.created_at.desc()).all(), reason_code,
        )
        total = len(matched)
        rows = matched[(page - 1) * limit: (page - 1) * limit + limit]
    else:
        total = query.count()
        rows = (
            query.order_by(AIImportDocument.created_at.desc())
            .offset((page - 1) * limit).limit(limit).all()
        )
    return ApiSuccess(data={
        "items": [_document_dict(db, d) for d in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
    })


@router.get("/documents/{document_id}", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_document(document_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Full detail: extraction with provenance, matches, postings and corrections."""
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    return ApiSuccess(data=_document_dict(db, document, detail=True))


@router.get("/documents/{document_id}/file", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_document_file(document_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Short-lived signed URL for the original document.

    The file itself lives in private storage. This is the only route to it and
    it runs the project access check first, so a supplier document is never
    reachable from a public URL.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)

    # Access logging happens here, immediately after the access check and
    # before the URL is produced: the auditable fact is that this user was
    # granted access to this supplier document, which is true whether or not
    # storage then manages to hand back a URL.
    # AuditEvent.action is a free-form string column, so "ACCESS" sits
    # alongside the AuditAction members without needing a new enum value.
    from app.services import audit_service
    audit_service.write_event(
        db, "ACCESS", "ai_import_document_file",
        current_user.id, document.id,
        after_value={
            "file_name": document.file_name,
            "checksum_sha256": document.checksum_sha256,
            "expires_in_seconds": settings.EVIDENCE_SIGNED_URL_EXPIRY_SECONDS,
        },
        notes="Access granted to the original document; signed URL requested.",
        commit=True,
    )

    try:
        url = ai_import_service.signed_document_url(document)
    except Exception as exc:                        # noqa: BLE001 - surfaced to the caller
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The document file could not be retrieved from storage: {exc}",
        )
    return ApiSuccess(data={
        "url": url,
        "expires_in_seconds": settings.EVIDENCE_SIGNED_URL_EXPIRY_SECONDS,
        "mime_type": document.mime_type,
        "file_name": document.file_name,
    })


# ── Review actions ────────────────────────────────────────────────────────────

@router.patch("/documents/{document_id}/context", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def assign_context(
    document_id: uuid.UUID, body: ContextAssignment, db: DbSession, current_user: CurrentUser,
):
    """Set the project, site, supplier, document type or legacy flag by hand."""
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    if body.project_id:
        check_project_access(db, current_user, body.project_id)
    document = ai_import_service.assign_context(db, document, body, current_user)
    return ApiSuccess(data=_document_dict(db, document, detail=True), message="Context updated.")


@router.patch("/documents/{document_id}/corrections", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def correct_fields(
    document_id: uuid.UUID, body: CorrectionRequest, db: DbSession, current_user: CurrentUser,
):
    """
    Correct extracted values before approval.

    Every change is written to the correction audit with its previous value,
    and the arithmetic checks are recomputed on the corrected numbers.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    document = ai_import_service.apply_corrections(db, document, body.corrections, current_user)
    return ApiSuccess(
        data=_document_dict(db, document, detail=True),
        message=f"{len(body.corrections)} correction(s) applied and recorded.",
    )


@router.post("/documents/{document_id}/matches/decide", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def decide_match(
    document_id: uuid.UUID, body: MatchDecision, db: DbSession, current_user: CurrentUser,
):
    """
    Accept or reject a proposed match.

    Accepting a `project` or `site` match moves the document's context, so it
    runs the same access check `PATCH /context` does. Without it, a proposed
    match — which the matcher may draw from any project — would be a way to
    move a document somewhere the caller has no access to.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)

    if body.accept:
        match = db.get(ai_import_service.AIImportMatch, body.match_id)
        if match is None or match.document_id != document.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match not found on this document.",
            )
        target_project = _match_target_project(db, match)
        if target_project:
            check_project_access(db, current_user, target_project)

    document = ai_import_service.decide_match(
        db, document, body.match_id, body.accept, current_user, body.reason,
    )
    return ApiSuccess(data=_document_dict(db, document, detail=True))


def _match_target_project(db, match) -> Optional[uuid.UUID]:
    """
    The project a match would place the document in, when accepting it moves
    the document's context. None when the match does not change the project.
    """
    if not match.target_id:
        return None
    if match.target_type == "project":
        return match.target_id
    if match.target_type == "site":
        from app.models.site import Site
        site = db.get(Site, match.target_id)
        return site.project_id if site else None
    return None


@router.post("/documents/{document_id}/matches", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def add_match(
    document_id: uuid.UUID, body: ManualMatchCreate, db: DbSession, current_user: CurrentUser,
):
    """
    Link the document to a procurement record the engine did not find.

    Only the record types in `LINKABLE_TARGET_TYPES` may be linked — the
    project, site and supplier are the document's own context and are set
    through `PATCH /context`, which has its own access check. The caller must
    also have access to the project the target record belongs to, so a link
    cannot be used to reach into another project.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)

    if body.target_type not in ai_import_service.LINKABLE_TARGET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{body.target_type}' cannot be linked by hand. Linkable records are: "
                + ", ".join(sorted(ai_import_service.LINKABLE_TARGET_TYPES))
                + ". Set the project, site or supplier on the document instead."
            ),
        )

    target_project = ai_import_service.target_project_id(db, body.target_type, body.target_id)
    if target_project:
        check_project_access(db, current_user, target_project)

    document = ai_import_service.add_manual_match(
        db, document, body.target_type, body.target_id, current_user, body.reason,
    )
    return ApiSuccess(data=_document_dict(db, document, detail=True))


@router.post("/documents/{document_id}/review", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def mark_reviewed(document_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    document = ai_import_service.mark_reviewed(db, document, current_user)
    return ApiSuccess(data=_document_dict(db, document, detail=True))


@router.post(
    "/documents/{document_id}/authorise",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def authorise_legacy(
    document_id: uuid.UUID, body: RejectRequest, db: DbSession, current_user: CurrentUser,
):
    """
    Authorise a legacy import.

    Records that a named manager vouched for the paper evidence. It is not a
    retroactive digital approval, and the created record says so in its notes.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    document = ai_import_service.authorise_legacy(db, document, body.reason, current_user)
    return ApiSuccess(
        data=_document_dict(db, document, detail=True),
        message="Legacy import authorised. The record will be marked as document-backed.",
    )


@router.post(
    "/documents/{document_id}/reject",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def reject_document(
    document_id: uuid.UUID, body: RejectRequest, db: DbSession, current_user: CurrentUser,
):
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    document = ai_import_service.reject_document(db, document, body.reason, current_user)
    return ApiSuccess(data=_document_dict(db, document), message="Document rejected.")


@router.post("/documents/{document_id}/retry", response_model=ApiSuccess[dict], dependencies=[IMPORT_USERS])
def retry_document(document_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Queue the document for processing again.

    Reprocessing rewrites only extraction, matching and the verdict. Anything
    already posted stays posted and is never created twice.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)
    document = ai_import_service.retry_document(db, document, current_user)
    return ApiSuccess(data=_document_dict(db, document), message="Queued for reprocessing.")


# ── Posting ───────────────────────────────────────────────────────────────────

@router.post(
    "/documents/{document_id}/post",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def post_document(
    document_id: uuid.UUID, body: PostRequest, db: DbSession, current_user: CurrentUser,
):
    """
    Create the real business records from this document.

    Refuses outright when the policy verdict is BLOCKED — no role and no flag
    overrides that, because the blocking conditions (duplicate posting, invalid
    arithmetic, cross-project reference, conflicting supplier identity) are the
    ones where posting would corrupt the books.

    A NEEDS_REVIEW document may be posted by an authorised user who passes
    `confirm_override`, which is recorded in the audit trail.

    A legacy document that has not been authorised yet requires
    `legacy_authorisation_note`; the note is recorded against the document and
    reproduced on the created record, so a historical import is never
    presented as having gone through the digital workflow.
    """
    document = ai_import_service.get_document(db, document_id)
    _assert_document_access(db, current_user, document)

    # A legacy document carries no digital approval history. Authorising it
    # here records who vouched for the paper trail, using the same path as the
    # dedicated endpoint, so the note is never silently discarded.
    if document.is_legacy and not document.authorised_by:
        note = (body.legacy_authorisation_note or "").strip()
        if not note:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "This is a historical document with no digital approval history. "
                    "Supply legacy_authorisation_note describing the paper evidence, or "
                    "authorise it first, before it can be posted."
                ),
            )
        document = ai_import_service.authorise_legacy(db, document, note, current_user)

    payload = ai_import_service.working_payload(db, document)
    outcome, reasons = policy.evaluate(db, document, payload)
    document.processing_outcome = outcome
    document.outcome_reasons = reasons
    db.commit()

    blocking = policy.blocking_reasons(reasons)
    if blocking:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This document cannot be posted.",
                "reasons": blocking,
            },
        )

    if outcome != policy.AIImportProcessingOutcome.AUTO_ELIGIBLE and not body.confirm_override:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "This document needs review before posting. Resolve the items below, "
                    "or re-send with confirm_override to post on your authority."
                ),
                "reasons": reasons,
            },
        )

    destination = None
    if body.destination:
        try:
            destination = DeliveryDestination(body.destination)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{body.destination}' is not a valid delivery destination.",
            )

    if body.lot_id:
        from app.models.lot import Lot
        lot = db.get(Lot, body.lot_id)
        if not lot or (document.project_id and lot.project_id != document.project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lot not found in this document's project.",
            )

    try:
        posting = posting_service.post_document(
            db, document, payload, current_user,
            destination=destination,
            lot_id=body.lot_id,
            overrun_reason=body.overrun_reason,
        )
    except posting_service.AlreadyPosted as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except posting_service.PostingRefused as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if body.confirm_override and outcome != policy.AIImportProcessingOutcome.AUTO_ELIGIBLE:
        from app.models.enums import AuditAction
        from app.services import audit_service
        audit_service.write_event(
            db, AuditAction.APPROVE, "ai_import_override", current_user.id, document.id,
            after_value={"outcome": outcome.value, "reasons": reasons},
            notes="Posted on the user's authority while review items were outstanding.",
            commit=True,
        )

    requeued = ai_import_service.reevaluate_related(db, document)
    ai_import_service.refresh_batch_status(db, document.batch)
    db.commit()

    return ApiSuccess(
        data={
            "document": _document_dict(db, document, detail=True),
            "posting": {
                "entity_type": posting.entity_type,
                "entity_id": str(posting.entity_id) if posting.entity_id else None,
                "entity_label": posting.entity_label,
            },
            "related_documents_reevaluated": requeued,
        },
        message=(
            f"Posted as {posting.entity_type.replace('_', ' ')} {posting.entity_label}."
            + (f" {requeued} related document(s) were re-checked against it." if requeued else "")
        ),
    )


# ── Dashboard and operations ──────────────────────────────────────────────────

@router.get("/dashboard", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_dashboard(
    db: DbSession,
    current_user: CurrentUser,
    company_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    site_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    document_type: Optional[AIImportDocumentType] = None,
    doc_status: Optional[AIImportDocumentStatus] = Query(None, alias="status"),
    uploaded_by: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    """
    Pipeline counts, operational queues and AI spend.

    Always scoped to the projects the caller may see, so a site-level user
    never receives company-wide figures — including the total invoice value
    awaiting authorisation — by simply omitting the project filter.
    """
    if project_id:
        check_project_access(db, current_user, project_id)
    filters = DashboardFilters(
        company_id=company_id,
        project_id=project_id, site_id=site_id, supplier_id=supplier_id,
        document_type=document_type, status=doc_status, uploaded_by=uploaded_by,
        date_from=date_from, date_to=date_to,
    )
    return ApiSuccess(data=ai_import_service.dashboard(db, filters, viewer=current_user))


@router.get("/service-status", response_model=ApiSuccess[dict], dependencies=[IMPORT_VIEWERS])
def get_service_status():
    """
    What this installation can actually do right now.

    Bypass Orders degrades rather than fails when its external integrations
    are absent: without an AI provider it still stores, hashes, de-duplicates
    and routes documents to human review, but reads almost nothing off them.
    That difference has to be visible to the operator, otherwise an empty
    extraction looks like a bad document rather than an unconfigured service.

    Deliberately viewer-level and free of secrets: it reports whether each
    integration is configured, never any part of a credential.
    """
    from app.core.storage import _supabase_enabled

    return ApiSuccess(data={
        "enabled": settings.AI_IMPORT_ENABLED,
        "extraction_available": extraction.ai_available(),
        "extraction_model": extraction.ai_model(),
        # Whether a workspace id is configured, never which one. An
        # organisation-scoped Anthropic key is refused with HTTP 400 "not
        # scoped to a workspace" unless every request names one, and that
        # refusal is indistinguishable, from the operator's side, from a
        # document the model could not read. Without this flag the only way
        # to tell them apart is to read the hosting dashboard.
        "workspace_scoped": bool(extraction.workspace_headers()),
        "private_storage_configured": _supabase_enabled(),
        "auto_post_enabled": settings.AI_IMPORT_AUTO_POST_ENABLED,
        "worker_enabled": settings.AI_IMPORT_WORKER_ENABLED,
    })


@router.get("/health", response_model=ApiSuccess[dict], dependencies=[OFFICE_ADMIN_AND_ABOVE])
def get_health(db: DbSession):
    """Queue depth, worker state and any postings left unverified by a crash."""
    return ApiSuccess(data=ai_import_worker.queue_health(db))


@router.post("/process", response_model=ApiSuccess[dict], dependencies=[OFFICE_ADMIN_AND_ABOVE])
def process_queue_now(
    db: DbSession,
    limit: int = Query(5, ge=1, le=25),
):
    """Drain the queue on demand, for use when the background loop is disabled."""
    return ApiSuccess(data=ai_import_worker.drain_once(db, limit=limit))


@router.get(
    "/postings/incomplete",
    response_model=ApiSuccess[list[dict]],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def list_incomplete_postings(db: DbSession):
    """
    Posting attempts interrupted after their claim was taken.

    Each one blocks retries of its document on purpose — the business record
    may or may not exist. Someone must look in the destination module and
    resolve it; until then the document cannot move.
    """
    return ApiSuccess(data=ai_import_posting_service.incomplete_posting_details(db))


@router.post(
    "/postings/{posting_id}/resolve",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def resolve_posting(
    posting_id: uuid.UUID,
    body: PostingResolution,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Close out an interrupted posting.

    `link` records the business record that was in fact created and marks the
    document posted. `discard` frees the claim so the document can be posted
    again — use it only after confirming no record exists, because discarding
    a posting that did happen is how a duplicate gets in. Both require a note
    and are audited.
    """
    posting = db.get(ai_import_service.AIImportPosting, posting_id)
    if posting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting not found.")

    document = ai_import_service.get_document(db, posting.document_id)
    _assert_document_access(db, current_user, document)

    try:
        resolved = ai_import_posting_service.resolve_incomplete_posting(
            db,
            posting_id=posting_id,
            resolution=body.resolution,
            actor=current_user,
            note=body.note,
            entity_id=body.entity_id,
        )
    except posting_service.PostingRefused as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return ApiSuccess(
        data={
            "resolution": body.resolution,
            "posting": None if resolved is None else {
                "id": str(resolved.id),
                "entity_type": resolved.entity_type,
                "entity_id": str(resolved.entity_id) if resolved.entity_id else None,
                "entity_label": resolved.entity_label,
            },
            "document": _document_dict(db, ai_import_service.get_document(db, document.id)),
        },
        message=(
            f"Posting linked to {resolved.entity_type.replace('_', ' ')} {resolved.entity_label}."
            if resolved is not None else
            "Posting discarded. The document can be posted again."
        ),
    )


@router.post("/retention/purge", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def purge_expired(
    db: DbSession,
    current_user: CurrentUser,
    apply: bool = Query(False, description="False reports what would be removed; True removes it."),
):
    """
    Apply the retention policy to stored document files.

    Defaults to a dry run. Only the stored file and raw extraction text are
    removed — document rows, postings and audit history are always kept, and a
    document behind a live posting is never purged.
    """
    result = ai_import_service.purge_expired_documents(db, dry_run=not apply)
    return ApiSuccess(
        data=result,
        message=(
            f"{result['purged_count']} document file(s) would be removed."
            if result["dry_run"] else
            f"{result['purged_count']} document file(s) removed."
        ),
    )
