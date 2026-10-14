"""
AI Document Import & Reconciliation Engine — persistence models.

This module stores only ingestion state. It owns no business balances:
stock, supplier liabilities, material requests and purchase orders are
created exclusively by calling the existing domain services, and the
`ai_import_postings` table records *that* a posting happened so a retry
can never produce a second one.

Tables
  ai_import_batches     — one upload session
  ai_import_documents   — one uploaded file and its lifecycle state
  ai_import_extractions — a versioned extraction attempt for a document
  ai_import_matches     — proposed/confirmed links to existing records
  ai_import_postings    — immutable record of business records created
  ai_import_jobs        — background work queue with retry/backoff
  ai_import_corrections — field-level human corrections (audit)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    AIImportBatchStatus,
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportJobStatus,
    AIImportMatchStatus,
    AIImportProcessingOutcome,
)


# ── Batch ─────────────────────────────────────────────────────────────────────

class AIImportBatch(TimestampMixin, Base):
    """One upload session. A batch may mix document types and projects."""

    __tablename__ = "ai_import_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)

    # Optional hints supplied by the uploader. Never override what the
    # document itself says without an explicit human confirmation.
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )

    # Historical paperwork predating the system. Drives the legacy-import
    # authorisation path: such records are never shown as digitally approved.
    is_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[AIImportBatchStatus] = mapped_column(
        Enum(AIImportBatchStatus, name="ai_import_batch_status_enum", create_type=False),
        nullable=False,
        default=AIImportBatchStatus.OPEN,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    documents: Mapped[list["AIImportDocument"]] = relationship(
        "AIImportDocument", back_populates="batch", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportBatch {self.reference} {self.status}>"


# ── Document ──────────────────────────────────────────────────────────────────

class AIImportDocument(TimestampMixin, Base):
    """One uploaded file travelling through the ingestion state machine."""

    __tablename__ = "ai_import_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_batches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── File identity ─────────────────────────────────────────────────────────
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SHA-256 of the file bytes. Identical content under a different filename
    # is still the same document — this is the duplicate-file signal.
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: Mapped[AIImportDocumentStatus] = mapped_column(
        Enum(AIImportDocumentStatus, name="ai_import_document_status_enum", create_type=False),
        nullable=False,
        default=AIImportDocumentStatus.UPLOADED,
        index=True,
    )
    processing_outcome: Mapped[Optional[AIImportProcessingOutcome]] = mapped_column(
        Enum(AIImportProcessingOutcome, name="ai_import_processing_outcome_enum", create_type=False),
        nullable=True,
        index=True,
    )
    # Machine-readable reasons behind processing_outcome, e.g.
    # [{"code": "ARITHMETIC_INVALID", "message": "...", "severity": "BLOCKED"}]
    outcome_reasons: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # ── Classification ────────────────────────────────────────────────────────
    document_type: Mapped[AIImportDocumentType] = mapped_column(
        Enum(AIImportDocumentType, name="ai_import_document_type_enum", create_type=False),
        nullable=False,
        default=AIImportDocumentType.UNKNOWN,
        index=True,
    )
    classification_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    # Set when a human overrides the classifier.
    document_type_confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── Resolved business context (filled by matching, confirmable by a human) ─
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Historical document: evidence exists on paper, digital approvals do not.
    is_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Duplicate bookkeeping — points at the document this one duplicates.
    duplicate_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="SET NULL"), nullable=True
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Review / authorisation ────────────────────────────────────────────────
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    authorised_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authorised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    batch: Mapped["AIImportBatch"] = relationship("AIImportBatch", back_populates="documents")
    extractions: Mapped[list["AIImportExtraction"]] = relationship(
        "AIImportExtraction", back_populates="document",
        cascade="all, delete-orphan", order_by="AIImportExtraction.created_at",
    )
    matches: Mapped[list["AIImportMatch"]] = relationship(
        "AIImportMatch", back_populates="document", cascade="all, delete-orphan"
    )
    postings: Mapped[list["AIImportPosting"]] = relationship(
        "AIImportPosting", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportDocument {self.file_name} {self.document_type} {self.status}>"


# ── Extraction ────────────────────────────────────────────────────────────────

class AIImportExtraction(Base):
    """
    One extraction attempt. Attempts are append-only so the original AI output
    survives every later human correction.
    """

    __tablename__ = "ai_import_extractions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Provenance — required to reproduce or audit any extraction.
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)       # anthropic | regex | none
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extraction_mode: Mapped[str] = mapped_column(String(30), nullable=False)  # vision | text | regex

    # fields: {field_name: {value, page, confidence, source, corrected, corrected_by}}
    fields: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    line_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Arithmetic recomputed by us, never trusted from the model.
    arithmetic_checks: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    overall_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # Cost / usage tracking.
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    document: Mapped["AIImportDocument"] = relationship(
        "AIImportDocument", back_populates="extractions"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportExtraction {self.document_id} {self.provider}/{self.extraction_mode}>"


# ── Match ─────────────────────────────────────────────────────────────────────

class AIImportMatch(Base):
    """
    A link between an uploaded document and an existing business record.

    AI may propose a match; `status` only becomes CONFIRMED through
    deterministic validation or an explicit human decision.
    """

    __tablename__ = "ai_import_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Free-form entity reference so new record types need no schema change.
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    target_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[AIImportMatchStatus] = mapped_column(
        Enum(AIImportMatchStatus, name="ai_import_match_status_enum", create_type=False),
        nullable=False,
        default=AIImportMatchStatus.PROPOSED,
        index=True,
    )
    # exact_reference | supplier_fuzzy | line_item | amount | composite | manual
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    # Human-readable justification shown in the UI.
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Structured evidence behind the explanation.
    evidence: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    document: Mapped["AIImportDocument"] = relationship(
        "AIImportDocument", back_populates="matches"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportMatch {self.target_type}:{self.target_id} {self.status}>"


# ── Posting ───────────────────────────────────────────────────────────────────

class AIImportPosting(Base):
    """
    Immutable record that a business record was created from a document.

    `idempotency_key` is UNIQUE: it is the hard guarantee that retrying a
    document can never create a second material request, purchase order,
    goods receipt or supplier invoice.
    """

    __tablename__ = "ai_import_postings"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ai_import_postings_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)

    # material_request | purchase_order | delivery | goods_receipt | invoice | supplier
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # NULL while the posting is in flight. The row is inserted and committed
    # BEFORE the domain service runs, so the unique idempotency key is claimed
    # first: if the process dies mid-post, a retry is refused rather than
    # creating a second business record. A row left with entity_id NULL means
    # "claimed, outcome unconfirmed" and is surfaced for manual verification.
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    entity_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Snapshot of the payload handed to the domain service.
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    posted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["AIImportDocument"] = relationship(
        "AIImportDocument", back_populates="postings"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportPosting {self.entity_type}:{self.entity_id}>"


# ── Job queue ─────────────────────────────────────────────────────────────────

class AIImportJob(Base):
    """
    Background work item. Mirrors the notification_queue pattern already used
    in this codebase: status + attempt_count + next_attempt_at, drained by an
    in-process loop and by an external cron safety net.
    """

    __tablename__ = "ai_import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # process = classify + extract + validate + match
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, default="process")

    status: Mapped[AIImportJobStatus] = mapped_column(
        Enum(AIImportJobStatus, name="ai_import_job_status_enum", create_type=False),
        nullable=False,
        default=AIImportJobStatus.PENDING,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Crash recovery: a RUNNING row whose lock is older than the stale timeout
    # is reclaimed by the next worker, so a process restart resumes the work.
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportJob {self.job_type} {self.status} attempts={self.attempt_count}>"


# ── Correction audit ──────────────────────────────────────────────────────────

class AIImportCorrection(Base):
    """Field-level human correction of an extracted value."""

    __tablename__ = "ai_import_corrections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_import_extractions.id", ondelete="SET NULL"), nullable=True
    )

    # Dotted path, e.g. "total_amount" or "line_items.2.quantity".
    field_path: Mapped[str] = mapped_column(String(200), nullable=False)
    before_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AIImportCorrection {self.field_path}>"
