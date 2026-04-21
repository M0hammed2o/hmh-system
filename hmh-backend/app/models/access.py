"""User access control models — project-level and site-level."""

import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class UserProjectAccess(Base):
    __tablename__ = "user_project_access"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_upa_user_project"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps (created_at only — no updated_at for access records)
    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="project_access")  # type: ignore[name-defined]
    project: Mapped["Project"] = relationship("Project", back_populates="user_access")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<UserProjectAccess user={self.user_id} project={self.project_id}>"


class UserSiteAccess(Base):
    __tablename__ = "user_site_access"
    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_usa_user_site"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    can_receive_delivery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_record_usage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_request_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_update_stage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="site_access")  # type: ignore[name-defined]
    site: Mapped["Site"] = relationship("Site", back_populates="user_access")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<UserSiteAccess user={self.user_id} site={self.site_id}>"
