"""Pydantic v2 schemas for BOQ (header → section → item)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import BoqStatus, ItemType


# ── BOQ Header ────────────────────────────────────────────────────────────────

class BOQHeaderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    version_name: str
    source_file_name: Optional[str] = None
    source_type: str
    status: BoqStatus
    is_active_version: bool
    uploaded_by: Optional[uuid.UUID] = None
    uploaded_at: datetime
    notes: Optional[str] = None


class BOQHeaderCreate(BaseModel):
    version_name: str
    source_type: str = "manual"
    notes: Optional[str] = None

    @field_validator("version_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("version_name cannot be blank")
        return v.strip()


class BOQHeaderUpdate(BaseModel):
    version_name: Optional[str] = None
    status: Optional[BoqStatus] = None
    is_active_version: Optional[bool] = None
    notes: Optional[str] = None


# ── BOQ Section ───────────────────────────────────────────────────────────────

class BOQSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_header_id: uuid.UUID
    stage_id: Optional[uuid.UUID] = None
    section_name: str
    sequence_order: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BOQSectionCreate(BaseModel):
    section_name: str
    stage_id: Optional[uuid.UUID] = None
    sequence_order: int = 0
    notes: Optional[str] = None

    @field_validator("section_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("section_name cannot be blank")
        return v.strip()


class BOQSectionUpdate(BaseModel):
    section_name: Optional[str] = None
    stage_id: Optional[uuid.UUID] = None
    sequence_order: Optional[int] = None
    notes: Optional[str] = None


# ── BOQ Item ──────────────────────────────────────────────────────────────────

class BOQItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_section_id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    raw_description: str
    normalized_description: Optional[str] = None
    specification: Optional[str] = None
    item_type: ItemType
    unit: Optional[str] = None
    planned_quantity: Optional[float] = None
    planned_rate: Optional[float] = None
    planned_total: Optional[float] = None   # GENERATED ALWAYS AS STORED — read-only
    sort_order: int
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BOQItemCreate(BaseModel):
    raw_description: str
    item_type: ItemType = ItemType.MATERIAL
    unit: Optional[str] = None
    planned_quantity: Optional[float] = None
    planned_rate: Optional[float] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    specification: Optional[str] = None
    sort_order: int = 0
    notes: Optional[str] = None

    @field_validator("raw_description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_description cannot be blank")
        return v.strip()


class BOQItemUpdate(BaseModel):
    raw_description: Optional[str] = None
    item_type: Optional[ItemType] = None
    unit: Optional[str] = None
    planned_quantity: Optional[float] = None
    planned_rate: Optional[float] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None
    supplier_id: Optional[uuid.UUID] = None
    specification: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
