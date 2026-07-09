"""Material Request models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import DeliveryDestination, MRPriority, RecordStatus

if TYPE_CHECKING:
    from app.models.vehicle import RepairJob


class MaterialRequest(TimestampMixin, Base):
    __tablename__ = "material_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="SET NULL"),
        nullable=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stage_master.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    preferred_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status_enum", create_type=False),
        nullable=False,
        default=RecordStatus.DRAFT,
        index=True,
    )
    requested_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    needed_by_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extended procurement fields
    priority: Mapped[MRPriority] = mapped_column(
        Enum(MRPriority, name="mr_priority_enum", create_type=True),
        nullable=False,
        default=MRPriority.NORMAL,
        server_default="NORMAL",
    )
    delivery_destination: Mapped[DeliveryDestination] = mapped_column(
        Enum(DeliveryDestination, name="delivery_destination_enum", create_type=True),
        nullable=False,
        default=DeliveryDestination.SITE_STORE,
        server_default="SITE_STORE",
    )
    over_boq: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    over_boq_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_to_po_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    issuing_company: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Repair job link
    repair_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    items: Mapped[list["MaterialRequestItem"]] = relationship(
        "MaterialRequestItem", back_populates="request", cascade="all, delete-orphan"
    )
    repair_job: Mapped[Optional["RepairJob"]] = relationship(
        "RepairJob",
        back_populates="material_requests",
        foreign_keys=[repair_job_id],
    )

    def __repr__(self) -> str:
        return f"<MaterialRequest {self.request_number}>"


class MaterialRequestItem(Base):
    __tablename__ = "material_request_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    preferred_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    requested_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    approved_quantity: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    over_boq_quantity: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    extra_reason_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extra_reason_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    request: Mapped["MaterialRequest"] = relationship("MaterialRequest", back_populates="items")

    def __repr__(self) -> str:
        return f"<MRItem item={self.item_id} qty={self.requested_quantity}>"


class MRApproval(Base):
    """Individual approval vote for a material request.

    Each user may cast exactly one vote per MR (enforced by unique constraint).
    PROCUREMENT_LEAD approvals set is_override=True when staff vote count < threshold.
    """
    __tablename__ = "mr_approvals"
    __table_args__ = (
        UniqueConstraint("mr_id", "approved_by", name="uq_mr_approvals_mr_approver"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<MRApproval mr={self.mr_id} by={self.approved_by} override={self.is_override}>"
