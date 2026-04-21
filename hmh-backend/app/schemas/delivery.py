"""Pydantic v2 schemas for Delivery."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import RecordStatus


class DeliveryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_id: uuid.UUID
    purchase_order_item_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    description: str
    quantity_expected: Optional[float] = None
    quantity_received: float
    unit: Optional[str] = None
    discrepancy_reason: Optional[str] = None
    created_at: datetime


class DeliveryItemCreate(BaseModel):
    description: str
    quantity_received: float
    quantity_expected: Optional[float] = None
    unit: Optional[str] = None
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    purchase_order_item_id: Optional[uuid.UUID] = None
    discrepancy_reason: Optional[str] = None

    @field_validator("description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description cannot be blank")
        return v.strip()


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_number: Optional[str] = None
    purchase_order_id: Optional[uuid.UUID] = None
    supplier_id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    received_by_user_id: uuid.UUID
    delivery_date: datetime
    supplier_delivery_note_number: Optional[str] = None
    delivery_status: RecordStatus
    comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[DeliveryItemRead] = []


class DeliveryCreate(BaseModel):
    supplier_id: uuid.UUID
    site_id: uuid.UUID
    purchase_order_id: Optional[uuid.UUID] = None
    delivery_number: Optional[str] = None
    supplier_delivery_note_number: Optional[str] = None
    delivery_date: Optional[datetime] = None
    comments: Optional[str] = None
    items: list[DeliveryItemCreate] = []


class DeliveryUpdate(BaseModel):
    delivery_status: Optional[RecordStatus] = None
    comments: Optional[str] = None
    supplier_delivery_note_number: Optional[str] = None
