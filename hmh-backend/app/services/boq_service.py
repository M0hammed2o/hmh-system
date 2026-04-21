"""BOQ service — three-level hierarchy: header → section → item."""

import csv
import io
import uuid
from datetime import datetime, timezone
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
    item = BOQItem(
        boq_section_id=section_id,
        project_id=section.header.project_id if section.header else None,
        site_id=data.site_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        item_id=data.item_id,
        supplier_id=data.supplier_id,
        raw_description=data.raw_description,
        specification=data.specification,
        item_type=data.item_type,
        unit=data.unit,
        planned_quantity=data.planned_quantity,
        planned_rate=data.planned_rate,
        sort_order=data.sort_order,
        notes=data.notes,
    )
    # We need the project_id — load header if not already loaded
    if item.project_id is None:
        header = db.get(BOQHeader, section.boq_header_id)
        if header:
            item.project_id = header.project_id
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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
