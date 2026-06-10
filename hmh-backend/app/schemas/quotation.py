"""Pydantic v2 schemas for Quotation."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import QuotationStatus


class QuotationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_number: str
    supplier_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    material_request_id: Optional[uuid.UUID] = None
    status: QuotationStatus
    quote_date: Optional[date] = None
    expiry_date: Optional[date] = None
    net_amount: float
    vat_amount: float
    gross_amount: float
    vat_rate_used: float
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class QuotationCreate(BaseModel):
    quote_number: str
    supplier_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    material_request_id: Optional[uuid.UUID] = None
    status: QuotationStatus = QuotationStatus.DRAFT
    quote_date: Optional[date] = None
    expiry_date: Optional[date] = None
    net_amount: float = 0.0
    vat_amount: float = 0.0
    gross_amount: float = 0.0
    vat_rate_used: float = 15.0
    notes: Optional[str] = None

    @field_validator("quote_number")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("quote_number cannot be blank")
        return v.strip().upper()


class QuotationUpdate(BaseModel):
    status: Optional[QuotationStatus] = None
    quote_date: Optional[date] = None
    expiry_date: Optional[date] = None
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    gross_amount: Optional[float] = None
    vat_rate_used: Optional[float] = None
    notes: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
