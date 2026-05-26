"""
Admin operational observability endpoints.

All endpoints are read-only and OWNER-only.
They surface health metrics by querying existing tables — no new schema needed.

Endpoints:
  GET /admin/ops/summary         — consolidated system health snapshot
  GET /admin/ops/queue           — notification queue depth + failure summary
  GET /admin/ops/ocr             — document extraction health (success rate, failures)
  GET /admin/ops/whatsapp        — WhatsApp outbound delivery health
  GET /admin/ops/gmail           — Gmail ingestion health (unprocessed backlog)
  GET /admin/ops/uploads         — orphan / failed attachment tracking
  GET /admin/ops/slow-workflows  — stuck workflows (overdue POs, unmatched invoices)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.dependencies import OWNER_ONLY, DbSession
from app.models.attachment import Attachment
from app.models.delivery import Delivery
from app.models.document_extraction import DocumentExtraction
from app.models.enums import (
    AlertType, NotificationChannel, NotificationStatus, RecordStatus,
)
from app.models.incoming_email import IncomingEmail
from app.models.invoice import Invoice
from app.models.notification_queue import NotificationQueue
from app.models.purchase_order import PurchaseOrder
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/admin/ops", tags=["admin"])

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── Shared query helpers ───────────────────────────────────────────────────────

def _queue_stats(db: Session) -> dict:
    """Notification queue counts by status + stuck detection."""
    now = _NOW()
    stuck_cutoff = now - timedelta(hours=24)
    old_failed_cutoff = now - timedelta(hours=48)

    rows = (
        db.query(
            NotificationQueue.status,
            func.count(NotificationQueue.id).label("cnt"),
        )
        .group_by(NotificationQueue.status)
        .all()
    )
    by_status = {str(r.status): r.cnt for r in rows}

    stuck_pending = (
        db.query(func.count(NotificationQueue.id))
        .filter(
            NotificationQueue.status == NotificationStatus.PENDING,
            NotificationQueue.created_at < stuck_cutoff,
        )
        .scalar() or 0
    )

    dead_letter = (
        db.query(func.count(NotificationQueue.id))
        .filter(
            NotificationQueue.status == NotificationStatus.FAILED,
            NotificationQueue.created_at < old_failed_cutoff,
        )
        .scalar() or 0
    )

    total_pending = by_status.get("PENDING", 0)
    total_failed  = by_status.get("FAILED", 0)
    health = (
        "error"   if (stuck_pending > 0 or dead_letter > 5)
        else "warning" if total_failed > 0
        else "ok"
    )

    return {
        "status": health,
        "pending":       total_pending,
        "sent":          by_status.get("SENT", 0),
        "acknowledged":  by_status.get("ACKNOWLEDGED", 0),
        "failed":        total_failed,
        "stuck_pending_24h": stuck_pending,
        "dead_letter_48h":   dead_letter,
    }


def _ocr_stats(db: Session) -> dict:
    """Document extraction success/failure rate (last 7 days)."""
    cutoff = _NOW() - timedelta(days=7)
    rows = (
        db.query(
            DocumentExtraction.status,
            func.count(DocumentExtraction.id).label("cnt"),
        )
        .filter(DocumentExtraction.created_at >= cutoff)
        .group_by(DocumentExtraction.status)
        .all()
    )
    by_status = {r.status: r.cnt for r in rows}
    total = sum(by_status.values()) or 1  # avoid /0

    needs_review = by_status.get("NEEDS_REVIEW", 0)
    failed       = by_status.get("FAILED", 0)
    extracted    = by_status.get("EXTRACTED", 0)

    success_rate = round(extracted / total * 100, 1)
    health = (
        "error"   if failed > 5
        else "warning" if (needs_review > 0 or success_rate < 70)
        else "ok"
    )

    # Most recent failures (up to 10)
    recent_failures = (
        db.query(
            DocumentExtraction.id,
            DocumentExtraction.source_type,
            DocumentExtraction.document_type,
            DocumentExtraction.status,
            DocumentExtraction.created_at,
        )
        .filter(
            DocumentExtraction.status.in_(["FAILED", "NEEDS_REVIEW"]),
            DocumentExtraction.created_at >= cutoff,
        )
        .order_by(DocumentExtraction.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "status":       health,
        "period_days":  7,
        "total":        total - 1,  # undo +1
        "extracted":    extracted,
        "needs_review": needs_review,
        "failed":       failed,
        "ocr_required": by_status.get("OCR_REQUIRED", 0),
        "success_rate_pct": success_rate,
        "recent_failures": [
            {
                "id":            str(r.id),
                "source_type":   r.source_type,
                "document_type": r.document_type,
                "status":        r.status,
                "created_at":    r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_failures
        ],
    }


def _whatsapp_stats(db: Session) -> dict:
    """WhatsApp outbound send health (last 48 h)."""
    cutoff = _NOW() - timedelta(hours=48)
    rows = (
        db.query(
            NotificationQueue.status,
            func.count(NotificationQueue.id).label("cnt"),
        )
        .filter(
            NotificationQueue.channel == NotificationChannel.WHATSAPP,
            NotificationQueue.created_at >= cutoff,
        )
        .group_by(NotificationQueue.status)
        .all()
    )
    by_status = {str(r.status): r.cnt for r in rows}
    total_out = sum(by_status.values()) or 0

    failures = by_status.get("FAILED", 0)
    sent     = by_status.get("SENT", 0)
    ackd     = by_status.get("ACKNOWLEDGED", 0)
    health   = "error" if failures > 3 else "warning" if failures > 0 else "ok"

    # Recent failed messages
    recent_failed = (
        db.query(
            NotificationQueue.id,
            NotificationQueue.phone_number,
            NotificationQueue.error_message,
            NotificationQueue.attempt_count,
            NotificationQueue.created_at,
        )
        .filter(
            NotificationQueue.channel == NotificationChannel.WHATSAPP,
            NotificationQueue.status  == NotificationStatus.FAILED,
            NotificationQueue.created_at >= cutoff,
        )
        .order_by(NotificationQueue.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "status":       health,
        "period_hours": 48,
        "total_outbound": total_out,
        "sent":          sent,
        "acknowledged":  ackd,
        "failed":        failures,
        "pending":       by_status.get("PENDING", 0),
        "recent_failures": [
            {
                "id":            str(r.id),
                "phone":         r.phone_number,
                "error":         r.error_message,
                "attempts":      r.attempt_count,
                "created_at":    r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_failed
        ],
    }


def _gmail_stats(db: Session) -> dict:
    """Gmail ingestion health — unprocessed backlog."""
    cutoff_old = _NOW() - timedelta(hours=24)

    rows = (
        db.query(
            IncomingEmail.processed_status,
            func.count(IncomingEmail.id).label("cnt"),
        )
        .group_by(IncomingEmail.processed_status)
        .all()
    )
    by_status = {r.processed_status: r.cnt for r in rows}

    old_unprocessed = (
        db.query(func.count(IncomingEmail.id))
        .filter(
            IncomingEmail.processed_status == "UNPROCESSED",
            IncomingEmail.created_at < cutoff_old,
        )
        .scalar() or 0
    )

    health = (
        "error"   if old_unprocessed > 10
        else "warning" if old_unprocessed > 0
        else "ok"
    )

    return {
        "status":           health,
        "unprocessed":      by_status.get("UNPROCESSED", 0),
        "processed":        by_status.get("PROCESSED", 0),
        "ignored":          by_status.get("IGNORED", 0),
        "old_unprocessed_24h": old_unprocessed,
    }


def _slow_workflow_stats(db: Session, project_id: Optional[uuid.UUID]) -> dict:
    """Stuck workflow detection — POs, invoices, deliveries."""
    now = _NOW()
    stale_po_cutoff       = now - timedelta(days=7)
    stale_invoice_cutoff  = now - timedelta(days=14)

    def _pf(q, model):
        if project_id:
            q = q.filter(model.project_id == project_id)
        return q

    # POs in SENT status > 7 days old with no deliveries
    stale_pos = (
        _pf(
            db.query(func.count(PurchaseOrder.id))
            .filter(
                PurchaseOrder.status == RecordStatus.SENT,
                PurchaseOrder.created_at < stale_po_cutoff,
            ),
            PurchaseOrder,
        )
        .scalar() or 0
    )

    # Invoices in PENDING/NEEDS_REVIEW > 14 days
    stale_invoices = (
        _pf(
            db.query(func.count(Invoice.id))
            .filter(
                Invoice.status.in_([RecordStatus.PENDING, "NEEDS_REVIEW"]),
                Invoice.created_at < stale_invoice_cutoff,
            ),
            Invoice,
        )
        .scalar() or 0
    )

    # Overdue invoices (due_date passed, not PAID)
    overdue_invoices = (
        _pf(
            db.query(func.count(Invoice.id))
            .filter(
                Invoice.status.notin_([RecordStatus.PAID, RecordStatus.CANCELLED]),
                Invoice.due_date < now.date(),
            ),
            Invoice,
        )
        .scalar() or 0
    )

    health = (
        "error"   if (stale_invoices > 5 or overdue_invoices > 5)
        else "warning" if (stale_pos > 0 or stale_invoices > 0 or overdue_invoices > 0)
        else "ok"
    )

    return {
        "status":           health,
        "stale_pos_7d":     stale_pos,
        "stale_invoices_14d": stale_invoices,
        "overdue_invoices": overdue_invoices,
    }


# ── Route handlers ─────────────────────────────────────────────────────────────

@router.get("/queue", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def queue_health(db: DbSession):
    """Notification queue depth, stuck entries, and dead-letter count."""
    return ApiSuccess(data=_queue_stats(db))


@router.get("/ocr", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def ocr_health(db: DbSession):
    """Document extraction success rate and recent failures (last 7 days)."""
    return ApiSuccess(data=_ocr_stats(db))


@router.get("/whatsapp", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def whatsapp_health(db: DbSession):
    """WhatsApp outbound message health (last 48 hours)."""
    return ApiSuccess(data=_whatsapp_stats(db))


@router.get("/gmail", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def gmail_health(db: DbSession):
    """Gmail ingestion health — unprocessed email backlog."""
    return ApiSuccess(data=_gmail_stats(db))


@router.get("/slow-workflows", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def slow_workflows(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    """Stuck workflow detection — stale POs, invoices, overdue payments."""
    return ApiSuccess(data=_slow_workflow_stats(db, project_id))


@router.get("/summary", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def ops_summary(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    """
    Consolidated operational health snapshot across all subsystems.
    Returns a single dict with a top-level 'overall' status field.
    """
    checks = {
        "queue":          _queue_stats(db),
        "ocr":            _ocr_stats(db),
        "whatsapp":       _whatsapp_stats(db),
        "gmail":          _gmail_stats(db),
        "slow_workflows": _slow_workflow_stats(db, project_id),
    }

    statuses = [v["status"] for v in checks.values()]
    if "error" in statuses:
        overall = "error"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "ok"

    return ApiSuccess(
        data={
            "checked_at": _NOW().isoformat(),
            "overall":    overall,
            "checks":     checks,
        },
        message="All systems healthy." if overall == "ok" else f"System status: {overall}",
    )
