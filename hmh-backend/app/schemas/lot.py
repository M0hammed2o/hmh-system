"""Pydantic v2 schemas for Lot."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import LotStatus


class LotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    lot_number: str
    unit_type: Optional[str] = None
    block_number: Optional[str] = None
    status: LotStatus
    created_at: datetime
    updated_at: datetime


class LotCreate(BaseModel):
    lot_number: str
    site_id: Optional[uuid.UUID] = None
    unit_type: Optional[str] = None
    block_number: Optional[str] = None
    status: LotStatus = LotStatus.AVAILABLE

    @field_validator("lot_number")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("lot_number cannot be blank")
        return v.strip()


class LotUpdate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    unit_type: Optional[str] = None
    block_number: Optional[str] = None
    status: Optional[LotStatus] = None
