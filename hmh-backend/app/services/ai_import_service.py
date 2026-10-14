"""
AI Document Import — ingestion, lifecycle and review.

Owns the document state machine and everything a reviewer does to a document.
Extraction lives in ai_import_extraction_service, matching in
ai_import_matching_service, the verdict in ai_import_policy_service and the
business writes in ai_import_posting_service; this module sequences them.

Uploading never runs extraction inline. A file is stored, hashed, queued and
the request returns — long model calls belong in the worker, not in an HTTP
request that a phone on site holds open.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import UploadFile
from sqlalchemy import false as sa_false, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging_config import get_logger
from app.core.storage import create_signed_url, save_upload
from app.core.upload_scanning import UnsafeUpload, check_upload
from app.core.upload_validation import DOCUMENT_MIMES, validate_upload
from app.models.ai_import import (
    AIImportBatch,
    AIImportCorrection,
    AIImportDocument,
    AIImportExtraction,
    AIImportJob,
    AIImportMatch,
    AIImportPosting,
)
from app.models.enums import (
    AIImportBatchStatus,
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportJobStatus,
    AIImportMatchStatus,
    AIImportProcessingOutcome,
    AuditAction,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.ai_import import (
    COMMON_FIELDS,
    ArithmeticCheck,
    DocumentExtractionPayload,
    ExtractedField,
    ExtractedLineItem,
)
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_matching_service as matching
from app.services import ai_import_policy_service as policy
from app.services import audit_service

logger = get_logger(__name__)

# States a document may be retried from.
RETRYABLE_STATES = frozenset({
    AIImportDocumentStatus.FAILED,
    AIImportDocumentStatus.AWAITING_REVIEW,
    AIImportDocumentStatus.AWAITING_AUTHORISATION,
    AIImportDocumentStatus.READY_TO_POST,
    AIImportDocumentStatus.EXTRACTED,
    AIImportDocumentStatus.CLASSIFIED,
    AIImportDocumentStatus.MATCHING,
})

# Roles permitted to post. Mirrors OFFICE_ADMIN_AND_ABOVE on
# POST /ai-import/documents/{id}/post — auto-posting must not be a way round it.
AUTO_POST_ROLES = frozenset({UserRole.OWNER, UserRole.OFFICE_ADMIN})

TERMINAL_STATES = frozenset({
    AIImportDocumentStatus.POSTED,
    AIImportDocumentStatus.REJECTED,
    AIImportDocumentStatus.DUPLICATE,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Batches ───────────────────────────────────────────────────────────────────

def _next_batch_reference(db: Session) -> str:
    today = _now().strftime("%Y%m%d")
    prefix = f"IMP-{today}-"
    count = (
        db.query(func.count(AIImportBatch.id))
        .filter(AIImportBatch.reference.like(f"{prefix}%"))
        .scalar()
    ) or 0
    return f"{prefix}{count + 1:03d}"


def create_batch(
    db: Session,
    uploaded_by: uuid.UUID,
    *,
    project_id: Optional[uuid.UUID] = None,
    site_id: Optional[uuid.UUID] = None,
    is_legacy: bool = False,
    notes: Optional[str] = None,
) -> AIImportBatch:
    batch = AIImportBatch(
        reference=_next_batch_reference(db),
        project_id=project_id,
        site_id=site_id,
        is_legacy=is_legacy,
        notes=notes,
        status=AIImportBatchStatus.OPEN,
        uploaded_by=uploaded_by,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def get_batch(db: Session, batch_id: uuid.UUID) -> AIImportBatch:
    batch = db.get(AIImportBatch, batch_id)
    if not batch:
        raise NotFoundError(f"Import batch {batch_id} not found.")
    return batch


def refresh_batch_status(db: Session, batch: AIImportBatch) -> AIImportBatch:
    """Derive the batch state from its documents rather than tracking it separately."""
    if batch.status == AIImportBatchStatus.CANCELLED:
        return batch
    statuses = [d.status for d in batch.documents]
    if not statuses:
        batch.status = AIImportBatchStatus.OPEN
    elif all(s in TERMINAL_STATES for s in statuses):
        batch.status = AIImportBatchStatus.COMPLETE
    else:
        batch.status = AIImportBatchStatus.PROCESSING
    return batch


# ── Upload ────────────────────────────────────────────────────────────────────

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _safe_file_name(raw: Optional[str]) -> str:
    base = os.path.basename(raw or "document")
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "document"
    return cleaned[:200]


def _probe_page_count(content: bytes, mime_type: str) -> Optional[int]:
    if mime_type != "application/pdf":
        return 1
    try:
        import io

        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:                               # noqa: BLE001 - page count is advisory
        return None


def upload_document(
    db: Session,
    batch: AIImportBatch,
    file: UploadFile,
    uploaded_by: uuid.UUID,
    *,
    is_legacy: Optional[bool] = None,
) -> AIImportDocument:
    """
    Store one uploaded file and queue it for processing.

    The same bytes uploaded twice — under any filename — are detected by SHA-256
    and the second copy is marked DUPLICATE without being queued, so re-sending
    a batch can never double-post anything.
    """
    validate_upload(file, DOCUMENT_MIMES, max_mb=settings.AI_IMPORT_MAX_UPLOAD_MB)

    existing_count = (
        db.query(func.count(AIImportDocument.id))
        .filter(AIImportDocument.batch_id == batch.id)
        .scalar()
    ) or 0
    if existing_count >= settings.AI_IMPORT_MAX_FILES_PER_BATCH:
        raise ValidationError(
            f"This batch already holds {existing_count} documents, the maximum is "
            f"{settings.AI_IMPORT_MAX_FILES_PER_BATCH}. Start another batch."
        )

    file.file.seek(0)
    content = file.file.read()
    if not content:
        raise ValidationError(f"'{file.filename}' is empty.")

    checksum = hashlib.sha256(content).hexdigest()
    mime_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    file_name = _safe_file_name(file.filename)

    # What the file actually is, then whether it is safe. Both before a byte
    # reaches storage: the MIME type and extension checked earlier are
    # client-supplied, and a renamed executable passes both.
    try:
        scan = check_upload(content, mime_type, file_name)
    except UnsafeUpload as exc:
        raise ValidationError(str(exc)) from exc
    if scan.scanned:
        logger.info("ai_import scanned %s: clean", file_name)

    # Private storage only — these are supplier financial documents.
    relative_path = f"ai_import/{batch.id}/{uuid.uuid4().hex}_{file_name}"
    stored_path = save_upload(content, relative_path, private=True)

    duplicate_of = (
        db.query(AIImportDocument)
        .filter(
            AIImportDocument.checksum_sha256 == checksum,
            AIImportDocument.status != AIImportDocumentStatus.REJECTED,
        )
        .order_by(AIImportDocument.created_at.asc())
        .first()
    )

    document = AIImportDocument(
        batch_id=batch.id,
        file_name=file_name,
        stored_path=stored_path,
        mime_type=mime_type,
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        page_count=_probe_page_count(content, mime_type),
        status=AIImportDocumentStatus.UPLOADED,
        project_id=batch.project_id,
        site_id=batch.site_id,
        is_legacy=batch.is_legacy if is_legacy is None else is_legacy,
        uploaded_by=uploaded_by,
    )

    if duplicate_of is not None:
        document.duplicate_of_id = duplicate_of.id
        document.status = AIImportDocumentStatus.DUPLICATE
        document.processing_outcome = AIImportProcessingOutcome.BLOCKED
        document.outcome_reasons = [{
            "code": "DUPLICATE_FILE",
            "message": (
                f"Identical to '{duplicate_of.file_name}' uploaded on "
                f"{duplicate_of.created_at:%Y-%m-%d} (same file contents). "
                f"It was not processed again."
            ),
            "severity": policy.BLOCKED,
            "field": None,
        }]

    db.add(document)
    db.flush()

    if duplicate_of is None:
        _enqueue(db, document)

    audit_service.write_event(
        db, AuditAction.UPLOAD, "ai_import_document", uploaded_by, document.id,
        after_value={
            "file_name": file_name,
            "checksum_sha256": checksum,
            "size_bytes": len(content),
            "batch": batch.reference,
            "duplicate_of": str(duplicate_of.id) if duplicate_of else None,
        },
    )
    refresh_batch_status(db, batch)
    db.commit()
    db.refresh(document)
    return document


# ── Job queue ─────────────────────────────────────────────────────────────────

def _enqueue(db: Session, document: AIImportDocument, delay_seconds: int = 0) -> Optional[AIImportJob]:
    """
    Queue a document for processing.

    A partial unique index allows only one PENDING/RUNNING job per document, so
    a duplicate enqueue is refused by the database rather than by a race-prone
    read-then-write check.
    """
    job = AIImportJob(
        document_id=document.id,
        job_type="process",
        status=AIImportJobStatus.PENDING,
        attempt_count=0,
        max_attempts=settings.AI_IMPORT_JOB_MAX_ATTEMPTS,
        next_attempt_at=_now() + timedelta(seconds=delay_seconds),
        created_at=_now(),
    )
    # A savepoint, not a plain flush: the partial unique index raises on a
    # duplicate live job, and a bare rollback here would discard the caller's
    # work (the document row being inserted alongside it).
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        logger.info("ai_import job already queued for document=%s", document.id)
        return None

    document.status = AIImportDocumentStatus.QUEUED
    return job


def current_job(db: Session, document_id: uuid.UUID) -> Optional[AIImportJob]:
    return (
        db.query(AIImportJob)
        .filter(AIImportJob.document_id == document_id)
        .order_by(AIImportJob.created_at.desc())
        .first()
    )


# ── Extraction persistence ────────────────────────────────────────────────────

def _store_extraction(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> AIImportExtraction:
    """Append a new extraction and demote the previous one. Nothing is overwritten."""
    db.query(AIImportExtraction).filter(
        AIImportExtraction.document_id == document.id,
        AIImportExtraction.is_current.is_(True),
    ).update({"is_current": False}, synchronize_session=False)

    record = AIImportExtraction(
        document_id=document.id,
        schema_version=payload.schema_version,
        prompt_version=payload.prompt_version,
        provider=payload.provider,
        model=payload.model,
        extraction_mode=payload.extraction_mode,
        fields={k: v.model_dump(mode="json") for k, v in payload.fields.items()},
        line_items=[i.model_dump(mode="json") for i in payload.line_items],
        arithmetic_checks=[c.model_dump(mode="json") for c in payload.arithmetic_checks],
        warnings=payload.warnings,
        raw_text=payload.raw_text,
        raw_response=payload.raw_response,
        overall_confidence=Decimal(str(payload.overall_confidence)),
        is_current=True,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cost_usd=Decimal(str(payload.cost_usd)) if payload.cost_usd is not None else None,
        duration_ms=payload.duration_ms,
        created_at=_now(),
    )
    db.add(record)
    db.flush()
    return record


def current_extraction(db: Session, document_id: uuid.UUID) -> Optional[AIImportExtraction]:
    return (
        db.query(AIImportExtraction)
        .filter(
            AIImportExtraction.document_id == document_id,
            AIImportExtraction.is_current.is_(True),
        )
        .first()
    )


def payload_from_record(record: Optional[AIImportExtraction]) -> DocumentExtractionPayload:
    """Rebuild the working payload from a stored extraction."""
    if record is None:
        return DocumentExtractionPayload()
    payload = DocumentExtractionPayload(
        schema_version=record.schema_version,
        prompt_version=record.prompt_version,
        provider=record.provider,
        model=record.model,
        extraction_mode=record.extraction_mode,  # type: ignore[arg-type]
        warnings=list(record.warnings or []),
        overall_confidence=float(record.overall_confidence or 0),
        raw_text=record.raw_text,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cost_usd=float(record.cost_usd) if record.cost_usd is not None else None,
    )
    for name, raw in (record.fields or {}).items():
        payload.fields[name] = ExtractedField(**raw)
    payload.line_items = [ExtractedLineItem(**raw) for raw in (record.line_items or [])]
    payload.arithmetic_checks = [ArithmeticCheck(**raw) for raw in (record.arithmetic_checks or [])]
    return payload


def working_payload(db: Session, document: AIImportDocument) -> DocumentExtractionPayload:
    payload = payload_from_record(current_extraction(db, document.id))
    payload.document_type = document.document_type
    payload.classification_confidence = float(document.classification_confidence or 0)
    return payload


# ── Processing ────────────────────────────────────────────────────────────────

def _local_copy(document: AIImportDocument) -> tuple[Optional[str], Optional[bytes]]:
    """
    Fetch the stored file.

    Returns (local_path, bytes). The path is only present when the file is on
    local disk; with Supabase storage the bytes are downloaded and the OCR and
    regex strategies are skipped in favour of vision.
    """
    from app.core import storage

    path = document.stored_path
    if not path:
        return None, None

    # Local disk path (storage falls back to disk when Supabase is unset).
    candidates = [path]
    if not os.path.isabs(path):
        candidates.append(os.path.join(settings.UPLOAD_DIR, path))
        candidates.append(os.path.join(os.getcwd(), path))
    for candidate in candidates:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "rb") as fh:
                    return candidate, fh.read()
            except OSError as exc:
                logger.warning("ai_import could not read %s: %s", candidate, exc)

    # Remote object: download via a short-lived signed URL.
    try:
        import httpx
        url = storage.create_signed_url(path, expires_in=120)
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        return None, response.content
    except Exception as exc:                        # noqa: BLE001 - processing reports this
        logger.warning("ai_import could not download %s: %s", path, exc)
        return None, None


def process_document(db: Session, document: AIImportDocument) -> AIImportDocument:
    """
    Run the full pipeline for one document: extract, classify, match, decide.

    Raises ExtractionTransientError when the AI provider is down so the worker
    can retry with backoff. Every other failure is recorded on the document.
    """
    document.status = AIImportDocumentStatus.PROCESSING
    db.commit()

    local_path, content = _local_copy(document)
    if content is None:
        document.status = AIImportDocumentStatus.FAILED
        document.failure_reason = (
            "The stored file could not be read back. Check storage configuration, "
            "then retry this document."
        )
        db.commit()
        return document

    # Raises on a transient provider failure; the worker turns that into a retry.
    payload = extraction.analyse_document(
        file_bytes=content,
        mime_type=document.mime_type,
        file_path=local_path,
        file_name=document.file_name,
    )

    document.status = AIImportDocumentStatus.EXTRACTED

    # The classifier only sets the type while no human has fixed it.
    if document.document_type_confirmed_by is None:
        document.document_type = payload.document_type
        document.classification_confidence = Decimal(str(payload.classification_confidence))
    else:
        payload.document_type = document.document_type
    document.status = AIImportDocumentStatus.CLASSIFIED

    _store_extraction(db, document, payload)

    document.status = AIImportDocumentStatus.MATCHING
    matching.rematch_document(db, document, payload)
    _attach_po_comparison(db, document, payload)

    outcome, reasons = policy.evaluate(db, document, payload)
    document.processing_outcome = outcome
    document.outcome_reasons = reasons
    document.status = policy.status_for_outcome(outcome, document)
    document.failure_reason = None

    db.commit()
    db.refresh(document)

    if (
        outcome == AIImportProcessingOutcome.AUTO_ELIGIBLE
        and settings.AI_IMPORT_AUTO_POST_ENABLED
    ):
        _auto_post(db, document, payload)

    return document


def _attach_po_comparison(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> None:
    """
    Run the three-way comparison and store it on the purchase-order match.

    The policy engine reads it from there, which keeps the comparison out of
    the policy module and means the UI and the verdict see the same numbers.
    """
    po_match = matching.best_match(db, document.id, "purchase_order")
    if not po_match or not po_match.target_id:
        return
    # An invoice is checked against what was ordered and received; a delivery
    # note against what is still outstanding. See compare_against_purchase_order.
    mode = "billing" if document.document_type in (
        AIImportDocumentType.SUPPLIER_INVOICE,
        AIImportDocumentType.SUPPLIER_CREDIT_NOTE,
    ) else "receipt"
    comparison = matching.compare_against_purchase_order(
        db, payload, po_match.target_id, mode=mode,
    )
    po_match.evidence = {**(po_match.evidence or {}), "po_comparison": comparison}
    db.flush()


def _auto_post(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> None:
    """
    Post an AUTO_ELIGIBLE document under the uploader's identity.

    Only reachable when AI_IMPORT_AUTO_POST_ENABLED is switched on, which it is
    not by default. The uploader must themselves hold the role the manual
    `POST /documents/{id}/post` endpoint requires: auto-posting is a
    convenience, never a way for someone who may only upload to become the
    recorded author of a stock movement or a supplier liability.

    Failures never crash the worker: the document falls back to review with
    the reason attached.
    """
    from app.services import ai_import_posting_service as posting

    actor = db.get(User, document.uploaded_by)
    if actor is None:
        return

    if actor.role not in AUTO_POST_ROLES:
        document.outcome_reasons = (document.outcome_reasons or []) + [{
            "code": "AUTO_POST_ROLE_REQUIRED",
            "message": (
                f"This document passed every check, but {actor.full_name or actor.email} "
                f"({actor.role.value}) may not post. Someone with posting rights must "
                f"confirm it."
            ),
            "severity": policy.REVIEW,
            "field": None,
        }]
        document.processing_outcome = AIImportProcessingOutcome.NEEDS_REVIEW
        document.status = AIImportDocumentStatus.AWAITING_REVIEW
        db.commit()
        return
    try:
        posting.post_document(db, document, payload, actor)
    except Exception as exc:                        # noqa: BLE001 - degrade to review
        db.rollback()
        logger.warning("ai_import auto-post failed for document=%s: %s", document.id, exc)
        document.status = AIImportDocumentStatus.AWAITING_REVIEW
        document.outcome_reasons = (document.outcome_reasons or []) + [{
            "code": "AUTO_POST_FAILED",
            "message": f"Automatic posting did not complete: {exc}",
            "severity": policy.REVIEW,
            "field": None,
        }]
        document.processing_outcome = AIImportProcessingOutcome.NEEDS_REVIEW
        db.commit()


def reevaluate(db: Session, document: AIImportDocument) -> AIImportDocument:
    """
    Re-run matching and policy against the stored extraction.

    Used after a correction, a context assignment or a match decision — and
    after another document is posted, which is what lets an invoice uploaded
    before its purchase order pick that order up once it exists.
    """
    if document.status in TERMINAL_STATES:
        return document

    payload = working_payload(db, document)
    matching.rematch_document(db, document, payload)
    _attach_po_comparison(db, document, payload)

    outcome, reasons = policy.evaluate(db, document, payload)
    document.processing_outcome = outcome
    document.outcome_reasons = reasons
    document.status = policy.status_for_outcome(outcome, document)
    db.commit()
    db.refresh(document)
    return document


def reevaluate_related(db: Session, posted_document: AIImportDocument) -> int:
    """
    Re-run waiting documents after a posting creates a new record.

    This is the out-of-order mechanism: posting Wednesday's purchase order
    re-evaluates Monday's invoice, which then finds it.
    """
    if not (posted_document.supplier_id or posted_document.project_id):
        return 0

    query = db.query(AIImportDocument).filter(
        AIImportDocument.id != posted_document.id,
        AIImportDocument.status.in_([
            AIImportDocumentStatus.AWAITING_REVIEW,
            AIImportDocumentStatus.AWAITING_AUTHORISATION,
            AIImportDocumentStatus.READY_TO_POST,
        ]),
    )
    if posted_document.supplier_id:
        query = query.filter(AIImportDocument.supplier_id == posted_document.supplier_id)
    if posted_document.project_id:
        query = query.filter(AIImportDocument.project_id == posted_document.project_id)

    count = 0
    for other in query.limit(100).all():
        try:
            reevaluate(db, other)
            count += 1
        except Exception as exc:                    # noqa: BLE001 - one bad doc must not stop the rest
            db.rollback()
            logger.warning("ai_import re-evaluation failed for document=%s: %s", other.id, exc)
    return count


# ── Reviewer actions ──────────────────────────────────────────────────────────

def get_document(db: Session, document_id: uuid.UUID) -> AIImportDocument:
    document = db.get(AIImportDocument, document_id)
    if not document:
        raise NotFoundError(f"Import document {document_id} not found.")
    return document


def _guard_mutable(document: AIImportDocument) -> None:
    if document.status in TERMINAL_STATES:
        raise ConflictError(
            f"This document is {document.status.value.lower()} and can no longer be changed. "
            f"Posted records are never silently overwritten."
        )


_LINE_PATH = re.compile(r"^line_items\.(\d+)\.(\w+)$")


def apply_corrections(
    db: Session,
    document: AIImportDocument,
    corrections: list[Any],
    actor: User,
) -> AIImportDocument:
    """
    Apply human corrections to the current extraction.

    Each change is written to ai_import_corrections before it is applied, so
    the original AI value and who changed it are always recoverable. Corrected
    fields are marked so the confidence rules stop penalising them.
    """
    _guard_mutable(document)

    record = current_extraction(db, document.id)
    if record is None:
        raise ValidationError("This document has no extraction to correct yet.")

    fields = dict(record.fields or {})
    line_items = [dict(i) for i in (record.line_items or [])]
    now = _now()

    for correction in corrections:
        path = correction.field_path
        line_match = _LINE_PATH.match(path)

        if line_match:
            index, attribute = int(line_match.group(1)), line_match.group(2)
            if index >= len(line_items):
                raise ValidationError(f"Line {index + 1} does not exist on this document.")
            if attribute not in ExtractedLineItem.model_fields:
                raise ValidationError(f"'{attribute}' is not a line item field.")
            before = line_items[index].get(attribute)
            line_items[index][attribute] = correction.value
            line_items[index]["confidence"] = 1.0
        else:
            if path not in fields and path not in set(COMMON_FIELDS):
                raise ValidationError(f"'{path}' is not a field on this document.")
            before = (fields.get(path) or {}).get("value")
            fields[path] = {
                **(fields.get(path) or {}),
                "value": correction.value,
                "confidence": 1.0,
                "source": "manual",
                "corrected": True,
                "corrected_by": str(actor.id),
                "validated": True,
                "page": (fields.get(path) or {}).get("page"),
            }

        db.add(AIImportCorrection(
            document_id=document.id,
            extraction_id=record.id,
            field_path=path,
            before_value=None if before is None else str(before)[:4000],
            after_value=None if correction.value is None else str(correction.value)[:4000],
            reason=correction.reason,
            corrected_by=actor.id,
            created_at=now,
        ))

    record.fields = fields
    record.line_items = line_items

    # Arithmetic is re-verified on the corrected numbers, not carried over.
    payload = payload_from_record(record)
    payload.document_type = document.document_type
    record.arithmetic_checks = [
        c.model_dump(mode="json") for c in extraction.verify_arithmetic(payload)
    ]

    audit_service.write_event(
        db, AuditAction.UPDATE, "ai_import_document", actor.id, document.id,
        after_value={"corrected_fields": [c.field_path for c in corrections]},
        notes="Extracted values corrected before posting.",
    )
    db.commit()
    return reevaluate(db, document)


def assign_context(
    db: Session,
    document: AIImportDocument,
    assignment: Any,
    actor: User,
) -> AIImportDocument:
    """Set the project, site, supplier, type or legacy flag by hand."""
    _guard_mutable(document)
    before = {
        "project_id": str(document.project_id) if document.project_id else None,
        "supplier_id": str(document.supplier_id) if document.supplier_id else None,
        "document_type": document.document_type.value,
    }

    if assignment.project_id is not None:
        from app.models.project import Project
        if not db.get(Project, assignment.project_id):
            raise NotFoundError("Project not found.")
        document.project_id = assignment.project_id
        _record_human_match(db, document, "project", assignment.project_id, actor)

    if assignment.site_id is not None:
        from app.models.site import Site
        site = db.get(Site, assignment.site_id)
        if not site:
            raise NotFoundError("Site not found.")
        if document.project_id and site.project_id != document.project_id:
            raise ValidationError("That site belongs to a different project.")
        document.site_id = assignment.site_id
        _record_human_match(db, document, "site", assignment.site_id, actor)

    if assignment.supplier_id is not None:
        from app.models.supplier import Supplier
        if not db.get(Supplier, assignment.supplier_id):
            raise NotFoundError("Supplier not found.")
        document.supplier_id = assignment.supplier_id
        _record_human_match(db, document, "supplier", assignment.supplier_id, actor)

    if assignment.document_type is not None:
        document.document_type = assignment.document_type
        document.document_type_confirmed_by = actor.id
        document.classification_confidence = Decimal("1.0")

    if assignment.is_legacy is not None:
        document.is_legacy = assignment.is_legacy

    audit_service.write_event(
        db, AuditAction.UPDATE, "ai_import_document", actor.id, document.id,
        before_value=before,
        after_value={
            "project_id": str(document.project_id) if document.project_id else None,
            "supplier_id": str(document.supplier_id) if document.supplier_id else None,
            "document_type": document.document_type.value,
        },
        notes="Document context set by a reviewer.",
    )
    db.commit()
    return reevaluate(db, document)


def _record_human_match(
    db: Session,
    document: AIImportDocument,
    target_type: str,
    target_id: uuid.UUID,
    actor: User,
) -> None:
    """A human decision outranks any recomputation, so it is stored as CONFIRMED."""
    db.query(AIImportMatch).filter(
        AIImportMatch.document_id == document.id,
        AIImportMatch.target_type == target_type,
    ).delete(synchronize_session=False)
    db.add(AIImportMatch(
        document_id=document.id,
        target_type=target_type,
        target_id=target_id,
        target_label=None,
        status=AIImportMatchStatus.CONFIRMED,
        method="manual",
        score=Decimal("1.0"),
        explanation=f"{target_type.replace('_', ' ').capitalize()} set by {actor.full_name or actor.email}.",
        evidence={"manual": True},
        decided_by=actor.id,
        decided_at=_now(),
        created_at=_now(),
    ))
    db.flush()


def decide_match(
    db: Session, document: AIImportDocument, match_id: uuid.UUID, accept: bool, actor: User,
    reason: Optional[str] = None,
) -> AIImportDocument:
    _guard_mutable(document)
    match = db.get(AIImportMatch, match_id)
    if not match or match.document_id != document.id:
        raise NotFoundError("Match not found on this document.")

    match.status = AIImportMatchStatus.CONFIRMED if accept else AIImportMatchStatus.REJECTED
    match.decided_by = actor.id
    match.decided_at = _now()
    if reason:
        match.explanation = f"{match.explanation or ''} Reviewer note: {reason}".strip()

    if accept and match.target_id:
        if match.target_type == "supplier":
            document.supplier_id = match.target_id
        elif match.target_type == "project":
            document.project_id = match.target_id
        elif match.target_type == "site":
            document.site_id = match.target_id

    audit_service.write_event(
        db, AuditAction.APPROVE if accept else AuditAction.REJECT,
        "ai_import_match", actor.id, match.id,
        after_value={"target_type": match.target_type, "target_id": str(match.target_id)},
    )
    db.commit()
    return reevaluate(db, document)


# Record types a reviewer may link a document to by hand. Project, site and
# supplier are deliberately NOT here: they are the document's own context and
# are set through assign_context, which runs its own project access check.
LINKABLE_TARGET_TYPES: frozenset[str] = frozenset({
    "purchase_order",
    "material_request",
    "existing_invoice",
    "existing_delivery",
})


def add_manual_match(
    db: Session, document: AIImportDocument, target_type: str, target_id: uuid.UUID, actor: User,
    reason: Optional[str] = None,
) -> AIImportDocument:
    """
    Link the document to a procurement record by hand.

    `target_type` is whitelisted and the target must belong to the document's
    project, so a manual link cannot move a document between projects or
    attach it to another project's records.
    """
    _guard_mutable(document)

    if target_type not in LINKABLE_TARGET_TYPES:
        raise ValidationError(
            f"'{target_type}' cannot be linked by hand. Linkable records are: "
            + ", ".join(sorted(LINKABLE_TARGET_TYPES))
            + ". The project, site and supplier are set on the document itself."
        )

    _verify_target_in_project(db, document, target_type, target_id)
    _record_human_match(db, document, target_type, target_id, actor)
    match = (
        db.query(AIImportMatch)
        .filter(AIImportMatch.document_id == document.id, AIImportMatch.target_type == target_type)
        .first()
    )
    if match and reason:
        match.explanation = f"{match.explanation} Reason: {reason}"
    db.commit()
    return reevaluate(db, document)


def target_project_id(
    db: Session, target_type: str, target_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """
    The project a linkable record belongs to, for the caller's access check.

    Raises NotFoundError for an unknown type or a missing record rather than
    returning None, so a caller can never read "no project" as "no restriction".
    """
    model = _linkable_model(target_type)
    target = db.get(model, target_id)
    if target is None:
        raise NotFoundError(f"{target_type.replace('_', ' ').capitalize()} not found.")
    return getattr(target, "project_id", None)


def _linkable_model(target_type: str):
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.models.purchase_order import PurchaseOrder

    model = {
        "purchase_order": PurchaseOrder,
        "material_request": MaterialRequest,
        "existing_invoice": Invoice,
        "existing_delivery": Delivery,
    }.get(target_type)
    if model is None:
        raise ValidationError(f"'{target_type}' is not a linkable record type.")
    return model


def _verify_target_in_project(
    db: Session, document: AIImportDocument, target_type: str, target_id: uuid.UUID,
) -> None:
    """
    The target must belong to the document's project.

    A document with no project yet is also refused: without a project there is
    nothing to compare against, and allowing the link would let an
    unclassified upload be attached to any project's records.
    """
    model = _linkable_model(target_type)
    target = db.get(model, target_id)
    if target is None:
        raise NotFoundError(f"{target_type.replace('_', ' ').capitalize()} not found.")

    if not document.project_id:
        raise ValidationError(
            "Set this document's project before linking it to a record, so the link "
            "can be checked against that project."
        )

    target_project = getattr(target, "project_id", None)
    if target_project != document.project_id:
        raise ValidationError(
            "That record belongs to a different project. Linking documents across "
            "projects is not permitted."
        )


def authorise_legacy(
    db: Session, document: AIImportDocument, note: str, actor: User,
) -> AIImportDocument:
    """
    Authorise a legacy import.

    This records that a named manager vouched for paper evidence. It is
    deliberately not the same thing as the digital approval workflow, and the
    imported record's notes say so.
    """
    _guard_mutable(document)
    if not document.is_legacy:
        raise ValidationError("This document is not marked as a legacy import.")
    if not note or len(note.strip()) < 3:
        raise ValidationError("A note describing the paper evidence is required.")

    document.authorised_by = actor.id
    document.authorised_at = _now()
    document.rejection_reason = None
    audit_service.write_event(
        db, AuditAction.APPROVE, "ai_import_document", actor.id, document.id,
        after_value={"legacy_authorisation_note": note.strip()},
        notes="Legacy import authorised. This is not a digital approval of the original transaction.",
    )
    db.commit()
    return reevaluate(db, document)


def mark_reviewed(db: Session, document: AIImportDocument, actor: User) -> AIImportDocument:
    _guard_mutable(document)
    document.reviewed_by = actor.id
    document.reviewed_at = _now()
    db.commit()
    return reevaluate(db, document)


def reject_document(
    db: Session, document: AIImportDocument, reason: str, actor: User,
) -> AIImportDocument:
    if document.status == AIImportDocumentStatus.POSTED:
        raise ConflictError(
            "This document has already been posted. Reverse the posted record in its own "
            "module rather than rejecting the import."
        )
    if document.status == AIImportDocumentStatus.REJECTED:
        raise ConflictError("This document has already been rejected.")
    document.status = AIImportDocumentStatus.REJECTED
    document.rejection_reason = reason
    document.reviewed_by = actor.id
    document.reviewed_at = _now()

    db.query(AIImportJob).filter(
        AIImportJob.document_id == document.id,
        AIImportJob.status.in_([AIImportJobStatus.PENDING, AIImportJobStatus.RUNNING]),
    ).update(
        {"status": AIImportJobStatus.DEAD, "last_error": "Document rejected by a reviewer."},
        synchronize_session=False,
    )

    audit_service.write_event(
        db, AuditAction.REJECT, "ai_import_document", actor.id, document.id,
        after_value={"reason": reason},
    )
    refresh_batch_status(db, document.batch)
    db.commit()
    db.refresh(document)
    return document


def retry_document(db: Session, document: AIImportDocument, actor: User) -> AIImportDocument:
    """
    Queue the document for processing again.

    Safe by construction: re-processing only rewrites extraction, matches and
    the policy verdict. Postings are protected by the unique idempotency key,
    so a retry can never produce a second stock movement or liability.
    """
    if document.status in TERMINAL_STATES:
        raise ConflictError(
            f"A {document.status.value.lower()} document is not reprocessed. "
            f"Postings already made are never repeated."
        )

    document.retry_count += 1
    document.failure_reason = None
    job = _enqueue(db, document)
    if job is None:
        raise ConflictError("This document is already queued for processing.")

    audit_service.write_event(
        db, AuditAction.UPDATE, "ai_import_document", actor.id, document.id,
        after_value={"retry_count": document.retry_count},
        notes="Reprocessing requested.",
    )
    db.commit()
    db.refresh(document)
    return document


# ── Evidence access ───────────────────────────────────────────────────────────

def purge_expired_documents(db: Session, dry_run: bool = True) -> dict:
    """
    Apply the configured retention period to stored import documents.

    Only the stored file and its raw extraction text are removed; the document
    row, its audit trail and any posting records are kept, because they are
    the evidence that a transaction was imported and by whom. A document that
    produced a posting is never purged at all while that posting stands.

    `dry_run=True` (the default) reports what would be removed without
    touching anything, so the retention window can be checked before it runs.
    """
    cutoff = _now() - timedelta(days=max(1, int(settings.AI_IMPORT_RETENTION_DAYS)))

    candidates = (
        db.query(AIImportDocument)
        .filter(
            AIImportDocument.created_at < cutoff,
            AIImportDocument.stored_path.isnot(None),
            AIImportDocument.stored_path != "",
        )
        .all()
    )

    purged: list[str] = []
    skipped: list[dict] = []

    for document in candidates:
        live_posting = any(p.reversed_at is None for p in document.postings)
        if live_posting:
            skipped.append({
                "document_id": str(document.id),
                "reason": "A posted transaction still refers to this document as its evidence.",
            })
            continue
        if dry_run:
            purged.append(str(document.id))
            continue

        from app.core.storage import delete_upload
        try:
            delete_upload(document.stored_path)
        except Exception as exc:                    # noqa: BLE001 - keep purging the rest
            logger.warning("ai_import retention could not delete %s: %s", document.stored_path, exc)
            skipped.append({"document_id": str(document.id), "reason": f"Storage delete failed: {exc}"})
            continue

        document.stored_path = ""
        document.failure_reason = (
            f"The stored file was removed on {_now().date().isoformat()} under the "
            f"{settings.AI_IMPORT_RETENTION_DAYS}-day retention policy. The extraction "
            f"record and audit history are retained."
        )
        for record in document.extractions:
            record.raw_text = None
            record.raw_response = None
        purged.append(str(document.id))

    if not dry_run and purged:
        audit_service.write_event(
            db, AuditAction.DELETE, "ai_import_retention", None, None,
            after_value={"purged": len(purged), "cutoff": cutoff.isoformat()},
            notes="Stored import files removed under the retention policy.",
        )
        db.commit()

    return {
        "dry_run": dry_run,
        "retention_days": settings.AI_IMPORT_RETENTION_DAYS,
        "cutoff": cutoff.isoformat(),
        "purged": purged,
        "purged_count": len(purged),
        "skipped": skipped,
    }


def signed_document_url(document: AIImportDocument) -> str:
    """
    Short-lived URL for viewing the original.

    Supplier documents are stored in the private bucket and are never served
    from a public path; the caller must already have passed the project check.
    """
    return create_signed_url(
        document.stored_path,
        expires_in=settings.EVIDENCE_SIGNED_URL_EXPIRY_SECONDS,
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

# Roles with company-wide reach. Everyone else sees only the projects they
# hold an explicit UserProjectAccess row for, plus their own uploads.
_COMPANY_WIDE_ROLES = frozenset({
    UserRole.OWNER,
    UserRole.OFFICE_ADMIN,
    UserRole.OFFICE_USER,
    UserRole.PROCUREMENT_LEAD,
    UserRole.READ_ONLY,
})


def filter_by_reason_code(documents: list, reason_code: str) -> list:
    """
    Narrow a document list to those carrying a given policy reason.

    The reasons live in a JSONB array, and the set of codes is open, so this
    filters in Python rather than committing to a JSON query the codes would
    outgrow. The lists involved are a review queue, not a report.
    """
    code = reason_code.strip().upper()
    return [
        d for d in documents
        if any((r or {}).get("code") == code for r in (d.outcome_reasons or []))
    ]


def visible_project_ids(db: Session, user: User) -> Optional[list[uuid.UUID]]:
    """
    Projects this user may see documents for.

    Returns None for company-wide roles, meaning "no restriction". A
    site-level user gets the explicit list, which may legitimately be empty —
    callers must treat an empty list as "nothing", never as "everything".
    """
    if user.role in _COMPANY_WIDE_ROLES:
        return None

    from app.models.access import UserProjectAccess
    return [
        row[0] for row in
        db.query(UserProjectAccess.project_id)
        .filter(UserProjectAccess.user_id == user.id)
        .all()
    ]


def _company_project_ids(db: Session, company_id: uuid.UUID) -> list[uuid.UUID]:
    """
    Projects belonging to a company.

    Documents carry no company of their own — company ownership lives on the
    project — so filtering by company means filtering by that company's
    projects. A company with no projects yields an empty list, which correctly
    matches nothing rather than everything.
    """
    from app.models.project import Project

    return [
        row[0] for row in
        db.query(Project.id).filter(Project.company_id == company_id).all()
    ]


def dashboard(db: Session, filters: Any, viewer: Optional[User] = None) -> dict:
    """
    Counts and queues for the reconciliation dashboard.

    `viewer` scopes the figures to the projects that user may see. It is
    optional only so internal callers can ask for an unscoped view; every API
    path passes it, because without it a site user would receive company-wide
    counts and the total value awaiting authorisation.
    """
    query = db.query(AIImportDocument)

    if viewer is not None:
        allowed = visible_project_ids(db, viewer)
        if allowed is not None:
            query = query.filter(
                (AIImportDocument.project_id.in_(allowed) if allowed else sa_false())
                | (AIImportDocument.uploaded_by == viewer.id)
            )

    if filters.company_id:
        query = query.filter(AIImportDocument.project_id.in_(_company_project_ids(db, filters.company_id)))
    if filters.project_id:
        query = query.filter(AIImportDocument.project_id == filters.project_id)
    if filters.site_id:
        query = query.filter(AIImportDocument.site_id == filters.site_id)
    if filters.supplier_id:
        query = query.filter(AIImportDocument.supplier_id == filters.supplier_id)
    if filters.document_type:
        query = query.filter(AIImportDocument.document_type == filters.document_type)
    if filters.status:
        query = query.filter(AIImportDocument.status == filters.status)
    if filters.uploaded_by:
        query = query.filter(AIImportDocument.uploaded_by == filters.uploaded_by)
    if filters.date_from:
        query = query.filter(AIImportDocument.created_at >= filters.date_from)
    if filters.date_to:
        query = query.filter(
            AIImportDocument.created_at < datetime.combine(
                filters.date_to, datetime.max.time(), tzinfo=timezone.utc,
            )
        )

    documents = query.all()
    ids = [d.id for d in documents]

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for doc in documents:
        by_status[doc.status.value] = by_status.get(doc.status.value, 0) + 1
        by_type[doc.document_type.value] = by_type.get(doc.document_type.value, 0) + 1

    def count(*statuses: AIImportDocumentStatus) -> int:
        return sum(by_status.get(s.value, 0) for s in statuses)

    classified = sum(
        1 for d in documents if d.document_type != AIImportDocumentType.UNKNOWN
    )

    # Reason-driven queues — these are the operational worklists.
    reason_counts: dict[str, int] = {}
    for doc in documents:
        for reason in (doc.outcome_reasons or []):
            code = reason.get("code", "UNKNOWN")
            reason_counts[code] = reason_counts.get(code, 0) + 1

    failed_jobs = (
        db.query(func.count(AIImportJob.id))
        .filter(
            AIImportJob.status.in_([AIImportJobStatus.FAILED, AIImportJobStatus.DEAD]),
            AIImportJob.document_id.in_(ids) if ids else sa_false(),
        )
        .scalar()
    ) or 0

    posted_rows = (
        db.query(AIImportPosting)
        .filter(AIImportPosting.document_id.in_(ids))
        .all()
    ) if ids else []

    cost_rows = (
        db.query(
            func.coalesce(func.sum(AIImportExtraction.cost_usd), 0),
            func.coalesce(func.sum(AIImportExtraction.input_tokens), 0),
            func.coalesce(func.sum(AIImportExtraction.output_tokens), 0),
        )
        .filter(AIImportExtraction.document_id.in_(ids))
        .one()
    ) if ids else (0, 0, 0)

    amounts_awaiting = Decimal("0")
    for doc in documents:
        if doc.status not in (
            AIImportDocumentStatus.AWAITING_REVIEW,
            AIImportDocumentStatus.AWAITING_AUTHORISATION,
            AIImportDocumentStatus.READY_TO_POST,
        ):
            continue
        if doc.document_type != AIImportDocumentType.SUPPLIER_INVOICE:
            continue
        record = current_extraction(db, doc.id)
        value = ((record.fields or {}).get("total_amount") or {}).get("value") if record else None
        try:
            if value is not None:
                amounts_awaiting += Decimal(str(value))
        except (ValueError, ArithmeticError):
            pass

    return {
        "totals": {
            "uploaded": len(documents),
            "classified": classified,
            "processed": count(
                AIImportDocumentStatus.READY_TO_POST,
                AIImportDocumentStatus.POSTED,
                AIImportDocumentStatus.PARTIALLY_POSTED,
                AIImportDocumentStatus.AWAITING_REVIEW,
                AIImportDocumentStatus.AWAITING_AUTHORISATION,
            ),
            "awaiting_review": count(AIImportDocumentStatus.AWAITING_REVIEW),
            "awaiting_authorisation": count(AIImportDocumentStatus.AWAITING_AUTHORISATION),
            "ready_to_post": count(AIImportDocumentStatus.READY_TO_POST),
            "posted": count(AIImportDocumentStatus.POSTED),
            "duplicates": count(AIImportDocumentStatus.DUPLICATE),
            "failed": count(AIImportDocumentStatus.FAILED),
            "rejected": count(AIImportDocumentStatus.REJECTED),
            "in_progress": count(
                AIImportDocumentStatus.UPLOADED,
                AIImportDocumentStatus.QUEUED,
                AIImportDocumentStatus.PROCESSING,
                AIImportDocumentStatus.EXTRACTED,
                AIImportDocumentStatus.CLASSIFIED,
                AIImportDocumentStatus.MATCHING,
            ),
            "failed_jobs": failed_jobs,
            "posted_transactions": len([p for p in posted_rows if p.entity_id and not p.reversed_at]),
            "incomplete_postings": len([p for p in posted_rows if not p.entity_id and not p.reversed_at]),
        },
        "queues": {
            "unmatched_invoices": reason_counts.get("NO_PURCHASE_ORDER", 0),
            "missing_purchase_orders": reason_counts.get("NO_PURCHASE_ORDER", 0),
            "unconfirmed_receipts": (
                reason_counts.get("NO_GOODS_RECEIPT", 0)
                + reason_counts.get("INVOICE_FOR_UNDELIVERED_GOODS", 0)
            ),
            "stock_discrepancies": (
                reason_counts.get("QUANTITY_DISCREPANCY", 0)
                + reason_counts.get("ITEM_NOT_ORDERED", 0)
                + reason_counts.get("UNIT_NOT_COMPARABLE", 0)
            ),
            "invoice_discrepancies": (
                reason_counts.get("PRICE_DISCREPANCY", 0)
                + reason_counts.get("TOTAL_DISCREPANCY", 0)
                + reason_counts.get("ARITHMETIC_INVALID", 0)
            ),
            "duplicate_documents": (
                reason_counts.get("DUPLICATE_FILE", 0)
                + reason_counts.get("DUPLICATE_INVOICE_NUMBER", 0)
                + reason_counts.get("DUPLICATE_DELIVERY", 0)
            ),
            "unknown_suppliers": reason_counts.get("UNKNOWN_SUPPLIER", 0),
            "unknown_projects": reason_counts.get("UNKNOWN_PROJECT", 0),
            "missing_authorisation": (
                reason_counts.get("MISSING_AUTHORISATION", 0)
                + reason_counts.get("LEGACY_AUTHORISATION_REQUIRED", 0)
            ),
        },
        "amounts_awaiting_authorisation": float(amounts_awaiting),
        "by_status": by_status,
        "by_document_type": by_type,
        "reason_counts": reason_counts,
        "ai_usage": {
            "cost_usd": float(cost_rows[0] or 0),
            "input_tokens": int(cost_rows[1] or 0),
            "output_tokens": int(cost_rows[2] or 0),
            "provider_configured": extraction.ai_available(),
            "model": extraction.ai_model(),
        },
    }
