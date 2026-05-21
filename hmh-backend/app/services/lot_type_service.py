"""LotType service — Phase 3D.2.

CRUD for LotType records and lot assignment operations.
Propagation (clone BOQ to all linked lots) is Phase 3D.3.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.boq import BOQHeader
from app.models.lot import Lot
from app.models.lot_type import LotType
from app.models.project import Project
from app.schemas.lot_type import LotTypeCreate, LotTypeRead, LotTypeUpdate, LotTypeWithLots


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, lot_type_id: uuid.UUID) -> LotType:
    lt = db.get(LotType, lot_type_id)
    if not lt:
        raise NotFoundError(f"LotType {lot_type_id} not found.")
    return lt


def _lot_count(db: Session, lot_type_id: uuid.UUID) -> int:
    return (
        db.query(func.count(Lot.id))
        .filter(Lot.lot_type_id == lot_type_id)
        .scalar() or 0
    )


def _template_name(db: Session, template_id: Optional[uuid.UUID]) -> Optional[str]:
    if not template_id:
        return None
    h = db.get(BOQHeader, template_id)
    return h.template_name or h.version_name if h else None


def _to_read(db: Session, lt: LotType) -> LotTypeRead:
    data = LotTypeRead.model_validate(lt)
    data.lot_count = _lot_count(db, lt.id)
    data.default_template_name = _template_name(db, lt.default_template_id)
    return data


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_lot_types(db: Session, project_id: uuid.UUID) -> list[LotTypeRead]:
    """Return all LotTypes for a project with lot counts."""
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    types = (
        db.query(LotType)
        .filter(LotType.project_id == project_id)
        .order_by(LotType.name)
        .all()
    )
    return [_to_read(db, lt) for lt in types]


def create_lot_type(
    db: Session, project_id: uuid.UUID, data: LotTypeCreate, actor_id: Optional[uuid.UUID] = None,
) -> LotTypeRead:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    # Validate unique code within project (if provided)
    if data.code:
        existing = (
            db.query(LotType)
            .filter(LotType.project_id == project_id, LotType.code == data.code.strip())
            .first()
        )
        if existing:
            raise ConflictError(
                f"A lot type with code '{data.code}' already exists in this project."
            )

    # Validate template belongs to this project (if provided)
    if data.default_template_id:
        tmpl = db.get(BOQHeader, data.default_template_id)
        if not tmpl or not tmpl.is_template:
            raise NotFoundError(f"BOQ template {data.default_template_id} not found.")

    now = datetime.now(timezone.utc)
    lt = LotType(
        project_id          = project_id,
        name                = data.name.strip(),
        code                = data.code.strip() if data.code else None,
        description         = data.description,
        default_template_id = data.default_template_id,
        created_at          = now,
        updated_at          = now,
    )
    db.add(lt)
    db.commit()
    db.refresh(lt)
    return _to_read(db, lt)


def get_lot_type(db: Session, lot_type_id: uuid.UUID) -> LotTypeWithLots:
    """Get LotType with linked lots summary."""
    lt = _get_or_404(db, lot_type_id)

    linked_lots = (
        db.query(Lot)
        .filter(Lot.lot_type_id == lot_type_id)
        .order_by(Lot.lot_number)
        .all()
    )

    base = _to_read(db, lt)
    return LotTypeWithLots(
        **base.model_dump(),
        lots=[{
            "id":              str(l.id),
            "lot_number":      l.lot_number,
            "unit_type":       l.unit_type,
            "site_id":         str(l.site_id) if l.site_id else None,
            "status":          l.status.value,
            "boq_customized":  l.boq_customized_at is not None,
        } for l in linked_lots],
    )


def update_lot_type(
    db: Session, lot_type_id: uuid.UUID, data: LotTypeUpdate,
) -> LotTypeRead:
    lt = _get_or_404(db, lot_type_id)
    fields = data.model_fields_set

    if "name" in fields and data.name is not None:
        lt.name = data.name.strip()
    if "code" in fields:
        if data.code:
            # Check uniqueness within project
            clash = (
                db.query(LotType)
                .filter(
                    LotType.project_id == lt.project_id,
                    LotType.code == data.code.strip(),
                    LotType.id != lot_type_id,
                )
                .first()
            )
            if clash:
                raise ConflictError(
                    f"A lot type with code '{data.code}' already exists in this project."
                )
            lt.code = data.code.strip()
        else:
            lt.code = None
    if "description" in fields:
        lt.description = data.description
    if "default_template_id" in fields:
        if data.default_template_id:
            tmpl = db.get(BOQHeader, data.default_template_id)
            if not tmpl or not tmpl.is_template:
                raise NotFoundError(f"BOQ template {data.default_template_id} not found.")
        lt.default_template_id = data.default_template_id

    lt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lt)
    return _to_read(db, lt)


def delete_lot_type(db: Session, lot_type_id: uuid.UUID) -> None:
    lt = _get_or_404(db, lot_type_id)
    count = _lot_count(db, lot_type_id)

    if count > 0:
        raise ConflictError(
            f"Cannot delete '{lt.name}': {count} lot(s) are still assigned. "
            "Unassign all lots before deleting this type."
        )

    db.delete(lt)
    db.commit()


# ── Lot assignment ────────────────────────────────────────────────────────────

def assign_lots(
    db: Session,
    lot_type_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
) -> dict:
    """
    Assign a list of lots to this LotType (sets lot.lot_type_id).
    Lots that already belong to another type are reassigned.
    Returns summary of assigned/already-assigned counts.
    """
    lt = _get_or_404(db, lot_type_id)

    lots = (
        db.query(Lot)
        .filter(Lot.id.in_(lot_ids), Lot.project_id == lt.project_id)
        .all()
    )
    if len(lots) != len(lot_ids):
        raise ValidationError(
            "One or more lot IDs do not belong to this project or do not exist."
        )

    assigned       = 0
    already_set    = 0
    reassigned     = 0
    now            = datetime.now(timezone.utc)

    for lot in lots:
        if lot.lot_type_id == lot_type_id:
            already_set += 1
        elif lot.lot_type_id is not None:
            lot.lot_type_id = lot_type_id
            lot.updated_at  = now
            reassigned += 1
        else:
            lot.lot_type_id = lot_type_id
            lot.updated_at  = now
            assigned += 1

    db.commit()
    return {
        "lot_type_id":   str(lot_type_id),
        "lot_type_name": lt.name,
        "assigned":      assigned,
        "reassigned":    reassigned,
        "already_set":   already_set,
        "total":         len(lots),
    }


def remove_lots(
    db: Session,
    lot_type_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
) -> dict:
    """
    Remove lots from this LotType (sets lot.lot_type_id = NULL).
    Only affects lots that currently belong to this type.
    """
    lt = _get_or_404(db, lot_type_id)

    removed = (
        db.query(Lot)
        .filter(
            Lot.id.in_(lot_ids),
            Lot.lot_type_id == lot_type_id,
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for lot in removed:
        lot.lot_type_id = None
        lot.updated_at  = now

    db.commit()
    return {
        "lot_type_id":   str(lot_type_id),
        "lot_type_name": lt.name,
        "removed":       len(removed),
        "not_in_type":   len(lot_ids) - len(removed),
    }
