"""Delivery models: Delivery, DeliveryItem."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import RecordStatus


class Delivery(TimestampMixin, Base):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    delivery_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    received_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    delivery_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supplier_delivery_note_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivery_status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status_enum", create_type=False),
        nullable=False,
        default=RecordStatus.RECEIVED,
    )
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["DeliveryItem"]] = relationship(
        "DeliveryItem", back_populates="delivery", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Delivery {self.delivery_number or self.id}>"


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
    )
    boq_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boq_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_expected: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_received: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    discrepancy_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    delivery: Mapped["Delivery"] = relationship("Delivery", back_populates="items")

    def __repr__(self) -> str:
        return f"<DeliveryItem {self.description[:30]} qty={self.quantity_received}>"
