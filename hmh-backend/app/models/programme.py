"""
Programme Activity model — forms the Gantt / timeline backbone for a project.

Each ProgrammeActivity represents one unit of planned work with explicit
planned/actual/baseline dates, progress tracking, and an optional predecessor
dependency (Gantt dependency chain).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, SmallInteger, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import ProgrammeActivityStatus, ProgrammeActivityType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProgrammeActivity(Base):
    __tablename__ = "programme_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_number = Column(String(80), unique=True, nullable=False)

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True)
    stage_status_id = Column(UUID(as_uuid=True), ForeignKey("project_stage_status.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    activity_type = Column(String(30), nullable=False, default=ProgrammeActivityType.CONSTRUCTION.value)

    planned_start_date = Column(Date, nullable=False)
    planned_finish_date = Column(Date, nullable=False)
    actual_start_date = Column(Date, nullable=True)
    actual_finish_date = Column(Date, nullable=True)
    baseline_start_date = Column(Date, nullable=True)
    baseline_finish_date = Column(Date, nullable=True)

    duration_days = Column(Integer, nullable=True)

    progress_pct = Column(SmallInteger, nullable=False, default=0)
    status = Column(String(30), nullable=False, default=ProgrammeActivityStatus.NOT_STARTED.value)

    predecessor_id = Column(UUID(as_uuid=True), ForeignKey("programme_activities.id", ondelete="SET NULL"), nullable=True)
    lag_days = Column(Integer, nullable=False, default=0)

    is_critical_path = Column(Boolean, nullable=False, default=False)
    is_milestone = Column(Boolean, nullable=False, default=False)

    responsible_team = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    project = relationship("Project", foreign_keys=[project_id])
    predecessor = relationship("ProgrammeActivity", remote_side="ProgrammeActivity.id", foreign_keys=[predecessor_id])
    weekly_plan_items = relationship("WeeklyPlanItem", back_populates="programme_activity")
