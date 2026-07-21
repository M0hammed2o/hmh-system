"""Stage service — stage master list and project stage statuses."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import StageStatus, UserRole
from app.models.lot import Lot
from app.models.project import Project
from app.models.site import Site
from app.models.stage import ProjectStageStatus, StageMaster
from app.schemas.stage import ProjectStageStatusRead, StageStatusUpsert


_DEFAULT_STAGES = [
    (1,  "FOUND",  "Foundation",   "Excavation, footings and strip foundations"),
    (2,  "SLAB",   "Slab",         "Ground floor concrete slab and blinding"),
    (3,  "BRICK",  "Brickwork",    "External and internal brickwork"),
    (4,  "ROOF",   "Roofing",      "Roof structure, sheeting and gutters"),
    (5,  "PLUMB",  "Plumbing",     "Water supply and drainage installation"),
    (6,  "ELEC",   "Electrical",   "Wiring, DB board and fitting out"),
    (7,  "PLAST",  "Plastering",   "Internal and external plaster"),
    (8,  "PAINT",  "Painting",     "Interior and exterior painting"),
    (9,  "FINISH", "Finishing",    "Tiling, doors, windows, skirting and fixtures"),
    (10, "HANDOV", "Handover",     "Final inspection, snag list and handover"),
]


def list_stage_masters(db: Session) -> list[StageMaster]:
    return db.query(StageMaster).order_by(StageMaster.sequence_order).all()


def seed_default_stages(db: Session) -> list[StageMaster]:
    """Create default stages if they don't exist. Returns full stage list."""
    now = datetime.now(timezone.utc)
    existing_orders = {s.sequence_order for s in db.query(StageMaster.sequence_order).all()}

    existing_codes = {s.code for s in db.query(StageMaster.code).all() if s.code}
    for seq, code, name, desc in _DEFAULT_STAGES:
        if seq not in existing_orders and code not in existing_codes:
            db.add(StageMaster(
                id=uuid.uuid4(),
                name=name,
                code=code,
                sequence_order=seq,
                description=desc,
                created_at=now,
                updated_at=now,
            ))

    db.commit()
    return list_stage_masters(db)


def list_project_stage_statuses(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    lot_id: Optional[uuid.UUID] = None,
) -> list[ProjectStageStatus]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    q = (
        db.query(ProjectStageStatus)
        .options(joinedload(ProjectStageStatus.stage))
        .filter(ProjectStageStatus.project_id == project_id)
    )
    if site_id:
        q = q.filter(ProjectStageStatus.site_id == site_id)
    if lot_id:
        q = q.filter(ProjectStageStatus.lot_id == lot_id)
    return q.order_by(ProjectStageStatus.stage_id).all()


def _enrich(pss: ProjectStageStatus) -> ProjectStageStatusRead:
    """Build the read schema with stage_name / sequence_order from the joined stage."""
    data = ProjectStageStatusRead.model_validate(pss)
    if pss.stage:
        data.stage_name = pss.stage.name
        data.sequence_order = pss.stage.sequence_order
    # Timezone-safe overdue: compare DB date to UTC calendar date
    if pss.planned_completion_date is not None:
        today = datetime.now(timezone.utc).date()
        data.is_overdue = (
            pss.planned_completion_date < today
            and pss.status not in (StageStatus.COMPLETED, StageStatus.CERTIFIED)
        )
    return data


def upsert_stage_status(
    db: Session,
    project_id: uuid.UUID,
    data: StageStatusUpsert,
    updated_by_id: uuid.UUID,
    actor_role: Optional[UserRole] = None,
) -> ProjectStageStatus:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    stage = db.get(StageMaster, data.stage_id)
    if not stage:
        raise NotFoundError(f"Stage {data.stage_id} not found.")

    # Try to find existing record
    q = (
        db.query(ProjectStageStatus)
        .filter(
            ProjectStageStatus.project_id == project_id,
            ProjectStageStatus.stage_id == data.stage_id,
        )
    )
    if data.site_id:
        q = q.filter(ProjectStageStatus.site_id == data.site_id)
    else:
        q = q.filter(ProjectStageStatus.site_id.is_(None))
    if data.lot_id:
        q = q.filter(ProjectStageStatus.lot_id == data.lot_id)
    else:
        q = q.filter(ProjectStageStatus.lot_id.is_(None))

    pss = q.first()

    # Edit-lock: site staff cannot modify completed/certified milestones
    if (
        pss is not None
        and actor_role == UserRole.SITE_STAFF
        and pss.status in (StageStatus.COMPLETED, StageStatus.CERTIFIED)
    ):
        raise ForbiddenError(
            "Completed milestones cannot be modified by site staff. "
            "Contact office or admin to reopen."
        )

    if pss is None:
        pss = ProjectStageStatus(
            project_id=project_id,
            stage_id=data.stage_id,
            site_id=data.site_id,
            lot_id=data.lot_id,
        )
        db.add(pss)

    fields = data.model_fields_set
    if "status" in fields and data.status is not None:
        pss.status = data.status
    if "inspection_required" in fields and data.inspection_required is not None:
        pss.inspection_required = data.inspection_required
    if "certification_required" in fields and data.certification_required is not None:
        pss.certification_required = data.certification_required
    if "ready_for_labour_payment" in fields and data.ready_for_labour_payment is not None:
        pss.ready_for_labour_payment = data.ready_for_labour_payment
    if "notes" in fields:
        pss.notes = data.notes

    # Phase 3J: progress + blocked_reason
    if "progress_pct" in fields and data.progress_pct is not None:
        pss.progress_pct = max(0, min(100, data.progress_pct))
    if "blocked_reason" in fields:
        pss.blocked_reason = data.blocked_reason

    # Phase FINAL-1: planned date + completion metadata
    if "planned_completion_date" in fields:
        pss.planned_completion_date = data.planned_completion_date
    if "completion_notes" in fields:
        pss.completion_notes = data.completion_notes
    if "completed_by_name" in fields:
        pss.completed_by_name = data.completed_by_name

    # Auto-force progress to 100 and stamp completed_at when transitioning to COMPLETED
    if "status" in fields and data.status == StageStatus.COMPLETED:
        pss.progress_pct = 100
        if pss.completed_at is None:
            pss.completed_at = datetime.now(timezone.utc)
        # Clear blocked state on completion
        pss.blocked_reason = None

    # Append delay reason to notes if provided
    if "delay_reason" in fields and data.delay_reason:
        existing = pss.notes or ""
        pss.notes = f"{existing}\nDELAY: {data.delay_reason}".strip()
        # Create a site delay alert
        from app.models.alert import SystemAlert
        from app.models.enums import AlertSeverity, AlertStatus, AlertType
        db.add(SystemAlert(
            project_id=project_id,
            alert_type=AlertType.SITE_DELAY,
            severity=AlertSeverity.MEDIUM,
            title=f"Stage delayed: {stage.name}",
            message=f"Stage '{stage.name}' has been marked as delayed. Reason: {data.delay_reason}",
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=datetime.now(timezone.utc),
        ))

    pss.updated_by = updated_by_id

    db.commit()
    db.refresh(pss)
    db.refresh(pss, ["stage"])
    return pss
