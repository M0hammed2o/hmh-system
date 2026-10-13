"""
AI Document Import — background worker.

Mirrors the notification-queue pattern already in this codebase: a job table
drained by an in-process asyncio loop in main.py, with an external cron
endpoint as a safety net. No new broker, no new runtime dependency.

Correctness properties:

  * Exactly one worker claims a job. `SELECT ... FOR UPDATE SKIP LOCKED` hands
    each row to a single transaction, so two processes draining at the same
    time cannot both run the same document.
  * A restart resumes. A job left RUNNING because its process died is
    reclaimed once its lock passes AI_IMPORT_JOB_STALE_MINUTES.
  * Provider outages retry, defects do not. A transient failure reschedules
    with exponential backoff; a deterministic failure is recorded against the
    document for a person to look at.
  * A retry cannot double-post. Reprocessing only rewrites extraction,
    matching and the policy verdict; postings are guarded by the unique
    idempotency key in ai_import_postings.
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.ai_import import AIImportDocument, AIImportJob
from app.models.enums import AIImportDocumentStatus, AIImportJobStatus
from app.services import ai_import_service
from app.services.ai_import_extraction_service import ExtractionTransientError

logger = get_logger(__name__)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:100]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt: int) -> int:
    """Exponential backoff, capped so a long outage still retries hourly."""
    base = max(1, int(settings.AI_IMPORT_RETRY_BACKOFF_SECONDS))
    return min(base * (2 ** max(0, attempt - 1)), 3600)


def reclaim_stale_jobs(db: Session) -> int:
    """
    Return jobs abandoned by a dead process to the queue.

    This is what makes "resume after process restart" true: a job that was
    RUNNING when the container stopped becomes PENDING again once its lock is
    older than the stale threshold.
    """
    cutoff = _now() - timedelta(minutes=settings.AI_IMPORT_JOB_STALE_MINUTES)
    stale = (
        db.query(AIImportJob)
        .filter(
            AIImportJob.status == AIImportJobStatus.RUNNING,
            AIImportJob.locked_at.isnot(None),
            AIImportJob.locked_at < cutoff,
        )
        .all()
    )
    for job in stale:
        # Read the owner before clearing it — the dead worker's identity is
        # the useful part of the message.
        previous_owner = job.locked_by or "unknown"
        job.status = AIImportJobStatus.PENDING
        job.locked_at = None
        job.locked_by = None
        job.next_attempt_at = _now()
        job.last_error = (
            f"Worker {previous_owner} stopped without finishing this job; "
            f"it was returned to the queue."
        )
        logger.warning(
            "ai_import reclaimed stale job=%s document=%s from worker=%s",
            job.id, job.document_id, previous_owner,
        )
    if stale:
        db.commit()
    return len(stale)


def _claim_next(db: Session) -> Optional[AIImportJob]:
    """
    Take the next due job, locking it against other workers.

    FOR UPDATE SKIP LOCKED is what prevents duplicate concurrent execution:
    a row already locked by another transaction is skipped, not waited on.
    """
    row = db.execute(
        text("""
            SELECT id FROM ai_import_jobs
            WHERE status = 'PENDING'
              AND (next_attempt_at IS NULL OR next_attempt_at <= now())
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """)
    ).first()
    if row is None:
        return None

    job = db.get(AIImportJob, row[0])
    if job is None or job.status != AIImportJobStatus.PENDING:
        return None

    job.status = AIImportJobStatus.RUNNING
    job.attempt_count += 1
    job.last_attempt_at = _now()
    job.locked_at = _now()
    job.locked_by = worker_id()
    db.commit()
    return job


def _fail(db: Session, job: AIImportJob, document: Optional[AIImportDocument], error: str, retryable: bool) -> None:
    job.locked_at = None
    job.locked_by = None
    job.last_error = error[:4000]

    if retryable and job.attempt_count < job.max_attempts:
        job.status = AIImportJobStatus.PENDING
        job.next_attempt_at = _now() + timedelta(seconds=_backoff_seconds(job.attempt_count))
        if document is not None:
            document.status = AIImportDocumentStatus.QUEUED
            document.failure_reason = (
                f"Processing attempt {job.attempt_count} did not succeed and will be retried: {error}"
            )[:2000]
        logger.warning(
            "ai_import job=%s retry %d/%d in %ds: %s",
            job.id, job.attempt_count, job.max_attempts,
            _backoff_seconds(job.attempt_count), error,
        )
    else:
        # A retryable failure that exhausted its budget is FAILED (it could
        # have succeeded); one that was never retryable is DEAD (it never
        # could). The queue health report distinguishes the two.
        job.status = AIImportJobStatus.FAILED if retryable else AIImportJobStatus.DEAD
        job.completed_at = _now()
        if document is not None:
            document.status = AIImportDocumentStatus.FAILED
            document.failure_reason = (
                f"Processing failed after {job.attempt_count} attempt(s): {error}. "
                f"Fix the underlying problem and retry this document."
            )[:2000]
        logger.error("ai_import job=%s permanently failed: %s", job.id, error)

    db.commit()


def _record_failure(
    db: Session, job_id: uuid.UUID, document_id: uuid.UUID, error: str, retryable: bool,
) -> None:
    """
    Record a failed attempt against the job and its document.

    The attempt is always rolled back first. `process_document` deletes the
    document's proposed matches and writes a new extraction row before it
    commits, so recording the failure without rolling back would persist a
    half-processed document — in particular one whose previous matches are
    gone. The rollback returns it to the state it had when the job was claimed.

    The rollback expires every ORM instance, so the job and document are
    re-read by id rather than taken from the caller's objects.
    """
    db.rollback()
    job = db.get(AIImportJob, job_id)
    if job is None:
        logger.warning("ai_import job=%s vanished while recording a failure", job_id)
        return
    _fail(db, job, db.get(AIImportDocument, document_id), error, retryable=retryable)


def run_job(db: Session, job: AIImportJob) -> bool:
    """
    Execute one claimed job. Returns True when it completed.

    `job_id` and `document_id` are captured as plain values up front: a
    rollback in the failure paths below expires every ORM instance, so the
    rows must be re-fetched rather than read off the stale objects.
    """
    job_id = job.id
    document_id = job.document_id

    document = db.get(AIImportDocument, document_id)
    if document is None:
        job.status = AIImportJobStatus.DEAD
        job.last_error = "The document no longer exists."
        job.completed_at = _now()
        job.locked_at = None
        db.commit()
        return False

    if document.status in ai_import_service.TERMINAL_STATES:
        job.status = AIImportJobStatus.COMPLETED
        job.completed_at = _now()
        job.locked_at = None
        job.last_error = f"Document was already {document.status.value.lower()}; nothing to do."
        db.commit()
        return True

    try:
        ai_import_service.process_document(db, document)
    except ExtractionTransientError as exc:
        _record_failure(db, job_id, document_id, str(exc), retryable=True)
        return False
    except Exception as exc:                        # noqa: BLE001 - recorded, not raised
        logger.exception("ai_import job=%s failed", job_id)
        _record_failure(
            db, job_id, document_id, f"{type(exc).__name__}: {exc}", retryable=False,
        )
        return False

    job = db.get(AIImportJob, job_id)
    if job is not None:
        job.status = AIImportJobStatus.COMPLETED
        job.completed_at = _now()
        job.locked_at = None
        job.locked_by = None
        job.last_error = None
    document = db.get(AIImportDocument, document_id)
    if document is not None and document.batch is not None:
        ai_import_service.refresh_batch_status(db, document.batch)
    db.commit()
    return True


def drain_once(db: Session, limit: Optional[int] = None) -> dict:
    """
    Process up to `limit` due jobs.

    Called by the in-process loop and by the internal cron endpoint. Safe to
    run concurrently from both.
    """
    if not settings.AI_IMPORT_ENABLED:
        return {"skipped": "AI_IMPORT_ENABLED is false", "processed": 0, "failed": 0}

    reclaimed = reclaim_stale_jobs(db)
    budget = limit if limit is not None else settings.AI_IMPORT_WORKER_BATCH_SIZE

    processed = failed = 0
    for _ in range(max(1, budget)):
        job = _claim_next(db)
        if job is None:
            break
        if run_job(db, job):
            processed += 1
        else:
            failed += 1

    return {"processed": processed, "failed": failed, "reclaimed": reclaimed}


def queue_health(db: Session) -> dict:
    """Operational snapshot for the ops dashboard."""
    from sqlalchemy import func

    rows = (
        db.query(AIImportJob.status, func.count(AIImportJob.id))
        .group_by(AIImportJob.status)
        .all()
    )
    counts = {status.value: count for status, count in rows}

    oldest = (
        db.query(func.min(AIImportJob.created_at))
        .filter(AIImportJob.status == AIImportJobStatus.PENDING)
        .scalar()
    )

    from app.services.ai_import_posting_service import incomplete_postings
    incomplete = incomplete_postings(db)

    return {
        "enabled": settings.AI_IMPORT_ENABLED,
        "worker_enabled": settings.AI_IMPORT_WORKER_ENABLED,
        "auto_post_enabled": settings.AI_IMPORT_AUTO_POST_ENABLED,
        "jobs": counts,
        "oldest_pending_at": oldest.isoformat() if oldest else None,
        "worker_id": worker_id(),
        "incomplete_postings": [
            {
                "posting_id": str(p.id),
                "document_id": str(p.document_id),
                "entity_type": p.entity_type,
                "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                "action": "Verify in the destination module whether this record exists.",
            }
            for p in incomplete
        ],
    }
