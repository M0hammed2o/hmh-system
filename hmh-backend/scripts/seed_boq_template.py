"""
Seed: Standard Residential Unit BOQ template.

Creates or fully updates a reusable BOQ template that appears under
"Apply BOQ Template to Lots" for every active project in the database.

12 sections, 56 items, Grand total R745 180.

Behaviour:
  NEW template  : creates from scratch.
  OLD template  : replaces all template-level items (lot_id IS NULL) with the
                  correct quantities/rates WITHOUT touching lot-specific items
                  (items where lot_id IS NOT NULL).  Lot data is preserved.

Run:
    python scripts/seed_boq_template.py

Safe to run multiple times — always ensures the template matches this spec.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import insert as _sa_insert

from app.db.session import SessionLocal
from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.enums import BoqStatus
from app.models.project import Project

TEMPLATE_NAME = "Standard Residential Unit BOQ"

# ── Exact data from the client-provided Lot 1 BOQ ─────────────────────────────
# Format: (description, unit, quantity, rate, item_type)
# item_type: MATERIAL | LABOUR | PLANT | SERVICE
SECTIONS = [
    # ── 1. Foundations ── R25 570 ──────────────────────────────────────────────
    ("Foundations", 1, [
        ("Bulk excavation",                      "m³",   13,    190.00, "MATERIAL"),
        ("Trench excavation",                    "m³",    8,    200.00, "LABOUR"),
        ("Strip foundation concrete (20MPa)",    "m³",    4.5, 2800.00, "MATERIAL"),
        ("Foundation steel reinforcing",         "kg",  250,     22.00, "MATERIAL"),
        ("Blinding layer (75mm)",                "m²",   40,     85.00, "MATERIAL"),
    ]),

    # ── 2. Concrete & Slab ── R67 740 ─────────────────────────────────────────
    ("Concrete & Slab", 2, [
        ("Ground floor slab concrete (25MPa)",  "m³",  18,  3100.00, "MATERIAL"),
        ("Slab steel mesh reinforcing (193)",   "m²",  90,    65.00, "MATERIAL"),
        ("Damp proof membrane (0.25mm)",        "m²",  95,    12.00, "MATERIAL"),
        ("Concrete slab finishing/screeding",   "m²",  90,    55.00, "LABOUR"),
    ]),

    # ── 3. Brickwork ── R62 315 ────────────────────────────────────────────────
    ("Brickwork", 3, [
        ("Standard stock brick (ext walls 230mm)", "each", 5500,   1.85, "MATERIAL"),
        ("Internal partition brickwork (115mm)",   "m²",     85, 320.00, "MATERIAL"),
        ("Mortar (cement/sand 1:4)",               "m³",    3.2, 1400.00, "MATERIAL"),
        ("Bricklaying labour",                     "m²",    180,   95.00, "LABOUR"),
        ("Lintels (precast 230mm)",                "each",   12,  280.00, "MATERIAL"),
    ]),

    # ── 4. Roofing ── R87 320 ──────────────────────────────────────────────────
    ("Roofing", 4, [
        ("Roof trusses (engineer certified)", "each",  14, 3200.00, "MATERIAL"),
        ("Roof battens (38x38)",             "m",    280,   22.00, "MATERIAL"),
        ("IBR sheeting (0.47mm)",            "m²",   120,  185.00, "MATERIAL"),
        ("Ridge capping",                    "m",      8,   95.00, "MATERIAL"),
        ("Roof fixing / labour",             "m²",   120,   65.00, "LABOUR"),
        ("Fascia board & barge boards",      "m",     32,   85.00, "MATERIAL"),
        ("Gutters & downpipes (PVC)",        "m",     24,  120.00, "MATERIAL"),
    ]),

    # ── 5. Plumbing ── R24 210 ─────────────────────────────────────────────────
    ("Plumbing", 5, [
        ("Water supply piping (HDPE 20mm)",       "m",    45,   48.00, "MATERIAL"),
        ("Sewage piping (uPVC 110mm)",            "m",    30,   95.00, "MATERIAL"),
        ("Sanitary ware (basin/toilet/shower)",   "set",   1, 8500.00, "MATERIAL"),
        ("Geyser (100L electric)",                "each",  1, 4200.00, "MATERIAL"),
        ("Plumbing labour & installation",        "item",  1, 6500.00, "LABOUR"),
    ]),

    # ── 6. Electrical ── R22 550 ───────────────────────────────────────────────
    ("Electrical", 6, [
        ("DB board (12-way)",                 "each",   1, 1800.00, "MATERIAL"),
        ("Wiring (2.5mm twin & earth)",       "m",    120,   28.00, "MATERIAL"),
        ("Light points (complete)",           "each",  12,  350.00, "MATERIAL"),
        ("Power points (complete)",           "each",  18,  380.00, "MATERIAL"),
        ("Electrical installation labour",    "item",   1, 5500.00, "LABOUR"),
        ("COC certification",                 "item",   1,  850.00, "SERVICE"),
    ]),

    # ── 7. Plastering ── R62 800 ───────────────────────────────────────────────
    ("Plastering", 7, [
        ("Internal plaster (12mm 1:4)",       "m²", 280,   85.00, "MATERIAL"),
        ("External roughcast plaster",        "m²", 180,   95.00, "MATERIAL"),
        ("Plastering labour",                 "m²", 460,   45.00, "LABOUR"),
        ("Plaster beads & accessories",       "item",  1, 1200.00, "MATERIAL"),
    ]),

    # ── 8. Painting ── R34 960 ─────────────────────────────────────────────────
    ("Painting", 8, [
        ("Interior PVA paint (2 coats)",      "m²", 280,  42.00, "MATERIAL"),
        ("Exterior paint (weatherproof)",     "m²", 180,  65.00, "MATERIAL"),
        ("Painting labour (int + ext)",       "m²", 460,  25.00, "LABOUR"),
    ]),

    # ── 9. Finishes ── R77 265 ─────────────────────────────────────────────────
    ("Finishes", 9, [
        ("Ceramic floor tiles (400x400)",     "m²",  75,  185.00, "MATERIAL"),
        ("Wall tiles (bathrooms/kitchen)",    "m²",  28,  220.00, "MATERIAL"),
        ("Tiling labour",                     "m²", 103,  120.00, "LABOUR"),
        ("Internal doors (hollow core)",      "each", 6, 1800.00, "MATERIAL"),
        ("External door (solid timber)",      "each", 1, 4500.00, "MATERIAL"),
        ("Windows (aluminium single glazed)", "each", 8, 2800.00, "MATERIAL"),
        ("Door & window installation",        "each", 9,  450.00, "LABOUR"),
        ("Skirting board (pine 68mm)",        "m",   65,   48.00, "MATERIAL"),
    ]),

    # ── 10. Labour ── R241 600 ─────────────────────────────────────────────────
    ("Labour", 10, [
        ("Site foreman (weeks)",              "week",  12, 3500.00, "LABOUR"),
        ("General labourers (man-days)",      "day",  120,  450.00, "LABOUR"),
        ("Concrete gang (days)",              "day",    8, 3200.00, "LABOUR"),
        ("Bricklaying team (days)",           "day",   25, 4800.00, "LABOUR"),
    ]),

    # ── 11. Plant & Equipment ── R31 350 ───────────────────────────────────────
    ("Plant & Equipment", 11, [
        ("Concrete mixer (rental/week)",      "week",  6, 1800.00, "PLANT"),
        ("Scaffolding (rental/week)",         "week",  4, 2200.00, "PLANT"),
        ("Compactor plate (rental/day)",      "day",   5,  650.00, "PLANT"),
        ("Generator (rental/day)",            "day",  10,  850.00, "PLANT"),
    ]),

    # ── 12. Doors & Windows ── R7 500 ─────────────────────────────────────────
    ("Doors & Windows", 12, [
        ("Aluminium windows",  "each", 5, 1500.00, "MATERIAL"),
    ]),
]


def _expected_grand_total() -> float:
    return sum(qty * rate for _, _, items in SECTIONS for _, _, qty, rate, _ in items)


def _verify_totals() -> bool:
    expected = [
        25570, 67740, 62315, 87320, 24210,
        22550, 62800, 34960, 77265, 241600, 31350, 7500,
    ]
    ok = True
    for i, (name, _, items) in enumerate(SECTIONS):
        calc = sum(qty * rate for _, _, qty, rate, _ in items)
        if abs(calc - expected[i]) > 0.01:
            print(f"  [FAIL] Section {i+1} '{name}': R{calc:,.2f} != R{expected[i]:,.2f}")
            ok = False
    return ok


def _apply_to_header(db, header: BOQHeader, project_id, now) -> int:
    """
    Replace all template-level items (lot_id IS NULL) in the header
    with the correct data from SECTIONS.  Sections that don't exist are
    created; extra sections are left untouched (safe for lots using them).
    Returns the count of template-level items written.
    """
    # Build a name-to-section map for existing sections
    existing_sections = {s.section_name: s for s in header.sections}
    item_count = 0

    for section_name, seq_order, items_data in SECTIONS:
        # Get or create the section
        if section_name in existing_sections:
            section = existing_sections[section_name]
            section.sequence_order = seq_order
        else:
            section = BOQSection(
                boq_header_id  = header.id,
                section_name   = section_name,
                sequence_order = seq_order,
                created_at     = now,
                updated_at     = now,
            )
            db.add(section)
            db.flush()

        # Delete only template-level items (lot_id IS NULL) in this section
        # LOT-SPECIFIC items (lot_id IS NOT NULL) are preserved.
        template_items = (
            db.query(BOQItem)
            .filter(
                BOQItem.boq_section_id == section.id,
                BOQItem.lot_id.is_(None),
                BOQItem.site_id.is_(None),
            )
            .all()
        )
        for old_item in template_items:
            db.delete(old_item)
        db.flush()

        # Insert the correct template items
        for sort_idx, (desc, unit, qty, rate, itype) in enumerate(items_data, 1):
            stmt = _sa_insert(BOQItem).values(
                boq_section_id   = section.id,
                project_id       = project_id,
                raw_description  = desc,
                item_type        = itype,
                unit             = unit,
                planned_quantity = qty,
                planned_rate     = rate,
                sort_order       = sort_idx,
                is_active        = True,
                created_at       = now,
                updated_at       = now,
            )
            db.execute(stmt)
            item_count += 1

    # Ensure header is marked as template and active
    header.is_template        = True
    header.is_active_version  = True
    header.template_name      = TEMPLATE_NAME
    header.status             = BoqStatus.ACTIVE
    header.notes = (
        "Standard residential unit BOQ template — 12 sections, 56 items, R745 180. "
        "Apply to any lot using 'Apply BOQ Template to Lots'."
    )
    return item_count


def _process_project(db, project, now) -> str:
    existing = (
        db.query(BOQHeader)
        .filter(
            BOQHeader.project_id == project.id,
            BOQHeader.is_template == True,
            BOQHeader.template_name == TEMPLATE_NAME,
        )
        .first()
    )

    if existing:
        item_count = _apply_to_header(db, existing, project.id, now)
        db.commit()
        return f"UPDATED (id={existing.id})  {item_count} template items rewritten"
    else:
        # Create fresh header
        header = BOQHeader(
            project_id       = project.id,
            version_name     = TEMPLATE_NAME,
            source_type      = "system_template",
            status           = BoqStatus.ACTIVE,
            is_template      = True,
            is_active_version = True,
            template_name    = TEMPLATE_NAME,
            uploaded_at      = now,
            notes=(
                "Standard residential unit BOQ template — 12 sections, 56 items, R745 180. "
                "Apply to any lot using 'Apply BOQ Template to Lots'."
            ),
        )
        db.add(header)
        db.flush()
        item_count = _apply_to_header(db, header, project.id, now)
        db.commit()
        return f"CREATED (id={header.id})  {item_count} items"


def run() -> None:
    print("=" * 65)
    print(f"BOQ Template Seed: '{TEMPLATE_NAME}'")
    print("=" * 65)

    # ── Step 1: verify totals ─────────────────────────────────────────────────
    print("\n[1/3] Verifying totals...")
    if not _verify_totals():
        print("  ABORT — section total mismatch.")
        sys.exit(1)
    grand = _expected_grand_total()
    print(f"  All totals correct. Grand total: R{grand:,.2f}")
    for name, _, items in SECTIONS:
        t = sum(qty * rate for _, _, qty, rate, _ in items)
        n = len(items)
        print(f"    {name:<22} R{t:>10,.2f}  ({n} items)")

    # ── Step 2: apply to all projects ─────────────────────────────────────────
    print("\n[2/3] Applying to all active projects...")
    db = SessionLocal()
    try:
        projects = db.query(Project).filter(Project.status == "ACTIVE").all()
        if not projects:
            projects = db.query(Project).all()
        if not projects:
            print("  WARNING: No projects found. Create a project first.")
            return
        now = datetime.now(timezone.utc)
        for p in projects:
            result = _process_project(db, p, now)
            print(f"  {p.name:<40} {result}")
    finally:
        db.close()

    # ── Step 3: verification read-back ────────────────────────────────────────
    print("\n[3/3] Verification read-back...")
    db = SessionLocal()
    try:
        templates = (
            db.query(BOQHeader)
            .filter(
                BOQHeader.is_template == True,
                BOQHeader.template_name == TEMPLATE_NAME,
            )
            .all()
        )
        all_ok = True
        for t in templates:
            proj = db.get(Project, t.project_id)
            total = 0.0
            for s in t.sections:
                for i in s.items:
                    if i.lot_id is None:
                        total += float(i.planned_quantity or 0) * float(i.planned_rate or 0)
            delta = abs(total - 745180.0)
            status = "OK" if delta < 1.0 else f"WRONG (off by R{delta:,.2f})"
            if delta >= 1.0:
                all_ok = False
            proj_name = proj.name if proj else "?"
            print(f"  {proj_name:<40} R{total:>10,.2f}  [{status}]")
        if all_ok:
            print("\n  All templates match R745,180 exactly.")
        else:
            print("\n  WARNING: Some templates have wrong totals.")
    finally:
        db.close()

    print("\n" + "=" * 65)
    print("DONE")
    print()
    print("Template appears in:")
    print("  - BOQ page > Site view > Generate Lots > BOQ Template dropdown")
    print("  - Projects page > Lots tab > Apply BOQ Template button")
    print("=" * 65)


if __name__ == "__main__":
    run()
