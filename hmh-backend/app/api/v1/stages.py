"""Stage routes."""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.core.storage import save_upload
from app.core.upload_validation import PHOTO_MIMES, validate_upload
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.attachment import Attachment
from app.models.enums import AttachmentEntity, AttachmentType
from app.schemas.common import ApiSuccess
from app.schemas.stage import ProjectStageStatusRead, StageMasterRead, StageStatusUpsert
from app.services import stage_service

stages_router = APIRouter(prefix="/stages", tags=["stages"])
project_stages_router = APIRouter(
    prefix="/projects/{project_id}/stage-statuses",
    tags=["stages"],
)


@stages_router.get(
    "/",
    response_model=ApiSuccess[list[StageMasterRead]],
    dependencies=[ALL_ROLES],
)
def list_stage_masters(db: DbSession):
    """List all stage master definitions in sequence order."""
    stages = stage_service.list_stage_masters(db)
    return ApiSuccess(data=[StageMasterRead.model_validate(s) for s in stages])


@stages_router.post(
    "/seed",
    response_model=ApiSuccess[list[StageMasterRead]],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def seed_stages(db: DbSession):
    """Seed default construction stages. Skips stages that already exist."""
    stages = stage_service.seed_default_stages(db)
    return ApiSuccess(
        data=[StageMasterRead.model_validate(s) for s in stages],
        message=f"{len(stages)} stages ensured.",
    )


@project_stages_router.get(
    "/",
    response_model=ApiSuccess[list[ProjectStageStatusRead]],
    dependencies=[ALL_ROLES],
)
def list_project_stage_statuses(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    site_id: Optional[uuid.UUID] = Query(None),
    lot_id: Optional[uuid.UUID] = Query(None),
):
    check_project_access(db, current_user, project_id)
    statuses = stage_service.list_project_stage_statuses(
        db, project_id, site_id=site_id, lot_id=lot_id
    )
    enriched = [stage_service._enrich(s) for s in statuses]
    return ApiSuccess(data=enriched)


@project_stages_router.post(
    "/",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[WRITE_ROLES],
)
def upsert_stage_status(
    project_id: uuid.UUID,
    body: StageStatusUpsert,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create or update a stage status for a project/site/lot combination."""
    check_project_access(db, current_user, project_id)
    try:
        pss = stage_service.upsert_stage_status(
            db, project_id, body, current_user.id, actor_role=current_user.role
        )
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message)
    return ApiSuccess(
        data=stage_service._enrich(pss),
        message="Stage status saved.",
    )


@project_stages_router.post(
    "/with-evidence",
    response_model=ApiSuccess[ProjectStageStatusRead],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
async def upsert_stage_status_with_evidence(
    project_id:              uuid.UUID,
    db:                      DbSession,
    current_user:            CurrentUser,
    stage_id:                str           = Form(...),
    status:                  Optional[str] = Form(None),
    site_id:                 Optional[str] = Form(None),
    lot_id:                  Optional[str] = Form(None),
    notes:                   Optional[str] = Form(None),
    delay_reason:            Optional[str] = Form(None),
    progress_pct:            Optional[int] = Form(None),
    planned_completion_date: Optional[str] = Form(None),
    blocked_reason:          Optional[str] = Form(None),
    completion_notes:        Optional[str] = Form(None),
    evidence_file:           Optional[UploadFile] = File(None),
):
    """Update a stage status and optionally upload a progress photo."""
    check_project_access(db, current_user, project_id)
    from app.models.enums import StageStatus
    from datetime import date as _date

    # Save evidence photo (Supabase Storage when configured, else local disk)
    from app.core.storage import save_upload
    evidence_url:   Optional[str] = None
    evidence_fname: Optional[str] = None
    evidence_mime:  Optional[str] = None
    evidence_size:  int           = 0
    if evidence_file and evidence_file.filename:
        validate_upload(evidence_file, PHOTO_MIMES)
        ext          = os.path.splitext(evidence_file.filename)[1] or ".bin"
        fname        = f"{uuid.uuid4().hex}{ext}"
        content      = await evidence_file.read()
        evidence_url   = save_upload(content, f"site_evidence/stages/{fname}")
        evidence_fname = evidence_file.filename
        evidence_mime  = evidence_file.content_type or "image/jpeg"
        evidence_size  = len(content)

    planned_date = None
    if planned_completion_date:
        try:
            planned_date = _date.fromisoformat(planned_completion_date)
        except ValueError:
            pass

    body = StageStatusUpsert(
        stage_id                 = uuid.UUID(stage_id),
        site_id                  = uuid.UUID(site_id) if site_id else None,
        lot_id                   = uuid.UUID(lot_id)  if lot_id  else None,
        status                   = StageStatus(status) if status else None,
        notes                    = notes or None,
        delay_reason             = delay_reason,
        progress_pct             = progress_pct,
        planned_completion_date  = planned_date,
        blocked_reason           = blocked_reason,
        completion_notes         = completion_notes,
    )
    try:
        pss = stage_service.upsert_stage_status(
            db, project_id, body, current_user.id, actor_role=current_user.role
        )
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message)

    # Store evidence photo as a proper Attachment record (not embedded in notes)
    if evidence_url:
        from app.models.enums import AttachmentType
        db.add(Attachment(
            entity_type     = AttachmentEntity.STAGE_STATUS,
            entity_id       = pss.id,
            file_name       = evidence_fname,
            stored_path     = evidence_url,
            file_url        = evidence_url,
            mime_type       = evidence_mime,
            file_size_bytes = evidence_size,
            attachment_type = AttachmentType.PHOTO,
            uploaded_by     = current_user.id,
            uploaded_at     = datetime.now(timezone.utc),
            is_active       = True,
        ))
        db.commit()

    return ApiSuccess(
        data=stage_service._enrich(pss),
        message="Stage updated." + (" Photo saved." if evidence_url else ""),
    )


# ── Milestone: manual completion ──────────────────────────────────────────────

class CompleteMilestoneBody(BaseModel):
    completion_notes:  Optional[str] = None
    completed_by_name: Optional[str] = None  # auto-filled from current_user if omitted


class BlockMilestoneBody(BaseModel):
    blocked_reason: str


class SetProgressBody(BaseModel):
    progress_pct: int   # 0–100


@project_stages_router.post(
    "/{status_id}/complete",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[WRITE_ROLES],
)
def complete_milestone(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    body: Optional[CompleteMilestoneBody] = None,
):
    """
    Manually mark a milestone as COMPLETED.
    Optionally captures completion notes and who completed it.
    Milestones are NEVER auto-completed.
    """
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")
    now = datetime.now(timezone.utc)
    pss.status      = StageStatus.COMPLETED
    pss.completed_at = now
    pss.updated_by   = current_user.id
    pss.progress_pct = 100
    if body:
        if body.completion_notes is not None:
            pss.completion_notes  = body.completion_notes
        if body.completed_by_name is not None:
            pss.completed_by_name = body.completed_by_name
    # Clear blocked state on completion
    pss.blocked_reason = None
    db.commit()
    db.refresh(pss)
    db.refresh(pss, ["stage"])
    return ApiSuccess(data=stage_service._enrich(pss), message="Milestone marked as completed.")


@project_stages_router.post(
    "/{status_id}/block",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[WRITE_ROLES],
)
def block_milestone(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    body: BlockMilestoneBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a milestone as BLOCKED with a required reason."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    if not body.blocked_reason.strip():
        raise HTTPException(422, "blocked_reason is required.")
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")
    if pss.status in (StageStatus.COMPLETED, StageStatus.CERTIFIED):
        raise HTTPException(422, "Cannot block a completed/certified milestone.")
    pss.status         = StageStatus.BLOCKED
    pss.blocked_reason = body.blocked_reason.strip()
    pss.updated_by     = current_user.id
    db.commit()
    db.refresh(pss)
    db.refresh(pss, ["stage"])
    return ApiSuccess(data=stage_service._enrich(pss), message="Milestone blocked.")


@project_stages_router.post(
    "/{status_id}/unblock",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[WRITE_ROLES],
)
def unblock_milestone(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Resume a blocked milestone — sets status back to IN_PROGRESS."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")
    if pss.status != StageStatus.BLOCKED:
        raise HTTPException(422, "Milestone is not blocked.")
    pss.status         = StageStatus.IN_PROGRESS
    pss.blocked_reason = None
    pss.updated_by     = current_user.id
    db.commit()
    db.refresh(pss)
    db.refresh(pss, ["stage"])
    return ApiSuccess(data=stage_service._enrich(pss), message="Milestone unblocked.")


@project_stages_router.patch(
    "/{status_id}/progress",
    response_model=ApiSuccess[ProjectStageStatusRead],
    dependencies=[WRITE_ROLES],
)
def set_milestone_progress(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    body: SetProgressBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """Set manual progress percentage (0–100)."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")
    pct = max(0, min(100, body.progress_pct))
    pss.progress_pct = pct
    pss.updated_by   = current_user.id
    # Auto-start if not started
    if pss.status == StageStatus.NOT_STARTED and pct > 0:
        pss.status     = StageStatus.IN_PROGRESS
        pss.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pss)
    db.refresh(pss, ["stage"])
    return ApiSuccess(data=stage_service._enrich(pss), message=f"Progress set to {pct}%.")


