"""
AI Document Import — typed, versioned extraction schemas and API contracts.

EXTRACTION_SCHEMA_VERSION is stored on every extraction row. Bump it whenever
the field set or field semantics change so old rows stay interpretable.

Design rules enforced here:
  * Every extracted value carries its own provenance (page, confidence,
    source) — a bare value is never accepted.
  * A field that could not be read stays explicitly unresolved (value None,
    confidence 0.0). Nothing is invented to fill a gap.
  * Arithmetic is never taken from the model; it is recomputed in
    ai_import_extraction_service and recorded as ArithmeticCheck rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AIImportBatchStatus,
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportJobStatus,
    AIImportMatchStatus,
    AIImportProcessingOutcome,
)

EXTRACTION_SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "1.0"


# ── Field-level provenance ────────────────────────────────────────────────────

class ExtractedField(BaseModel):
    """One extracted value and everything needed to audit it."""

    value: Optional[Any] = None
    page: Optional[int] = None
    confidence: float = 0.0
    # vision = model read the image/PDF directly; text = model read OCR output;
    # regex = deterministic parser; manual = a human typed it.
    source: Literal["vision", "text", "regex", "manual"] = "vision"
    validated: bool = False
    corrected: bool = False
    corrected_by: Optional[uuid.UUID] = None

    @property
    def is_resolved(self) -> bool:
        return self.value is not None and str(self.value).strip() != ""


class ExtractedLineItem(BaseModel):
    """A single document line. Quantities and prices stay optional on purpose."""

    description: Optional[str] = None
    stock_code: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    discount: Optional[float] = None
    vat_rate: Optional[float] = None
    line_total: Optional[float] = None
    page: Optional[int] = None
    confidence: float = 0.0


class ArithmeticCheck(BaseModel):
    """
    One independently recomputed total compared against the document.

    `passed=False` on any check is a BLOCKED condition for financial postings:
    a document whose own numbers do not add up is not evidence of anything.
    """

    name: str
    expected: Optional[float] = None   # what we computed
    actual: Optional[float] = None     # what the document claims
    difference: Optional[float] = None
    tolerance: float = 0.02
    passed: bool = False
    message: Optional[str] = None


# ── The versioned document schema ─────────────────────────────────────────────

# Field names the extractor may return, per document type. Anything outside
# this set is discarded, which also keeps injected keys out of the record.
COMMON_FIELDS: tuple[str, ...] = (
    "document_type",
    "document_number",
    "issue_date",
    "due_date",
    "supplier_name",
    "supplier_registration_number",
    "supplier_vat_number",
    "project_name",
    "project_number",
    "site_name",
    "department",
    "requesting_employee",
    "approving_employee",
    "purchase_order_reference",
    "material_request_reference",
    "invoice_reference",
    "delivery_reference",
    "currency",
    "subtotal_amount",
    "discount_amount",
    "vat_rate",
    "vat_amount",
    "total_amount",
    "delivery_date",
    "payment_terms",
    "bank_details",          # comparison only — never written to suppliers
    "received_by",
    "notes",
)

NUMERIC_FIELDS: frozenset[str] = frozenset({
    "subtotal_amount", "discount_amount", "vat_rate", "vat_amount", "total_amount",
})

DATE_FIELDS: frozenset[str] = frozenset({
    "issue_date", "due_date", "delivery_date",
})


class DocumentExtractionPayload(BaseModel):
    """The validated, normalised result of one extraction attempt."""

    schema_version: str = EXTRACTION_SCHEMA_VERSION
    prompt_version: str = PROMPT_VERSION
    document_type: AIImportDocumentType = AIImportDocumentType.UNKNOWN
    classification_confidence: float = 0.0
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    arithmetic_checks: list[ArithmeticCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    overall_confidence: float = 0.0

    provider: str = "none"
    model: Optional[str] = None
    extraction_mode: Literal["vision", "text", "regex", "none"] = "none"
    raw_text: Optional[str] = None
    raw_response: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None

    def value(self, name: str) -> Any:
        f = self.fields.get(name)
        return f.value if f else None

    def confidence_of(self, name: str) -> float:
        f = self.fields.get(name)
        return f.confidence if f else 0.0


# ── API request/response contracts ────────────────────────────────────────────

class BatchCreate(BaseModel):
    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    is_legacy: bool = False
    notes: Optional[str] = None


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    project_id: Optional[uuid.UUID]
    site_id: Optional[uuid.UUID]
    is_legacy: bool
    status: AIImportBatchStatus
    notes: Optional[str]
    uploaded_by: uuid.UUID
    created_at: datetime
    document_count: int = 0


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_type: str
    target_id: Optional[uuid.UUID]
    target_label: Optional[str]
    status: AIImportMatchStatus
    method: str
    score: Optional[Decimal]
    explanation: Optional[str]
    evidence: Optional[dict]
    created_at: datetime


class PostingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: Optional[uuid.UUID]
    entity_label: Optional[str]
    project_id: Optional[uuid.UUID]
    posted_by: uuid.UUID
    posted_at: datetime
    reversed_at: Optional[datetime]


class ExtractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schema_version: str
    prompt_version: str
    provider: str
    model: Optional[str]
    extraction_mode: str
    fields: Optional[dict]
    line_items: Optional[list]
    arithmetic_checks: Optional[list]
    warnings: Optional[list]
    overall_confidence: Optional[Decimal]
    is_current: bool
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    cost_usd: Optional[Decimal]
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: int
    checksum_sha256: str
    page_count: Optional[int]
    status: AIImportDocumentStatus
    processing_outcome: Optional[AIImportProcessingOutcome]
    outcome_reasons: Optional[list]
    document_type: AIImportDocumentType
    classification_confidence: Optional[Decimal]
    project_id: Optional[uuid.UUID]
    site_id: Optional[uuid.UUID]
    supplier_id: Optional[uuid.UUID]
    is_legacy: bool
    duplicate_of_id: Optional[uuid.UUID]
    failure_reason: Optional[str]
    retry_count: int
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    authorised_by: Optional[uuid.UUID]
    authorised_at: Optional[datetime]
    rejection_reason: Optional[str]
    uploaded_by: uuid.UUID
    created_at: datetime


class DocumentDetail(DocumentRead):
    extraction: Optional[ExtractionRead] = None
    matches: list[MatchRead] = Field(default_factory=list)
    postings: list[PostingRead] = Field(default_factory=list)
    job_status: Optional[AIImportJobStatus] = None
    related_documents: list[dict] = Field(default_factory=list)


class FieldCorrection(BaseModel):
    """One human correction. `value` of None explicitly clears the field."""

    field_path: str
    value: Optional[Any] = None
    reason: Optional[str] = None


class CorrectionRequest(BaseModel):
    corrections: list[FieldCorrection] = Field(min_length=1)


class ContextAssignment(BaseModel):
    """Human resolution of the document's business context."""

    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    document_type: Optional[AIImportDocumentType] = None
    is_legacy: Optional[bool] = None


