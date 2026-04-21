"""Dashboard stats route."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, DbSession
from app.schemas.common import ApiSuccess
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/stats",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_dashboard_stats(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    stats = dashboard_service.get_stats(db, project_id)
    return ApiSuccess(data=stats)
