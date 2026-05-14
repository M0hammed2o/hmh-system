"""Pydantic v2 schemas for MaterialRequest."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DeliveryDestination, MRPriority, RecordStatus


class MaterialRequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_request_id: uuid.UUID
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    description: str = ""
    requested_quantity: float
    approved_quantity: Optional[float] = None
    over_boq_quantity: Optional[float] = None
    unit: Optional[str] = None
    remarks: Optional[str] = None


class MaterialRequestItemCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    description: str = ""
    # Accept both "requested_quantity" (canonical) and "quantity_requested" (legacy/test)
    requested_quantity: float = Field(
        validation_alias=AliasChoices("requested_quantity", "quantity_requested")
    )
    unit: Optional[str] = None
    remarks: Optional[str] = None


class MREmailLogRead(BaseModel):
    """Embedded email log summary returned with each MR."""
    model_config = ConfigDict(from_attributes=True)

    id:            uuid.UUID
    status:        str
    sent_to_email: str
    sent_at:       Optional[datetime] = None
    error_message: Optional[str]      = None
    created_at:    datetime


class MaterialRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_number: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    requested_by: uuid.UUID
    preferred_supplier_id: Optional[uuid.UUID] = None
    priority: MRPriority = MRPriority.NORMAL
    delivery_destination: DeliveryDestination = DeliveryDestination.SITE_STORE
    status: RecordStatus
    over_boq: bool = False
    over_boq_reason: Optional[str] = None
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    requested_date: datetime
    needed_by_date: Optional[date] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[MaterialRequestItemRead] = []
    # Latest email send attempt — populated by the service layer, not a DB column
    email_log: Optional[MREmailLogRead] = None


class MaterialRequestCreate(BaseModel):
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    priority: MRPriority = MRPriority.NORMAL
    delivery_destination: DeliveryDestination = DeliveryDestination.SITE_STORE
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    items: list[MaterialRequestItemCreate] = []

    @field_validator("items")
    @classmethod
    def at_least_one_item(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one item is required")
        return v


class MaterialRequestUpdate(BaseModel):
    status: Optional[RecordStatus] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
