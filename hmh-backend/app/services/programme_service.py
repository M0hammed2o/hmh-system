"""Programme Activity service — Gantt/timeline management."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.programme import ProgrammeActivity
from app.models.enums import ProgrammeActivityStatus, ProgrammeActivityType, AuditAction
from app.services import audit_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_activity_number(db: Session, project_id: uuid.UUID) -> str:
    from app.models.project import Project
    project = db.get(Project, project_id)
    prefix = f"ACT-{project.code if project else 'PRJ'}-"
    latest = db.execute(
        select(ProgrammeActivity.activity_number)
        .where(ProgrammeActivity.activity_number.like(f"{prefix}%"))
        .where(ProgrammeActivity.project_id == project_id)
        .order_by(ProgrammeActivity.activity_number.desc())
    ).scalars().first()
    seq = 1
    if latest:
        try:
            seq = int(latest.split("-")[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f"{prefix}{seq:03d}"


def create_activity(
    db: Session,
    project_id: uuid.UUID,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgrammeActivity:
    activity_number = _next_activity_number(db, project_id)
    planned_start = data["planned_start_date"]
    planned_finish = data["planned_finish_date"]
    duration = (planned_finish - planned_start).days + 1 if isinstance(planned_start, date) else None

    activity = ProgrammeActivity(
        activity_number=activity_number,
        project_id=project_id,
        site_id=data.get("site_id"),
        lot_id=data.get("lot_id"),
        stage_status_id=data.get("stage_status_id"),
        title=data["title"],
        description=data.get("description"),
        activity_type=data.get("activity_type", ProgrammeActivityType.CONSTRUCTION.value),
        planned_start_date=planned_start,
        planned_finish_date=planned_finish,
        duration_days=duration,
        status=ProgrammeActivityStatus.NOT_STARTED.value,
        predecessor_id=data.get("predecessor_id"),
        lag_days=data.get("lag_days", 0),
        is_critical_path=data.get("is_critical_path", False),
        is_milestone=data.get("is_milestone", False),
        responsible_team=data.get("responsible_team"),
        notes=data.get("notes"),
        created_by=actor_id,
    )
    db.add(activity)
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="ProgrammeActivity",
        actor_id=actor_id,
        entity_id=activity.id,
        after_value={"activity_number": activity_number, "title": activity.title},
    )
    return activity


def get_activity(db: Session, activity_id: uuid.UUID) -> Optional[ProgrammeActivity]:
    return db.get(ProgrammeActivity, activity_id)


def list_activities(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> list[ProgrammeActivity]:
    q = select(ProgrammeActivity).where(ProgrammeActivity.project_id == project_id)
    if site_id:
        q = q.where(ProgrammeActivity.site_id == site_id)
    if status:
        q = q.where(ProgrammeActivity.status == status)
    q = q.order_by(ProgrammeActivity.planned_start_date, ProgrammeActivity.activity_number)
    return list(db.execute(q).scalars().all())


def update_activity(
    db: Session,
    activity: ProgrammeActivity,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgrammeActivity:
    if activity.status in (
        ProgrammeActivityStatus.COMPLETED.value,
        ProgrammeActivityStatus.VERIFIED.value,
        ProgrammeActivityStatus.CANCELLED.value,
    ):
        raise ValueError(f"Activity {activity.activity_number} is terminal and cannot be modified.")

    before = {"status": activity.status, "progress_pct": activity.progress_pct}

    for field in [
        "title", "description", "activity_type", "site_id", "lot_id", "stage_status_id",
        "planned_start_date", "planned_finish_date", "actual_start_date", "actual_finish_date",
        "baseline_start_date", "baseline_finish_date", "progress_pct", "status",
        "predecessor_id", "lag_days", "is_critical_path", "is_milestone",
        "responsible_team", "notes",
    ]:
        if field in data and data[field] is not None:
            setattr(activity, field, data[field])

    # Recalculate duration if planned dates changed
    if activity.planned_start_date and activity.planned_finish_date:
        activity.duration_days = (activity.planned_finish_date - activity.planned_start_date).days + 1

    activity.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="ProgrammeActivity",
        actor_id=actor_id,
        entity_id=activity.id,
        before_value=before,
        after_value={"status": activity.status, "progress_pct": activity.progress_pct},
    )
    return activity


def set_baseline(
    db: Session,
    activity: ProgrammeActivity,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgrammeActivity:
    """Freeze current planned dates as baseline (immutable after this call)."""
    activity.baseline_start_date = activity.planned_start_date
    activity.baseline_finish_date = activity.planned_finish_date
    activity.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="ProgrammeActivity",
        actor_id=actor_id,
        entity_id=activity.id,
        after_value={
            "baseline_start_date": str(activity.baseline_start_date),
            "baseline_finish_date": str(activity.baseline_finish_date),
        },
        notes="Baseline set",
    )
    return activity


def delete_activity(
    db: Session,
    activity: ProgrammeActivity,
    actor_id: Optional[uuid.UUID] = None,
) -> None:
    if activity.status not in (
        ProgrammeActivityStatus.NOT_STARTED.value,
        ProgrammeActivityStatus.CANCELLED.value,
    ):
        raise ValueError(
            f"Activity {activity.activity_number} cannot be deleted in status {activity.status}. "
            "Cancel it first."
        )
    audit_service.write_event(
        db,
        action=AuditAction.DELETE,
        entity_type="ProgrammeActivity",
        actor_id=actor_id,
        entity_id=activity.id,
        before_value={"activity_number": activity.activity_number},
    )
    db.delete(activity)
    db.flush()
