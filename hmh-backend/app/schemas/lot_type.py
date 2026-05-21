"""Pydantic v2 schemas for LotType — Phase 3D.2."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class LotTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  uuid.UUID
    project_id:          uuid.UUID
    name:                str
    code:                Optional[str]      = None
    description:         Optional[str]      = None
    default_template_id: Optional[uuid.UUID] = None
    created_at:          datetime
    updated_at:          datetime
    # Populated by the service layer (not a DB column)
    lot_count:           int                = 0
    default_template_name: Optional[str]   = None


class LotTypeWithLots(LotTypeRead):
    """Extended read schema that includes linked lot summaries."""
    lots: list[dict] = []


class LotTypeCreate(BaseModel):
    name:                str
    code:                Optional[str]      = None
    description:         Optional[str]      = None
    default_template_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip()

    @field_validator("code")
    @classmethod
    def code_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


class LotTypeUpdate(BaseModel):
    name:                Optional[str]      = None
    code:                Optional[str]      = None
    description:         Optional[str]      = None
    default_template_id: Optional[uuid.UUID] = None


class AssignLotsRequest(BaseModel):
    """Bulk-assign a list of lots to this LotType."""
    lot_ids: list[uuid.UUID]

    @field_validator("lot_ids")
    @classmethod
    def not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("lot_ids must not be empty")
        return v


class RemoveLotsRequest(BaseModel):
    """Remove a list of lots from this LotType (sets lot_type_id = NULL)."""
    lot_ids: list[uuid.UUID]
