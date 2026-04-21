"""Pydantic v2 schemas for MaterialRequest."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import RecordStatus


class MaterialRequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_request_id: uuid.UUID
    item_id: uuid.UUID
    boq_item_id: Optional[uuid.UUID] = None
    requested_quantity: float
    unit: Optional[str] = None
    remarks: Optional[str] = None


class MaterialRequestItemCreate(BaseModel):
    item_id: uuid.UUID
    boq_item_id: Optional[uuid.UUID] = None
    requested_quantity: float
    unit: Optional[str] = None
    remarks: Optional[str] = None


class MaterialRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_number: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    requested_by: uuid.UUID
    preferred_supplier_id: Optional[uuid.UUID] = None
    status: RecordStatus
    requested_date: datetime
    needed_by_date: Optional[date] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[MaterialRequestItemRead] = []


class MaterialRequestCreate(BaseModel):
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    items: list[MaterialRequestItemCreate] = []

    @field_validator("items")
    @classmethod
    def at_least_one_item(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one item is required")
        return v


class MaterialRequestUpdate(BaseModel):
    status: Optional[RecordStatus] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
