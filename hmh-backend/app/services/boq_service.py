"""BOQ service — three-level hierarchy: header → section → item."""

import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import insert as _sa_insert
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.project import Project
from app.schemas.boq import (
    BOQHeaderCreate, BOQHeaderUpdate,
    BOQItemCreate, BOQItemUpdate,
    BOQSectionCreate, BOQSectionUpdate,
)

_GENERATED_COLS = {"planned_total"}


def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise NotFoundError(f"Project {project_id} not found.")
    return p


def _header_or_404(db: Session, header_id: uuid.UUID) -> BOQHeader:
    h = db.get(BOQHeader, header_id)
    if not h:
        raise NotFoundError(f"BOQ header {header_id} not found.")
    return h


def _section_or_404(db: Session, section_id: uuid.UUID) -> BOQSection:
    s = db.get(BOQSection, section_id)
    if not s:
        raise NotFoundError(f"BOQ section {section_id} not found.")
    return s


def _item_or_404(db: Session, item_id: uuid.UUID) -> BOQItem:
    i = db.get(BOQItem, item_id)
    if not i:
        raise NotFoundError(f"BOQ item {item_id} not found.")
    return i


# ── Headers ───────────────────────────────────────────────────────────────────

def list_headers(db: Session, project_id: uuid.UUID) -> list[BOQHeader]:
    _project_or_404(db, project_id)
    return (
        db.query(BOQHeader)
        .filter(BOQHeader.project_id == project_id)
        .order_by(BOQHeader.uploaded_at.desc())
        .all()
    )


def get_header(db: Session, header_id: uuid.UUID) -> BOQHeader:
    return _header_or_404(db, header_id)


