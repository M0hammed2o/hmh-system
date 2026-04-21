"""BOQ models: BOQHeader, BOQSection, BOQItem."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import BoqStatus, ItemType


class BOQHeader(Base):
    __tablename__ = "boq_headers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    status: Mapped[BoqStatus] = mapped_column(
        Enum(BoqStatus, name="boq_status_enum", create_type=False),
        nullable=False,
        default=BoqStatus.DRAFT,
    )
    is_active_version: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project")  # type: ignore[name-defined]
    sections: Mapped[list["BOQSection"]] = relationship(
        "BOQSection", back_populates="header", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BOQHeader {self.version_name} (project={self.project_id})>"


class BOQSection(TimestampMixin, Base):
    __tablename__ = "boq_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    boq_header_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boq_headers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stage_master.id", ondelete="SET NULL"),
        nullable=True,
    )
    section_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    header: Mapped["BOQHeader"] = relationship("BOQHeader", back_populates="sections")
    items: Mapped[list["BOQItem"]] = relationship(
        "BOQItem", back_populates="section", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BOQSection {self.section_name}>"


class BOQItem(TimestampMixin, Base):
    __tablename__ = "boq_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    boq_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boq_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
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
    item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType, name="item_type_enum", create_type=False),
        nullable=False,
        default=ItemType.MATERIAL,
    )
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    planned_quantity: Mapped[Optional[float]] = mapped_column(Numeric(14, 3), nullable=True)
    planned_rate: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    # planned_total is GENERATED ALWAYS AS STORED — do NOT write this column
    planned_total: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    section: Mapped["BOQSection"] = relationship("BOQSection", back_populates="items")

    def __repr__(self) -> str:
        return f"<BOQItem {self.raw_description[:40]}>"
