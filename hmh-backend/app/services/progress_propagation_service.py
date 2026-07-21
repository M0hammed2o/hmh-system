"""
Progress propagation service.

Propagates progress upward through the hierarchy:
  WeeklyPlanItem.actual_progress_pct
    → ProgrammeActivity.progress_pct
      → ProjectStageStatus.progress_pct
        → Lot.progress_pct (via average of stage statuses)
          → Project.progress_pct (via average of lots)

Each step only updates if the new value is higher than the current value
(progress never goes backward due to a single late update).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.programme import ProgrammeActivity
from app.models.stage import ProjectStageStatus
from app.models.lot import Lot
from app.models.project import Project
from app.models.weekly_plan import WeeklyPlanItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


def propagate_from_plan_item(
    db: Session,
    item: WeeklyPlanItem,
    actual_progress_pct: int,
) -> None:
    """Called when a WeeklyPlanItem is marked done."""
    if not item.programme_activity_id:
        return

    activity = db.get(ProgrammeActivity, item.programme_activity_id)
    if not activity:
        return

    if actual_progress_pct > (activity.progress_pct or 0):
        activity.progress_pct = actual_progress_pct
        activity.updated_at = _now()

        if actual_progress_pct >= 100:
            from app.models.enums import ProgrammeActivityStatus
            activity.status = ProgrammeActivityStatus.COMPLETED.value
            from datetime import date
            activity.actual_finish_date = date.today()

        db.flush()

        if activity.stage_status_id:
            _propagate_to_stage_status(db, activity.stage_status_id, actual_progress_pct)


def _propagate_to_stage_status(
    db: Session,
    stage_status_id: uuid.UUID,
    progress_pct: int,
) -> None:
    ss = db.get(ProjectStageStatus, stage_status_id)
    if not ss:
        return

    if progress_pct > (ss.progress_pct or 0):
        ss.progress_pct = progress_pct

        if progress_pct >= 100:
            from app.models.enums import StageStatus
            if ss.status not in (StageStatus.COMPLETED.value, StageStatus.CERTIFIED.value):
                # Move to AWAITING_INSPECTION — do not set completed_at here; that is set
                # only on the COMPLETED/CERTIFIED transition by the milestones service.
                ss.status = StageStatus.AWAITING_INSPECTION.value

        db.flush()

        if ss.lot_id:
            _propagate_to_lot(db, ss.lot_id, ss.project_id)


def _propagate_to_lot(
    db: Session,
    lot_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    avg = db.execute(
        select(func.avg(ProjectStageStatus.progress_pct))
        .where(
            ProjectStageStatus.lot_id == lot_id,
            ProjectStageStatus.project_id == project_id,
        )
    ).scalar() or 0

    lot = db.get(Lot, lot_id)
    if lot and hasattr(lot, "progress_pct"):
        new_pct = min(100, int(avg))
        if new_pct > (getattr(lot, "progress_pct", None) or 0):
            lot.progress_pct = new_pct
            db.flush()
            _propagate_to_project(db, project_id)


def _propagate_to_project(db: Session, project_id: uuid.UUID) -> None:
    avg = db.execute(
        select(func.avg(Lot.progress_pct))
        .where(Lot.project_id == project_id)
    ).scalar() or 0

    project = db.get(Project, project_id)
    if project:
        new_pct = min(100, int(avg))
        if hasattr(project, "progress_pct") and new_pct > (project.progress_pct or 0):
            project.progress_pct = new_pct
            db.flush()


def propagate_stage_status_update(
    db: Session,
    stage_status: ProjectStageStatus,
) -> None:
    """Call after any direct update to ProjectStageStatus.progress_pct."""
    if stage_status.lot_id:
        _propagate_to_lot(db, stage_status.lot_id, stage_status.project_id)
