"""Stock routes — ledger, balances, usage."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.stock import StockBalanceRead, StockLedgerRead, UsageLogCreate, UsageLogRead
from app.services import stock_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get(
    "/balances",
    response_model=ApiSuccess[list[StockBalanceRead]],
    dependencies=[ALL_ROLES],
)
def get_stock_balances(
    db: DbSession,
    project_id: uuid.UUID = Query(...),
    site_id: Optional[uuid.UUID] = Query(None),
):
    balances = stock_service.get_balances(db, project_id, site_id)
    return ApiSuccess(data=balances)


@router.get(
    "/ledger",
    response_model=ApiSuccess[list[StockLedgerRead]],
    dependencies=[ALL_ROLES],
)
def get_ledger(
    db: DbSession,
    project_id: uuid.UUID = Query(...),
    site_id: Optional[uuid.UUID] = Query(None),
    item_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(200, le=500),
):
    entries = stock_service.list_ledger(db, project_id, site_id, item_id, limit)
    return ApiSuccess(data=[StockLedgerRead.model_validate(e) for e in entries])


@router.post(
    "/usage",
    response_model=ApiSuccess[UsageLogRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def record_usage(
    body: UsageLogCreate,
    db: DbSession,
    current_user: CurrentUser,
    project_id: uuid.UUID = Query(...),
):
    usage = stock_service.record_usage(db, project_id, body, current_user.id)
    return ApiSuccess(data=UsageLogRead.model_validate(usage), message="Usage recorded.")
