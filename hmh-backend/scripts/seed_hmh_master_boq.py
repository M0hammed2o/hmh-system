"""
HMH Master BOQ Template — professional residential unit BOQ.

Run from the hmh-backend directory:
    python scripts/seed_hmh_master_boq.py

Idempotent: if a template named 'HMH Master Residential Unit BOQ' already
exists for the first project, updates its items in place.

Suppliers referenced in the BOQ are auto-created if not found.
Stages are matched to the stage_master table by code (seeds if missing).
"""

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import insert as _sa_insert, text
from app.db.session import db_session
from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.enums import BoqStatus
from app.models.supplier import Supplier

TEMPLATE_NAME = "HMH Master Residential Unit BOQ"

# ── Supplier lookup / creation ───────────────────────────────────────────────

def _get_or_create_supplier(db, name: str) -> uuid.UUID | None:
    if not name or name.lower() == "to confirm":
        return None
    s = db.query(Supplier).filter(Supplier.name == name).first()
    if s:
        return s.id
    now = datetime.now(timezone.utc)
    new_s = Supplier(name=name, is_active=True, created_at=now, updated_at=now)
    db.add(new_s)
    db.flush()
    return new_s.id


# ── Stage lookup ─────────────────────────────────────────────────────────────

def _stage_id(db, code: str) -> uuid.UUID | None:
    row = db.execute(
        text("SELECT id FROM stage_master WHERE code = :c"), {"c": code}
    ).fetchone()
    return row[0] if row else None


# ── BOQ data ──────────────────────────────────────────────────────────────────
# Format: (section_name, stage_code, [(description, unit, qty, supplier_name)])

SECTIONS = [
    ("Platform / Slab", "PLATFORM", [
        ("RMC Concrete",             "M3",   10.0,    "RMC"),
        ("Midlands Underlay",        "lot",   1.0,    "Midlands"),
        ("Steelbar SCBD",            "lot",   1.0,    "Steelbar"),
        ("Shutter Board",            "sheets",2.0,    "Midlands"),
        ("3 inch Nails",             "kg",    5.0,    "Midlands"),
        ("Flat Nails",               "kg",    5.0,    "Midlands"),
    ]),
    ("Wallplate", "WALLPLATE", [
        ("W/F D/Frames",             "lot",   1.0,    "Yane"),
        ("Brickforce",               "rolls", 8.0,    "Midlands"),
        ("Dampcourse",               "rolls", 1.0,    "Midlands"),
        ("Lintels 0.9m",             "each",  1.0,    "Killarney"),
        ("Cement",                   "bags",  23.0,   "Alpine"),
        ("Hoop Iron 0.6",            "rolls", 10.0,   "Buco"),
        ("Hoop Iron 1m",             "rolls", 8.0,    "Buco"),
        ("Y10 2m Top",               "bars",  4.0,    "Steelbar"),
        ("M150 7MPA Blocks",         "each",  680.0,  "Ally Blocks"),
        ("M150 Blocks",              "each",  500.0,  "SDS Blocks"),
        ("M100 Blocks",              "each",  318.0,  "SDS Blocks"),
        ("110m 600mm",               "m",     15.0,   "Buco"),
        ("Brickforce 100",           "rolls", 2.0,    "Midlands"),
        ("Brickforce",               "rolls", 5.0,    "Midlands"),
    ]),
    ("Roof", "ROOF", [
        ("Roof Complete",            "lot",   1.0,    "Midlands"),
        ("Tiles",                    "each",  341.0,  "Afristar"),
        ("Ridging",                  "m",     12.0,   "Afristar"),
        ("Hoop Iron 1.2",            "rolls", 12.0,   "Buco"),
    ]),
    ("Completion", "COMPLETION", [
        ("Ceiling / Doors",          "lot",   1.0,    "Midlands"),
        ("Screws 25mm",              "box",   180.0,  "Exodus"),
        ("Screws 32mm",              "box",   230.0,  "Exodus"),
        ("Solid Doors",              "lot",   1.0,    None),
    ]),
    ("Plumbing", "PLUMBING", [
        ("Plumbing",                 "lot",   1.0,    "Midlands"),
    ]),
    ("Paint", "PAINT", [
        ("Waterproof 2.5L",          "tin",   1.0,    "Africote"),
        ("20L Interior Paint",       "drum",  1.636,  "Africote"),
        ("20L Exterior Paint",       "drum",  2.55,   "Africote"),
    ]),
    ("Staircase", "COMPLETION", [
        ("Staircase Handrails",      "lot",   1.0,    "Fusion"),
    ]),
    ("Tank", "TANK", [
        ("180L Roof Tank",           "each",  1.0,    "Global"),
        ("Drip Tray",                "each",  1.0,    "Global"),
    ]),
    ("Apron", "APRON", [
        ("20MPA Front/Back Concrete","M3",    1.25,   "RMC"),
        ("Ref 100 600x2.4",          "each",  12.0,   None),
        ("Softboard 10mm x 1220x2440","sheet",0.5,    None),
        ("Crusher",                  "M3",    2.0,    None),
        ("Cement",                   "bags",  1.0,    None),
        ("20MPA Concrete",           "M3",    2.25,   "RMC"),
    ]),
    ("Beam Filling", "BEAM_FILLING", [
        ("Cement",                   "bags",  2.0,    None),
        ("Carbolineum 5L",           "tin",   1.7,    None),
        ("Blocks",                   "each",  35.0,   None),
    ]),
    ("Screed", "SCREED", [
        ("Bonding Liquid 5L",        "tin",   2.0,    None),
        ("Cement",                   "bags",  1.0,    None),
    ]),
    ("Glazing", "DOORS_WINDOWS", [
        ("Glass",                    "lot",   1.0,    None),
        ("Ref W/Frame",              "lot",   1.0,    None),
    ]),
    ("Electrical", "ELECTRICAL", [
        ("Electrical",               "lot",   1.0,    "Diksol"),
    ]),
    ("Plaster", "PLASTERING", [
        ("Cement Inside",            "bags",  25.0,   None),
        ("Cement Outside",           "bags",  1.0,    None),
        ("M3 Plaster Sand 2.5",      "M3",    1.0,    None),
        ("M3 Building Sand 5",       "M3",    1.0,    None),
    ]),
]


