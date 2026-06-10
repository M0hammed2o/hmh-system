"""Schemas for ProcurementReconciliation — Phase 4."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReconciliationStatus


# ── Nested document summaries returned in detail view ────────────────────────

class _POSummary(BaseModel):
    po_id: str
    po_number: str
    po_date: Optional[str]
    status: str
    subtotal_amount: float
    vat_amount: float
    total_amount: float
    supplier_id: str
    supplier_name: Optional[str]
    project_id: str

class _InvoiceSummary(BaseModel):
    invoice_id: str
    invoice_number: str
    invoice_date: Optional[str]
    due_date: Optional[str]
    subtotal_amount: Optional[float]
    vat_amount: Optional[float]
    total_amount: float
    status: str
    vat_rate_used: Optional[float]

class _DeliverySummary(BaseModel):
    delivery_id: str
    delivery_number: Optional[str]
    delivery_date: Optional[str]
    status: str
    items_count: int

class _QuotationSummary(BaseModel):
    quotation_id: str
    quote_number: str
    quote_date: Optional[str]
    status: str
    net_amount: float
    vat_amount: float
    gross_amount: float
    vat_rate_used: float

class _MRSummary(BaseModel):
    mr_id: str
    mr_number: str
    status: str


# ── Main read schema ──────────────────────────────────────────────────────────

class ProcurementReconciliationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reconciliation_number: str
    status: ReconciliationStatus

    purchase_order_id: Optional[uuid.UUID]
    invoice_id: Optional[uuid.UUID]
    delivery_id: Optional[uuid.UUID]
    quotation_id: Optional[uuid.UUID]
    material_request_id: Optional[uuid.UUID]

    variance_data: Optional[Any]
    notes: Optional[str]
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class ProcurementReconciliationDetail(ProcurementReconciliationRead):
    """Full detail with resolved document summaries."""
    po: Optional[_POSummary] = None
    invoice: Optional[_InvoiceSummary] = None
    delivery: Optional[_DeliverySummary] = None
    quotation: Optional[_QuotationSummary] = None
    material_request: Optional[_MRSummary] = None
    reviewed_by_name: Optional[str] = None


# ── Create ────────────────────────────────────────────────────────────────────

class ProcurementReconciliationCreate(BaseModel):
    purchase_order_id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None
    delivery_id: Optional[uuid.UUID] = None
    quotation_id: Optional[uuid.UUID] = None
    material_request_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


# ── Update (approve / reject / recompute) ────────────────────────────────────

class ProcurementReconciliationUpdate(BaseModel):
    status: Optional[ReconciliationStatus] = None
    notes: Optional[str] = None
    invoice_id: Optional[uuid.UUID] = None
    delivery_id: Optional[uuid.UUID] = None
    quotation_id: Optional[uuid.UUID] = None


# ── Dashboard stats ───────────────────────────────────────────────────────────

class ReconciliationDashboard(BaseModel):
    pending: int
    matched: int
    variance_detected: int
    approved: int
    rejected: int
    awaiting_review: int   # matched + variance_detected (needs human decision)
    total: int