def create_header(
    db: Session,
    project_id: uuid.UUID,
    data: BOQHeaderCreate,
    uploaded_by_id: uuid.UUID,
) -> BOQHeader:
    _project_or_404(db, project_id)
    header = BOQHeader(
        project_id=project_id,
        version_name=data.version_name,
        source_type=data.source_type,
        notes=data.notes,
        uploaded_by=uploaded_by_id,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(header)
    db.commit()
    db.refresh(header)
    return header


def update_header(db: Session, header_id: uuid.UUID, data: BOQHeaderUpdate) -> BOQHeader:
    header = _header_or_404(db, header_id)
    fields = data.model_fields_set

    if "version_name" in fields and data.version_name is not None:
        header.version_name = data.version_name.strip()
    if "status" in fields and data.status is not None:
        header.status = data.status
    if "is_active_version" in fields and data.is_active_version is not None:
        if data.is_active_version:
            # Deactivate any other active version for this project
            db.query(BOQHeader).filter(
                BOQHeader.project_id == header.project_id,
                BOQHeader.id != header_id,
                BOQHeader.is_active_version == True,  # noqa: E712
            ).update({"is_active_version": False})
        header.is_active_version = data.is_active_version
    if "notes" in fields:
        header.notes = data.notes

    db.commit()
    db.refresh(header)
    return header


# ── Sections ──────────────────────────────────────────────────────────────────

def list_sections(db: Session, header_id: uuid.UUID) -> list[BOQSection]:
    _header_or_404(db, header_id)
    return (
        db.query(BOQSection)
        .filter(BOQSection.boq_header_id == header_id)
        .order_by(BOQSection.sequence_order, BOQSection.section_name)
        .all()
    )


def create_section(
    db: Session, header_id: uuid.UUID, data: BOQSectionCreate
) -> BOQSection:
    _header_or_404(db, header_id)
    section = BOQSection(
        boq_header_id=header_id,
        section_name=data.section_name,
        stage_id=data.stage_id,
        sequence_order=data.sequence_order,
        notes=data.notes,
    )
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


def update_section(
    db: Session, section_id: uuid.UUID, data: BOQSectionUpdate
) -> BOQSection:
    section = _section_or_404(db, section_id)
    fields = data.model_fields_set
    if "section_name" in fields and data.section_name is not None:
        section.section_name = data.section_name.strip()
    if "stage_id" in fields:
        section.stage_id = data.stage_id
    if "sequence_order" in fields and data.sequence_order is not None:
        section.sequence_order = data.sequence_order
    if "notes" in fields:
        section.notes = data.notes
    db.commit()
    db.refresh(section)
    return section


# ── Items ─────────────────────────────────────────────────────────────────────

def list_items(db: Session, section_id: uuid.UUID) -> list[BOQItem]:
    _section_or_404(db, section_id)
    return (
        db.query(BOQItem)
        .filter(BOQItem.boq_section_id == section_id, BOQItem.is_active == True)  # noqa: E712
        .order_by(BOQItem.sort_order, BOQItem.raw_description)
        .all()
    )


def create_item(
    db: Session, section_id: uuid.UUID, data: BOQItemCreate
) -> BOQItem:
    section = _section_or_404(db, section_id)
    header = db.get(BOQHeader, section.boq_header_id)
    project_id = header.project_id if header else None

    now = datetime.now(timezone.utc)
    new_id = uuid.uuid4()

    # Use Core INSERT to avoid touching planned_total (GENERATED ALWAYS AS STORED)
    stmt = _sa_insert(BOQItem).values(
        id=new_id,
        boq_section_id=section_id,
        project_id=project_id,
        site_id=data.site_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        item_id=data.item_id,
        supplier_id=data.supplier_id,
        raw_description=data.raw_description,
        specification=data.specification,
        item_type=data.item_type.value if hasattr(data.item_type, "value") else data.item_type,
        unit=data.unit,
        planned_quantity=data.planned_quantity,
        planned_rate=data.planned_rate,
        sort_order=data.sort_order,
        notes=data.notes,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.execute(stmt)
    db.commit()
    return _item_or_404(db, new_id)


def import_csv(
    db: Session,
    project_id: uuid.UUID,
    csv_content: str,
    version_name: str,
    uploaded_by_id: uuid.UUID,
) -> BOQHeader:
    """Parse a CSV file and create a BOQ header + sections + items in one commit.

    Expected CSV columns (case-insensitive, extras ignored):
        section, description, unit, quantity, rate, type, specification, notes
    """
    _project_or_404(db, project_id)

    header = BOQHeader(
        project_id=project_id,
        version_name=version_name,
        source_type="CSV",
        uploaded_by=uploaded_by_id,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(header)
    db.flush()  # obtain header.id before creating children

    reader = csv.DictReader(io.StringIO(csv_content))
    sections: dict[str, BOQSection] = {}
    section_seq = 1
    item_sort = 1
    valid_types = {"MATERIAL", "SERVICE", "PACKAGE"}

    def _num(val: str) -> Optional[float]:
        try:
            return float(val) if val and val.strip() else None
        except (ValueError, TypeError):
            return None

    for row in reader:
        norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

        section_name = norm.get("section", "").strip() or "General"
        description = norm.get("description", "").strip()
        if not description:
            continue  # skip blank rows

        if section_name not in sections:
            section = BOQSection(
                boq_header_id=header.id,
                section_name=section_name,
                sequence_order=section_seq,
            )
            db.add(section)
            db.flush()
            sections[section_name] = section
            section_seq += 1

        section = sections[section_name]
        item_type_raw = norm.get("type", "MATERIAL").upper()
        item_type = item_type_raw if item_type_raw in valid_types else "MATERIAL"

        # Use Core INSERT to avoid touching the GENERATED ALWAYS planned_total column
        stmt = _sa_insert(BOQItem).values(
            boq_section_id=section.id,
            project_id=project_id,
            raw_description=description,
            item_type=item_type,
            unit=norm.get("unit") or None,
            planned_quantity=_num(norm.get("quantity", "")),
            planned_rate=_num(norm.get("rate", "")),
            specification=norm.get("specification") or None,
            notes=norm.get("notes") or None,
            sort_order=item_sort,
        )
        db.execute(stmt)
        item_sort += 1

    db.commit()
    db.refresh(header)
    return header


def delete_item(db: Session, item_id: uuid.UUID) -> None:
    item = _item_or_404(db, item_id)
    item.is_active = False
    db.commit()


def delete_section(db: Session, section_id: uuid.UUID) -> None:
    section = _section_or_404(db, section_id)
    # Soft-delete all items in section first
    db.query(BOQItem).filter(BOQItem.boq_section_id == section_id).update({"is_active": False})
    db.delete(section)
    db.commit()


def delete_section_scoped(
    db: Session,
    section_id: uuid.UUID,
    scope: str = "lot",
) -> dict:
    """
    Delete a BOQ section with either lot-only or site-wide scope.

    scope="lot"  — deletes only this specific section (same as delete_section).
    scope="site" — finds all sections with the same name across every lot in the
                   same site, then deletes them all.  Safety constraints:
                   - Never touches a different site.
                   - Never touches BOQ templates (is_template=True headers).
                   - Matches by section_name, not section_id, because each lot
                     has its own cloned section rows.

    Returns a dict with sections_deleted, lots_affected, items_deleted, message.
    """
    from app.models.lot import Lot

    section = _section_or_404(db, section_id)
    target_name = section.section_name

    if scope == "site":
        # Infer lot_id from any active item in this section
        sample_item = (
            db.query(BOQItem)
            .filter(BOQItem.boq_section_id == section_id)
            .first()
        )
        lot_id   = sample_item.lot_id if sample_item else None
        site_id  = None

        if lot_id:
            lot = db.get(Lot, lot_id)
            site_id = lot.site_id if lot else None

        if site_id:
            # All lots in the same site
            site_lot_ids = [
                row[0] for row in db.query(Lot.id).filter(Lot.site_id == site_id).all()
            ]

            # Find all section IDs that:
            #   - have section_name matching the target
            #   - contain at least one item whose lot_id is in this site's lots
            # (This excludes template headers and other sites automatically.)
            matching_section_ids = [
                row[0] for row in (
                    db.query(BOQItem.boq_section_id)
                    .join(BOQSection, BOQItem.boq_section_id == BOQSection.id)
                    .filter(
                        BOQItem.lot_id.in_(site_lot_ids),
                        BOQSection.section_name == target_name,
                    )
                    .distinct()
                    .all()
                )
            ]
            # Always include the section the user clicked on
            if section_id not in matching_section_ids:
                matching_section_ids.append(section_id)

            # Collect metrics before deleting
            items_deleted = (
                db.query(BOQItem)
                .filter(
                    BOQItem.boq_section_id.in_(matching_section_ids),
                    BOQItem.is_active == True,
                )
                .count()
            )
            lots_affected_ids: set = set()
            for sid in matching_section_ids:
                for row in (
                    db.query(BOQItem.lot_id)
                    .filter(BOQItem.boq_section_id == sid, BOQItem.lot_id.isnot(None))
                    .distinct()
                    .all()
                ):
                    lots_affected_ids.add(row[0])

            # Soft-delete items then hard-delete sections
            db.query(BOQItem).filter(
                BOQItem.boq_section_id.in_(matching_section_ids),
                BOQItem.is_active == True,
            ).update({"is_active": False}, synchronize_session=False)

            for sid in matching_section_ids:
                sec = db.get(BOQSection, sid)
                if sec:
                    db.delete(sec)

            db.commit()
            lots_affected = len(lots_affected_ids)
            return {
                "scope": "site",
                "sections_deleted": len(matching_section_ids),
                "lots_affected": lots_affected,
                "items_deleted": items_deleted,
                "message": f"Deleted section from {lots_affected} lot(s) in this site.",
            }

    # Default / fallback: lot scope
    items_deleted = (
        db.query(BOQItem)
        .filter(BOQItem.boq_section_id == section_id, BOQItem.is_active == True)
        .count()
    )
    db.query(BOQItem).filter(BOQItem.boq_section_id == section_id).update({"is_active": False})
    db.delete(section)
    db.commit()
    return {
        "scope": "lot",
        "sections_deleted": 1,
        "lots_affected": 1,
        "items_deleted": items_deleted,
        "message": "Section deleted from this lot.",
    }


def get_full_boq(db: Session, header_id: uuid.UUID) -> dict:
    """Return full nested BOQ with section totals and grand total."""
    header = _header_or_404(db, header_id)
    sections = list_sections(db, header_id)

    grand_total = Decimal("0.00")
    sections_out = []
    for section in sections:
        items = list_items(db, section.id)
        section_total = Decimal("0.00")
        for i in items:
            if i.planned_total is not None:
                # planned_total is Decimal from PostgreSQL NUMERIC column
                section_total += i.planned_total
            elif i.planned_quantity is not None and i.planned_rate is not None:
                section_total += Decimal(str(i.planned_quantity)) * Decimal(str(i.planned_rate))
        grand_total += section_total
        sections_out.append({
            "section": section,
            "items": items,
            "section_total": float(round(section_total, 2)),
        })

    return {
        "header": header,
        "sections": sections_out,
        "grand_total": float(round(grand_total, 2)),
    }


def mark_as_template(db: Session, header_id: uuid.UUID, template_name: str) -> BOQHeader:
    header = _header_or_404(db, header_id)
    header.is_template = True
    header.template_name = template_name.strip()
    db.commit()
    db.refresh(header)
    return header


def seed_standard_residential_template(db: Session, project_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None) -> BOQHeader:
    """
    Create 'Standard Residential Unit BOQ' template for a project.
    Idempotent — skips if a template with this name already exists for the project.
    """
    existing = (
        db.query(BOQHeader)
        .filter(
            BOQHeader.project_id == project_id,
            BOQHeader.is_template == True,
            BOQHeader.template_name == "Standard Residential Unit BOQ",
        )
        .first()
    )
    if existing:
        return existing

    now = datetime.now(timezone.utc)
    header = BOQHeader(
        project_id=project_id,
        version_name="Standard Residential Unit BOQ",
        source_type="system_template",
        is_template=True,
        template_name="Standard Residential Unit BOQ",
        uploaded_by=actor_id,
        uploaded_at=now,
        notes="Default editable template for a standard residential unit. Edit rates and quantities to match your project.",
    )
    db.add(header)
    db.flush()

    # Each section: (name, order, [(description, unit, qty, rate, type)])
    sections_data = [
        ("Foundations", 1, [
            ("Bulk excavation", "m³", 12.0, 180.0, "MATERIAL"),
            ("Trench excavation", "m³", 8.0, 200.0, "LABOUR"),
            ("Strip foundation concrete (20MPa)", "m³", 4.5, 2800.0, "MATERIAL"),
            ("Foundation steel reinforcing", "kg", 250.0, 22.0, "MATERIAL"),
            ("Blinding layer (75mm)", "m²", 40.0, 85.0, "MATERIAL"),
        ]),
        ("Concrete & Slab", 2, [
            ("Ground floor slab concrete (25MPa)", "m³", 18.0, 3100.0, "MATERIAL"),
            ("Slab steel mesh reinforcing (193)", "m²", 90.0, 65.0, "MATERIAL"),
            ("Damp proof membrane (0.25mm)", "m²", 95.0, 12.0, "MATERIAL"),
            ("Concrete slab finishing/screeding", "m²", 90.0, 55.0, "LABOUR"),
        ]),
        ("Brickwork", 3, [
            ("Standard stock brick (ext walls 230mm)", "each", 5500.0, 1.85, "MATERIAL"),
            ("Internal partition brickwork (115mm)", "m²", 85.0, 320.0, "MATERIAL"),
            ("Mortar (cement/sand 1:4)", "m³", 3.2, 1400.0, "MATERIAL"),
            ("Bricklaying labour", "m²", 180.0, 95.0, "LABOUR"),
            ("Lintels (precast 230mm)", "each", 12.0, 280.0, "MATERIAL"),
        ]),
        ("Roofing", 4, [
            ("Roof trusses (engineer certified)", "each", 14.0, 3200.0, "MATERIAL"),
            ("Roof battens (38x38)", "m", 280.0, 22.0, "MATERIAL"),
            ("IBR sheeting (0.47mm)", "m²", 120.0, 185.0, "MATERIAL"),
            ("Ridge capping", "m", 8.0, 95.0, "MATERIAL"),
            ("Roof fixing / labour", "m²", 120.0, 65.0, "LABOUR"),
            ("Fascia board & barge boards", "m", 32.0, 85.0, "MATERIAL"),
            ("Gutters & downpipes (PVC)", "m", 24.0, 120.0, "MATERIAL"),
        ]),
        ("Plumbing", 5, [
            ("Water supply piping (HDPE 20mm)", "m", 45.0, 48.0, "MATERIAL"),
            ("Sewage piping (uPVC 110mm)", "m", 30.0, 95.0, "MATERIAL"),
            ("Sanitary ware (basin/toilet/shower)", "set", 1.0, 8500.0, "MATERIAL"),
            ("Geyser (100L electric)", "each", 1.0, 4200.0, "MATERIAL"),
            ("Plumbing labour & installation", "item", 1.0, 6500.0, "LABOUR"),
        ]),
        ("Electrical", 6, [
            ("DB board (12-way)", "each", 1.0, 1800.0, "MATERIAL"),
            ("Wiring (2.5mm twin & earth)", "m", 120.0, 28.0, "MATERIAL"),
            ("Light points (complete)", "each", 12.0, 350.0, "MATERIAL"),
            ("Power points (complete)", "each", 18.0, 380.0, "MATERIAL"),
            ("Electrical installation labour", "item", 1.0, 5500.0, "LABOUR"),
            ("COC certification", "item", 1.0, 850.0, "SERVICE"),
        ]),
        ("Plastering", 7, [
            ("Internal plaster (12mm 1:4)", "m²", 280.0, 85.0, "MATERIAL"),
            ("External roughcast plaster", "m²", 180.0, 95.0, "MATERIAL"),
            ("Plastering labour", "m²", 460.0, 45.0, "LABOUR"),
            ("Plaster beads & accessories", "item", 1.0, 1200.0, "MATERIAL"),
        ]),
        ("Painting", 8, [
            ("Interior PVA paint (2 coats)", "m²", 280.0, 42.0, "MATERIAL"),
            ("Exterior paint (weatherproof)", "m²", 180.0, 65.0, "MATERIAL"),
            ("Painting labour (int + ext)", "m²", 460.0, 25.0, "LABOUR"),
        ]),
        ("Finishes", 9, [
            ("Ceramic floor tiles (400x400)", "m²", 75.0, 185.0, "MATERIAL"),
            ("Wall tiles (bathrooms/kitchen)", "m²", 28.0, 220.0, "MATERIAL"),
            ("Tiling labour", "m²", 103.0, 120.0, "LABOUR"),
            ("Internal doors (hollow core)", "each", 6.0, 1800.0, "MATERIAL"),
            ("External door (solid timber)", "each", 1.0, 4500.0, "MATERIAL"),
            ("Windows (aluminium single glazed)", "each", 8.0, 2800.0, "MATERIAL"),
            ("Door & window installation", "each", 9.0, 450.0, "LABOUR"),
            ("Skirting board (pine 68mm)", "m", 65.0, 48.0, "MATERIAL"),
        ]),
        ("Labour", 10, [
            ("Site foreman (weeks)", "week", 12.0, 3500.0, "LABOUR"),
            ("General labourers (man-days)", "day", 120.0, 450.0, "LABOUR"),
            ("Concrete gang (days)", "day", 8.0, 3200.0, "LABOUR"),
            ("Bricklaying team (days)", "day", 25.0, 4800.0, "LABOUR"),
        ]),
        ("Plant & Equipment", 11, [
            ("Concrete mixer (rental/week)", "week", 6.0, 1800.0, "PLANT"),
            ("Scaffolding (rental/week)", "week", 4.0, 2200.0, "PLANT"),
            ("Compactor plate (rental/day)", "day", 5.0, 650.0, "PLANT"),
            ("Generator (rental/day)", "day", 10.0, 850.0, "PLANT"),
        ]),
    ]

    valid_types = {"MATERIAL", "LABOUR", "PLANT", "SERVICE", "PACKAGE"}

    for section_name, seq_order, items_data in sections_data:
        section = BOQSection(
            boq_header_id=header.id,
            section_name=section_name,
            sequence_order=seq_order,
            created_at=now,
            updated_at=now,
        )
        db.add(section)
        db.flush()

        for sort_idx, (desc, unit, qty, rate, itype) in enumerate(items_data, 1):
            stmt = _sa_insert(BOQItem).values(
                boq_section_id=section.id,
                project_id=project_id,
                raw_description=desc,
                item_type=itype if itype in valid_types else "MATERIAL",
                unit=unit,
                planned_quantity=qty,
                planned_rate=rate,
                sort_order=sort_idx,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.execute(stmt)

    db.commit()
    db.refresh(header)
    return header


def update_item(db: Session, item_id: uuid.UUID, data: BOQItemUpdate) -> BOQItem:
    item = _item_or_404(db, item_id)
    fields = data.model_fields_set

    if "raw_description" in fields and data.raw_description is not None:
        item.raw_description = data.raw_description.strip()
    if "item_type" in fields and data.item_type is not None:
        item.item_type = data.item_type
    if "unit" in fields:
        item.unit = data.unit
    if "planned_quantity" in fields:
        item.planned_quantity = data.planned_quantity
    if "planned_rate" in fields:
        item.planned_rate = data.planned_rate
    # planned_total is GENERATED ALWAYS AS STORED — never set it
    if "site_id" in fields:
        item.site_id = data.site_id
    if "lot_id" in fields:
        item.lot_id = data.lot_id
    if "stage_id" in fields:
        item.stage_id = data.stage_id
    if "item_id" in fields:
        item.item_id = data.item_id
    if "supplier_id" in fields:
        item.supplier_id = data.supplier_id
    if "specification" in fields:
        item.specification = data.specification
    if "sort_order" in fields and data.sort_order is not None:
        item.sort_order = data.sort_order
    if "is_active" in fields and data.is_active is not None:
        item.is_active = data.is_active
    if "notes" in fields:
        item.notes = data.notes

    db.commit()
    db.refresh(item)
    return item


# ── Site BOQ copy ─────────────────────────────────────────────────────────────

def copy_boq(
    db: Session,
    source_header_id: uuid.UUID,
    target_project_id: uuid.UUID,
    new_version_name: str,
    target_site_id: Optional[uuid.UUID] = None,
    uploaded_by_id: Optional[uuid.UUID] = None,
) -> BOQHeader:
    """
    Copy a BOQ header (all sections + items) to a new header.

    Used to:
    - Duplicate a template to a specific site
    - Copy one site's BOQ to another site
    Items are copied WITHOUT lot_id (site-level), ready for generate_lot_boqs().
    planned_total is GENERATED ALWAYS — never included in INSERT.
    """
    source = _header_or_404(db, source_header_id)
    now = datetime.now(timezone.utc)

    new_header = BOQHeader(
        project_id=target_project_id,
        version_name=new_version_name,
        source_type="copy",
        notes=f"Copied from: {source.version_name}",
        uploaded_by=uploaded_by_id,
        uploaded_at=now,
    )
    db.add(new_header)
    db.flush()

    for section in source.sections:
        new_section = BOQSection(
            boq_header_id=new_header.id,
            section_name=section.section_name,
            sequence_order=section.sequence_order,
            stage_id=section.stage_id,
            notes=section.notes,
            created_at=now,
            updated_at=now,
        )
        db.add(new_section)
        db.flush()

        for item in section.items:
            if not item.is_active:
                continue
            stmt = _sa_insert(BOQItem).values(
                boq_section_id=new_section.id,
                project_id=target_project_id,
                site_id=target_site_id,
                lot_id=None,           # always site-level on copy
                stage_id=item.stage_id,
                item_id=item.item_id,
                supplier_id=item.supplier_id,
                raw_description=item.raw_description,
                specification=item.specification,
                item_type=(
                    item.item_type.value
                    if hasattr(item.item_type, "value")
                    else item.item_type
                ),
                unit=item.unit,
                planned_quantity=item.planned_quantity,
                planned_rate=item.planned_rate,
                sort_order=item.sort_order,
                is_active=True,
                notes=item.notes,
                created_at=now,
                updated_at=now,
            )
            db.execute(stmt)

    db.commit()
    db.refresh(new_header)
    return new_header


# ── Lot BOQ generation ────────────────────────────────────────────────────────

def generate_lot_boqs(
    db: Session,
    source_header_id: uuid.UUID,
    lot_ids: list[uuid.UUID],
) -> int:
    """
    For each lot, copy every site-level BOQItem (lot_id IS NULL) in the header
    into a lot-specific copy.  Idempotent — skips lots that already have items
    in a given section.

    Returns total number of new BOQItem rows created.
    """
    source = _header_or_404(db, source_header_id)
    now = datetime.now(timezone.utc)
    total_created = 0

    for section in source.sections:
        site_items = [i for i in section.items if i.is_active and i.lot_id is None]
        if not site_items:
            continue

        for lot_id in lot_ids:
            already = (
                db.query(BOQItem)
                .filter(
                    BOQItem.boq_section_id == section.id,
                    BOQItem.lot_id == lot_id,
                )
                .count()
            )
            if already:
                continue   # already generated for this lot+section

            for item in site_items:
                stmt = _sa_insert(BOQItem).values(
                    boq_section_id=section.id,
                    project_id=source.project_id,
                    site_id=item.site_id,
                    lot_id=lot_id,
                    stage_id=item.stage_id,
                    item_id=item.item_id,
                    raw_description=item.raw_description,
                    specification=item.specification,
                    item_type=(
                        item.item_type.value
                        if hasattr(item.item_type, "value")
                        else item.item_type
                    ),
                    unit=item.unit,
                    planned_quantity=item.planned_quantity,
                    planned_rate=item.planned_rate,
                    sort_order=item.sort_order,
                    is_active=True,
                    notes=item.notes,
                    created_at=now,
                    updated_at=now,
                )
                db.execute(stmt)
                total_created += 1

    db.commit()
    return total_created


# ── Lot BOQ summary ───────────────────────────────────────────────────────────

def get_lot_boq_summary(db: Session, lot_id: uuid.UUID) -> list[dict]:
    """
    Return allocated / used / remaining per item for a lot.
    Uses allocation_service for the calculation.
    """
    from app.services.allocation_service import get_all_lot_allocations

    allocations = get_all_lot_allocations(db, lot_id)
    return [
        {
            "item_id":            str(a.item_id),
            "item_name":          a.item_name,
            "item_unit":          a.item_unit,
            "allocated_quantity": a.allocated_quantity,
            "used_quantity":      a.used_quantity,
            "remaining_quantity": a.remaining_quantity,
            "over_quantity":      a.over_quantity,
            "is_over":            a.is_over,
        }
        for a in allocations
    ]


# ── BOQ Adjustments ───────────────────────────────────────────────────────────

_VALID_ADJUSTMENT_TYPES = {"CREDIT", "NON_SUPPLY", "RETURN"}


def create_adjustment(
    db: Session,
    adjustment_type: str,
    reason: str,
    created_by_id: uuid.UUID,
    project_id: Optional[uuid.UUID] = None,
    site_id: Optional[uuid.UUID] = None,
    lot_id: Optional[uuid.UUID] = None,
    boq_item_id: Optional[uuid.UUID] = None,
    item_id: Optional[uuid.UUID] = None,
    purchase_order_id: Optional[uuid.UUID] = None,
    invoice_id: Optional[uuid.UUID] = None,
    delivery_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    quantity=None,
    amount=None,
    notes: Optional[str] = None,
):
    from app.models.boq_adjustment import BOQAdjustment
    from app.core.exceptions import ValidationError

    adj_type = adjustment_type.upper()
    if adj_type not in _VALID_ADJUSTMENT_TYPES:
        raise ValidationError(
            f"adjustment_type must be one of: {', '.join(_VALID_ADJUSTMENT_TYPES)}"
        )

    now = datetime.now(timezone.utc)
    adj = BOQAdjustment(
        project_id=project_id,
        site_id=site_id,
        lot_id=lot_id,
        boq_item_id=boq_item_id,
        item_id=item_id,
        purchase_order_id=purchase_order_id,
        invoice_id=invoice_id,
        delivery_id=delivery_id,
        supplier_id=supplier_id,
        adjustment_type=adj_type,
        quantity=quantity,
        amount=amount,
        reason=reason,
        notes=notes,
        created_by=created_by_id,
        created_at=now,
    )
    db.add(adj)
    db.commit()
    db.refresh(adj)
    return adj


def list_adjustments(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
    site_id: Optional[uuid.UUID] = None,
    lot_id: Optional[uuid.UUID] = None,
    adjustment_type: Optional[str] = None,
    limit: int = 100,
):
    from app.models.boq_adjustment import BOQAdjustment

    q = db.query(BOQAdjustment).order_by(BOQAdjustment.created_at.desc())
    if project_id:
        q = q.filter(BOQAdjustment.project_id == project_id)
    if site_id:
        q = q.filter(BOQAdjustment.site_id == site_id)
    if lot_id:
        q = q.filter(BOQAdjustment.lot_id == lot_id)
    if adjustment_type:
        q = q.filter(BOQAdjustment.adjustment_type == adjustment_type.upper())
    return q.limit(limit).all()


# ── Site / Project BOQ hierarchy ──────────────────────────────────────────────

import re as _re

def _item_total_safe(item: BOQItem) -> float:
    """Compute line total with fallback to qty × rate when planned_total is null."""
    if item.planned_total is not None:
        return float(item.planned_total)
    return float(item.planned_quantity or 0) * float(item.planned_rate or 0)


def _item_type_str(item: BOQItem) -> str:
    return item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type)


def _type_breakdown(items: list) -> dict:
    t: dict[str, float] = {}
    for i in items:
        k = _item_type_str(i)
        t[k] = t.get(k, 0.0) + _item_total_safe(i)
    return {
        "material_total": round(t.get("MATERIAL", 0.0), 2),
        "labour_total":   round(t.get("LABOUR",   0.0), 2),
        "plant_total":    round(t.get("PLANT",     0.0), 2),
        "service_total":  round(t.get("SERVICE",   0.0), 2),
        "other_total":    round(sum(v for k, v in t.items() if k not in {"MATERIAL","LABOUR","PLANT","SERVICE"}), 2),
    }


def _lot_sort_key(lot_number: str) -> tuple:
    """Numerical sort: '1' < '2' < '10' instead of lexicographic '1' < '10' < '2'."""
    m = _re.match(r"^(\d+)(.*)", (lot_number or "").strip())
    if m:
        return (0, int(m.group(1)), m.group(2).lower())
    return (1, 0, (lot_number or "").lower())


def _variance(actual: float, expected: float) -> dict:
    amt = round(actual - expected, 2)
    pct = round((amt / expected * 100) if expected > 0 else 0.0, 1)
    return {"variance_amount": amt, "variance_pct": pct}


def get_project_master_summary(db: Session, project_id: uuid.UUID) -> dict:
    """
    Project-level roll-up keyed by site.

    Returns one record per site (active sites for the project), including:
    - Site name
    - unit_total  — sum of site-level BOQ items (lot_id IS NULL)
    - lot_count   — number of lots attached to the site
    - site_total  — unit_total × lot_count (rough planned value for the site)
    - has_boq     — whether site-level BOQ items exist
    - boq_header_ids — headers that own those site items (for Edit/Build links)
    """
    from app.models.site import Site
    from app.models.lot import Lot

    _project_or_404(db, project_id)
    all_sites = (
        db.query(Site)
        .filter(Site.project_id == project_id, Site.is_active == True)
        .all()
    )

    # ── Bulk-fetch all data in 3 queries instead of N×3 queries ─────────────
    # Query 1: all site-level BOQ items for this project (site_id may be NULL for freestanding)
    all_site_items = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.lot_id.is_(None),
            BOQItem.is_active  == True,
        )
        .all()
    )
    site_items_by_site: dict = {}
    for item in all_site_items:
        # Key is site_id (may be None for project-level freestanding items)
        site_items_by_site.setdefault(item.site_id, []).append(item)

    # Query 2: all lots for this project (count + first-lot lookup)
    all_lots = db.query(Lot).filter(Lot.project_id == project_id).all()
    lots_by_site: dict = {}
    for lot in all_lots:
        # Key is site_id (may be None for freestanding lots)
        lots_by_site.setdefault(lot.site_id, []).append(lot)

    # Query 3: all lot-level BOQ items (only needed if site-level items missing)
    all_lot_items = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.lot_id.isnot(None),
            BOQItem.is_active  == True,
        )
        .all()
    )
    lot_items_by_lot: dict = {}
    for item in all_lot_items:
        if item.lot_id:
            lot_items_by_lot.setdefault(item.lot_id, []).append(item)

    # Query 4: section → header mapping (bulk)
    section_to_header: dict = {
        str(s.id): str(s.boq_header_id)
        for s in db.query(BOQSection).filter(
            BOQSection.boq_header_id.in_(
                db.query(BOQHeader.id).filter(BOQHeader.project_id == project_id)
            )
        ).all()
    }

    total_planned   = 0.0
    total_lot_count = 0
    proj_types: dict[str, float] = {}
    sites_out       = []

    for site in all_sites:
        site_items = site_items_by_site.get(site.id, [])
        site_lots  = lots_by_site.get(site.id, [])
        lot_count  = len(site_lots)

        if site_items:
            unit_total = sum(_item_total_safe(i) for i in site_items)
            site_total = unit_total * max(lot_count, 1)
            type_b     = _type_breakdown(site_items)
        else:
            # Fall back to lot BOQs — use the first lot as representative
            first_lot = site_lots[0] if site_lots else None
            rep_items: list = lot_items_by_lot.get(first_lot.id, []) if first_lot else []
            unit_total = sum(_item_total_safe(i) for i in rep_items)

            # Actual site total = sum of all lots
            all_lot_items_for_site = [
                item
                for lot in site_lots
                for item in lot_items_by_lot.get(lot.id, [])
            ]
            site_total = sum(_item_total_safe(i) for i in all_lot_items_for_site) if all_lot_items_for_site else unit_total
            type_b = _type_breakdown(rep_items or all_lot_items_for_site)

        # Accumulate project-wide type totals
        for k, v in type_b.items():
            proj_types[k] = proj_types.get(k, 0.0) + v

        # Find header IDs from pre-built mapping
        header_ids: set[str] = {
            section_to_header[str(item.boq_section_id)]
            for item in site_items
            if str(item.boq_section_id) in section_to_header
        }

        expected = unit_total * max(lot_count, 1)
        var = _variance(site_total, expected)

        total_planned   += site_total
        total_lot_count += lot_count
        sites_out.append({
            "site_id":        str(site.id),
            "site_name":      site.name,
            "unit_total":     round(unit_total, 2),
            "lot_count":      lot_count,
            "site_total":     round(site_total, 2),
            "item_count":     len(site_items),
            "has_boq":        len(site_items) > 0 or site_total > 0,
            "boq_header_ids": list(header_ids),
            **type_b,
            **var,
        })

    # ── Freestanding lots (lot.site_id IS NULL) ──────────────────────────────
    # These lots are not attached to any site and were silently excluded above.
    freestanding_lots = lots_by_site.get(None, [])
    if freestanding_lots:
        fl_site_level_items = site_items_by_site.get(None, [])
        fl_lot_items_all    = [
            item
            for lot in freestanding_lots
            for item in lot_items_by_lot.get(lot.id, [])
        ]

        if fl_site_level_items:
            # Use project-level (site=NULL) template items for unit_total
            unit_total = sum(_item_total_safe(i) for i in fl_site_level_items)
        elif freestanding_lots:
            # Fall back to first freestanding lot as representative
            first_fl = freestanding_lots[0]
            rep_items = lot_items_by_lot.get(first_fl.id, [])
            unit_total = sum(_item_total_safe(i) for i in rep_items)
        else:
            unit_total = 0.0

        site_total = (
            sum(_item_total_safe(i) for i in fl_lot_items_all)
            if fl_lot_items_all
            else unit_total * len(freestanding_lots)
        )
        lot_count = len(freestanding_lots)
        type_b    = _type_breakdown(fl_site_level_items or fl_lot_items_all)

        fl_header_ids: set[str] = {
            section_to_header[str(item.boq_section_id)]
            for item in fl_site_level_items
            if str(item.boq_section_id) in section_to_header
        }

        var = _variance(site_total, unit_total * max(lot_count, 1))
        total_planned   += site_total
        total_lot_count += lot_count

        for k, v in type_b.items():
            proj_types[k] = proj_types.get(k, 0.0) + v

        sites_out.append({
            "site_id":        None,
            "site_name":      "Freestanding Units",
            "is_freestanding": True,
            "unit_total":     round(unit_total, 2),
            "lot_count":      lot_count,
            "site_total":     round(site_total, 2),
            "item_count":     len(fl_site_level_items),
            "has_boq":        len(fl_site_level_items) > 0 or site_total > 0,
            "boq_header_ids": list(fl_header_ids),
            **type_b,
            **var,
        })

    all_headers      = list_headers(db, project_id)
    legacy_lot_count = len([h for h in all_headers if " — Lot " in h.version_name or " – Lot " in h.version_name])

    return {
        "project_id":      str(project_id),
        "total_planned":   round(total_planned, 2),
        "site_count":      len(all_sites),
        "total_lot_count": total_lot_count,
        "freestanding_lot_count": len(freestanding_lots),
        "legacy_lot_count": legacy_lot_count,
        "sites":           sites_out,
        "material_total":  round(proj_types.get("material_total", proj_types.get("MATERIAL", 0)), 2),
        "labour_total":    round(proj_types.get("labour_total",   proj_types.get("LABOUR",   0)), 2),
        "plant_total":     round(proj_types.get("plant_total",    proj_types.get("PLANT",    0)), 2),
        "service_total":   round(proj_types.get("service_total",  proj_types.get("SERVICE",  0)), 2),
    }


