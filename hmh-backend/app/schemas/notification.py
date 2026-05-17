"""Pydantic v2 schemas for AlertRecipient and NotificationQueue."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import NotificationChannel, NotificationStatus


# ── Alert Recipient ───────────────────────────────────────────────────────────

class AlertRecipientCreate(BaseModel):
    name: str
    phone_number: str
    label: Optional[str] = None
    receives_critical_alerts: bool = True
    receives_daily_summary: bool = True
    receives_invoice_alerts: bool = False
    receives_delivery_alerts: bool = False
    receives_vehicle_alerts: bool = False
    receives_material_alerts: bool = False

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Phone number must be in international format, e.g. +27831234567")
        digits = v[1:].replace(" ", "")
        if not digits.isdigit() or len(digits) < 8:
            raise ValueError("Invalid phone number")
        return v


class AlertRecipientUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    label: Optional[str] = None
    receives_critical_alerts: Optional[bool] = None
    receives_daily_summary: Optional[bool] = None
    receives_invoice_alerts: Optional[bool] = None
    receives_delivery_alerts: Optional[bool] = None
    receives_vehicle_alerts: Optional[bool] = None
    receives_material_alerts: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Phone number must be in international format, e.g. +27831234567")
        digits = v[1:].replace(" ", "")
        if not digits.isdigit() or len(digits) < 8:
            raise ValueError("Invalid phone number")
        return v


class AlertRecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone_number: str
    label: Optional[str] = None
    receives_critical_alerts: bool
    receives_daily_summary: bool
    receives_invoice_alerts: bool
    receives_delivery_alerts: bool
    receives_vehicle_alerts: bool
    receives_material_alerts: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Notification Queue ────────────────────────────────────────────────────────

class NotificationQueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: Optional[uuid.UUID] = None
    recipient_id: Optional[uuid.UUID] = None
    channel: NotificationChannel
    phone_number: str
    message_body: str
    status: NotificationStatus
    attempt_count: int
    last_attempt_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    requires_acknowledgement: bool
    acknowledged_at: Optional[datetime] = None
    created_at: datetime


class QueueStats(BaseModel):
    pending: int
    sent: int
    mock_sent: int
    failed: int
    acknowledged: int
    cancelled: int
