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


@router.get(
    "/operations",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def get_project_operations(db: DbSession):
    """Per-project operational overview: lots, milestones, requests, alerts, spend."""
    data = dashboard_service.get_project_operations(db)
    return ApiSuccess(data=data)


@router.get(
    "/ops-summary",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_ops_summary(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    """
    Operational command-center summary — all sections in one call.

    Returns: { financial, milestones, warehouse, fuel }

    Optionally scoped to a single project via ?project_id=.
    All periods bounded (current month / last 7 days).
    No N+1 queries — bulk counts only.
    """
    data = dashboard_service.get_ops_summary(db, project_id)
    return ApiSuccess(data=data)
