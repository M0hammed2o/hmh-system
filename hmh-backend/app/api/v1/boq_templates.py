"""BOQ template routes — list templates, clone template to lots."""

import logging
import traceback
import uuid

from fastapi import APIRouter, HTTPException

from app.core.logging_config import get_logger

logger = get_logger(__name__)

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.services import boq_template_service
from pydantic import BaseModel
from typing import Optional


router = APIRouter(prefix="/boq-templates", tags=["boq-templates"])


class BOQTemplateRead(BaseModel):
    id: uuid.UUID
    version_name: str
    template_name: Optional[str]
    notes: Optional[str]


class CloneToLotsRequest(BaseModel):
    template_boq_id:     uuid.UUID
    project_id:          uuid.UUID
    lot_ids:             list[uuid.UUID]
    mode:                str  = "CREATE"  # "CREATE" | "SAFE" | "FORCE"
    overwrite:           bool = False     # deprecated alias for mode="FORCE"
    generate_milestones: bool = True      # seed ProjectStageStatus for template stages


class PreviewCloneRequest(BaseModel):
    template_boq_id: uuid.UUID
    project_id:      uuid.UUID
    lot_ids:         list[uuid.UUID]
    mode:            str = "CREATE"     # "CREATE" | "SAFE" | "FORCE"


@router.get("/", response_model=ApiSuccess[list[BOQTemplateRead]], dependencies=[ALL_ROLES])
def list_templates(db: DbSession):
    templates = boq_template_service.list_templates(db)
    return ApiSuccess(data=[
        BOQTemplateRead(
            id=t.id,
            version_name=t.version_name,
            template_name=t.template_name,
            notes=t.notes,
        )
        for t in templates
    ])


@router.delete(
    "/{template_id}",
    response_model=ApiSuccess[None],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_template(template_id: uuid.UUID, db: DbSession):
    """
    Delete a BOQ template header (marks it as inactive / removes the is_template flag).
    Lots that were already cloned from this template keep their BOQ data.
    """
    from app.models.boq import BOQHeader
    from fastapi import HTTPException

    header = db.get(BOQHeader, template_id)
    if not header or not header.is_template:
        raise HTTPException(404, "BOQ template not found.")
    # Soft-remove: unmark as template rather than hard-deleting
    # so cloned lot BOQs that reference this template_boq_id are unaffected.
    header.is_template = False
    header.template_name = None
    db.commit()
    logger.info("boq_template deleted id=%s", template_id)
    return ApiSuccess(data=None, message="Template deleted.")


@router.post(
    "/preview-clone",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def preview_clone(body: PreviewCloneRequest, db: DbSession):
    """
    Dry-run: show what WOULD happen if the template were applied to the
    selected lots, without writing anything to the database.
    """
    if not body.lot_ids:
        raise HTTPException(422, "Select at least one lot.")
    try:
        result = boq_template_service.preview_clone(
            db,
            template_boq_id=body.template_boq_id,
            project_id=body.project_id,
            lot_ids=body.lot_ids,
            mode=body.mode,
        )
        return ApiSuccess(data=result)
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("preview_clone failed: %s\n%s", exc, tb)
        raise HTTPException(400, detail=str(exc))


@router.post(
    "/clone-to-lots",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def clone_to_lots(body: CloneToLotsRequest, db: DbSession, current_user: CurrentUser):
    logger.info("boq_clone template=%s project=%s lots=%d mode=%s actor=%s",
                body.template_boq_id, body.project_id, len(body.lot_ids), body.mode, current_user.id)
    if not body.lot_ids:
        raise HTTPException(422, "No lots selected. Select at least one lot.")
    try:
        result = boq_template_service.clone_template_to_lots(
            db,
            template_boq_id=body.template_boq_id,
            project_id=body.project_id,
            lot_ids=body.lot_ids,
            actor_id=current_user.id,
            mode=body.mode,
            overwrite=body.overwrite,   # compat alias
            generate_milestones=body.generate_milestones,
        )
        parts = [f"BOQ applied to {result['created_count']} lot(s)"]
        if result.get("skipped_count"):
            parts.append(f"{result['skipped_count']} lot(s) skipped")
        if result.get("milestones_created"):
            parts.append(f"{result['milestones_created']} milestone(s) seeded")
        if result.get("deactivated_count"):
            parts.append(f"{result['deactivated_count']} item(s) replaced")
        msg = " · ".join(parts)
        logger.info("boq_clone success %s", msg)
        return ApiSuccess(data=result, message=msg.strip())
    except Exception as exc:
        logger.exception("boq_clone failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply template: {exc}",
        )