class MatchDecision(BaseModel):
    match_id: uuid.UUID
    accept: bool
    reason: Optional[str] = None


class ManualMatchCreate(BaseModel):
    target_type: str
    target_id: uuid.UUID
    reason: Optional[str] = None


class PostRequest(BaseModel):
    """
    Request to post a document's extracted content as real business records.

    `destination` and `lot_id` apply to goods receipt only. `legacy_authorisation_note`
    is required when posting a legacy document that carries no digital approval.
    """

    destination: Optional[str] = None       # MAIN_WAREHOUSE | SITE_STORE | LOT | PICKUP
    lot_id: Optional[uuid.UUID] = None
    overrun_reason: Optional[str] = None
    legacy_authorisation_note: Optional[str] = None
    confirm_override: bool = False


class PostingResolution(BaseModel):
    """
    How an interrupted posting is closed out.

    `link` when the business record does exist (supply its id); `discard` when
    it does not. The note records what was checked, because choosing wrongly
    is how a duplicate gets in.
    """

    resolution: Literal["link", "discard"]
    entity_id: Optional[uuid.UUID] = None
    note: str = Field(min_length=3)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3)


class DashboardFilters(BaseModel):
    # Company is not held on the document; it is resolved through the
    # document's project, which is where company ownership lives.
    company_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    document_type: Optional[AIImportDocumentType] = None
    status: Optional[AIImportDocumentStatus] = None
    uploaded_by: Optional[uuid.UUID] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