# ── Seed function ─────────────────────────────────────────────────────────────

def seed() -> None:
    with db_session() as db:
        now = datetime.now(timezone.utc)

        # Use first project or create a placeholder header (templates are project-scoped)
        from app.models.project import Project
        from app.models.user import User
        project = db.query(Project).order_by(Project.created_at).first()
        if not project:
            print("No projects found. Create a project first, then re-run this script.")
            return

        actor = db.query(User).first()

        # Pre-cache supplier IDs
        supplier_cache: dict[str, uuid.UUID | None] = {}
        for _, _, items in SECTIONS:
            for _, _, _, sup_name in items:
                if sup_name and sup_name not in supplier_cache:
                    supplier_cache[sup_name] = _get_or_create_supplier(db, sup_name)
        db.flush()

        # Find or create template header
        header = (
            db.query(BOQHeader)
            .filter(
                BOQHeader.project_id == project.id,
                BOQHeader.is_template == True,
                BOQHeader.template_name == TEMPLATE_NAME,
            )
            .first()
        )
        if header:
            print(f"Updating existing template id={header.id}")
            # Wipe existing items and sections cleanly
            from sqlalchemy import text as _t
            db.execute(_t("DELETE FROM boq_items WHERE boq_section_id IN "
                          "(SELECT id FROM boq_sections WHERE boq_header_id = :hid)"),
                       {"hid": str(header.id)})
            db.execute(_t("DELETE FROM boq_sections WHERE boq_header_id = :hid"),
                       {"hid": str(header.id)})
            db.flush()
        else:
            header = BOQHeader(
                id=uuid.uuid4(),
                project_id=project.id,
                version_name=TEMPLATE_NAME,
                source_type="master_template",
                status=BoqStatus.ACTIVE,
                is_active_version=True,
                is_template=True,
                template_name=TEMPLATE_NAME,
                uploaded_by=actor.id if actor else None,
                uploaded_at=now,
                notes="HMH professional master residential unit BOQ.",
            )
            db.add(header)
            db.flush()
            print(f"Created new template id={header.id}")

        # Insert sections and items
        total_items = 0
        for seq, (section_name, stage_code, items) in enumerate(SECTIONS, 1):
            stage_id = _stage_id(db, stage_code)

            section = BOQSection(
                id=uuid.uuid4(),
                boq_header_id=header.id,
                section_name=section_name,
                sequence_order=seq,
                stage_id=stage_id,
                created_at=now,
                updated_at=now,
            )
            db.add(section)
            db.flush()

            for sort_idx, (desc, unit, qty, sup_name) in enumerate(items, 1):
                supplier_id = supplier_cache.get(sup_name) if sup_name else None
                db.execute(_sa_insert(BOQItem).values(
                    id=uuid.uuid4(),
                    boq_section_id=section.id,
                    project_id=project.id,
                    stage_id=stage_id,
                    supplier_id=supplier_id,
                    raw_description=desc,
                    item_type="MATERIAL",
                    unit=unit,
                    planned_quantity=qty,
                    sort_order=sort_idx,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                ))
                total_items += 1

        db.commit()
        print(f"Done. {len(SECTIONS)} sections, {total_items} items seeded.")
        print(f"Template: {TEMPLATE_NAME}")
        print(f"Project:  {project.name} ({project.id})")


if __name__ == "__main__":
    seed()
