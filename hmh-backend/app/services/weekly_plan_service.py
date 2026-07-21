"""Weekly Plan service — operational weekly work tracking."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.weekly_plan import WeeklyPlan, WeeklyPlanItem
from app.models.enums import WeeklyPlanStatus, AuditAction, AlertType, AlertSeverity
from app.services import audit_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _monday(d: date) -> date:
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _next_plan_number(db: Session, project_id: uuid.UUID) -> str:
    from app.models.project import Project
    project = db.get(Project, project_id)
    code = project.code if project else "PRJ"
    today = date.today()
    iso = today.isocalendar()
    return f"WP-{iso[0]}-W{iso[1]:02d}-{code}"


def create_plan(
    db: Session,
    project_id: uuid.UUID,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> WeeklyPlan:
    week_start = _monday(data["week_start_date"])
    week_end = week_start + timedelta(days=6)

    existing = db.execute(
        select(WeeklyPlan).where(
            WeeklyPlan.project_id == project_id,
            WeeklyPlan.site_id == data.get("site_id"),
            WeeklyPlan.week_start_date == week_start,
        )
    ).scalars().first()
    if existing:
        raise ValueError(
            f"A weekly plan already exists for this project/site/week: {existing.plan_number}"
        )

    plan_number = _next_plan_number(db, project_id)

    plan = WeeklyPlan(
        plan_number=plan_number,
        project_id=project_id,
        site_id=data.get("site_id"),
        week_start_date=week_start,
        week_end_date=week_end,
        status=WeeklyPlanStatus.DRAFT.value,
        notes=data.get("notes"),
    )
    db.add(plan)
    db.flush()

    for item_data in data.get("items", []):
        item = WeeklyPlanItem(
            plan_id=plan.id,
            programme_activity_id=item_data.get("programme_activity_id"),
            stage_status_id=item_data.get("stage_status_id"),
            lot_id=item_data.get("lot_id"),
            description=item_data["description"],
            planned_progress_pct=item_data.get("planned_progress_pct", 0),
            carry_forward=item_data.get("carry_forward", False),
            sort_order=item_data.get("sort_order", 0),
        )
        db.add(item)

    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="WeeklyPlan",
        actor_id=actor_id,
        entity_id=plan.id,
        after_value={"plan_number": plan_number, "week_start_date": str(week_start)},
    )
    return plan


def get_plan(db: Session, plan_id: uuid.UUID) -> Optional[WeeklyPlan]:
    return db.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.id == plan_id)
        .options(selectinload(WeeklyPlan.items))
    ).scalars().first()


def list_plans(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> list[WeeklyPlan]:
    q = select(WeeklyPlan).where(WeeklyPlan.project_id == project_id)
    if site_id:
        q = q.where(WeeklyPlan.site_id == site_id)
    if status:
        q = q.where(WeeklyPlan.status == status)
    q = q.order_by(WeeklyPlan.week_start_date.desc())
    return list(db.execute(q).scalars().all())


def submit_plan(
    db: Session,
    plan: WeeklyPlan,
    actor_id: Optional[uuid.UUID] = None,
) -> WeeklyPlan:
    if plan.status != WeeklyPlanStatus.DRAFT.value:
        raise ValueError(f"Plan {plan.plan_number} is not in DRAFT status.")
    plan.status = WeeklyPlanStatus.SUBMITTED.value
    plan.submitted_by = actor_id
    plan.submitted_at = _now()
    plan.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="WeeklyPlan",
        actor_id=actor_id,
        entity_id=plan.id,
        before_value={"status": WeeklyPlanStatus.DRAFT.value},
        after_value={"status": plan.status},
    )
    return plan


def approve_plan(
    db: Session,
    plan: WeeklyPlan,
    actor_id: Optional[uuid.UUID] = None,
) -> WeeklyPlan:
    if plan.status != WeeklyPlanStatus.SUBMITTED.value:
        raise ValueError(f"Plan {plan.plan_number} is not in SUBMITTED status.")
    plan.status = WeeklyPlanStatus.APPROVED.value
    plan.approved_by = actor_id
    plan.approved_at = _now()
    plan.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.APPROVE,
        entity_type="WeeklyPlan",
        actor_id=actor_id,
        entity_id=plan.id,
        before_value={"status": WeeklyPlanStatus.SUBMITTED.value},
        after_value={"status": plan.status},
    )
    return plan


def reject_plan(
    db: Session,
    plan: WeeklyPlan,
    actor_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
) -> WeeklyPlan:
    if plan.status not in (WeeklyPlanStatus.SUBMITTED.value,):
        raise ValueError(f"Plan {plan.plan_number} cannot be rejected in status {plan.status}.")
    plan.status = WeeklyPlanStatus.DRAFT.value
    plan.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.REJECT,
        entity_type="WeeklyPlan",
        actor_id=actor_id,
        entity_id=plan.id,
        after_value={"status": plan.status},
        notes=reason,
    )
    return plan


def mark_item_done(
    db: Session,
    item: WeeklyPlanItem,
    actual_progress_pct: int,
    completion_notes: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
) -> WeeklyPlanItem:
    item.actual_progress_pct = actual_progress_pct
    item.completion_notes = completion_notes
    item.completed_at = _now()

    if item.programme_activity_id:
        from app.services.progress_propagation_service import propagate_from_plan_item
        propagate_from_plan_item(db, item, actual_progress_pct)

    db.flush()
    return item


def add_item(
    db: Session,
    plan: WeeklyPlan,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> WeeklyPlanItem:
    if plan.status not in (WeeklyPlanStatus.DRAFT.value, WeeklyPlanStatus.APPROVED.value, WeeklyPlanStatus.IN_PROGRESS.value):
        raise ValueError(f"Cannot add items to plan in status {plan.status}.")
    item = WeeklyPlanItem(
        plan_id=plan.id,
        programme_activity_id=data.get("programme_activity_id"),
        stage_status_id=data.get("stage_status_id"),
        lot_id=data.get("lot_id"),
        description=data["description"],
        planned_progress_pct=data.get("planned_progress_pct", 0),
        carry_forward=data.get("carry_forward", False),
        sort_order=data.get("sort_order", 0),
    )
    db.add(item)
    db.flush()
    return item
