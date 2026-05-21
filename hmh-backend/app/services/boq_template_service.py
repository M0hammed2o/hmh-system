"""
BOQ template service.

Supports:
- Listing reusable templates (is_template=True BOQHeaders)
- Previewing a template clone (dry-run, no DB writes)
- Cloning a template into per-lot BOQHeaders in bulk
- Deactivating existing lot BOQ items before overwrite
- Seeding ProjectStageStatus milestones from template sections
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, insert as _sa_insert
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.enums import AuditAction, BoqStatus, StageStatus
from app.models.lot import Lot
from app.models.project import Project
from app.models.stage import ProjectStageStatus
from app.services import audit_service


def list_templates(db: Session) -> list[BOQHeader]:
    return (
        db.query(BOQHeader)
        .filter(BOQHeader.is_template == True)
        .order_by(BOQHeader.template_name)
        .all()
    )


def _load_template_sections_items(
    db: Session, template_id: uuid.UUID
) -> tuple[list[BOQSection], list[BOQItem], int]:
    """
    Load all template sections and their items in two queries.
    Returns (sections, all_items_flat, item_count).
    """
    sections = (
        db.query(BOQSection)
        .filter(BOQSection.boq_header_id == template_id)
        .order_by(BOQSection.sequence_order)
        .all()
    )
    all_items: list[BOQItem] = []
    for section in sections:
        items = (
            db.query(BOQItem)
            .filter(BOQItem.boq_section_id == section.id, BOQItem.is_active == True)
            .order_by(BOQItem.sort_order)
            .all()
        )
        all_items.extend(items)
    return sections, all_items, len(all_items)


def _deactivate_lot_boq_items(
    db: Session,
    project_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
) -> int:
    """
    Soft-delete all lot-level BOQ items for the given lots.
    Called before re-cloning when overwrite=True.
    Returns the number of items deactivated.
    """
    count = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.lot_id.in_(lot_ids),
            BOQItem.is_active == True,
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    db.flush()
    return count


def _seed_milestones(
    db: Session,
    project_id: uuid.UUID,
    lot: Lot,
    stage_ids: set[uuid.UUID],
    actor_id: Optional[uuid.UUID],
) -> int:
    """
    Create NOT_STARTED ProjectStageStatus records for each stage_id,
    skipping any that already exist. Returns count of records created.
    """
    created = 0
    now = datetime.now(timezone.utc)
    for stage_id in stage_ids:
        # Check for existing record with the same (project, lot, stage) tuple
        existing = (
            db.query(ProjectStageStatus)
            .filter(
                ProjectStageStatus.project_id == project_id,
                ProjectStageStatus.lot_id     == lot.id,
                ProjectStageStatus.stage_id   == stage_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(ProjectStageStatus(
            project_id  = project_id,
            site_id     = lot.site_id,    # None for freestanding lots — valid after 0015
            lot_id      = lot.id,
            stage_id    = stage_id,
            status      = StageStatus.NOT_STARTED,
            updated_by  = actor_id,
        ))
        created += 1
    if created:
        db.flush()
    return created


_APPLY_MODES = {"CREATE", "SAFE", "FORCE"}


def _resolve_lot_action(
    lot: Lot,
    existing_item_count: int,
    mode: str,
) -> tuple[str, Optional[str]]:
    """
    Determine what action the template apply will take for this lot.

    Returns: (action, skip_reason)
      action ∈ {"create", "overwrite", "skip"}

    Modes:
      CREATE — only apply to lots with no existing BOQ items
      SAFE   — skip lots where boq_customized_at IS NOT NULL (user manually edited)
      FORCE  — overwrite all lots regardless of customization
    """
    if mode == "CREATE":
        if existing_item_count > 0:
            return "skip", "already has BOQ — use SAFE or FORCE to update"
        return "create", None

    if mode == "SAFE":
        if lot.boq_customized_at is not None:
            return "skip", "manually customized — use FORCE to overwrite"
        if existing_item_count > 0:
            return "overwrite", None
        return "create", None

    # FORCE — overwrite everything
    if existing_item_count > 0:
        return "overwrite", None
    return "create", None


def preview_clone(
    db: Session,
    template_boq_id: uuid.UUID,
    project_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
    mode: str = "CREATE",
) -> dict:
    """
    Dry-run: return what WOULD happen without writing anything.

    mode:
      CREATE — only lots with no existing BOQ
      SAFE   — skip lots where boq_customized_at IS NOT NULL
      FORCE  — all lots (with overwrite where needed)
    """
    if mode not in _APPLY_MODES:
        mode = "CREATE"

    template = db.get(BOQHeader, template_boq_id)
    if not template or not template.is_template:
        raise NotFoundError(f"BOQ template {template_boq_id} not found.")

    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    sections, all_items, item_count = _load_template_sections_items(db, template_boq_id)
    stage_ids = {s.stage_id for s in sections if s.stage_id}

    lots = (
        db.query(Lot)
        .filter(Lot.id.in_(lot_ids), Lot.project_id == project_id)
        .order_by(Lot.lot_number)
        .all()
    )

    lots_preview = []
    for lot in lots:
        existing_item_count = (
            db.query(func.count(BOQItem.id))
            .filter(BOQItem.lot_id == lot.id, BOQItem.is_active == True)
            .scalar() or 0
        )
        existing_milestone_count = (
            db.query(func.count(ProjectStageStatus.id))
            .filter(
                ProjectStageStatus.project_id == project_id,
                ProjectStageStatus.lot_id     == lot.id,
            )
            .scalar() or 0
        )
        action, skip_reason = _resolve_lot_action(lot, existing_item_count, mode)
        lots_preview.append({
            "lot_id":                   str(lot.id),
            "lot_number":               lot.lot_number,
            "unit_type":                lot.unit_type,
            "is_freestanding":          lot.site_id is None,
            "is_customized":            lot.boq_customized_at is not None,
            "has_existing_boq":         existing_item_count > 0,
            "existing_item_count":      existing_item_count,
            "new_item_count":           item_count,
            "has_existing_milestones":  existing_milestone_count > 0,
            "existing_milestone_count": existing_milestone_count,
            "new_milestone_count":      len(stage_ids),
            "action":                   action,
            "skip_reason":              skip_reason,
        })

    return {
        "template_id":            str(template_boq_id),
        "template_name":          template.template_name or template.version_name,
        "template_section_count": len(sections),
        "template_item_count":    item_count,
        "template_stage_count":   len(stage_ids),
        "mode":                   mode,
        "lots":                   lots_preview,
        "lots_to_apply":          sum(1 for l in lots_preview if l["action"] != "skip"),
        "lots_to_skip":           sum(1 for l in lots_preview if l["action"] == "skip"),
        "lots_needing_overwrite": sum(1 for l in lots_preview if l["action"] == "overwrite"),
        "total_lots":             len(lots),
    }


def clone_template_to_lots(
    db: Session,
    *,
    template_boq_id: uuid.UUID,
    project_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
    actor_id: Optional[uuid.UUID] = None,
    overwrite: bool = False,      # deprecated alias — use mode="FORCE" instead
    mode: str = "CREATE",         # "CREATE" | "SAFE" | "FORCE"
    generate_milestones: bool = True,
    lot_type_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Clone a BOQ template into one BOQHeader per lot.

    mode controls how existing lot BOQs are handled:
      CREATE — only apply to lots with no existing items (default)
      SAFE   — skip lots where boq_customized_at IS NOT NULL; reclone the rest
      FORCE  — reclone all lots; deactivate existing items first

    backward compat: overwrite=True is treated as mode="FORCE"

    For each applied lot:
    - Deactivates existing lot-level BOQ items (if mode != CREATE or overwrite=True)
    - Creates a new BOQHeader linked to the project
    - Clones all BOQSections + BOQItems (lot_id + project_id set on each)
    - Does NOT include planned_total (GENERATED column)
    - If generate_milestones=True: seeds ProjectStageStatus (NOT_STARTED)
      for every stage referenced in the template sections
    - If lot_type_id is given: sets generated_from_lot_type_id on every created item

    Freestanding lots (site_id=None) are supported:
    - Their lot-level items get site_id=None (valid after migration 0015)
    - A project-level master (site_id=None, lot_id=None) is created if absent

    Returns a dict with created_headers + milestone counts for the success summary.
    """
    template = db.get(BOQHeader, template_boq_id)
    if not template or not template.is_template:
        raise NotFoundError(f"BOQ template {template_boq_id} not found.")

    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    if not lot_ids:
        raise ValidationError("At least one lot_id is required.")

    if mode not in _APPLY_MODES:
        mode = "CREATE"

    # backward compat: overwrite=True → FORCE
    if overwrite and mode == "CREATE":
        mode = "FORCE"

    # Validate all lots belong to this project
    all_lots = db.query(Lot).filter(Lot.id.in_(lot_ids), Lot.project_id == project_id).all()
    if len(all_lots) != len(lot_ids):
        raise ValidationError("One or more lot IDs do not belong to this project.")

    # Filter lots based on mode (same logic as _resolve_lot_action)
    lots_to_apply: list[Lot] = []
    lots_skipped:  list[Lot] = []
    lots_skipped_reasons: dict = {}

    for lot in all_lots:
        existing = (
            db.query(func.count(BOQItem.id))
            .filter(BOQItem.lot_id == lot.id, BOQItem.is_active == True)
            .scalar() or 0
        )
        action, skip_reason = _resolve_lot_action(lot, existing, mode)
        if action == "skip":
            lots_skipped.append(lot)
            lots_skipped_reasons[str(lot.id)] = skip_reason
        else:
            lots_to_apply.append(lot)

    # If no lots to apply, return early with informative result
    if not lots_to_apply:
        return {
            "created_count":       0,
            "milestones_created":  0,
            "deactivated_count":   0,
            "skipped_count":       len(lots_skipped),
            "skipped_reasons":     lots_skipped_reasons,
            "lot_ids":             [],
            "freestanding_master": False,
            "mode":                mode,
        }

    # Deactivate existing items for lots we're going to apply (SAFE/FORCE modes)
    deactivated_count = 0
    lots_needing_deactivate = [l.id for l in lots_to_apply]
    if mode in ("SAFE", "FORCE") and lots_needing_deactivate:
        deactivated_count = _deactivate_lot_boq_items(db, project_id, lots_needing_deactivate)

    # Work only with the filtered lots from here on
    lots = lots_to_apply

    now = datetime.now(timezone.utc)
    created_headers: list[BOQHeader] = []
    milestones_created = 0

    # Load template sections + items once, reuse for all lots
    template_sections, _, _ = _load_template_sections_items(db, template_boq_id)

    # Stage IDs referenced in the template (for milestone generation)
    stage_ids = {s.stage_id for s in template_sections if s.stage_id}

    def _clone_sections_into_header(header_id: uuid.UUID, target_site_id, target_lot_id) -> None:
        """Inner helper: clone template sections+items into a given header."""
        for tmpl_section in template_sections:
            sec = BOQSection(
                id=uuid.uuid4(),
                boq_header_id=header_id,
                stage_id=tmpl_section.stage_id,
                section_name=tmpl_section.section_name,
                sequence_order=tmpl_section.sequence_order,
                notes=tmpl_section.notes,
                created_at=now,
                updated_at=now,
            )
            db.add(sec)
            db.flush()

            tmpl_items = (
                db.query(BOQItem)
                .filter(BOQItem.boq_section_id == tmpl_section.id, BOQItem.is_active == True)
                .order_by(BOQItem.sort_order)
                .all()
            )
            for tmpl_item in tmpl_items:
                # Core INSERT avoids "cannot insert into column planned_total"
                # (GENERATED ALWAYS AS STORED column).
                db.execute(_sa_insert(BOQItem).values(
                    id                     = uuid.uuid4(),
                    boq_section_id         = sec.id,
                    project_id             = project_id,
                    site_id                = target_site_id,
                    lot_id                 = target_lot_id,
                    stage_id               = tmpl_item.stage_id,
                    item_id                = tmpl_item.item_id,
                    supplier_id            = tmpl_item.supplier_id,
                    raw_description        = tmpl_item.raw_description,
                    normalized_description = tmpl_item.normalized_description,
                    specification          = tmpl_item.specification,
                    item_type              = (
                        tmpl_item.item_type.value
                        if hasattr(tmpl_item.item_type, "value")
                        else tmpl_item.item_type
                    ),
                    unit                   = tmpl_item.unit,
                    planned_quantity       = tmpl_item.planned_quantity,
                    planned_rate           = tmpl_item.planned_rate,
                    sort_order             = tmpl_item.sort_order,
                    is_active                   = True,
                    notes                       = tmpl_item.notes,
                    generated_from_lot_type_id  = lot_type_id,  # Phase 3D.3
                    created_at                  = now,
                    updated_at                  = now,
                ))

    # ── Site-level masters (one per unique site) ──────────────────────────────
    # Creates items with lot_id=NULL at each site level so "Generate Lot BOQs"
    # has a source to copy from.  Skipped if site already has active items.
    seen_site_ids: set = set()
    for lot in lots:
        if not lot.site_id or lot.site_id in seen_site_ids:
            continue
        seen_site_ids.add(lot.site_id)

        already_has = (
            db.query(BOQItem.id)
            .filter(
                BOQItem.project_id == project_id,
                BOQItem.site_id    == lot.site_id,
                BOQItem.lot_id.is_(None),
                BOQItem.is_active  == True,
            )
            .first()
        )
        if already_has and mode == "CREATE":
            continue
        # SAFE/FORCE: deactivate site-level items for this site before recreating
        if already_has:
            db.query(BOQItem).filter(
                BOQItem.project_id == project_id,
                BOQItem.site_id    == lot.site_id,
                BOQItem.lot_id.is_(None),
                BOQItem.is_active  == True,
            ).update({"is_active": False}, synchronize_session=False)
            db.flush()

        site_header = BOQHeader(
            id=uuid.uuid4(), project_id=project_id,
            version_name=f"{template.template_name or template.version_name} — Site Master",
            source_type="template_clone_site", status=BoqStatus.ACTIVE,
            is_active_version=True, is_template=False,
            uploaded_by=actor_id, uploaded_at=now,
            notes=f"Site master cloned from template: {template.template_name or template.id}",
        )
        db.add(site_header)
        db.flush()
        _clone_sections_into_header(site_header.id, lot.site_id, None)
        print(f"[BOQ-CLONE] site master header={site_header.id} site={lot.site_id}", flush=True)

    # ── Freestanding lot master (site_id=NULL, lot_id=NULL) ───────────────────
    # Phase 3B: freestanding lots use site_id=None. A project-level master
    # is created so "Generate Lot BOQs" works for freestanding lots.
    freestanding_lots = [l for l in lots if l.site_id is None]
    if freestanding_lots:
        already_has_project_master = (
            db.query(BOQItem.id)
            .filter(
                BOQItem.project_id  == project_id,
                BOQItem.site_id.is_(None),
                BOQItem.lot_id.is_(None),
                BOQItem.is_active   == True,
            )
            .first()
        )
        if not already_has_project_master or mode in ("SAFE", "FORCE"):
            if already_has_project_master:
                db.query(BOQItem).filter(
                    BOQItem.project_id  == project_id,
                    BOQItem.site_id.is_(None),
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active   == True,
                ).update({"is_active": False}, synchronize_session=False)
                db.flush()

            proj_header = BOQHeader(
                id=uuid.uuid4(), project_id=project_id,
                version_name=f"{template.template_name or template.version_name} — Project Master",
                source_type="template_clone_project", status=BoqStatus.ACTIVE,
                is_active_version=True, is_template=False,
                uploaded_by=actor_id, uploaded_at=now,
                notes=f"Project-level master for freestanding lots (cloned from template: {template.template_name or template.id})",
            )
            db.add(proj_header)
            db.flush()
            _clone_sections_into_header(proj_header.id, None, None)
            print(f"[BOQ-CLONE] project master header={proj_header.id} for {len(freestanding_lots)} freestanding lot(s)", flush=True)

    # ── Per-lot BOQ headers ───────────────────────────────────────────────────
    for lot in lots:
        header = BOQHeader(
            id=uuid.uuid4(), project_id=project_id,
            version_name=f"{template.template_name or template.version_name} — Lot {lot.lot_number}",
            source_type="template_clone", status=BoqStatus.ACTIVE,
            is_active_version=True, is_template=False,
            uploaded_by=actor_id, uploaded_at=now,
            notes=f"Cloned from template: {template.template_name or template.id}",
        )
        db.add(header)
        db.flush()
        _clone_sections_into_header(header.id, lot.site_id, lot.id)

        lot.boq_template_id = template.id
        created_headers.append(header)

        audit_service.write_event(
            db, action=AuditAction.CREATE, entity_type="boq_header",
            actor_id=actor_id, entity_id=header.id,
            after_value={
                "lot_id": str(lot.id), "lot_number": lot.lot_number,
                "cloned_from_template": str(template_boq_id),
                "mode": mode,
            },
        )

        # Seed milestones for this lot
        if generate_milestones and stage_ids:
            milestones_created += _seed_milestones(db, project_id, lot, stage_ids, actor_id)

    db.commit()
    print(
        f"[BOQ-CLONE] Done — {len(created_headers)} lot(s) applied, "
        f"{len(lots_skipped)} skipped, "
        f"{milestones_created} milestone(s), {deactivated_count} item(s) replaced "
        f"(mode={mode})",
        flush=True,
    )
    return {
        "created_count":       len(created_headers),
        "milestones_created":  milestones_created,
        "deactivated_count":   deactivated_count,
        "skipped_count":       len(lots_skipped),
        "skipped_reasons":     lots_skipped_reasons,
        "lot_ids":             [str(h.id) for h in created_headers],
        "freestanding_master": len(freestanding_lots) > 0,
        "mode":                mode,
    }
