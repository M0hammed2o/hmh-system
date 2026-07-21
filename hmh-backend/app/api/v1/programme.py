"""Programme Activity routes — Gantt / timeline management."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import (
    ALL_ROLES, CurrentUser, DbSession,
    OFFICE_AND_ABOVE, WRITE_ROLES,
    check_project_access,
)
from app.models.programme import ProgrammeActivity
from app.schemas.common import ApiSuccess
from app.schemas.programme import (
    ProgrammeActivityRead, ProgrammeActivityCreate, ProgrammeActivityUpdate,
    SetBaselineRequest,
)
from app.services import programme_service

programme_project_router = APIRouter(
    prefix="/projects/{project_id}/programme",
    tags=["programme"],
)
programme_router = APIRouter(prefix="/programme", tags=["programme"])


def _get_or_404(db: DbSession, activity_id: uuid.UUID) -> ProgrammeActivity:
    activity = programme_service.get_activity(db, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Programme activity not found")
    return activity


@programme_project_router.get("", response_model=ApiSuccess[list[ProgrammeActivityRead]], dependencies=[ALL_ROLES])
def list_activities(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    site_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
):
    check_project_access(db, current_user, project_id)
    activities = programme_service.list_activities(db, project_id, site_id=site_id, status=status)
    return ApiSuccess(data=[ProgrammeActivityRead.model_validate(a) for a in activities])


@programme_project_router.post("", response_model=ApiSuccess[ProgrammeActivityRead], dependencies=[WRITE_ROLES])
def create_activity(
    project_id: uuid.UUID,
    body: ProgrammeActivityCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    activity = programme_service.create_activity(db, project_id, body.model_dump(), actor_id=current_user.id)
    db.commit()
    db.refresh(activity)
    return ApiSuccess(data=ProgrammeActivityRead.model_validate(activity))


@programme_router.get("/{activity_id}", response_model=ApiSuccess[ProgrammeActivityRead], dependencies=[ALL_ROLES])
def get_activity(activity_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    activity = _get_or_404(db, activity_id)
    check_project_access(db, current_user, activity.project_id)
    return ApiSuccess(data=ProgrammeActivityRead.model_validate(activity))


@programme_router.patch("/{activity_id}", response_model=ApiSuccess[ProgrammeActivityRead], dependencies=[WRITE_ROLES])
def update_activity(
    activity_id: uuid.UUID,
    body: ProgrammeActivityUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    activity = _get_or_404(db, activity_id)
    check_project_access(db, current_user, activity.project_id)
    try:
        programme_service.update_activity(db, activity, body.model_dump(exclude_none=True), actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    db.refresh(activity)
    return ApiSuccess(data=ProgrammeActivityRead.model_validate(activity))


@programme_router.delete("/{activity_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_activity(activity_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    activity = _get_or_404(db, activity_id)
    check_project_access(db, current_user, activity.project_id)
    try:
        programme_service.delete_activity(db, activity, actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return ApiSuccess(data={"deleted": True})


@programme_router.post("/{activity_id}/baseline", response_model=ApiSuccess[ProgrammeActivityRead], dependencies=[OFFICE_AND_ABOVE])
def set_baseline(
    activity_id: uuid.UUID,
    body: SetBaselineRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to freeze the baseline dates.")
    activity = _get_or_404(db, activity_id)
    check_project_access(db, current_user, activity.project_id)
    programme_service.set_baseline(db, activity, actor_id=current_user.id)
    db.commit()
    db.refresh(activity)
    return ApiSuccess(data=ProgrammeActivityRead.model_validate(activity))
