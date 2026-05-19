"""Stage routes."""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.core.config import settings
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


@stages_router.post(
    "/seed",
    response_model=ApiSuccess[list[StageMasterRead]],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def seed_stages(db: DbSession):
    """Seed default construction stages. Skips stages that already exist."""
    stages = stage_service.seed_default_stages(db)
    return ApiSuccess(
        data=[StageMasterRead.model_validate(s) for s in stages],
        message=f"{len(stages)} stages ensured.",
    )


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
    dependencies=[ALL_ROLES],   # site managers must be able to update stage progress
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


@project_stages_router.post(
    "/with-evidence",
    response_model=ApiSuccess[ProjectStageStatusRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
async def upsert_stage_status_with_evidence(
    project_id: uuid.UUID,
    db:          DbSession,
    current_user: CurrentUser,
    stage_id:    str           = Form(...),
    status:      Optional[str] = Form(None),
    site_id:     Optional[str] = Form(None),
    lot_id:      Optional[str] = Form(None),
    notes:       Optional[str] = Form(None),
    delay_reason: Optional[str] = Form(None),
    evidence_file: Optional[UploadFile] = File(None),
):
    """Update a stage status and optionally upload a progress photo."""
    from app.models.enums import StageStatus

    # Save evidence photo (Supabase Storage when configured, else local disk)
    from app.core.storage import save_upload
    evidence_url: Optional[str] = None
    if evidence_file and evidence_file.filename:
        ext     = os.path.splitext(evidence_file.filename)[1] or ".bin"
        fname   = f"{uuid.uuid4().hex}{ext}"
        content = await evidence_file.read()
        evidence_url = save_upload(content, f"site_evidence/stages/{fname}")

    # Append evidence URL to notes so it's linked to the record
    combined_notes = notes or ""
    if evidence_url:
        combined_notes = f"evidence:{evidence_url}" + (f" | {combined_notes}" if combined_notes else "")

    body = StageStatusUpsert(
        stage_id     = uuid.UUID(stage_id),
        site_id      = uuid.UUID(site_id) if site_id else None,
        lot_id       = uuid.UUID(lot_id)  if lot_id  else None,
        status       = StageStatus(status) if status else None,
        notes        = combined_notes or None,
        delay_reason = delay_reason,
    )
    pss = stage_service.upsert_stage_status(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=stage_service._enrich(pss),
        message="Stage updated." + (f" Photo saved: {evidence_url}" if evidence_url else ""),
    )
