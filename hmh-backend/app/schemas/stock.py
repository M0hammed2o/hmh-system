"""Pydantic v2 schemas for stock ledger, balances, and usage."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MovementType


class StockLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    item_id: uuid.UUID
    boq_item_id: Optional[uuid.UUID] = None
    movement_type: MovementType
    reference_type: str
    reference_id: Optional[uuid.UUID] = None
    quantity_in: float
    quantity_out: float
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    movement_date: datetime
    entered_by: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime


class StockBalanceRead(BaseModel):
    """Represents a row from the stock_balances materialized view."""
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    item_id: uuid.UUID
    balance: float
    last_movement_date: Optional[datetime] = None

    # Populated by joining items table
    item_name: Optional[str] = None
    item_unit: Optional[str] = None


class UsageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    item_id: uuid.UUID
    boq_item_id: Optional[uuid.UUID] = None
    quantity_used: float
    used_by_person_name: Optional[str] = None
    used_by_team_name: Optional[str] = None
    recorded_by_user_id: uuid.UUID
    usage_date: datetime
    comments: Optional[str] = None
    created_at: datetime


class UsageLogCreate(BaseModel):
    site_id: uuid.UUID
    item_id: uuid.UUID
    quantity_used: float
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    used_by_person_name: Optional[str] = None
    used_by_team_name: Optional[str] = None
    usage_date: Optional[datetime] = None
    comments: Optional[str] = None
