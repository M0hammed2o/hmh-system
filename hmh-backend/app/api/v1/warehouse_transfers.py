"""Warehouse Transfer Request API — project-to-project transfers with 3-person office approval."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, OWNER_ONLY, WRITE_ROLES, check_project_access
from app.models.project import Project
from app.models.user import User
from app.models.warehouse_transfer import TRANSFER_VOTES_REQUIRED, WarehouseTransferRequest, WarehouseTransferVote
from app.schemas.common import ApiSuccess
from app.schemas.warehouse_transfer import (
    CastVoteRequest,
    RejectTransferRequest,
    WarehouseTransferRequestCreate,
    WarehouseTransferRequestRead,
    VoteRead,
)
from app.services import warehouse_transfer_service as svc

router = APIRouter(prefix="/warehouse-transfers", tags=["warehouse-transfers"])
project_wt_router = APIRouter(prefix="/projects/{project_id}/warehouse-transfers", tags=["warehouse-transfers"])


def _enrich(db: Session, req: WarehouseTransferRequest) -> dict:
    """Add display names to a transfer request dict."""
    from app.models.item import Item

    from_proj = db.get(Project, req.from_project_id)
    to_proj   = db.get(Project, req.to_project_id)
    item      = db.get(Item, req.item_id)
    requester = db.get(User, req.requested_by)

    votes = []
    for v in req.votes:
        voter = db.get(User, v.voted_by)
        votes.append({
            "id": str(v.id),
            "voted_by": str(v.voted_by),
            "voted_by_name": voter.full_name if voter else None,
            "voted_at": v.voted_at.isoformat(),
            "is_override": v.is_override,
            "notes": v.notes,
        })

    non_override_votes = sum(1 for v in req.votes if not v.is_override)

    return {
        "id": str(req.id),
        "from_project_id": str(req.from_project_id),
        "from_project_name": from_proj.name if from_proj else None,
        "to_project_id": str(req.to_project_id),
        "to_project_name": to_proj.name if to_proj else None,
        "item_id": str(req.item_id),
        "item_name": item.name if item else None,
        "quantity": float(req.quantity),
        "unit": req.unit,
        "reason": req.reason,
        "notes": req.notes,
        "status": req.status,
        "requested_by": str(req.requested_by),
        "requested_by_name": requester.full_name if requester else None,
        "requested_at": req.requested_at.isoformat(),
        "executed_at": req.executed_at.isoformat() if req.executed_at else None,
        "rejection_reason": req.rejection_reason,
        "vote_count": non_override_votes,
        "votes_required": TRANSFER_VOTES_REQUIRED,
        "votes": votes,
        "created_at": req.created_at.isoformat(),
    }


# ── Submit a new transfer request (any write-capable user including site staff) ──

@project_wt_router.post("/", response_model=ApiSuccess[dict], dependencies=[WRITE_ROLES])
def submit_transfer_request(
    project_id: uuid.UUID,
    body: WarehouseTransferRequestCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    req = svc.create_transfer_request(
        db,
        from_project_id=project_id,
        to_project_id=body.to_project_id,
        item_id=body.item_id,
        quantity=body.quantity,
        reason=body.reason,
        requested_by=current_user.id,
        notes=body.notes,
    )
    return ApiSuccess(data=_enrich(db, req))


# ── List transfer requests for a project ──

@project_wt_router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES])
def list_project_transfer_requests(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = Query(None),
):
    check_project_access(db, current_user, project_id)
    requests = svc.list_transfer_requests(db, project_id=project_id, status=status)
    return ApiSuccess(data=[_enrich(db, r) for r in requests])


# ── List ALL pending transfers (office-wide view) ──

@router.get("/pending", response_model=ApiSuccess[list[dict]], dependencies=[OFFICE_AND_ABOVE])
def list_all_pending(db: DbSession):
    requests = svc.list_transfer_requests(db, status="PENDING")
    return ApiSuccess(data=[_enrich(db, r) for r in requests])


# ── Get single transfer request ──

@router.get("/{transfer_id}", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_transfer_request(transfer_id: uuid.UUID, db: DbSession):
    req = svc.get_transfer_request(db, transfer_id)
    return ApiSuccess(data=_enrich(db, req))


# ── Cast a vote (office staff) ──

@router.post("/{transfer_id}/vote", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def cast_vote(transfer_id: uuid.UUID, body: CastVoteRequest, db: DbSession, current_user: CurrentUser):
    req = svc.cast_vote(db, transfer_id, current_user.id, body.notes)
    return ApiSuccess(data=_enrich(db, req))


# ── Owner override ──

@router.post("/{transfer_id}/override", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def override_approve(transfer_id: uuid.UUID, body: CastVoteRequest, db: DbSession, current_user: CurrentUser):
    req = svc.override_approve(db, transfer_id, current_user.id, body.notes)
    return ApiSuccess(data=_enrich(db, req))


# ── Reject ──

@router.post("/{transfer_id}/reject", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def reject_transfer(transfer_id: uuid.UUID, body: RejectTransferRequest, db: DbSession, current_user: CurrentUser):
    req = svc.reject_transfer(db, transfer_id, current_user.id, body.reason)
    return ApiSuccess(data=_enrich(db, req))
