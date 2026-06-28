"""Pydantic v2 schemas for vehicles, vehicle costs, and repair jobs."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import FuelType, VehicleCostType, VehicleStatus, VehicleType


class VehicleCreate(BaseModel):
    registration: str
    name: str
    vehicle_type: VehicleType = VehicleType.OTHER
    status: VehicleStatus = VehicleStatus.ACTIVE
    vin_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[FuelType] = None
    tank_capacity_l: Optional[float] = None
    fuel_consumption_per_100km: Optional[float] = None
    current_odometer_km: Optional[float] = None
    service_interval_km: Optional[int] = None
    assigned_project_id: Optional[uuid.UUID] = None
    assigned_site_id: Optional[uuid.UUID] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    registration: Optional[str] = None
    name: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    status: Optional[VehicleStatus] = None
    vin_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[FuelType] = None
    tank_capacity_l: Optional[float] = None
    fuel_consumption_per_100km: Optional[float] = None
    current_odometer_km: Optional[float] = None
    service_interval_km: Optional[int] = None
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
    vin_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[FuelType] = None
    tank_capacity_l: Optional[float] = None
    fuel_consumption_per_100km: Optional[float] = None
    current_odometer_km: Optional[float] = None
    service_interval_km: Optional[int] = None
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
    repair_job_id: Optional[uuid.UUID] = None


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
    repair_job_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Repair job schemas
# ---------------------------------------------------------------------------

class RepairJobCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "OPEN"
    workshop_name: Optional[str] = None
    date_opened: date
    date_closed: Optional[date] = None
    odometer_at_repair: Optional[float] = None
    notes: Optional[str] = None


class RepairJobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    workshop_name: Optional[str] = None
    date_opened: Optional[date] = None
    date_closed: Optional[date] = None
    odometer_at_repair: Optional[float] = None
    notes: Optional[str] = None


class RepairJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: str
    workshop_name: Optional[str] = None
    date_opened: date
    date_closed: Optional[date] = None
    odometer_at_repair: Optional[float] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    # computed totals (populated in the API layer, not direct ORM fields)
    total_labour_cost: float = 0.0
    total_parts_cost: float = 0.0
    labour_cost_count: int = 0
    mr_count: int = 0
