"""
Weekly Plan models — operational week-by-week execution of the programme.

WeeklyPlan: one plan per project-site per week.
WeeklyPlanItem: individual tasks planned for that week, optionally linked
to a ProgrammeActivity for progress propagation.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, SmallInteger, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import WeeklyPlanStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "site_id", "week_start_date", name="uq_weekly_plan_project_site_week"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_number = Column(String(80), unique=True, nullable=False)

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)

    week_start_date = Column(Date, nullable=False)
    week_end_date = Column(Date, nullable=False)

    status = Column(String(30), nullable=False, default=WeeklyPlanStatus.DRAFT.value)
    notes = Column(Text, nullable=True)

    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    items = relationship("WeeklyPlanItem", back_populates="plan", cascade="all, delete-orphan", order_by="WeeklyPlanItem.sort_order")
    project = relationship("Project", foreign_keys=[project_id])


class WeeklyPlanItem(Base):
    __tablename__ = "weekly_plan_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False, index=True)

    programme_activity_id = Column(UUID(as_uuid=True), ForeignKey("programme_activities.id", ondelete="SET NULL"), nullable=True)
    stage_status_id = Column(UUID(as_uuid=True), ForeignKey("project_stage_status.id", ondelete="SET NULL"), nullable=True)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True)

    description = Column(Text, nullable=False)

    planned_progress_pct = Column(SmallInteger, nullable=False, default=0)
    actual_progress_pct = Column(SmallInteger, nullable=True)

    carry_forward = Column(Boolean, nullable=False, default=False)
    completion_notes = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    sort_order = Column(Integer, nullable=False, default=0)

    plan = relationship("WeeklyPlan", back_populates="items")
    programme_activity = relationship("ProgrammeActivity", back_populates="weekly_plan_items")
