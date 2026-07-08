"""Pydantic v2 schemas for the Workshop module."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models.enums import MRPriority, RecordStatus


# ── Stock ─────────────────────────────────────────────────────────────────────

class WorkshopStockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quantity_on_hand: float = 0.0
    last_updated: Optional[datetime] = None


# ── Categories ────────────────────────────────────────────────────────────────

class WorkshopCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ── Embedded resolved references ──────────────────────────────────────────────

class _SiteBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    site_type: str


class _VehicleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration: str
    name: str


class _UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str


class WorkshopCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Category name is required")
        return v.strip()


# ── Items ─────────────────────────────────────────────────────────────────────

class WorkshopItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    part_number: Optional[str] = None
    unit: str
    description: Optional[str] = None
    reorder_level: Optional[float] = None
    is_active: bool
    stock: Optional[WorkshopStockRead] = None
    category: Optional[WorkshopCategoryRead] = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def quantity_on_hand(self) -> float:
        return float(self.stock.quantity_on_hand) if self.stock else 0.0

    @computed_field
    @property
    def category_name(self) -> Optional[str]:
        return self.category.name if self.category else None


class WorkshopItemCreate(BaseModel):
    category_id: uuid.UUID
    name: str
    part_number: Optional[str] = None
    unit: str = "each"
    description: Optional[str] = None
    reorder_level: Optional[float] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Item name is required")
        return v.strip()


class WorkshopItemUpdate(BaseModel):
    name: Optional[str] = None
    part_number: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    reorder_level: Optional[float] = None
    is_active: Optional[bool] = None


# ── Supplier links ─────────────────────────────────────────────────────────────

class _SupplierBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: Optional[str] = None


class WorkshopSupplierLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    supplier_id: uuid.UUID
    is_preferred: bool
    category: Optional[WorkshopCategoryRead] = None
    supplier: Optional[_SupplierBrief] = None


class WorkshopSupplierLinkCreate(BaseModel):
    category_id: uuid.UUID
    supplier_id: uuid.UUID
    is_preferred: bool = False


# ── MR lines ──────────────────────────────────────────────────────────────────

class WorkshopItemBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    part_number: Optional[str] = None


class WorkshopMRLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    item_id: uuid.UUID
    quantity_requested: float
    quantity_approved: Optional[float] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = None
    item: Optional[WorkshopItemBrief] = None


class WorkshopMRLineCreate(BaseModel):
    item_id: uuid.UUID
    quantity_requested: float
    preferred_supplier_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = None

    @field_validator("quantity_requested")
    @classmethod
    def qty_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v


# ── MR Email Logs ────────────────────────────────────────────────────────────

class _SupplierEmailBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: Optional[str] = None


class WorkshopMREmailLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    supplier_id: Optional[uuid.UUID] = None
    sent_to_email: str
    email_subject: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    supplier: Optional[_SupplierEmailBrief] = None


# ── MR Approvals ─────────────────────────────────────────────────────────────

class WorkshopMRApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mr_id: uuid.UUID
    approved_by: Optional[uuid.UUID] = None
    approved_at: datetime
    is_override: bool
    notes: Optional[str] = None
    voter: Optional[_UserBrief] = None


# ── Workshop MRs ──────────────────────────────────────────────────────────────

class WorkshopMRRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mr_number: str
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    reason: str
    status: RecordStatus
    priority: MRPriority
    needed_by_date: Optional[date] = None
    requested_by: uuid.UUID
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: list[WorkshopMRLineRead] = []
    approvals: list[WorkshopMRApprovalRead] = []
    email_logs: list[WorkshopMREmailLogRead] = []
    quotes: list["WorkshopQuoteRead"] = []
    purchase_orders: list["WorkshopPurchaseOrderRead"] = []
    invoices: list["WorkshopInvoiceRead"] = []
    delivery_notes: list["WorkshopDeliveryNoteRead"] = []
    site: Optional[_SiteBrief] = None
    vehicle: Optional[_VehicleBrief] = None

    @computed_field
    @property
    def vote_count(self) -> int:
        return sum(1 for a in self.approvals if not a.is_override)


class WorkshopMRCreate(BaseModel):
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    reason: str
    priority: MRPriority = MRPriority.NORMAL
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    lines: list[WorkshopMRLineCreate] = []

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Reason is required")
        return v.strip()

    @field_validator("lines")
    @classmethod
    def at_least_one_line(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one line item is required")
        return v


# ── Workshop Quotes ───────────────────────────────────────────────────────────

class WorkshopQuoteApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_id: uuid.UUID
    approved_by: Optional[uuid.UUID] = None
    approved_at: datetime
    is_override: bool
    notes: Optional[str] = None
    voter: Optional[_UserBrief] = None


class WorkshopQuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    quote_file_url: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str
    notes: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    approvals: list[WorkshopQuoteApprovalRead] = []
    supplier: Optional[_SupplierBrief] = None

    @computed_field
    @property
    def vote_count(self) -> int:
        return sum(1 for a in self.approvals if not a.is_override)


class WorkshopQuoteCreate(BaseModel):
    workshop_mr_id: uuid.UUID
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "ZAR"
    notes: Optional[str] = None


# ── Purchase Orders ───────────────────────────────────────────────────────────

class WorkshopPurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    quote_id: Optional[uuid.UUID] = None
    po_number: str
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str
    notes: Optional[str] = None
    status: str
    po_file_url: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    supplier: Optional[_SupplierBrief] = None


class WorkshopPurchaseOrderCreate(BaseModel):
    workshop_mr_id: uuid.UUID
    quote_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "ZAR"
    notes: Optional[str] = None


# ── Invoices ──────────────────────────────────────────────────────────────────

class WorkshopInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    po_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    invoice_file_url: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str
    invoice_date: Optional[date] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    supplier: Optional[_SupplierBrief] = None


class WorkshopInvoiceCreate(BaseModel):
    workshop_mr_id: uuid.UUID
    po_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "ZAR"
    invoice_date: Optional[date] = None
    notes: Optional[str] = None


# ── Delivery Notes ────────────────────────────────────────────────────────────

class WorkshopDeliveryNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_mr_id: uuid.UUID
    po_id: Optional[uuid.UUID] = None
    delivery_number: Optional[str] = None
    delivery_file_url: Optional[str] = None
    delivery_date: Optional[date] = None
    received_by_name: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class WorkshopDeliveryNoteCreate(BaseModel):
    workshop_mr_id: uuid.UUID
    po_id: Optional[uuid.UUID] = None
    delivery_number: Optional[str] = None
    delivery_date: Optional[date] = None
    received_by_name: Optional[str] = None
    notes: Optional[str] = None


# Update forward refs
WorkshopMRRead.model_rebuild()


# ── Issuances ─────────────────────────────────────────────────────────────────

class WorkshopIssuanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    vehicle_id: uuid.UUID
    workshop_mr_id: Optional[uuid.UUID] = None
    quantity_issued: float
    issued_by: uuid.UUID
    issued_at: datetime
    notes: Optional[str] = None
    created_at: datetime
    item:    Optional[WorkshopItemBrief] = None
    vehicle: Optional[_VehicleBrief]    = None


class WorkshopIssuanceCreate(BaseModel):
    item_id: uuid.UUID
    vehicle_id: uuid.UUID
    workshop_mr_id: Optional[uuid.UUID] = None
    quantity_issued: float
    notes: Optional[str] = None

    @field_validator("quantity_issued")
    @classmethod
    def qty_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v
