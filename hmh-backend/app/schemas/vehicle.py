"""Pydantic v2 schemas for vehicles and vehicle costs."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import VehicleCostType, VehicleStatus, VehicleType


class VehicleCreate(BaseModel):
    registration: str
    name: str
    vehicle_type: VehicleType = VehicleType.OTHER
    status: VehicleStatus = VehicleStatus.ACTIVE
    assigned_project_id: Optional[uuid.UUID] = None
    assigned_site_id: Optional[uuid.UUID] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    name: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    status: Optional[VehicleStatus] = None
    assigned_project_id: Optional[uuid.UUID] = None
    assigned_site_id: Optional[uuid.UUID] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    notes: Optional[str] = None


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration: str
    name: str
    vehicle_type: VehicleType
    status: VehicleStatus
    assigned_project_id: Optional[uuid.UUID] = None
    assigned_site_id: Optional[uuid.UUID] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class VehicleCostCreate(BaseModel):
    cost_type: VehicleCostType
    amount: float
    description: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    proof_image_url: Optional[str] = None
    cost_date: date
    notes: Optional[str] = None


class VehicleCostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_id: uuid.UUID
    cost_type: VehicleCostType
    amount: float
    description: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    proof_image_url: Optional[str] = None
    cost_date: date
    recorded_by: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime
