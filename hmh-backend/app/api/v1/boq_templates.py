"""BOQ template routes — list templates, clone template to lots."""

import logging
import traceback
import uuid

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

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
    template_boq_id: uuid.UUID
    project_id: uuid.UUID
    lot_ids: list[uuid.UUID]


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


@router.post(
    "/clone-to-lots",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def clone_to_lots(body: CloneToLotsRequest, db: DbSession, current_user: CurrentUser):
    print(
        f"[BOQ-CLONE] template_boq_id={body.template_boq_id}"
        f" project_id={body.project_id}"
        f" lot_ids={body.lot_ids}"
        f" actor={current_user.id}",
        flush=True,
    )
    if not body.lot_ids:
        raise HTTPException(
            status_code=422,
            detail="No lots selected. Please select at least one lot to apply the template to.",
        )
    try:
        headers = boq_template_service.clone_template_to_lots(
            db,
            template_boq_id=body.template_boq_id,
            project_id=body.project_id,
            lot_ids=body.lot_ids,
            actor_id=current_user.id,
        )
        print(f"[BOQ-CLONE] SUCCESS — created {len(headers)} header(s)", flush=True)
        return ApiSuccess(
            data={"created_count": len(headers), "lot_ids": [str(h.id) for h in headers]},
            message=f"BOQ cloned to {len(headers)} lots.",
        )
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[BOQ-CLONE] FAILED: {exc!r}\n{tb}", flush=True)
        logger.error("clone_to_lots failed: %s\n%s", exc, tb)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clone template: {exc}",
        )
