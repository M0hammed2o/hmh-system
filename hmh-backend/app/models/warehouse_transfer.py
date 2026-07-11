"""Warehouse Transfer Request model — project-to-project stock transfers with 3-person approval."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class WarehouseTransferStatus(str, enum.Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


TRANSFER_VOTES_REQUIRED = 3


class WarehouseTransferRequest(TimestampMixin, Base):
    __tablename__ = "warehouse_transfer_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    from_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    to_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[WarehouseTransferStatus] = mapped_column(
        Enum(WarehouseTransferStatus, name="warehouse_transfer_status_enum", native_enum=False),
        nullable=False,
        default=WarehouseTransferStatus.PENDING,
        index=True,
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    votes: Mapped[list["WarehouseTransferVote"]] = relationship(
        "WarehouseTransferVote", back_populates="transfer_request", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WarehouseTransferRequest {self.id} {self.status}>"


class WarehouseTransferVote(Base):
    __tablename__ = "warehouse_transfer_votes"
    __table_args__ = (UniqueConstraint("transfer_request_id", "voted_by"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    transfer_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouse_transfer_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    transfer_request: Mapped["WarehouseTransferRequest"] = relationship(
        "WarehouseTransferRequest", back_populates="votes",
    )

    def __repr__(self) -> str:
        return f"<WarehouseTransferVote transfer={self.transfer_request_id} by={self.voted_by}>"
