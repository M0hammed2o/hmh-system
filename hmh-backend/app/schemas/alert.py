"""Pydantic v2 schemas for SystemAlert."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import AlertSeverity, AlertStatus, AlertType, UserRole


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    reference_type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    status: AlertStatus
    target_role: Optional[UserRole] = None
    target_user_id: Optional[uuid.UUID] = None
    notification_channel: str
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    acknowledged_by: Optional[uuid.UUID] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[uuid.UUID] = None


class AlertUpdate(BaseModel):
    """Used for acknowledge / resolve actions."""
    status: Optional[AlertStatus] = None
