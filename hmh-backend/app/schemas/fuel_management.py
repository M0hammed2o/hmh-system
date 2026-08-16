"""Pydantic v2 contracts for Fuel Management."""

import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FuelTypeRead(OrmModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class FuelStorageCreate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    fuel_type_id: uuid.UUID
    name: str = Field(min_length=2, max_length=160)
    location_type: str = "TANK"
    capacity_litres: Optional[float] = Field(default=None, gt=0)
    low_stock_threshold_litres: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None
    opening_stock_litres: float = Field(default=0, ge=0)


class FuelStorageRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    fuel_type_id: uuid.UUID
    name: str
    location_type: str
    capacity_litres: Optional[float]
    low_stock_threshold_litres: Optional[float]
    is_active: bool
    notes: Optional[str]
    calculated_balance_litres: float = 0
    cutover_confirmed_at: Optional[datetime] = None
    cutover_confirmed_by: Optional[uuid.UUID] = None


class FuelOrderCreate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    fuel_type_id: uuid.UUID
    supplier_id: Optional[uuid.UUID] = None
    storage_location_id: Optional[uuid.UUID] = None
    request_date: date = Field(default_factory=date.today)
    requested_litres: float = Field(gt=0)
    expected_delivery_date: Optional[date] = None
    delivery_location: str = Field(min_length=2, max_length=300)
    purpose: Optional[str] = None
    intended_use: Optional[str] = Field(default=None, max_length=80)
    destination_type: Optional[Literal[
        "VEHICLE", "SITE_STORAGE", "GENERATOR", "PLANT", "OTHER_EQUIPMENT"
    ]] = None
    vehicle_id: Optional[uuid.UUID] = None
    equipment_reference: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None
    submit_now: bool = False


class FuelOrderUpdate(BaseModel):
    supplier_id: Optional[uuid.UUID] = None
    storage_location_id: Optional[uuid.UUID] = None
    expected_delivery_date: Optional[date] = None
    delivery_location: Optional[str] = Field(default=None, min_length=2, max_length=300)
    requested_litres: Optional[float] = Field(default=None, gt=0)
    purpose: Optional[str] = None
    supplier_reference: Optional[str] = None
    purchase_order_reference: Optional[str] = None


class FuelTransition(BaseModel):
    reason: Optional[str] = None
    override_reason: Optional[str] = None
    supplier_reference: Optional[str] = None
    purchase_order_reference: Optional[str] = None


class FuelOrderHistoryRead(OrmModel):
    id: uuid.UUID
    from_status: Optional[str]
    to_status: str
    actor_id: uuid.UUID
    actor_name: Optional[str] = None
    reason: Optional[str]
    created_at: datetime


class FuelOrderRead(OrmModel):
    id: uuid.UUID
    order_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    fuel_type_id: uuid.UUID
    supplier_id: Optional[uuid.UUID]
    storage_location_id: Optional[uuid.UUID]
    requested_by: uuid.UUID
    request_date: date
    requested_litres: float
    expected_delivery_date: Optional[date]
    delivery_location: str
    purpose: Optional[str]
    intended_use: Optional[str] = None
    destination_type: Optional[str] = None
    vehicle_id: Optional[uuid.UUID] = None
    equipment_reference: Optional[str] = None
    notes: Optional[str] = None
    status: str
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    supplier_reference: Optional[str]
    purchase_order_reference: Optional[str]
    submitted_at: Optional[datetime] = None
    feasibility_status: str = "NOT_EVALUATED"
    feasibility_message: Optional[str] = None
    estimated_remaining_litres: Optional[float] = None
    feasibility_override_reason: Optional[str] = None
    feasibility_override_by: Optional[uuid.UUID] = None
    feasibility_override_at: Optional[datetime] = None
    requester_name: Optional[str] = None
    next_approver: Optional[str] = None
    history: list[FuelOrderHistoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    delivered_litres: float = 0


class FuelDeliveryCreate(BaseModel):
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_litres: float = Field(gt=0)
    confirmed_litres: Optional[float] = Field(default=None, gt=0)
    delivery_note_number: str = Field(min_length=1, max_length=120)
    supplier_id: Optional[uuid.UUID] = None
    storage_location_id: Optional[uuid.UUID] = None
    opening_reading: Optional[float] = Field(default=None, ge=0)
    closing_reading: Optional[float] = Field(default=None, ge=0)
    tanker_registration: Optional[str] = None
    driver_details: Optional[str] = None
    notes: Optional[str] = None
    allow_excess: bool = False
    excess_reason: Optional[str] = None

    @model_validator(mode="after")
    def readings_are_complete(self):
        if (self.opening_reading is None) != (self.closing_reading is None):
            raise ValueError("opening and closing readings must be supplied together")
        if self.opening_reading is not None and self.closing_reading < self.opening_reading:
            raise ValueError("closing reading cannot be lower than opening reading")
        if self.allow_excess and not self.excess_reason:
            raise ValueError("excess_reason is required for an excess override")
        return self


class FuelDeliveryRead(OrmModel):
    id: uuid.UUID
    order_id: Optional[uuid.UUID]
    procurement_delivery_item_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID]
    site_id: uuid.UUID
    supplier_id: Optional[uuid.UUID]
    fuel_type_id: Optional[uuid.UUID]
    storage_location_id: Optional[uuid.UUID]
    delivery_date: date
    delivered_at: Optional[datetime]
    delivery_note_number: Optional[str]
    litres_delivered: float
    calculated_received_litres: Optional[float]
    confirmed_litres: Optional[float]
    variance_litres: Optional[float]
    supplier_variance_litres: Optional[float] = None
    meter_variance_litres: Optional[float] = None
    is_manual_emergency: bool = False
    emergency_reason: Optional[str] = None
    tanker_registration: Optional[str]
    driver_details: Optional[str]
    verification_status: str
    excess_override: bool
    notes: Optional[str]
    created_at: datetime


class FuelDeliveryFromProcurementCreate(BaseModel):
    """Hand-off from a real procurement DeliveryItem into the Fuel Control
    layer (Phase 5). litres_delivered is taken from the DeliveryItem itself
    (the office's documented/supplier quantity) — only the Fuel-side
    confirmation and optional meter readings are captured here."""
    delivery_item_id: uuid.UUID
    storage_location_id: uuid.UUID
    confirmed_litres: float = Field(gt=0)
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    opening_reading: Optional[float] = Field(default=None, ge=0)
    closing_reading: Optional[float] = Field(default=None, ge=0)
    tanker_registration: Optional[str] = None
    driver_details: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def readings_are_complete(self):
        if (self.opening_reading is None) != (self.closing_reading is None):
            raise ValueError("opening and closing readings must be supplied together")
        if self.opening_reading is not None and self.closing_reading < self.opening_reading:
            raise ValueError("closing reading cannot be lower than opening reading")
        return self


class FuelManualEmergencyDeliveryCreate(BaseModel):
    """Emergency receipt with no procurement chain behind it at all (e.g. a
    cash fuel purchase before a Material Request could be raised). Gated on
    fuel.admin at the API layer; reason is mandatory, not optional notes."""
    storage_location_id: uuid.UUID
    delivered_litres: float = Field(gt=0)
    confirmed_litres: Optional[float] = Field(default=None, gt=0)
    reason: str = Field(min_length=3)
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivery_note_number: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    opening_reading: Optional[float] = Field(default=None, ge=0)
    closing_reading: Optional[float] = Field(default=None, ge=0)
    tanker_registration: Optional[str] = None
    driver_details: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def readings_are_complete(self):
        if (self.opening_reading is None) != (self.closing_reading is None):
            raise ValueError("opening and closing readings must be supplied together")
        if self.opening_reading is not None and self.closing_reading < self.opening_reading:
            raise ValueError("closing reading cannot be lower than opening reading")
        return self


class FuelIssueCreate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    storage_location_id: uuid.UUID
    fuel_type_id: uuid.UUID
    vehicle_id: Optional[uuid.UUID] = None
    destination_type: Literal["VEHICLE", "PLANT", "GENERATOR", "STORAGE_TANK", "OTHER_EQUIPMENT"]
    equipment_reference: Optional[str] = None
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    litres: float = Field(gt=0)
    odometer_reading: Optional[float] = Field(default=None, ge=0)
    hour_meter_reading: Optional[float] = Field(default=None, ge=0)
    received_by: Optional[str] = None
    purpose: Optional[str] = None
    evidence_url: Optional[str] = None
    notes: Optional[str] = None
    reading_source: Literal["MANUAL", "PHOTOGRAPH_VERIFIED", "TRACKER_VERIFIED", "MANAGER_OVERRIDDEN"] = "MANUAL"
    evidence_override_reason: Optional[str] = None
    feasibility_override_reason: Optional[str] = None


class FuelIssueRead(OrmModel):
    id: uuid.UUID
    issue_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    storage_location_id: uuid.UUID
    fuel_type_id: uuid.UUID
    vehicle_id: Optional[uuid.UUID]
    destination_type: str
    equipment_reference: Optional[str]
    issued_at: datetime
    litres: float
    odometer_reading: Optional[float]
    hour_meter_reading: Optional[float]
    received_by: Optional[str]
    purpose: Optional[str]
    evidence_url: Optional[str]
    distance_since_previous_km: Optional[float]
    litres_per_100km: Optional[float]
    operating_hours_since_previous: Optional[float]
    litres_per_hour: Optional[float]
    anomaly_flag: bool
    anomaly_reason: Optional[str]
    reading_source: str = "MANUAL"
    tracker_provider: Optional[str] = None
    tracker_reading_at: Optional[datetime] = None
    estimated_remaining_litres: Optional[float] = None
    feasibility_status: str = "NOT_EVALUATED"
    evidence_override_reason: Optional[str] = None
    evidence_override_by: Optional[uuid.UUID] = None
    evidence_override_at: Optional[datetime] = None
    feasibility_override_reason: Optional[str] = None
    feasibility_override_by: Optional[uuid.UUID] = None
    feasibility_override_at: Optional[datetime] = None
    evidence: list[dict] = Field(default_factory=list)
    is_reversed: bool
    reversal_reason: Optional[str]
    created_at: datetime


class FuelAdjustmentCreate(BaseModel):
    storage_location_id: uuid.UUID
    adjustment_type: str
    litres_delta: float
    reason: str = Field(min_length=3)
    reference_reconciliation_id: Optional[uuid.UUID] = None


class FuelAdjustmentRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    storage_location_id: uuid.UUID
    fuel_type_id: uuid.UUID
    adjustment_type: str
    litres_delta: float
    reason: str
    authorised_by: uuid.UUID
    created_at: datetime


class FuelReconciliationCreate(BaseModel):
    storage_location_id: uuid.UUID
    reconciliation_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    physical_balance_litres: float = Field(ge=0)
    explanation: str = Field(min_length=3)


class FuelReconciliationRead(OrmModel):
    id: uuid.UUID
    reconciliation_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    storage_location_id: uuid.UUID
    fuel_type_id: uuid.UUID
    reconciliation_date: datetime
    calculated_balance_litres: float
    physical_balance_litres: float
    variance_litres: float
    variance_pct: Optional[float]
    explanation: str
    status: str
    requires_approval: bool
    reconciled_by: uuid.UUID
    approved_by: Optional[uuid.UUID]
    approval_notes: Optional[str]
    created_at: datetime


class FuelEquipmentProfileCreate(BaseModel):
    site_id: Optional[uuid.UUID] = None
    equipment_reference: str = Field(min_length=1, max_length=200)
    destination_type: str
    expected_litres_per_hour: Optional[float] = Field(default=None, gt=0)
    tolerance_pct: float = Field(default=20, ge=0, le=500)
    tank_capacity_litres: Optional[float] = Field(default=None, gt=0)
    minimum_issue_interval_hours: float = Field(default=0, ge=0)
    hour_meter_required: bool = True
    override_required: bool = False


class FuelEquipmentProfileRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID]
    equipment_reference: str
    destination_type: str
    expected_litres_per_hour: Optional[float]
    tolerance_pct: float
    tank_capacity_litres: Optional[float]
    minimum_issue_interval_hours: float
    hour_meter_required: bool
    override_required: bool
    is_active: bool


class FuelEmailLogRead(OrmModel):
    id: uuid.UUID
    order_id: Optional[uuid.UUID]
    delivery_id: Optional[uuid.UUID]
    event_type: str
    recipient_email: str
    subject: str
    status: str
    attempt_count: int
    last_attempt_at: Optional[datetime]
    next_attempt_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
