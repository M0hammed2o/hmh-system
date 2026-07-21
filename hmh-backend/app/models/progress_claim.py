"""
Municipality Progress Claim models.

A MunicipalityProgressClaim aggregates completed work evidence for a billing period
into a structured document that can be reviewed, adjusted, and then handed off
for pricing. It contains NO monetary amounts — pricing is added by a human after
the claim reaches READY_FOR_PRICING status.

Separate from MunicipalityInvoice (which is the financial/payment document).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import ProgressClaimStatus, ClaimSourceType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MunicipalityProgressClaim(Base):
    __tablename__ = "municipality_progress_claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_number = Column(String(50), unique=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)

    claim_title = Column(String(200), nullable=False)
    municipality_name = Column(String(200), nullable=False, default="Ethekweni Municipality")
    cert_number = Column(String(100), nullable=True)

    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    reporting_cutoff_date = Column(Date, nullable=False)

    status = Column(String(30), nullable=False, default=ProgressClaimStatus.DRAFT.value)
    notes = Column(Text, nullable=True)

    generation_summary = Column(JSONB, nullable=True)
    snapshot_json = Column(JSONB, nullable=True)

    linked_invoice_id = Column(UUID(as_uuid=True), ForeignKey("municipality_invoices.id", ondelete="SET NULL"), nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    lines = relationship("ProgressClaimLine", back_populates="claim", cascade="all, delete-orphan", order_by="ProgressClaimLine.sort_order")
    evidence = relationship("ProgressClaimEvidence", back_populates="claim", cascade="all, delete-orphan")
    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])


class ProgressClaimLine(Base):
    __tablename__ = "progress_claim_lines"
    __table_args__ = (
        UniqueConstraint("claim_id", "lot_id", "stage_status_id", "source_type", name="uq_claim_line_lot_stage_source"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("municipality_progress_claims.id", ondelete="CASCADE"), nullable=False, index=True)

    source_type = Column(String(30), nullable=False)

    lot_id = Column(UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True)
    stage_status_id = Column(UUID(as_uuid=True), ForeignKey("project_stage_status.id", ondelete="SET NULL"), nullable=True)
    work_done_id = Column(UUID(as_uuid=True), ForeignKey("subcontractor_work_done.id", ondelete="SET NULL"), nullable=True)
    job_card_id = Column(UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="SET NULL"), nullable=True)

    description = Column(Text, nullable=False)
    stage_name = Column(String(200), nullable=True)
    lot_number = Column(String(50), nullable=True)
    work_date = Column(Date, nullable=True)

    quantity = Column(String(50), nullable=True)
    unit = Column(String(50), nullable=True)
    progress_pct = Column(SmallInteger, nullable=True)

    is_included = Column(Boolean, nullable=False, default=True)
    is_system_generated = Column(Boolean, nullable=False, default=True)
    reviewer_notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    claim = relationship("MunicipalityProgressClaim", back_populates="lines")
    evidence = relationship("ProgressClaimEvidence", back_populates="line", cascade="all, delete-orphan")


class ProgressClaimEvidence(Base):
    __tablename__ = "progress_claim_evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("municipality_progress_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    line_id = Column(UUID(as_uuid=True), ForeignKey("progress_claim_lines.id", ondelete="CASCADE"), nullable=True)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True)

    evidence_type = Column(String(50), nullable=True)
    caption = Column(String(500), nullable=True)
    is_included = Column(Boolean, nullable=False, default=True)

    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    claim = relationship("MunicipalityProgressClaim", back_populates="evidence")
    line = relationship("ProgressClaimLine", back_populates="evidence")
