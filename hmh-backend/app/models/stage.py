"""Stage master and project stage status models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import StageStatus


class StageMaster(Base):
    __tablename__ = "stage_master"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    project_statuses: Mapped[list["ProjectStageStatus"]] = relationship(
        "ProjectStageStatus", back_populates="stage"
    )

    def __repr__(self) -> str:
        return f"<StageMaster {self.sequence_order}: {self.name}>"


class ProjectStageStatus(TimestampMixin, Base):
    __tablename__ = "project_stage_status"
    __table_args__ = (
        # PostgreSQL 15+: UNIQUE NULLS NOT DISTINCT
        # SQLAlchemy does not natively emit this syntax; the constraint is created
        # via the schema.sql or a custom Alembic migration operation.
        # We declare it here for documentation and Alembic autogenerate awareness.
        UniqueConstraint(
            "project_id", "site_id", "lot_id", "stage_id",
            name="uq_pss_project_site_lot_stage",
        ),
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
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stage_master.id"),
        nullable=False,
    )
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, name="stage_status_enum", create_type=False),
        nullable=False,
        default=StageStatus.NOT_STARTED,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    certified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    inspection_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    certification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ready_for_labour_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="stage_statuses")  # type: ignore[name-defined]
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="stage_statuses")  # type: ignore[name-defined]
    lot: Mapped[Optional["Lot"]] = relationship("Lot", back_populates="stage_statuses")  # type: ignore[name-defined]
    stage: Mapped["StageMaster"] = relationship("StageMaster", back_populates="project_statuses")

    def __repr__(self) -> str:
        return f"<ProjectStageStatus project={self.project_id} stage={self.stage_id} [{self.status}]>"
