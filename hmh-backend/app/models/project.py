"""Project model."""

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import ProjectStatus


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estimated_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    go_live_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status_enum", create_type=False),
        nullable=False,
        default=ProjectStatus.PLANNED,
        index=True,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    sites: Mapped[list["Site"]] = relationship(  # type: ignore[name-defined]
        "Site", back_populates="project", cascade="all, delete-orphan"
    )
    lots: Mapped[list["Lot"]] = relationship(  # type: ignore[name-defined]
        "Lot", back_populates="project", cascade="all, delete-orphan"
    )
    stage_statuses: Mapped[list["ProjectStageStatus"]] = relationship(  # type: ignore[name-defined]
        "ProjectStageStatus", back_populates="project", cascade="all, delete-orphan"
    )
    user_access: Mapped[list["UserProjectAccess"]] = relationship(  # type: ignore[name-defined]
        "UserProjectAccess", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.code} — {self.name}>"
