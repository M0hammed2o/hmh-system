"""Weekly Plan routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import (
    ALL_ROLES, CurrentUser, DbSession,
    OFFICE_AND_ABOVE, WRITE_ROLES, OFFICE_ADMIN_AND_ABOVE,
    check_project_access,
)
from app.models.enums import UserRole
from app.models.weekly_plan import WeeklyPlan, WeeklyPlanItem
from app.schemas.common import ApiSuccess
from app.schemas.weekly_plan import (
    WeeklyPlanRead, WeeklyPlanCreate, WeeklyPlanUpdate,
    WeeklyPlanItemCreate, WeeklyPlanItemUpdate, MarkItemDoneRequest,
)
from app.services import weekly_plan_service

weekly_plan_project_router = APIRouter(
    prefix="/projects/{project_id}/weekly-plans",
    tags=["weekly-plans"],
)
weekly_plan_router = APIRouter(prefix="/weekly-plans", tags=["weekly-plans"])


def _get_or_404(db: DbSession, plan_id: uuid.UUID) -> WeeklyPlan:
    plan = weekly_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    return plan


@weekly_plan_project_router.get("", response_model=ApiSuccess[list[WeeklyPlanRead]], dependencies=[ALL_ROLES])
def list_plans(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    site_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
):
    check_project_access(db, current_user, project_id)
    plans = weekly_plan_service.list_plans(db, project_id, site_id=site_id, status=status)
    return ApiSuccess(data=[WeeklyPlanRead.model_validate(p) for p in plans])


@weekly_plan_project_router.post("", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[WRITE_ROLES])
def create_plan(
    project_id: uuid.UUID,
    body: WeeklyPlanCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    try:
        plan = weekly_plan_service.create_plan(db, project_id, body.model_dump(), actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    plan = _get_or_404(db, plan.id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


@weekly_plan_router.get("/{plan_id}", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[ALL_ROLES])
def get_plan(plan_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


@weekly_plan_router.patch("/{plan_id}", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[WRITE_ROLES])
def update_plan(
    plan_id: uuid.UUID,
    body: WeeklyPlanUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    if body.notes is not None:
        plan.notes = body.notes
        from datetime import datetime, timezone
        plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    plan = _get_or_404(db, plan_id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


@weekly_plan_router.post("/{plan_id}/submit", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[WRITE_ROLES])
def submit_plan(plan_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    try:
        weekly_plan_service.submit_plan(db, plan, actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    plan = _get_or_404(db, plan_id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


@weekly_plan_router.post("/{plan_id}/approve", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[OFFICE_AND_ABOVE])
def approve_plan(plan_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    try:
        weekly_plan_service.approve_plan(db, plan, actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    plan = _get_or_404(db, plan_id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


@weekly_plan_router.post("/{plan_id}/reject", response_model=ApiSuccess[WeeklyPlanRead], dependencies=[OFFICE_AND_ABOVE])
def reject_plan(
    plan_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = Query(None),
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    try:
        weekly_plan_service.reject_plan(db, plan, actor_id=current_user.id, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    plan = _get_or_404(db, plan_id)
    return ApiSuccess(data=WeeklyPlanRead.model_validate(plan))


# ── Plan item endpoints ────────────────────────────────────────────────────────

@weekly_plan_router.post("/{plan_id}/items", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def add_item(
    plan_id: uuid.UUID,
    body: WeeklyPlanItemCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    try:
        item = weekly_plan_service.add_item(db, plan, body.model_dump(), actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return ApiSuccess(data={"id": str(item.id)})


@weekly_plan_router.patch("/{plan_id}/items/{item_id}", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def update_item(
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    body: WeeklyPlanItemUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    from sqlalchemy import select
    item = db.execute(
        select(WeeklyPlanItem).where(
            WeeklyPlanItem.id == item_id,
            WeeklyPlanItem.plan_id == plan_id,
        )
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Plan item not found")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(item, field, val)
    db.commit()
    return ApiSuccess(data={"updated": True})


@weekly_plan_router.post("/{plan_id}/items/{item_id}/done", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def mark_item_done(
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    body: MarkItemDoneRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    from sqlalchemy import select
    item = db.execute(
        select(WeeklyPlanItem).where(
            WeeklyPlanItem.id == item_id,
            WeeklyPlanItem.plan_id == plan_id,
        )
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Plan item not found")

    weekly_plan_service.mark_item_done(
        db, item,
        actual_progress_pct=body.actual_progress_pct,
        completion_notes=body.completion_notes,
        actor_id=current_user.id,
    )
    db.commit()
    return ApiSuccess(data={"updated": True})


@weekly_plan_router.delete("/{plan_id}/items/{item_id}", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def delete_item(
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    plan = _get_or_404(db, plan_id)
    check_project_access(db, current_user, plan.project_id)
    from sqlalchemy import select
    item = db.execute(
        select(WeeklyPlanItem).where(
            WeeklyPlanItem.id == item_id,
            WeeklyPlanItem.plan_id == plan_id,
        )
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Plan item not found")
    db.delete(item)
    db.commit()
    return ApiSuccess(data={"deleted": True})
