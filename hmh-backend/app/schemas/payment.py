"""Pydantic v2 schemas for Payment."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import PaymentStatus, PaymentType


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    project_id: uuid.UUID
    payment_type: PaymentType
    payment_reference: Optional[str] = None
    payment_date: Optional[date] = None
    amount_paid: float
    status: PaymentStatus
    approved_by: Optional[uuid.UUID] = None
    captured_by: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    payment_type: PaymentType
    amount_paid: float
    invoice_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    payment_reference: Optional[str] = None
    payment_date: Optional[date] = None
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    payment_reference: Optional[str] = None
    payment_date: Optional[date] = None
    notes: Optional[str] = None
