"""Stage service — stage master list and project stage statuses."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.lot import Lot
from app.models.project import Project
from app.models.site import Site
from app.models.stage import ProjectStageStatus, StageMaster
from app.schemas.stage import ProjectStageStatusRead, StageStatusUpsert


_DEFAULT_STAGES = [
    (1,  "Foundation",   "Excavation, footings and strip foundations"),
    (2,  "Slab",         "Ground floor concrete slab and blinding"),
    (3,  "Brickwork",    "External and internal brickwork"),
    (4,  "Roofing",      "Roof structure, sheeting and gutters"),
    (5,  "Plumbing",     "Water supply and drainage installation"),
    (6,  "Electrical",   "Wiring, DB board and fitting out"),
    (7,  "Plastering",   "Internal and external plaster"),
    (8,  "Painting",     "Interior and exterior painting"),
    (9,  "Finishing",    "Tiling, doors, windows, skirting and fixtures"),
    (10, "Handover",     "Final inspection, snag list and handover"),
]


def list_stage_masters(db: Session) -> list[StageMaster]:
    return db.query(StageMaster).order_by(StageMaster.sequence_order).all()


def seed_default_stages(db: Session) -> list[StageMaster]:
    """Create default stages if they don't exist. Returns full stage list."""
    now = datetime.now(timezone.utc)
    existing_orders = {s.sequence_order for s in db.query(StageMaster.sequence_order).all()}

    for seq, name, desc in _DEFAULT_STAGES:
        if seq not in existing_orders:
            db.add(StageMaster(
                id=uuid.uuid4(),
                name=name,
                sequence_order=seq,
                description=desc,
                created_at=now,
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
    return data


def upsert_stage_status(
    db: Session,
    project_id: uuid.UUID,
    data: StageStatusUpsert,
    updated_by_id: uuid.UUID,
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

    # Append delay reason to notes if provided
    if "delay_reason" in fields and data.delay_reason:
        existing = pss.notes or ""
        pss.notes = f"{existing}\nDELAY: {data.delay_reason}".strip()
        # Create a site delay alert
        from app.models.alert import SystemAlert
        from app.models.enums import AlertSeverity, AlertStatus, AlertType
        from datetime import datetime, timezone
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
