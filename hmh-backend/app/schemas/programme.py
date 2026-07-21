"""Pydantic schemas for Programme Activities."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ProgrammeActivityStatus, ProgrammeActivityType


class ProgrammeActivityRead(BaseModel):
    id: uuid.UUID
    activity_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    activity_type: str
    planned_start_date: date
    planned_finish_date: date
    actual_start_date: Optional[date] = None
    actual_finish_date: Optional[date] = None
    baseline_start_date: Optional[date] = None
    baseline_finish_date: Optional[date] = None
    duration_days: Optional[int] = None
    progress_pct: int
    status: str
    predecessor_id: Optional[uuid.UUID] = None
    lag_days: int
    is_critical_path: bool
    is_milestone: bool
    responsible_team: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProgrammeActivityCreate(BaseModel):
    title: str
    description: Optional[str] = None
    activity_type: str = ProgrammeActivityType.CONSTRUCTION.value
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    planned_start_date: date
    planned_finish_date: date
    predecessor_id: Optional[uuid.UUID] = None
    lag_days: int = 0
    is_critical_path: bool = False
    is_milestone: bool = False
    responsible_team: Optional[str] = None
    notes: Optional[str] = None


class ProgrammeActivityUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    activity_type: Optional[str] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    planned_start_date: Optional[date] = None
    planned_finish_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_finish_date: Optional[date] = None
    baseline_start_date: Optional[date] = None
    baseline_finish_date: Optional[date] = None
    progress_pct: Optional[int] = None
    status: Optional[str] = None
    predecessor_id: Optional[uuid.UUID] = None
    lag_days: Optional[int] = None
    is_critical_path: Optional[bool] = None
    is_milestone: Optional[bool] = None
    responsible_team: Optional[str] = None
    notes: Optional[str] = None


class SetBaselineRequest(BaseModel):
    """Freeze current planned dates as immutable baseline."""
    confirm: bool = False
