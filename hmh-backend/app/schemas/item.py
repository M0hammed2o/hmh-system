"""Pydantic v2 schemas for ItemCategory, Item."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import ItemType


class ItemCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    category_id: Optional[uuid.UUID] = None
    default_unit: Optional[str] = None
    item_type: ItemType
    requires_remaining_photo: bool
    is_high_risk: bool
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ItemCreate(BaseModel):
    name: str
    category_id: Optional[uuid.UUID] = None
    default_unit: Optional[str] = None
    item_type: ItemType = ItemType.MATERIAL
    requires_remaining_photo: bool = False
    is_high_risk: bool = False
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip()


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    default_unit: Optional[str] = None
    item_type: Optional[ItemType] = None
    requires_remaining_photo: Optional[bool] = None
    is_high_risk: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
