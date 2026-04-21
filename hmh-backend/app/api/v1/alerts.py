"""System alert routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.models.enums import AlertStatus
from app.schemas.alert import AlertRead, AlertUpdate
from app.schemas.common import ApiSuccess
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "/",
    response_model=ApiSuccess[list[AlertRead]],
    dependencies=[ALL_ROLES],
)
def list_alerts(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
    status: Optional[AlertStatus] = Query(None),
    limit: int = Query(100, le=500),
):
    alerts = alert_service.list_alerts(db, project_id, status, limit)
    return ApiSuccess(data=[AlertRead.model_validate(a) for a in alerts])


@router.patch(
    "/{alert_id}",
    response_model=ApiSuccess[AlertRead],
    dependencies=[ALL_ROLES],
)
def update_alert(
    alert_id: uuid.UUID,
    body: AlertUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    alert = alert_service.update_alert(db, alert_id, body, current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert updated.")
