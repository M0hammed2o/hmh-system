"""AlertRecipient — WhatsApp / notification contact list."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class AlertRecipient(TimestampMixin, Base):
    __tablename__ = "alert_recipients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # E.164 format: +27831234567
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Alert category subscriptions
    receives_critical_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    receives_daily_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    receives_invoice_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    receives_delivery_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    receives_vehicle_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    receives_material_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Tracks when this recipient last sent us a WhatsApp message.
    # Used to determine whether we're inside the 24-hour conversation window.
    # NULL means they have never messaged us → always use template.
    last_inbound_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    notifications: Mapped[list["NotificationQueue"]] = relationship(  # type: ignore[name-defined]
        "NotificationQueue", back_populates="recipient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AlertRecipient {self.name} {self.phone_number}>"
