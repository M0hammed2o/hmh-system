"""Job Card routes — labour approval chain."""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.job_card import JobCard
from app.models.enums import JobCardStatus, JobCardWorkType
from app.schemas.common import ApiSuccess
from app.services import job_card_service

project_jc_router = APIRouter(prefix="/projects/{project_id}/job-cards", tags=["job-cards"])
jc_router = APIRouter(prefix="/job-cards", tags=["job-cards"])


class JobCardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_card_number: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None   # links to stage_master.id for milestone grouping
    work_description: str
    work_type: JobCardWorkType
    worker_name: Optional[str] = None
    team_name: Optional[str] = None
    quantity: float
    unit: Optional[str] = None
    rate: float
    total_amount: float
    owner_approval_required: bool
    status: JobCardStatus
    submitted_by: Optional[uuid.UUID] = None
    submitted_at: Optional[datetime] = None
    site_approved_by: Optional[uuid.UUID] = None
    site_approved_at: Optional[datetime] = None
    office_approved_by: Optional[uuid.UUID] = None
    office_approved_at: Optional[datetime] = None
    owner_approved_by: Optional[uuid.UUID] = None
    owner_approved_at: Optional[datetime] = None
    payment_approved_by: Optional[uuid.UUID] = None
    payment_approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    work_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobCardCreate(BaseModel):
    site_id: uuid.UUID
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    work_description: str
    work_type: JobCardWorkType = JobCardWorkType.DAILY_LABOUR
    worker_name: Optional[str] = None
    team_name: Optional[str] = None
    quantity: float = 1.0
    unit: Optional[str] = None
    rate: float
    work_date: Optional[str] = None
    notes: Optional[str] = None


class RejectBody(BaseModel):
    reason: str


@project_jc_router.get("/", response_model=ApiSuccess[list[JobCardRead]], dependencies=[ALL_ROLES])
def list_job_cards(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    status:  Optional[JobCardStatus] = Query(None),
    lot_id:  Optional[uuid.UUID]     = Query(None),
    site_id: Optional[uuid.UUID]     = Query(None),
):
    check_project_access(db, current_user, project_id)
    jcs = job_card_service.list_job_cards(db, project_id, status=status, lot_id=lot_id, site_id=site_id)
    return ApiSuccess(data=[JobCardRead.model_validate(j) for j in jcs])


@project_jc_router.post("/", response_model=ApiSuccess[JobCardRead], status_code=201, dependencies=[WRITE_ROLES])
def create_job_card(project_id: uuid.UUID, body: JobCardCreate, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    from datetime import date
    work_date = date.fromisoformat(body.work_date) if body.work_date else None
    jc = job_card_service.create_job_card(
        db, project_id, body.site_id, body.work_description, body.work_type,
        body.quantity, body.unit, body.rate, current_user.id,
        lot_id=body.lot_id, stage_id=body.stage_id,
        worker_name=body.worker_name, team_name=body.team_name,
        work_date=work_date, notes=body.notes,
    )
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Job card created.")


@project_jc_router.get("/summary", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    return ApiSuccess(data=job_card_service.get_summary(db, project_id))


@jc_router.get("/{jc_id}", response_model=ApiSuccess[JobCardRead], dependencies=[ALL_ROLES])
def get_job_card(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    jc = job_card_service._get_or_404(db, jc_id)
    check_project_access(db, current_user, jc.project_id)
    return ApiSuccess(data=JobCardRead.model_validate(jc))


@jc_router.post("/{jc_id}/submit", response_model=ApiSuccess[JobCardRead], dependencies=[WRITE_ROLES])
def submit(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.submit(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Submitted.")


@jc_router.post("/{jc_id}/site-approve", response_model=ApiSuccess[JobCardRead], dependencies=[WRITE_ROLES])
def site_approve(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.site_approve(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Site approved.")


@jc_router.post("/{jc_id}/office-approve", response_model=ApiSuccess[JobCardRead], dependencies=[OFFICE_AND_ABOVE])
def office_approve(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.office_approve(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Office approved.")


@jc_router.post("/{jc_id}/owner-approve", response_model=ApiSuccess[JobCardRead], dependencies=[WRITE_ROLES])
def owner_approve(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.owner_approve(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Owner approved.")


@jc_router.post("/{jc_id}/approve-payment", response_model=ApiSuccess[JobCardRead], dependencies=[OFFICE_AND_ABOVE])
def approve_payment(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.approve_payment(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Approved for payment.")


@jc_router.post("/{jc_id}/mark-paid", response_model=ApiSuccess[JobCardRead], dependencies=[OFFICE_AND_ABOVE])
def mark_paid(jc_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.mark_paid(db, jc_id, current_user.id)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Marked as paid.")


@jc_router.post("/{jc_id}/reject", response_model=ApiSuccess[JobCardRead], dependencies=[WRITE_ROLES])
def reject(jc_id: uuid.UUID, body: RejectBody, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, job_card_service._get_or_404(db, jc_id).project_id)
    jc = job_card_service.reject(db, jc_id, current_user.id, body.reason)
    return ApiSuccess(data=JobCardRead.model_validate(jc), message="Rejected.")