@project_stages_router.delete(
    "/{status_id}",
    response_model=ApiSuccess[dict],
    dependencies=[WRITE_ROLES],
)
def delete_stage_status(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Remove a stage tracking entry from a project. Blocked if stage is COMPLETED or CERTIFIED."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")
    if pss.status in (StageStatus.COMPLETED, StageStatus.CERTIFIED):
        raise HTTPException(
            409,
            f"Cannot remove a {pss.status.value.lower()} stage. Reset its status first or archive the project.",
        )
    db.delete(pss)
    db.commit()
    return ApiSuccess(data={"id": str(status_id)}, message="Stage removed from project tracking.")


class RenameStageMasterBody(BaseModel):
    name: str


@stages_router.patch(
    "/{stage_id}",
    response_model=ApiSuccess[StageMasterRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def rename_stage_master(
    stage_id: uuid.UUID,
    body: RenameStageMasterBody,
    db: DbSession,
):
    """Rename a stage master definition. Affects all projects using this stage."""
    from app.models.stage import StageMaster
    master = db.get(StageMaster, stage_id)
    if not master:
        raise HTTPException(404, "Stage not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be blank.")
    master.name = name
    db.commit()
    db.refresh(master)
    return ApiSuccess(data=StageMasterRead.model_validate(master), message="Stage renamed.")


@project_stages_router.get(
    "/{status_id}/activity",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def get_milestone_activity(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(30, le=100),
):
    """
    Return a human-readable activity feed for this milestone.
    Combines audit events with photo upload events.
    """
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    from app.models.audit import AuditEvent
    from sqlalchemy import text

    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")

    # Audit events for this stage status
    audit_rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_id == status_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )

    # Photo attachments (latest uploads)
    photo_rows = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == AttachmentEntity.STAGE_STATUS,
            Attachment.entity_id   == status_id,
        )
        .order_by(Attachment.uploaded_at.desc())
        .limit(10)
        .all()
    )

    activity = []

    for a in audit_rows:
        actor = None
        if a.actor_id:
            from app.models.user import User
            u = db.get(User, a.actor_id)
            actor = u.full_name if u else None
        after = a.after_value or {}
        description = _audit_description(a.action, after)
        activity.append({
            "type":        "audit",
            "timestamp":   a.created_at.isoformat(),
            "actor":       actor or "System",
            "description": description,
            "action":      a.action,
        })

    for p in photo_rows:
        actor_name = None
        if p.uploaded_by:
            from app.models.user import User as _User
            u2 = db.get(_User, p.uploaded_by)
            actor_name = u2.full_name if u2 else None
        activity.append({
            "type":        "photo",
            "timestamp":   p.uploaded_at.isoformat(),
            "actor":       actor_name,
            "description": f"Photo uploaded: {p.file_name}",
            "url":         f"/api/v1/attachments/{p.id}/download",
            "photo_id":    str(p.id),
        })

    # Phase 3J: warehouse dispatch events for the lot this status belongs to
    if pss.lot_id:
        from app.models.stock import StockLedger
        from app.models.enums import MovementType as _MT
        from app.models.item import Item as _Item

        dispatch_rows = (
            db.query(StockLedger)
            .filter(
                StockLedger.lot_id        == pss.lot_id,
                StockLedger.movement_type == _MT.TRANSFER_IN,
            )
            .order_by(StockLedger.movement_date.desc())
            .limit(10)
            .all()
        )
        for d in dispatch_rows:
            item_name = None
            if d.item_id:
                it = db.get(_Item, d.item_id)
                item_name = it.name if it else None
            desc = f"{float(d.quantity_in):.3g} {d.unit or ''} {item_name or 'material'} dispatched to lot".strip()
            activity.append({
                "type":        "dispatch",
                "timestamp":   d.movement_date.isoformat() if d.movement_date else d.created_at.isoformat(),
                "actor":       None,
                "description": desc,
            })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return ApiSuccess(data=activity[:limit])


