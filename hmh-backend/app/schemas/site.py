"""Pydantic v2 schemas for Site."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    code: Optional[str] = None
    site_type: str
    location_description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SiteCreate(BaseModel):
    name: str
    code: Optional[str] = None
    site_type: str = "construction_site"
    location_description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Site name cannot be blank")
        return v.strip()


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    site_type: Optional[str] = None
    location_description: Optional[str] = None
    is_active: Optional[bool] = None
