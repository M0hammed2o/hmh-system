"""Lot model."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import LotStatus


class Lot(TimestampMixin, Base):
    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("project_id", "lot_number", name="uq_lots_project_lot_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
        index=True,
    )
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    block_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[LotStatus] = mapped_column(
        Enum(LotStatus, name="lot_status_enum", create_type=False),
        nullable=False,
        default=LotStatus.AVAILABLE,
    )

    # Extended fields
    buyer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manager_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    boq_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boq_headers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Phase 3D: LotType FK — nullable, backward compatible
    lot_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lot_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Phase 3D: customization tracking
    # NULL  = BOQ is purely generated (never manually edited)
    # Value = timestamp of the first manual edit; propagation SAFE mode skips this lot
    boq_customized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expected_completion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    budgeted_cost: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="lots")  # type: ignore[name-defined]
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="lots")  # type: ignore[name-defined]
    lot_type: Mapped[Optional["LotType"]] = relationship(  # type: ignore[name-defined]
        "LotType", back_populates="lots"
    )
    stage_statuses: Mapped[list["ProjectStageStatus"]] = relationship(  # type: ignore[name-defined]
        "ProjectStageStatus", back_populates="lot"
    )

    def __repr__(self) -> str:
        return f"<Lot {self.lot_number} (project={self.project_id})>"
