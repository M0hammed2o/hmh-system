"""Owner daily summary route."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, DbSession
from app.schemas.common import ApiSuccess
from app.services import summary_service
from pydantic import BaseModel
from datetime import date


router = APIRouter(prefix="/summary", tags=["summary"])


class DailySummaryRead(BaseModel):
    date_today: date
    spend_today: float
    spend_week: float
    spend_month: float
    deliveries_today: int
    active_lots: int
    delayed_lots: int
    completed_lots: int
    open_alerts: int
    material_overrun_alerts: int
    unmatched_invoices: int
    vehicle_spend_today: float
    vehicle_spend_month: float
    burn_rate_daily_avg: float


@router.get("/daily", response_model=ApiSuccess[DailySummaryRead], dependencies=[ALL_ROLES])
def get_daily_summary(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    summary = summary_service.get_daily_summary(db, project_id)
    return ApiSuccess(data=DailySummaryRead(**vars(summary)))
