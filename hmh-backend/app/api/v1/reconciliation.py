"""Admin reconciliation endpoint — read-only integrity checks across the system."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import OWNER_ONLY, DbSession
from app.schemas.common import ApiSuccess
from app.services import reconciliation_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/reconciliation",
    response_model=ApiSuccess[dict],
    dependencies=[OWNER_ONLY],
)
def run_integrity_check(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None, description="Scope to a single project"),
):
    """
    Run a full read-only integrity check across stock, procurement, payments,
    allocations, attachments, and notification queue.

    Returns a structured report — no data is modified.
    """
    result = reconciliation_service.run_full_integrity_check(db, project_id)
    overall = result.get("overall", "ok")
    total = result.get("total_issues", 0)
    msg = "All checks passed." if total == 0 else f"{total} issue(s) detected — see details."
    return ApiSuccess(data=result, message=msg)
