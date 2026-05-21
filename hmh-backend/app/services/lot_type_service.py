"""LotType service — Phase 3D.2 + 3D.3.

CRUD for LotType records, lot assignment, and BOQ propagation.
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


# ── Propagation (Phase 3D.3) ──────────────────────────────────────────────────

_VALID_MODES = {"SAFE", "FORCE"}


def _get_propagation_lots(
    db: Session,
    lot_type_id: uuid.UUID,
    lot_ids: Optional[list[uuid.UUID]],
    mode: str,
) -> tuple[list[Lot], list[Lot]]:
    """
    Split the target lots into (to_propagate, skipped) based on mode.

    SAFE:  skip lots where boq_customized_at IS NOT NULL (manually edited)
    FORCE: propagate all lots regardless of customization
    """
    if mode not in _VALID_MODES:
        raise ValidationError(f"Invalid mode '{mode}'. Must be SAFE or FORCE.")

    # Base query: all lots linked to this type
    q = db.query(Lot).filter(Lot.lot_type_id == lot_type_id)
    if lot_ids:
        q = q.filter(Lot.id.in_(lot_ids))
    all_lots = q.order_by(Lot.lot_number).all()

    if mode == "FORCE":
        return all_lots, []

    # SAFE: split customized vs clean
    to_propagate = [l for l in all_lots if l.boq_customized_at is None]
    skipped      = [l for l in all_lots if l.boq_customized_at is not None]
    return to_propagate, skipped


def preview_propagate(
    db: Session,
    lot_type_id: uuid.UUID,
    lot_ids: Optional[list[uuid.UUID]] = None,
    mode: str = "SAFE",
) -> dict:
    """
    Dry-run: show which lots would receive BOQ changes and which would be skipped.
    No DB writes.
    """
    lt = _get_or_404(db, lot_type_id)

    if not lt.default_template_id:
        raise ValidationError(
            f"Lot type '{lt.name}' has no default template. "
            "Set a default BOQ template before propagating."
        )

    from app.services.boq_template_service import preview_clone, _load_template_sections_items

    to_propagate, skipped = _get_propagation_lots(db, lot_type_id, lot_ids, mode)
    all_target_ids = [l.id for l in to_propagate]

    template_preview = None
    if all_target_ids:
        template_preview = preview_clone(
            db,
            template_boq_id = lt.default_template_id,
            project_id      = lt.project_id,
            lot_ids         = all_target_ids,
        )

    # Per-lot detail
    def _lot_detail(lot: Lot, action: str, skip_reason: Optional[str]) -> dict:
        return {
            "lot_id":        str(lot.id),
            "lot_number":    lot.lot_number,
            "unit_type":     lot.unit_type,
            "site_id":       str(lot.site_id) if lot.site_id else None,
            "is_customized": lot.boq_customized_at is not None,
            "action":        action,
            "skip_reason":   skip_reason,
        }

    lots_detail = (
        [_lot_detail(l, "propagate", None) for l in to_propagate]
        + [_lot_detail(l, "skip", "manually customized") for l in skipped]
    )

    return {
        "lot_type_id":         str(lot_type_id),
        "lot_type_name":       lt.name,
        "template_name":       _template_name(db, lt.default_template_id),
        "mode":                mode,
        "total_linked_lots":   len(to_propagate) + len(skipped),
        "lots_to_propagate":   len(to_propagate),
        "lots_skipped":        len(skipped),
        "skipped_reason":      "manually customized" if skipped else None,
        "items_per_lot":       template_preview["template_item_count"] if template_preview else 0,
        "stages_per_lot":      template_preview["template_stage_count"] if template_preview else 0,
        "lots":                lots_detail,
    }


def propagate_to_lots(
    db: Session,
    lot_type_id: uuid.UUID,
    actor_id: Optional[uuid.UUID] = None,
    lot_ids: Optional[list[uuid.UUID]] = None,
    mode: str = "SAFE",
    generate_milestones: bool = True,
) -> dict:
    """
    Propagate the LotType's default template to all linked lots.

    SAFE mode: skips lots where boq_customized_at IS NOT NULL.
    FORCE mode: propagates to all lots, resetting customized_at to NULL.

    After propagation, resets boq_customized_at = NULL for propagated lots
    (they now have fresh generated items — no manual edits).
    """
    lt = _get_or_404(db, lot_type_id)

    if not lt.default_template_id:
        raise ValidationError(
            f"Lot type '{lt.name}' has no default template. "
            "Set a default BOQ template before propagating."
        )

    to_propagate, skipped = _get_propagation_lots(db, lot_type_id, lot_ids, mode)

    if not to_propagate:
        return {
            "lot_type_id":       str(lot_type_id),
            "lot_type_name":     lt.name,
            "mode":              mode,
            "propagated":        0,
            "skipped":           len(skipped),
            "milestones_created": 0,
            "items_replaced":    0,
            "message":           "No lots to propagate. All linked lots are customized (use FORCE to override)." if skipped else "No lots linked to this type.",
        }

    from app.services.boq_template_service import clone_template_to_lots

    result = clone_template_to_lots(
        db,
        template_boq_id     = lt.default_template_id,
        project_id          = lt.project_id,
        lot_ids             = [l.id for l in to_propagate],
        actor_id            = actor_id,
        overwrite           = True,             # always replace when propagating
        generate_milestones = generate_milestones,
        lot_type_id         = lot_type_id,      # sets generated_from_lot_type_id
    )

    # Reset customized_at for propagated lots — they're clean again
    now = datetime.now(timezone.utc)
    for lot in to_propagate:
        lot.boq_customized_at = None
        lot.updated_at = now
    db.commit()

    return {
        "lot_type_id":        str(lot_type_id),
        "lot_type_name":      lt.name,
        "mode":               mode,
        "propagated":         len(to_propagate),
        "skipped":            len(skipped),
        "milestones_created": result.get("milestones_created", 0),
        "items_replaced":     result.get("deactivated_count", 0),
        "message": (
            f"Propagated to {len(to_propagate)} lot(s). "
            + (f"{len(skipped)} customized lot(s) skipped." if skipped else "")
        ).strip(),
    }
