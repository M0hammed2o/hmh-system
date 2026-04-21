"""Pydantic v2 schemas for Project."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import ProjectStatus


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: Optional[str] = None
    location: Optional[str] = None
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    go_live_date: Optional[date] = None
    status: ProjectStatus
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    location: Optional[str] = None
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    go_live_date: Optional[date] = None
    status: ProjectStatus = ProjectStatus.PLANNED

    @field_validator("name", "code")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    go_live_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