def _audit_description(action: str, after: dict) -> str:
    """Convert an audit action into human-readable text."""
    status = after.get("status", "").replace("_", " ").title()
    if action == "CREATE":
        return "Milestone started"
    if action == "UPDATE":
        if status:
            return f"Status → {status}"
        pct = after.get("progress_pct")
        if pct is not None:
            return f"Progress set to {pct}%"
        return "Milestone updated"
    if action == "APPROVE":
        return "Milestone approved"
    return action.replace("_", " ").title()


# ── Milestone photos ──────────────────────────────────────────────────────────

@project_stages_router.get(
    "/{status_id}/photos",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def list_milestone_photos(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """List all photos attached to a milestone (stage status)."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")

    photos = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == AttachmentEntity.STAGE_STATUS,
            Attachment.entity_id   == status_id,
            Attachment.is_active   == True,
        )
        .order_by(Attachment.uploaded_at.asc())
        .all()
    )
    return ApiSuccess(data=[{
        "id":          str(p.id),
        "url":         f"/api/v1/attachments/{p.id}/download",
        "file_name":   p.file_name,
        "mime_type":   p.mime_type,
        "uploaded_at": p.uploaded_at.isoformat(),
    } for p in photos])


@project_stages_router.post(
    "/{status_id}/photos",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
async def upload_milestone_photo(
    project_id:  uuid.UUID,
    status_id:   uuid.UUID,
    db:          DbSession,
    current_user: CurrentUser,
    photo: UploadFile = File(...),
):
    """Upload a progress photo to a milestone."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")

    if not photo.filename:
        raise HTTPException(422, "No file provided.")

    ext     = os.path.splitext(photo.filename)[1].lower() or ".bin"
    fname   = f"{uuid.uuid4().hex}{ext}"
    content = await photo.read()

    url = save_upload(content, f"milestones/{project_id}/{status_id}/{fname}")

    now = datetime.now(timezone.utc)
    att = Attachment(
        entity_type      = AttachmentEntity.STAGE_STATUS,
        entity_id        = status_id,
        file_name        = photo.filename,
        stored_path      = url,
        file_url         = url,
        mime_type        = photo.content_type or "application/octet-stream",
        file_size_bytes  = len(content),
        attachment_type  = AttachmentType.PHOTO,
        uploaded_by      = current_user.id,
        uploaded_at      = now,
        is_active        = True,
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    return ApiSuccess(data={
        "id":          str(att.id),
        "url":         f"/api/v1/attachments/{att.id}/download",
        "file_name":   att.file_name,
        "uploaded_at": att.uploaded_at.isoformat(),
    }, message="Photo uploaded.")


@project_stages_router.delete(
    "/{status_id}/photos/{photo_id}",
    response_model=ApiSuccess[dict],
    dependencies=[WRITE_ROLES],
)
def delete_milestone_photo(
    project_id: uuid.UUID,
    status_id:  uuid.UUID,
    photo_id:   uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Soft-delete a milestone photo."""
    check_project_access(db, current_user, project_id)
    from app.models.stage import ProjectStageStatus
    pss = db.get(ProjectStageStatus, status_id)
    if not pss or pss.project_id != project_id:
        raise HTTPException(404, "Stage status not found.")

    att = db.get(Attachment, photo_id)
    if not att or att.entity_id != status_id:
        raise HTTPException(404, "Photo not found.")

    att.is_active = False
    db.commit()
    return ApiSuccess(data={"id": str(photo_id)}, message="Photo removed.")
