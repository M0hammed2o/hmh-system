"""Workshop models — vehicle spare parts catalog, stock, and material requests."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import MRPriority, RecordStatus


class WorkshopCategory(TimestampMixin, Base):
    """Parts category — e.g. Tyres, Engine Oil, Filters."""
    __tablename__ = "workshop_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["WorkshopItem"]] = relationship("WorkshopItem", back_populates="category")
    supplier_links: Mapped[list["WorkshopSupplierLink"]] = relationship(
        "WorkshopSupplierLink", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<WorkshopCategory {self.name}>"


class WorkshopItem(TimestampMixin, Base):
    """Fixed parts catalog entry."""
    __tablename__ = "workshop_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    part_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="each", server_default="each")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reorder_level: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    category: Mapped["WorkshopCategory"] = relationship("WorkshopCategory", back_populates="items")
    stock: Mapped[Optional["WorkshopStock"]] = relationship(
        "WorkshopStock", back_populates="item", uselist=False
    )

    def __repr__(self) -> str:
        return f"<WorkshopItem {self.name}>"


class WorkshopStock(Base):
    """Current stock on hand per item at the main workshop."""
    __tablename__ = "workshop_stock"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    quantity_on_hand: Mapped[float] = mapped_column(
        Numeric(14, 3), nullable=False, default=0, server_default="0"
    )
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["WorkshopItem"] = relationship("WorkshopItem", back_populates="stock")

    def __repr__(self) -> str:
        return f"<WorkshopStock item={self.item_id} qty={self.quantity_on_hand}>"


class WorkshopSupplierLink(Base):
    """Links a supplier to a parts category (preferred or capable)."""
    __tablename__ = "workshop_supplier_links"
    __table_args__ = (
        UniqueConstraint("category_id", "supplier_id", name="uq_workshop_supplier_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    category: Mapped["WorkshopCategory"] = relationship("WorkshopCategory", back_populates="supplier_links")
    supplier: Mapped[Optional[object]] = relationship("Supplier", foreign_keys=[supplier_id], viewonly=True)

    def __repr__(self) -> str:
        return f"<WorkshopSupplierLink category={self.category_id} supplier={self.supplier_id}>"


class WorkshopMR(TimestampMixin, Base):
    """Workshop material request — vehicle parts request initiated by site staff."""
    __tablename__ = "workshop_mrs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mr_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status_enum", create_type=False),
        nullable=False,
        default=RecordStatus.DRAFT,
        index=True,
    )
    priority: Mapped[MRPriority] = mapped_column(
        Enum(MRPriority, name="mr_priority_enum", create_type=False),
        nullable=False,
        default=MRPriority.NORMAL,
        server_default="NORMAL",
    )
    needed_by_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[list["WorkshopMRLine"]] = relationship(
        "WorkshopMRLine", back_populates="workshop_mr", cascade="all, delete-orphan"
    )

    # Read-only resolved relationships (for API responses)
    site:    Mapped[Optional[object]] = relationship("Site",    foreign_keys=[site_id],    viewonly=True)
    vehicle: Mapped[Optional[object]] = relationship("Vehicle", foreign_keys=[vehicle_id], viewonly=True)

    def __repr__(self) -> str:
        return f"<WorkshopMR {self.mr_number} status={self.status}>"


class WorkshopMRLine(Base):
    """Line item on a WorkshopMR."""
    __tablename__ = "workshop_mr_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workshop_mr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_mrs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_requested: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_approved: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    preferred_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    workshop_mr: Mapped["WorkshopMR"] = relationship("WorkshopMR", back_populates="lines")
    item: Mapped["WorkshopItem"] = relationship("WorkshopItem")

    def __repr__(self) -> str:
        return f"<WorkshopMRLine item={self.item_id} qty={self.quantity_requested}>"


class WorkshopIssuance(TimestampMixin, Base):
    """Record of parts issued from workshop stock to a vehicle."""
    __tablename__ = "workshop_issuances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workshop_mr_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workshop_mrs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity_issued: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    item: Mapped["WorkshopItem"] = relationship("WorkshopItem")

    def __repr__(self) -> str:
        return f"<WorkshopIssuance item={self.item_id} vehicle={self.vehicle_id} qty={self.quantity_issued}>"
