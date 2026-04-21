"""Pydantic v2 schemas for FuelLog."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import FuelType, FuelUsageType


class FuelLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    fuel_type: FuelType
    usage_type: FuelUsageType
    equipment_ref: Optional[str] = None
    litres: float
    cost_per_litre: Optional[float] = None
    total_cost: Optional[float] = None   # DB-generated
    fuelled_by: Optional[str] = None
    recorded_by: uuid.UUID
    fuel_date: datetime
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FuelLogCreate(BaseModel):
    fuel_type: FuelType = FuelType.DIESEL
    usage_type: FuelUsageType = FuelUsageType.EQUIPMENT
    equipment_ref: Optional[str] = None
    litres: float
    cost_per_litre: Optional[float] = None
    fuelled_by: Optional[str] = None
    site_id: Optional[uuid.UUID] = None
    fuel_date: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("litres")
    @classmethod
    def litres_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("litres must be greater than zero")
        return v

    @field_validator("cost_per_litre")
    @classmethod
    def cost_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("cost_per_litre cannot be negative")
        return v


class FuelLogUpdate(BaseModel):
    fuel_type: Optional[FuelType] = None
    usage_type: Optional[FuelUsageType] = None
    equipment_ref: Optional[str] = None
    litres: Optional[float] = None
    cost_per_litre: Optional[float] = None
    fuelled_by: Optional[str] = None
    site_id: Optional[uuid.UUID] = None
    fuel_date: Optional[datetime] = None
    notes: Optional[str] = None
