"""Subcontractor Work Done routes — progress/payment claim module."""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.enums import WorkDoneStatus
from app.models.work_done import SubcontractorWorkDone
from app.schemas.common import ApiSuccess
from app.services import work_done_service

project_wd_router = APIRouter(prefix="/projects/{project_id}/work-done", tags=["work-done"])
wd_router = APIRouter(prefix="/work-done", tags=["work-done"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class WorkDoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_done_number: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    supplier_id: uuid.UUID
    job_card_id: Optional[uuid.UUID] = None
    work_description: str
    quantity: float
    unit: Optional[str] = None
    rate: float
    amount: float
    month: date
    comments: Optional[str] = None
    status: WorkDoneStatus
    submitted_by: Optional[uuid.UUID] = None
    submitted_at: Optional[datetime] = None
    site_approved_by: Optional[uuid.UUID] = None
    site_approved_at: Optional[datetime] = None
    office_approved_by: Optional[uuid.UUID] = None
    office_approved_at: Optional[datetime] = None
    paid_by: Optional[uuid.UUID] = None
    paid_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class WorkDoneCreate(BaseModel):
    site_id: uuid.UUID
    supplier_id: uuid.UUID
    work_description: str
    quantity: float = 1.0
    unit: Optional[str] = None
    rate: float
    month: date  # frontend sends ISO date; will be normalised to 1st of month
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    job_card_id: Optional[uuid.UUID] = None
    comments: Optional[str] = None


class WorkDoneUpdate(BaseModel):
    work_description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    rate: Optional[float] = None
    month: Optional[date] = None
    comments: Optional[str] = None
    lot_id: Optional[uuid.UUID] = None
    stage_status_id: Optional[uuid.UUID] = None
    job_card_id: Optional[uuid.UUID] = None


class RejectBody(BaseModel):
    reason: str


# ── Project-scoped list + create ──────────────────────────────────────────────

@project_wd_router.get("/", response_model=ApiSuccess[list[WorkDoneRead]], dependencies=[ALL_ROLES])
def list_work_done(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    status:      Optional[WorkDoneStatus] = Query(None),
    site_id:     Optional[uuid.UUID]      = Query(None),
    lot_id:      Optional[uuid.UUID]      = Query(None),
    supplier_id: Optional[uuid.UUID]      = Query(None),
    month:       Optional[date]           = Query(None),
):
    check_project_access(db, current_user, project_id)
    items = work_done_service.list_work_done(
        db, project_id, status=status, site_id=site_id,
        lot_id=lot_id, supplier_id=supplier_id, month=month,
    )
    return ApiSuccess(data=[WorkDoneRead.model_validate(w) for w in items])


@project_wd_router.post("/", response_model=ApiSuccess[WorkDoneRead], status_code=201, dependencies=[WRITE_ROLES])
def create_work_done(project_id: uuid.UUID, body: WorkDoneCreate, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    wd = work_done_service.create_work_done(
        db, project_id, body.site_id, body.supplier_id,
        body.work_description, body.quantity, body.unit, body.rate, body.month,
        current_user.id,
        lot_id=body.lot_id, stage_status_id=body.stage_status_id,
        job_card_id=body.job_card_id, comments=body.comments,
    )
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Work done record created.")


@project_wd_router.get("/summary", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    return ApiSuccess(data=work_done_service.get_summary(db, project_id))


@project_wd_router.get("/monthly-summary", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def monthly_summary(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    month:       Optional[date]      = Query(None),
    site_id:     Optional[uuid.UUID] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
):
    check_project_access(db, current_user, project_id)
    return ApiSuccess(data=work_done_service.get_monthly_summary(
        db, project_id, month=month, site_id=site_id, supplier_id=supplier_id,
    ))


# ── Single-record endpoints ────────────────────────────────────────────────────

@wd_router.get("/{wd_id}", response_model=ApiSuccess[WorkDoneRead], dependencies=[ALL_ROLES])
def get_work_done(wd_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd))


@wd_router.patch("/{wd_id}", response_model=ApiSuccess[WorkDoneRead], dependencies=[WRITE_ROLES])
def update_work_done(wd_id: uuid.UUID, body: WorkDoneUpdate, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.update_work_done(
        db, wd_id, current_user.id,
        work_description=body.work_description,
        quantity=body.quantity,
        unit=body.unit,
        rate=body.rate,
        month=body.month,
        comments=body.comments,
        lot_id=body.lot_id,
        stage_status_id=body.stage_status_id,
        job_card_id=body.job_card_id,
    )
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Updated.")


@wd_router.post("/{wd_id}/submit", response_model=ApiSuccess[WorkDoneRead], dependencies=[WRITE_ROLES])
def submit(wd_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.submit(db, wd_id, current_user.id)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Submitted for review.")


@wd_router.post("/{wd_id}/site-approve", response_model=ApiSuccess[WorkDoneRead], dependencies=[WRITE_ROLES])
def site_approve(wd_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.site_approve(db, wd_id, current_user.id)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Site approved.")


@wd_router.post("/{wd_id}/office-approve", response_model=ApiSuccess[WorkDoneRead], dependencies=[OFFICE_AND_ABOVE])
def office_approve(wd_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.office_approve(db, wd_id, current_user.id)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Office approved.")


@wd_router.post("/{wd_id}/mark-paid", response_model=ApiSuccess[WorkDoneRead], dependencies=[OFFICE_AND_ABOVE])
def mark_paid(wd_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.mark_paid(db, wd_id, current_user.id)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Marked as paid.")


@wd_router.post("/{wd_id}/reject", response_model=ApiSuccess[WorkDoneRead], dependencies=[WRITE_ROLES])
def reject(wd_id: uuid.UUID, body: RejectBody, db: DbSession, current_user: CurrentUser):
    wd = work_done_service._get_or_404(db, wd_id)
    check_project_access(db, current_user, wd.project_id)
    wd = work_done_service.reject(db, wd_id, current_user.id, body.reason)
    return ApiSuccess(data=WorkDoneRead.model_validate(wd), message="Rejected.")
