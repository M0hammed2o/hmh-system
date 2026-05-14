"""Lot service — CRUD scoped to a project."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.lot import Lot
from app.models.project import Project
from app.models.site import Site
from app.schemas.lot import LotCreate, LotUpdate


def _get_project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return project


def _get_lot_or_404(db: Session, lot_id: uuid.UUID) -> Lot:
    lot = db.get(Lot, lot_id)
    if not lot:
        raise NotFoundError(f"Lot {lot_id} not found.")
    return lot


def _assert_lot_number_unique(
    db: Session,
    project_id: uuid.UUID,
    lot_number: str,
    exclude_id: Optional[uuid.UUID] = None,
) -> None:
    q = (
        db.query(Lot)
        .filter(Lot.project_id == project_id)
        .filter(Lot.lot_number == lot_number.strip())
    )
    if exclude_id:
        q = q.filter(Lot.id != exclude_id)
    if q.first():
        raise ConflictError(f"Lot number '{lot_number.strip()}' already exists in this project.")


def list_lots(db: Session, project_id: uuid.UUID) -> list[Lot]:
    _get_project_or_404(db, project_id)
    return (
        db.query(Lot)
        .filter(Lot.project_id == project_id)
        .order_by(Lot.lot_number)
        .all()
    )


def get_lot(db: Session, lot_id: uuid.UUID) -> Lot:
    return _get_lot_or_404(db, lot_id)


def create_lot(db: Session, project_id: uuid.UUID, data: LotCreate) -> Lot:
    _get_project_or_404(db, project_id)
    _assert_lot_number_unique(db, project_id, data.lot_number)

    # Validate site belongs to project if provided
    if data.site_id:
        site = db.get(Site, data.site_id)
        if not site or site.project_id != project_id:
            raise NotFoundError(f"Site {data.site_id} not found in this project.")

    lot = Lot(
        project_id=project_id,
        lot_number=data.lot_number.strip(),
        site_id=data.site_id,
        unit_type=data.unit_type.strip() if data.unit_type else None,
        block_number=data.block_number.strip() if data.block_number else None,
        status=data.status,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


def generate_lots(
    db: Session,
    project_id: uuid.UUID,
    start_number: int,
    end_number: int,
    site_id: Optional[uuid.UUID] = None,
    unit_type: Optional[str] = None,
    boq_template_id: Optional[uuid.UUID] = None,
    actor_id: Optional[uuid.UUID] = None,
) -> list[Lot]:
    """
    Create lots numbered start_number..end_number (inclusive).
    Silently skips numbers where a lot already exists.
    If boq_template_id is given, clone the template BOQ to each new lot.
    """
    _get_project_or_404(db, project_id)

    # Get existing lot numbers for fast lookup
    existing = {
        l.lot_number
        for l in db.query(Lot.lot_number)
        .filter(Lot.project_id == project_id)
        .all()
    }

    created: list[Lot] = []
    for n in range(start_number, end_number + 1):
        lot_number = str(n)
        if lot_number in existing:
            continue

        lot = Lot(
            project_id=project_id,
            lot_number=lot_number,
            site_id=site_id,
            unit_type=unit_type,
            boq_template_id=boq_template_id,
        )
        db.add(lot)
        created.append(lot)

    db.flush()

    # Clone BOQ template if requested
    if boq_template_id and created:
        from app.services.boq_template_service import clone_template_to_lots
        clone_template_to_lots(
            db,
            template_boq_id=boq_template_id,
            project_id=project_id,
            lot_ids=[l.id for l in created],
            actor_id=actor_id,
        )
    else:
        db.commit()

    for lot in created:
        db.refresh(lot)
    return created


def update_lot(db: Session, lot_id: uuid.UUID, data: LotUpdate) -> Lot:
    lot = _get_lot_or_404(db, lot_id)
    fields = data.model_fields_set

    if "site_id" in fields:
        if data.site_id:
            site = db.get(Site, data.site_id)
            if not site or site.project_id != lot.project_id:
                raise NotFoundError(f"Site {data.site_id} not found in this project.")
        lot.site_id = data.site_id
    if "unit_type" in fields:
        lot.unit_type = data.unit_type.strip() if data.unit_type else None
    if "block_number" in fields:
        lot.block_number = data.block_number.strip() if data.block_number else None
    if "status" in fields and data.status is not None:
        lot.status = data.status

    db.commit()
    db.refresh(lot)
    return lot
