"""Site model."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class Site(TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_sites_project_code"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    site_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="construction_site"
    )
    location_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="sites")  # type: ignore[name-defined]
    lots: Mapped[list["Lot"]] = relationship(  # type: ignore[name-defined]
        "Lot", back_populates="site"
    )
    stage_statuses: Mapped[list["ProjectStageStatus"]] = relationship(  # type: ignore[name-defined]
        "ProjectStageStatus", back_populates="site"
    )
    user_access: Mapped[list["UserSiteAccess"]] = relationship(  # type: ignore[name-defined]
        "UserSiteAccess", back_populates="site", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Site {self.name} (project={self.project_id})>"