def get_site_boq_summary(db: Session, site_id: uuid.UUID) -> dict:
    """
    Site-level BOQ detail.

    Primary source: items where site_id = X and lot_id IS NULL.
    Fallback:       if none, use the first lot's items as the representative
                    "unit template" and sum all lots for the site total.
    Includes type breakdown (MATERIAL/LABOUR/PLANT/SERVICE) and variance.
    """
    from app.models.site import Site
    from app.models.lot import Lot

    site = db.get(Site, site_id)
    if not site:
        return {}

    site_items = (
        db.query(BOQItem)
        .filter(BOQItem.site_id == site_id, BOQItem.lot_id.is_(None), BOQItem.is_active == True)
        .all()
    )
    derived_from_lots = False

    if not site_items:
        # Fallback — use first lot as representative unit template
        first_lot = (
            db.query(Lot)
            .filter(Lot.project_id == site.project_id, Lot.site_id == site_id)
            .first()
        )
        if first_lot:
            site_items = (
                db.query(BOQItem)
                .filter(BOQItem.lot_id == first_lot.id, BOQItem.is_active == True)
                .all()
            )
            derived_from_lots = True

    unit_total = sum(_item_total_safe(i) for i in site_items)
    type_b     = _type_breakdown(site_items)

    lot_count = (
        db.query(Lot)
        .filter(Lot.project_id == site.project_id, Lot.site_id == site_id)
        .count()
    )

    if derived_from_lots:
        # Actual site total = sum of every lot's BOQ
        all_lot_ids = [
            row[0] for row in db.query(Lot.id)
            .filter(Lot.project_id == site.project_id, Lot.site_id == site_id).all()
        ]
        all_lot_items = (
            db.query(BOQItem)
            .filter(BOQItem.lot_id.in_(all_lot_ids), BOQItem.is_active == True)
            .all()
        ) if all_lot_ids else []
        actual_site_total = sum(_item_total_safe(i) for i in all_lot_items)
    else:
        actual_site_total = unit_total * max(lot_count, 1)

    expected_site_total = unit_total * max(lot_count, 1)
    var = _variance(actual_site_total, expected_site_total)

    # Build sections from template items
    section_map: dict[uuid.UUID, dict] = {}
    header_ids: set[str] = set()
    for item in site_items:
        sid = item.boq_section_id
        if sid not in section_map:
            sec = db.get(BOQSection, sid)
            if sec:
                header_ids.add(str(sec.boq_header_id))
            section_map[sid] = {
                "section_id":     str(sid),
                "section_name":   sec.section_name if sec else "—",
                "sequence_order": sec.sequence_order if sec else 0,
                "items":          [],
                "section_total":  0.0,
            }
        t = _item_total_safe(item)
        # Resolve supplier name for display
        _sup_id   = str(item.supplier_id) if item.supplier_id else None
        _sup_name = None
        if item.supplier_id:
            from app.models.supplier import Supplier as _S
            _sup = db.get(_S, item.supplier_id)
            if _sup:
                _sup_name = _sup.name

        section_map[sid]["items"].append({
            "id":               str(item.id),
            "description":      item.raw_description,
            "unit":             item.unit,
            "planned_quantity": float(item.planned_quantity or 0),
            "planned_rate":     float(item.planned_rate or 0),
            "line_total":       round(t, 2),
            "item_type":        _item_type_str(item),
            "supplier_id":      _sup_id,
            "supplier_name":    _sup_name,
        })
        # Accumulate at full precision; round only in the final output to avoid
        # floating-point drift that causes section totals to diverge from unit_total.
        section_map[sid]["section_total"] += t

    # Round section_totals at output time (not during accumulation) to avoid drift
    for sec in section_map.values():
        sec["section_total"] = round(sec["section_total"], 2)
    # Round section_totals at output time (not during accumulation) to avoid drift
    for sec in section_map.values():
        sec["section_total"] = round(sec["section_total"], 2)
    sections = sorted(section_map.values(), key=lambda s: s["sequence_order"])
    # Use sum of section totals as the canonical unit_total to ensure consistency
    # with what the frontend sees when it sums sections.reduce(s + sec.section_total)
    unit_total = sum(s["section_total"] for s in sections)

    return {
        "site_id":              str(site_id),
        "site_name":            site.name,
        "project_id":           str(site.project_id),
        "unit_total":           round(unit_total, 2),
        "lot_count":            lot_count,
        "site_total":           round(actual_site_total, 2),
        "item_count":           len(site_items),
        "sections":             sections,
        "boq_header_ids":       list(header_ids),
        "derived_from_lots":    derived_from_lots,
        **type_b,
        **var,
    }


