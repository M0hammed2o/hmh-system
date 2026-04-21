"""Pydantic v2 schemas for Invoice."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import RecordStatus


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    supplier_id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    subtotal_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: float
    status: RecordStatus
    captured_by: Optional[uuid.UUID] = None
    captured_at: datetime
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class InvoiceCreate(BaseModel):
    invoice_number: str
    supplier_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    subtotal_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: float
    notes: Optional[str] = None

    @field_validator("invoice_number")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("invoice_number cannot be blank")
        return v.strip()


class InvoiceUpdate(BaseModel):
    status: Optional[RecordStatus] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    total_amount: Optional[float] = None
    subtotal_amount: Optional[float] = None
    vat_amount: Optional[float] = None
