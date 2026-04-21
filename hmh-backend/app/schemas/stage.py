"""Pydantic v2 schemas for StageMaster and ProjectStageStatus."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import StageStatus


class StageMasterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sequence_order: int
    description: Optional[str] = None
    created_at: datetime


class ProjectStageStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: uuid.UUID
    status: StageStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    certified_at: Optional[datetime] = None
    inspection_required: bool
    certification_required: bool
    ready_for_labour_payment: bool
    notes: Optional[str] = None
    updated_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    # Convenience — populated when stage is eager-loaded
    stage_name: Optional[str] = None
    sequence_order: Optional[int] = None


class StageStatusUpsert(BaseModel):
    """Body for PUT /projects/:id/stages."""
    stage_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    status: Optional[StageStatus] = None
    inspection_required: Optional[bool] = None
    certification_required: Optional[bool] = None
    ready_for_labour_payment: Optional[bool] = None
    notes: Optional[str] = None
