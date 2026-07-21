"""Pydantic schemas for Weekly Plans."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import WeeklyPlanStatus


class WeeklyPlanItemRead(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    programme_activity_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    description: str
    planned_progress_pct: int
    actual_progress_pct: Optional[int] = None
    carry_forward: bool
    completion_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    sort_order: int

    class Config:
        from_attributes = True


class WeeklyPlanItemCreate(BaseModel):
    programme_activity_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    description: str
    planned_progress_pct: int = 0
    carry_forward: bool = False
    sort_order: int = 0


class WeeklyPlanItemUpdate(BaseModel):
    description: Optional[str] = None
    planned_progress_pct: Optional[int] = None
    actual_progress_pct: Optional[int] = None
    carry_forward: Optional[bool] = None
    completion_notes: Optional[str] = None
    sort_order: Optional[int] = None


class MarkItemDoneRequest(BaseModel):
    actual_progress_pct: int
    completion_notes: Optional[str] = None


class WeeklyPlanRead(BaseModel):
    id: uuid.UUID
    plan_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    week_start_date: date
    week_end_date: date
    status: str
    notes: Optional[str] = None
    submitted_by: Optional[uuid.UUID] = None
    approved_by: Optional[uuid.UUID] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: list[WeeklyPlanItemRead] = []

    class Config:
        from_attributes = True


class WeeklyPlanCreate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    week_start_date: date
    notes: Optional[str] = None
    items: list[WeeklyPlanItemCreate] = []


class WeeklyPlanUpdate(BaseModel):
    notes: Optional[str] = None
