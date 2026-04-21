"""Stage routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.stage import ProjectStageStatusRead, StageMasterRead, StageStatusUpsert
from app.services import stage_service

stages_router = APIRouter(prefix="/stages", tags=["stages"])
project_stages_router = APIRouter(
    prefix="/projects/{project_id}/stage-statuses",
    tags=["stages"],
)


@stages_router.get(
    "/",
    response_model=ApiSuccess[list[StageMasterRead]],
    dependencies=[ALL_ROLES],
)
def list_stage_masters(db: DbSession):
    """List all stage master definitions in sequence order."""
    stages = stage_service.list_stage_masters(db)
    return ApiSuccess(data=[StageMasterRead.model_validate(s) for s in stages])


@project_stages_router.get(
    "/",
    response_model=ApiSuccess[list[ProjectStageStatusRead]],
    dependencies=[ALL_ROLES],
)
def list_project_stage_statuses(
    project_id: uuid.UUID,
    db: DbSession,
    site_id: Optional[uuid.UUID] = Query(None),
    lot_id: Optional[uuid.UUID] = Query(None),
):
    statuses = stage_service.list_project_stage_statuses(
        db, project_id, site_id=site_id, lot_id=lot_id
    )
    enriched = [stage_service._enrich(s) for s in statuses]
    return ApiSuccess(data=enriched)


@project_stages_router.post(
    "/",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def upsert_stage_status(
    project_id: uuid.UUID,
    body: StageStatusUpsert,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create or update a stage status for a project/site/lot combination."""
    pss = stage_service.upsert_stage_status(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=stage_service._enrich(pss),
        message="Stage status saved.",
    )
