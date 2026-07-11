"""Pydantic v2 schemas for WarehouseTransferRequest."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class WarehouseTransferRequestCreate(BaseModel):
    to_project_id: uuid.UUID
    item_id: uuid.UUID
    quantity: float
    reason: str
    notes: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason cannot be blank")
        return v.strip()

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class VoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voted_by: uuid.UUID
    voted_by_name: Optional[str] = None
    voted_at: datetime
    is_override: bool
    notes: Optional[str] = None


class WarehouseTransferRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_project_id: uuid.UUID
    from_project_name: Optional[str] = None
    to_project_id: uuid.UUID
    to_project_name: Optional[str] = None
    item_id: uuid.UUID
    item_name: Optional[str] = None
    quantity: float
    unit: Optional[str] = None
    reason: str
    notes: Optional[str] = None
    status: str
    requested_by: uuid.UUID
    requested_by_name: Optional[str] = None
    requested_at: datetime
    executed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    vote_count: int = 0
    votes: list[VoteRead] = []
    created_at: datetime


class CastVoteRequest(BaseModel):
    notes: Optional[str] = None


class RejectTransferRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason cannot be blank")
        return v.strip()
