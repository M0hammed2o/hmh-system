"""Lot model."""

import uuid
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
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

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="lots")  # type: ignore[name-defined]
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="lots")  # type: ignore[name-defined]
    stage_statuses: Mapped[list["ProjectStageStatus"]] = relationship(  # type: ignore[name-defined]
        "ProjectStageStatus", back_populates="lot"
    )

    def __repr__(self) -> str:
        return f"<Lot {self.lot_number} (project={self.project_id})>"
