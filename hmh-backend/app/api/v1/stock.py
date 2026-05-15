"""Stock routes — ledger, balances, usage, transfers."""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel

from app.core.config import settings
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
    usage = stock_service.record_usage(db, project_id, body, current_user.id, overrun_reason=body.overrun_reason)
    return ApiSuccess(data=UsageLogRead.model_validate(usage), message="Usage recorded.")


# ── Issue to lot ──────────────────────────────────────────────────────────────

@router.post(
    "/refresh-balances",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def refresh_stock_balances(db: DbSession):
    """Force-refresh the stock_balances materialized view."""
    from sqlalchemy import text as _t
    try:
        db.execute(_t("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
        db.commit()
        return ApiSuccess(data={"refreshed": True}, message="Stock balances refreshed.")
    except Exception as exc:
        db.rollback()
        return ApiSuccess(data={"refreshed": False, "error": str(exc)}, message="Refresh attempted.")


@router.post(
    "/usage-with-evidence",
    response_model=ApiSuccess[UsageLogRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
async def record_usage_with_evidence(
    db:              DbSession,
    current_user:    CurrentUser,
    project_id:      str  = Form(...),
    site_id:         str  = Form(...),
    item_id:         str  = Form(...),
    quantity_used:   float = Form(...),
    lot_id:          Optional[str]  = Form(None),
    stage_id:        Optional[str]  = Form(None),
    boq_item_id:     Optional[str]  = Form(None),
    used_by_person_name: Optional[str] = Form(None),
    used_by_team_name:   Optional[str] = Form(None),
    comments:        Optional[str]  = Form(None),
    overrun_reason:  Optional[str]  = Form(None),
    evidence_file:   Optional[UploadFile] = File(None),
):
    """Record usage and optionally save an evidence photo."""
    from app.schemas.stock import UsageLogCreate

    # Save evidence file first
    evidence_url: Optional[str] = None
    if evidence_file and evidence_file.filename:
        ev_dir = os.path.join(settings.UPLOAD_DIR, "site_evidence", "usage")
        os.makedirs(ev_dir, exist_ok=True)
        ext    = os.path.splitext(evidence_file.filename)[1] or ".bin"
        fname  = f"{uuid.uuid4().hex}{ext}"
        content = await evidence_file.read()
        with open(os.path.join(ev_dir, fname), "wb") as fh:
            fh.write(content)
        evidence_url = f"/uploads/site_evidence/usage/{fname}"

    note_parts = []
    if comments:
        note_parts.append(comments)
    if evidence_url:
        note_parts.append(f"evidence:{evidence_url}")

    body = UsageLogCreate(
        site_id             = uuid.UUID(site_id),
        item_id             = uuid.UUID(item_id),
        quantity_used       = quantity_used,
        lot_id              = uuid.UUID(lot_id)      if lot_id      else None,
        stage_id            = uuid.UUID(stage_id)    if stage_id    else None,
        boq_item_id         = uuid.UUID(boq_item_id) if boq_item_id else None,
        used_by_person_name = used_by_person_name,
        used_by_team_name   = used_by_team_name,
        usage_date          = datetime.now(timezone.utc),
        comments            = " | ".join(note_parts) or None,
        overrun_reason      = overrun_reason,
    )
    usage = stock_service.record_usage(
        db, uuid.UUID(project_id), body, current_user.id,
        overrun_reason=overrun_reason,
    )
    return ApiSuccess(
        data=UsageLogRead.model_validate(usage),
        message="Usage recorded." + (f" Evidence saved: {evidence_url}" if evidence_url else ""),
    )


class IssueToLotBody(BaseModel):
    project_id: uuid.UUID
    from_site_id: uuid.UUID
    lot_id: uuid.UUID
    item_id: uuid.UUID
    quantity: float
    notes: Optional[str] = None
    overrun_reason: Optional[str] = None
    unit_cost: Optional[float] = None


@router.post(
    "/issue-to-lot",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def issue_to_lot(body: IssueToLotBody, db: DbSession, current_user: CurrentUser):
    """
    Issue stock from a site store/warehouse into a specific lot.
    Runs BOQ allocation check — raises 422 with overrun detail if over budget.
    """
    from app.services.transfer_service import transfer_to_lot
    entry = transfer_to_lot(
        db,
        project_id=body.project_id,
        site_id=body.from_site_id,
        lot_id=body.lot_id,
        item_id=body.item_id,
        quantity=body.quantity,
        entered_by=current_user.id,
        notes=body.notes,
        overrun_reason=body.overrun_reason,
        unit_cost=body.unit_cost,
    )
    return ApiSuccess(
        data={"ledger_id": str(entry.id), "lot_id": str(body.lot_id), "quantity": body.quantity},
        message=f"{body.quantity} units issued to lot.",
    )


class SiteTransferBody(BaseModel):
    project_id: uuid.UUID
    from_site_id: uuid.UUID
    to_site_id: uuid.UUID
    item_id: uuid.UUID
    quantity: float
    notes: Optional[str] = None
    unit_cost: Optional[float] = None


@router.post(
    "/site-transfer",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def site_transfer(body: SiteTransferBody, db: DbSession, current_user: CurrentUser):
    """Transfer stock between two sites (e.g. main warehouse → site store)."""
    from app.services.transfer_service import transfer_to_site
    out_entry, in_entry = transfer_to_site(
        db,
        project_id=body.project_id,
        from_site_id=body.from_site_id,
        to_site_id=body.to_site_id,
        item_id=body.item_id,
        quantity=body.quantity,
        entered_by=current_user.id,
        notes=body.notes,
        unit_cost=body.unit_cost,
    )
    return ApiSuccess(
        data={"out_ledger_id": str(out_entry.id), "in_ledger_id": str(in_entry.id)},
        message=f"{body.quantity} units transferred.",
    )
