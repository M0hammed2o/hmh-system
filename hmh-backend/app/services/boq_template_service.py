"""
BOQ template service.

Supports:
- Listing reusable templates (is_template=True BOQHeaders)
- Cloning a template into per-lot BOQHeaders in bulk
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert as _sa_insert
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.enums import AuditAction, BoqStatus
from app.models.lot import Lot
from app.models.project import Project
from app.services import audit_service


def list_templates(db: Session) -> list[BOQHeader]:
    return (
        db.query(BOQHeader)
        .filter(BOQHeader.is_template == True)
        .order_by(BOQHeader.template_name)
        .all()
    )


def clone_template_to_lots(
    db: Session,
    *,
    template_boq_id: uuid.UUID,
    project_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
    actor_id: Optional[uuid.UUID] = None,
) -> list[BOQHeader]:
    """
    Clone a BOQ template into one BOQHeader per lot.

    For each lot:
    - Creates a new BOQHeader (not a template) linked to the project
    - Clones all BOQSections
    - Clones all BOQItems, setting lot_id + project_id on each item
    - Does NOT include planned_total (it's a GENERATED column)

    This is done in a single transaction. At 76 lots × ~50 items = 3,800 rows,
    this is fast enough for a synchronous request. For larger projects, this
    would move to a background task.
    """
    template = db.get(BOQHeader, template_boq_id)
    if not template or not template.is_template:
        raise NotFoundError(f"BOQ template {template_boq_id} not found.")

    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    if not lot_ids:
        raise ValidationError("At least one lot_id is required.")

    # Validate all lots belong to this project
    lots = db.query(Lot).filter(Lot.id.in_(lot_ids), Lot.project_id == project_id).all()
    if len(lots) != len(lot_ids):
        raise ValidationError("One or more lot IDs do not belong to this project.")

    now = datetime.now(timezone.utc)
    created_headers: list[BOQHeader] = []

    # Load template sections + items once, reuse for all lots
    template_sections = (
        db.query(BOQSection)
        .filter(BOQSection.boq_header_id == template.id)
        .order_by(BOQSection.sequence_order)
        .all()
    )

    for lot in lots:
        header = BOQHeader(
            id=uuid.uuid4(),
            project_id=project_id,
            version_name=f"{template.template_name or template.version_name} — Lot {lot.lot_number}",
            source_type="template_clone",
            status=BoqStatus.ACTIVE,
            is_active_version=True,
            is_template=False,
            uploaded_by=actor_id,
            uploaded_at=now,
            notes=f"Cloned from template: {template.template_name or template.id}",
        )
        db.add(header)
        db.flush()  # get header.id before adding sections

        for tmpl_section in template_sections:
            section = BOQSection(
                id=uuid.uuid4(),
                boq_header_id=header.id,
                stage_id=tmpl_section.stage_id,
                section_name=tmpl_section.section_name,
                sequence_order=tmpl_section.sequence_order,
                notes=tmpl_section.notes,
                created_at=now,
                updated_at=now,
            )
            db.add(section)
            db.flush()

            # Load items for this section
            tmpl_items = (
                db.query(BOQItem)
                .filter(BOQItem.boq_section_id == tmpl_section.id, BOQItem.is_active == True)
                .order_by(BOQItem.sort_order)
                .all()
            )

            for tmpl_item in tmpl_items:
                # Use Core INSERT (not ORM add) so SQLAlchemy never includes
                # planned_total in the INSERT statement.  planned_total is
                # GENERATED ALWAYS AS STORED in PostgreSQL — any explicit value
                # (even NULL) causes: "cannot insert into column planned_total".
                stmt = _sa_insert(BOQItem).values(
                    id                     = uuid.uuid4(),
                    boq_section_id         = section.id,
                    project_id             = project_id,
                    site_id                = lot.site_id,
                    lot_id                 = lot.id,
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
                    is_active              = True,
                    notes                  = tmpl_item.notes,
                    created_at             = now,
                    updated_at             = now,
                )
                db.execute(stmt)

        # Update lot to point to this template
        lot.boq_template_id = template.id

        created_headers.append(header)

        audit_service.write_event(
            db,
            action=AuditAction.CREATE,
            entity_type="boq_header",
            actor_id=actor_id,
            entity_id=header.id,
            after_value={
                "lot_id": str(lot.id),
                "lot_number": lot.lot_number,
                "cloned_from_template": str(template_boq_id),
            },
        )

    db.commit()
    return created_headers
