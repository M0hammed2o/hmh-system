"""Pydantic schemas for Municipality Progress Claim."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import ProgressClaimStatus, ClaimSourceType


# ── Evidence schemas ───────────────────────────────────────────────────────────

class EvidenceRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    line_id: Optional[uuid.UUID] = None
    attachment_id: Optional[uuid.UUID] = None
    evidence_type: Optional[str] = None
    caption: Optional[str] = None
    is_included: bool
    added_by: Optional[uuid.UUID] = None
    added_at: datetime

    class Config:
        from_attributes = True


class EvidenceAdd(BaseModel):
    line_id: Optional[uuid.UUID] = None
    attachment_id: Optional[uuid.UUID] = None
    evidence_type: Optional[str] = None
    caption: Optional[str] = None
    is_included: bool = True


class EvidenceUpdate(BaseModel):
    is_included: Optional[bool] = None
    caption: Optional[str] = None


# ── Claim Line schemas ─────────────────────────────────────────────────────────

class ClaimLineRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    source_type: str
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    work_done_id: Optional[uuid.UUID] = None
    job_card_id: Optional[uuid.UUID] = None
    description: str
    stage_name: Optional[str] = None
    lot_number: Optional[str] = None
    work_date: Optional[date] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    progress_pct: Optional[int] = None
    is_included: bool
    is_system_generated: bool
    reviewer_notes: Optional[str] = None
    sort_order: int
    evidence: list[EvidenceRead] = []

    class Config:
        from_attributes = True


class ClaimLineUpdate(BaseModel):
    is_included: Optional[bool] = None
    reviewer_notes: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class ClaimLineCreate(BaseModel):
    source_type: str
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    work_done_id: Optional[uuid.UUID] = None
    job_card_id: Optional[uuid.UUID] = None
    description: str
    stage_name: Optional[str] = None
    lot_number: Optional[str] = None
    work_date: Optional[date] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    progress_pct: Optional[int] = None
    sort_order: int = 0


# ── Progress Claim schemas ─────────────────────────────────────────────────────

class ProgressClaimRead(BaseModel):
    id: uuid.UUID
    claim_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    claim_title: str
    municipality_name: str
    cert_number: Optional[str] = None
    period_start: date
    period_end: date
    reporting_cutoff_date: date
    status: str
    notes: Optional[str] = None
    generation_summary: Optional[dict] = None
    linked_invoice_id: Optional[uuid.UUID] = None
    generated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    lines: list[ClaimLineRead] = []
    evidence: list[EvidenceRead] = []

    class Config:
        from_attributes = True


class ProgressClaimListItem(BaseModel):
    id: uuid.UUID
    claim_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    claim_title: str
    period_start: date
    period_end: date
    status: str
    line_count: int = 0
    included_line_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProgressClaimCreate(BaseModel):
    claim_title: str
    municipality_name: str = "Ethekweni Municipality"
    cert_number: Optional[str] = None
    period_start: date
    period_end: date
    reporting_cutoff_date: Optional[date] = None
    site_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class ProgressClaimUpdate(BaseModel):
    claim_title: Optional[str] = None
    municipality_name: Optional[str] = None
    cert_number: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    reporting_cutoff_date: Optional[date] = None
    notes: Optional[str] = None
    linked_invoice_id: Optional[uuid.UUID] = None


class GenerateClaimRequest(BaseModel):
    """Trigger claim-line auto-generation from canonical operational sources."""
    include_work_done: bool = True
    include_job_cards: bool = True
    include_milestones: bool = True
    overwrite_existing: bool = False


class GenerationSummary(BaseModel):
    milestone_lines: int = 0
    work_done_lines: int = 0
    job_card_lines: int = 0
    total_lines: int = 0
    skipped_duplicates: int = 0
    generated_at: str
