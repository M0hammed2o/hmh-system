"""Municipality Progress Claim routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from app.dependencies import (
    ALL_ROLES, CurrentUser, DbSession,
    OFFICE_AND_ABOVE, WRITE_ROLES, OWNER_ONLY,
    OFFICE_ADMIN_AND_ABOVE,
    check_project_access,
)
from app.models.enums import UserRole
from app.models.progress_claim import MunicipalityProgressClaim, ProgressClaimLine
from app.schemas.common import ApiSuccess
from app.schemas.progress_claim import (
    ProgressClaimRead, ProgressClaimCreate, ProgressClaimUpdate,
    ProgressClaimListItem, GenerateClaimRequest, ClaimLineUpdate, ClaimLineCreate,
    EvidenceAdd,
)
from app.services import progress_claim_service

project_claim_router = APIRouter(
    prefix="/projects/{project_id}/progress-claims",
    tags=["progress-claims"],
)
claim_router = APIRouter(prefix="/progress-claims", tags=["progress-claims"])


def _get_or_404(db: DbSession, claim_id: uuid.UUID) -> MunicipalityProgressClaim:
    claim = progress_claim_service.get_claim(db, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Progress claim not found")
    return claim


# ── Project-scoped endpoints ───────────────────────────────────────────────────

@project_claim_router.get("", response_model=ApiSuccess[list[ProgressClaimListItem]], dependencies=[ALL_ROLES])
def list_claims(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    site_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
):
    check_project_access(db, current_user, project_id)
    claims = progress_claim_service.list_claims(db, project_id, site_id=site_id, status=status)
    items = []
    for c in claims:
        lines = c.lines if hasattr(c, "lines") and c.lines else []
        items.append(
            ProgressClaimListItem(
                id=c.id,
                claim_number=c.claim_number,
                project_id=c.project_id,
                site_id=c.site_id,
                claim_title=c.claim_title,
                period_start=c.period_start,
                period_end=c.period_end,
                status=c.status,
                line_count=len(lines),
                included_line_count=sum(1 for l in lines if l.is_included),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )
    return ApiSuccess(data=items)


@project_claim_router.post("", response_model=ApiSuccess[ProgressClaimRead], dependencies=[OFFICE_AND_ABOVE])
def create_claim(
    project_id: uuid.UUID,
    body: ProgressClaimCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    claim = progress_claim_service.create_claim(
        db, project_id, body.model_dump(), actor_id=current_user.id
    )
    db.commit()
    db.refresh(claim)
    return ApiSuccess(data=ProgressClaimRead.model_validate(claim))


# ── Claim-level endpoints ──────────────────────────────────────────────────────

@claim_router.get("/{claim_id}", response_model=ApiSuccess[ProgressClaimRead], dependencies=[ALL_ROLES])
def get_claim(claim_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    return ApiSuccess(data=ProgressClaimRead.model_validate(claim))


@claim_router.patch("/{claim_id}", response_model=ApiSuccess[ProgressClaimRead], dependencies=[OFFICE_AND_ABOVE])
def update_claim(
    claim_id: uuid.UUID,
    body: ProgressClaimUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    try:
        progress_claim_service.update_claim(db, claim, body.model_dump(exclude_none=True), actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    db.refresh(claim)
    return ApiSuccess(data=ProgressClaimRead.model_validate(claim))


@claim_router.delete("/{claim_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_ADMIN_AND_ABOVE])
def delete_claim(claim_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    try:
        progress_claim_service.delete_claim(db, claim, actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return ApiSuccess(data={"deleted": True})


@claim_router.post("/{claim_id}/generate", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def generate_lines(
    claim_id: uuid.UUID,
    body: GenerateClaimRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    try:
        summary = progress_claim_service.generate_lines(
            db, claim,
            actor_id=current_user.id,
            include_work_done=body.include_work_done,
            include_job_cards=body.include_job_cards,
            include_milestones=body.include_milestones,
            overwrite_existing=body.overwrite_existing,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return ApiSuccess(data=summary, message="Lines generated successfully")


@claim_router.post("/{claim_id}/transition/{new_status}", response_model=ApiSuccess[ProgressClaimRead])
def transition_status(
    claim_id: uuid.UUID,
    new_status: str,
    db: DbSession,
    current_user: CurrentUser,
):
    from app.models.enums import ProgressClaimStatus
    check_status = new_status.upper()

    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)

    # Only OWNER can approve
    if check_status == ProgressClaimStatus.APPROVED.value:
        if current_user.role not in (UserRole.OWNER.value, UserRole.OFFICE_ADMIN.value):
            raise HTTPException(status_code=403, detail="Only OWNER or OFFICE_ADMIN can approve claims.")

    try:
        progress_claim_service.transition_status(
            db, claim, check_status, actor_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    claim = _get_or_404(db, claim_id)
    return ApiSuccess(data=ProgressClaimRead.model_validate(claim))


@claim_router.get("/{claim_id}/export/pdf", dependencies=[ALL_ROLES])
def export_pdf(claim_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    pdf_bytes = progress_claim_service.export_pdf(claim)
    filename = f"{claim.claim_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Claim line endpoints ───────────────────────────────────────────────────────

@claim_router.patch("/{claim_id}/lines/{line_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def update_line(
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    body: ClaimLineUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    from sqlalchemy import select
    line = db.execute(
        select(ProgressClaimLine).where(
            ProgressClaimLine.id == line_id,
            ProgressClaimLine.claim_id == claim_id,
        )
    ).scalars().first()
    if not line:
        raise HTTPException(status_code=404, detail="Claim line not found")
    progress_claim_service.update_line(db, line, body.model_dump(exclude_none=True), actor_id=current_user.id)
    db.commit()
    return ApiSuccess(data={"updated": True})


@claim_router.post("/{claim_id}/lines", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def add_line(
    claim_id: uuid.UUID,
    body: ClaimLineCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    try:
        line = progress_claim_service.add_manual_line(db, claim, body.model_dump(), actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return ApiSuccess(data={"id": str(line.id)})


@claim_router.delete("/{claim_id}/lines/{line_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_line(
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    from sqlalchemy import select
    line = db.execute(
        select(ProgressClaimLine).where(
            ProgressClaimLine.id == line_id,
            ProgressClaimLine.claim_id == claim_id,
        )
    ).scalars().first()
    if not line:
        raise HTTPException(status_code=404, detail="Claim line not found")
    db.delete(line)
    db.commit()
    return ApiSuccess(data={"deleted": True})


# ── Evidence endpoints ─────────────────────────────────────────────────────────

@claim_router.post("/{claim_id}/evidence", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def add_evidence(
    claim_id: uuid.UUID,
    body: EvidenceAdd,
    db: DbSession,
    current_user: CurrentUser,
):
    claim = _get_or_404(db, claim_id)
    check_project_access(db, current_user, claim.project_id)
    ev = progress_claim_service.add_evidence(db, claim_id, body.model_dump(), actor_id=current_user.id)
    db.commit()
    return ApiSuccess(data={"id": str(ev.id)})