def get_site_lot_boqs(db: Session, site_id: uuid.UUID) -> list[dict]:
    """
    Per-lot BOQ totals for a site, sorted numerically by lot_number.
    Includes type breakdown and variance vs the site unit total.
    """
    from app.models.site import Site
    from app.models.lot import Lot

    site = db.get(Site, site_id)
    if not site:
        return []

    lots = (
        db.query(Lot)
        .filter(Lot.site_id == site_id, Lot.project_id == site.project_id)
        .all()
    )
    # Numerical sort: 1,2,3...10,11 instead of 1,10,11,2...
    lots = sorted(lots, key=lambda l: _lot_sort_key(l.lot_number))

    # Site unit total for comparison (try site-level items, fall back to first lot)
    site_items = (
        db.query(BOQItem)
        .filter(BOQItem.site_id == site_id, BOQItem.lot_id.is_(None), BOQItem.is_active == True)
        .all()
    )
    if site_items:
        site_unit_total = sum(_item_total_safe(i) for i in site_items)
    else:
        # Use first lot as baseline
        first = lots[0] if lots else None
        if first:
            fi = db.query(BOQItem).filter(BOQItem.lot_id == first.id, BOQItem.is_active == True).all()
            site_unit_total = sum(_item_total_safe(i) for i in fi)
        else:
            site_unit_total = 0.0

    results = []
    for lot in lots:
        lot_items = (
            db.query(BOQItem)
            .filter(BOQItem.lot_id == lot.id, BOQItem.is_active == True)
            .all()
        )
        lot_total   = sum(_item_total_safe(i) for i in lot_items)
        has_lot_boq = len(lot_items) > 0
        has_custom  = has_lot_boq and abs(lot_total - site_unit_total) > 0.01
        type_b      = _type_breakdown(lot_items)
        var         = _variance(lot_total, site_unit_total) if site_unit_total > 0 else {"variance_amount": 0.0, "variance_pct": 0.0}

        lot_header_ids: set[str] = set()
        for item in lot_items:
            sec = db.get(BOQSection, item.boq_section_id)
            if sec:
                lot_header_ids.add(str(sec.boq_header_id))

        results.append({
            "lot_id":         str(lot.id),
            "lot_number":     lot.lot_number,
            "lot_status":     lot.status.value if hasattr(lot.status, "value") else str(lot.status),
            "lot_total":      round(lot_total, 2),
            "has_lot_boq":    has_lot_boq,
            "has_custom_boq": has_custom,
            "item_count":     len(lot_items),
            "boq_header_ids": list(lot_header_ids),
            **type_b,
            **var,
        })

    return results


def reset_lot_to_site_boq(db: Session, lot_id: uuid.UUID) -> int:
    """
    Soft-delete all lot-specific BOQ items for a lot, then regenerate
    from the site's BOQ header.  Returns count of new items created.
    """
    from app.models.lot import Lot

    lot = db.get(Lot, lot_id)
    if not lot or not lot.site_id:
        return 0

    # Find the BOQHeader that owns site-level items for this site
    section_ids = [
        row[0] for row in (
            db.query(BOQItem.boq_section_id)
            .filter(
                BOQItem.site_id   == lot.site_id,
                BOQItem.lot_id.is_(None),
                BOQItem.is_active == True,
            )
            .distinct()
            .all()
        )
    ]
    if not section_ids:
        return 0

    header_row = (
        db.query(BOQSection.boq_header_id)
        .filter(BOQSection.id.in_(section_ids))
        .first()
    )
    if not header_row:
        return 0
    header_id = header_row[0]

    # Soft-delete existing lot items
    db.query(BOQItem).filter(
        BOQItem.lot_id    == lot_id,
        BOQItem.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.flush()

    return generate_lot_boqs(db, header_id, [lot_id])
