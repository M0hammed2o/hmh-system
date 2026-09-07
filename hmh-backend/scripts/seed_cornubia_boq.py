"""
Cornubia BOQ — captured from the source document 'BOQ CORNUBIA.pdf' (5 pages).

Attaches a single BOQ version, holding the BOQ exactly as it appears in that
PDF, to the EXISTING Cornubia project (code CORNUBIA).

This script never creates a Project row and never edits the project's own
configuration (client, dates, site, status, description). If no CORNUBIA
project exists in the target database it stops with an error rather than
inventing one.

Run from the hmh-backend directory:
    python scripts/seed_hmh_suppliers.py      # canonical supplier names (idempotent)
    python scripts/seed_cornubia_boq.py

Idempotent: re-running replaces the sections/items of this BOQ version in place.
It never touches any other project, BOQ or historical record.

Data-entry rules applied:
  * No rate, price or budget is set — the source PDF contains no commercial data.
  * `unit` is populated ONLY where the PDF states or unambiguously implies it
    (m3 for concrete/sand, 'each' for the enumerated bar counts, 'sheet' for
    mesh). Every other line is a bare number in the source, so `unit` stays NULL
    rather than being invented.
  * Plumbing and Electrical are single high-level items by client instruction —
    the individual plumbing components and electrical components listed in the
    PDF are deliberately NOT itemised.
  * Where the supplier column is blank the supplier of the row above carries
    down, which is how the source spreadsheet is laid out. Every such line says
    so in its notes.
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
from app.models.project import Project
from app.models.supplier import Supplier
from app.models.user import User

PROJECT_CODE = "CORNUBIA"
BOQ_VERSION_NAME = "Cornubia BOQ"   # overridable with --version-name
SOURCE_FILE_NAME = "BOQ CORNUBIA.pdf"

CARRIED_DOWN = "Supplier column blank in source; carried down from the row above."

SHUTTER_NOTE = (
    "All lip channel and angle iron on sundry was for fabrication of shutter "
    "used on Cornubia site for shuttering foundation."
)
RAFT_NOTE = (
    "Supplier's covering note: all the material that goes into 1 single raft "
    "and 1 double raft, to be checked with site to confirm."
)

HEADER_NOTES = (
    "Captured from the source document 'BOQ CORNUBIA.pdf' (5 pages).\n"
    "No rates or prices are recorded — the source document contains none.\n"
    "PLUMBING and ELECTRICAL are held as single high-level items by client "
    "instruction; the individual fittings, pipes, connectors, cables, breakers, "
    "conduits and switches listed in the source are deliberately not itemised.\n"
    + SHUTTER_NOTE
)

# Supplier present in this BOQ but not in scripts/seed_hmh_suppliers.py.
EXTRA_SUPPLIERS = [
    {"name": "Nyathi", "notes": "Suspended slab"},
]

# (section_name, stage_code, section_notes, [ (desc, spec, unit, qty, supplier, item_notes) ])
SECTIONS = [
    ("Platform", "PLATFORM",
     "Heading present in the source BOQ with no line items beneath it.", []),

    ("Slab", "SLAB", None, [
        ("CONCRETE M3", None, "m³", 10.0, "RMC",
         "Source row: 'CONCRETE M3 / RMC INKUNZI'. Confirm whether RMC INKUNZI "
         "is a supplier distinct from RMC."),
        ("UNDERLAY", None, None, 1.0, "Midlands", None),
        ("SCBD", None, None, 1.0, "Steelbar",
         "Source row: 'STEELBAR / SCBD SEE BELOW' — refers to the single/double "
         "raft steel schedule captured in the 'Steel — ...' sections of this BOQ."),
        ("RMC CONCRETE M3", None, "m³", 4.0, "RMC", None),
        ("SUSPENDED SLAB", None, None, 1.0, "Nyathi", None),
        ("SHUTTER BOARD", None, None, 2.0, "Midlands", None),
        ("3\" NAILS", None, None, 5.0, "Midlands", None),
        ("FLAT NAILS", None, None, 5.0, "Midlands", CARRIED_DOWN),
    ]),

    ("Wallplate", "WALLPLATE",
     "The source lists two blocks of wallplate material separated by a blank "
     "row; both are reproduced here in source order and quantities are NOT "
     "summed across them.", [
        ("W/F D/FRAMES", None, None, 1.0, "Yane", None),
        ("BRICKFORCE", None, None, 8.0, "Midlands", None),
        ("DAMPCOURSE", None, None, 1.0, "Midlands", CARRIED_DOWN),
        ("LINTELS 0.9", "0.9 m", None, 1.0, "Killarney",
         "Source spelling: 'LINTELES .9'."),
        ("LINTELS 1.2", "1.2 m", None, 3.0, "Killarney",
         "Source row shows the length 1.2 only; item and supplier carried down "
         "from the 'LINTELES .9' row above."),
        ("LINTELS 1.5", "1.5 m", None, 2.0, "Killarney",
         "Source row shows the length 1.5 only; item and supplier carried down "
         "from the 'LINTELES .9' row above."),
        ("CEMENT", None, None, 9.0, "Alpine", None),
        ("HOOP IRON 0.6", "0.6", None, 10.0, "Buco",
         "Source spelling: 'HOOP IRON .6'."),
        ("HOOP IRON 1M", "1 m", None, 8.0, "Buco", CARRIED_DOWN),
        ("Y10 2M {ON TOP}", "Y10 bar, 2 m", None, 4.0, "Steelbar", None),
        ("M150 7MPA", "M150 7 MPa block", None, 680.0, "Ally Blocks", None),
        ("INCLUDED ON TOP", None, None, None, "Yane",
         "Source row 'YANE / INCLUDED ON TOP' carries no quantity. Recorded "
         "with no quantity rather than inventing one — needs confirmation."),
        ("M150", "M150 block", None, 500.0, "SDS Blocks", None),
        ("M100", "M100 block", None, 318.0, "SDS Blocks", CARRIED_DOWN),
        ("CEMENT", None, None, 14.0, "Alpine",
         "Second cement line in the source Wallplate section; deliberately not "
         "summed with the earlier 9."),
        ("LINTELS 0.9", "0.9 m", None, 1.0, "Killarney",
         "Second lintel block in the source Wallplate section."),
        ("LINTELS 1.2", "1.2 m", None, 2.0, "Killarney",
         "Second lintel block in the source Wallplate section; item and "
         "supplier carried down from the row above."),
        ("LINTELS 1.5", "1.5 m", None, 2.0, "Killarney",
         "Second lintel block in the source Wallplate section; item and "
         "supplier carried down from the row above."),
        ("HOOP IRON 110M 600M", None, None, 15.0, "Buco",
         "Source shows 'BUCO / HOOP IRON' on one row with no quantity and "
         "'110M 600M / 15' on the next; merged into this single line. The "
         "'110M 600M' notation is unclear — needs confirmation."),
        ("BRICKFORCE 100", None, None, 2.0, "Buco",
         "Supplier column blank in source; carried down from the Buco rows above."),
        ("BRICKFORCE", None, None, 5.0, "Midlands", None),
        ("DAMPCOURSE", None, None, 1.0, "Midlands",
         "Source spelling: 'DAMPCORSE'. " + CARRIED_DOWN),
    ]),

    ("Roof", "ROOF", None, [
        ("COMPLETE", None, None, 1.0, "Midlands", None),
        ("TILES", None, None, 341.0, "Afristar", None),
        ("RIDGING", None, None, 12.0, "Afristar", CARRIED_DOWN),
        ("HOOP IRON 1.2", "1.2", None, 12.0, "Buco", None),
    ]),

    ("Completion", "COMPLETION", None, [
        ("CEILING/DOORS", None, None, 1.0, "Midlands", None),
        ("SCREWS 25MM", "25 mm", None, 180.0, "Exodus", None),
        ("SCREWS 32MM", "32 mm", None, 230.0, "Exodus",
         "Source row reads '32MM'; item and supplier carried down from the "
         "'SCREWS25MM' row above."),
        ("SOLID DOORS", None, None, None, None,
         "Source row reads 'SOLID DOORS?' with no supplier and no quantity — "
         "recorded as queried in the source. Needs confirmation."),
    ]),

    ("Plumbing", "PLUMBING",
     "Held as a single high-level item by client instruction. The source PDF "
     "(pages 1-2) lists the individual plumbing components — fittings, pipes, "
     "connectors, traps, taps and sanitaryware — which were deliberately NOT "
     "itemised in this BOQ.", [
        ("Plumbing Works", None, None, 1.0, "Midlands",
         "Source row: 'MIDLANDS / PLUMBING / 1'."),
    ]),

    ("Paint", "PAINT", None, [
        ("WATERPROOF 2.5L", "2.5 L", None, 1.0, "Africote", None),
        ("20L INTERIOR", "20 L", None, 1.636, "Africote", CARRIED_DOWN),
        ("20L EXTERIOR", "20 L", None, 2.55, "Africote", CARRIED_DOWN),
    ]),

    ("Staircase", "COMPLETION",
     "Source BOQ heading 'STAIRCASE'. stage_master has no staircase stage, so "
     "this section is mapped to the Completion stage.", [
        ("STAIRCASE H/RAILS", None, None, 1.0, "Fusion", None),
    ]),

    ("Tank", "TANK", None, [
        ("180L ROOF TANK", "180 L", None, 1.0, "Global", None),
        ("DRIP TRAY", None, None, 1.0, "Global", CARRIED_DOWN),
    ]),

    ("Apron", "APRON", None, [
        ("20MPA FRONT/BK", "20 MPa", None, 1.25, "RMC",
         "Source states no unit for the 1.25 — needs confirmation."),
    ]),

    ("Beam Filling", "BEAM_FILLING",
     "Heading present in the source BOQ with no line items beneath it.", []),

    ("Screed", "SCREED", None, [
        ("Bonding liquid 5l", "5 L", None, 2.0, None,
         "No supplier given in the source."),
        ("Cement", None, None, 1.0, None,
         "No supplier given in the source."),
    ]),

    ("Glazing", "DOORS_&_WINDOWS",
     "Source BOQ heading 'GLAZZING' (source spelling).", [
        ("GLASS", None, None, 1.0, None,
         "No supplier given in the source."),
    ]),

    ("Electrical", "ELECTRICAL",
     "Held as a single high-level item by client instruction. The source PDF "
     "(pages 3-4) lists the individual electrical components — conduits, boxes, "
     "house wire, light fittings, switches, plugs, breakers and certification "
     "items — which were deliberately NOT itemised in this BOQ.", [
        ("Electrical Works", None, None, 1.0, "Diksol",
         "Source row: 'DIKSOL / ELECTRICAL / 1'."),
    ]),

    ("Plaster", "PLASTERING", None, [
        ("CEMENT INSIDE", None, None, 25.0, None,
         "No supplier given in the source."),
        ("CEMENT OUTSIDE", None, None, 1.0, None,
         "No supplier given in the source."),
        ("PLASTER SAND", "2.5 m³", "m³", 2.5, None,
         "Source row: 'M3 PLASTER SAND 2.5' with 1 in the quantity column. "
         "Read as 2.5 m3 of plaster sand; needs confirmation."),
        ("BUILDING SAND", "5 m³", "m³", 5.0, None,
         "Source row: 'M3 BUILDING SAND 5' with 1 in the quantity column. "
         "Read as 5 m3 of building sand; needs confirmation."),
    ]),

    ("Tiling", "TILING", None, [
        ("TILING", None, None, None, "Midlands",
         "Source page 5 in full: 'TILING  MIDLANDS' / 'SOME HOUSES CERTAIN "
         "AREAS'. No quantity, area or scope given — needs confirmation."),
    ]),

    # ── Steel / reinforcement schedule (source PDF page 4) ────────────────────
    ("Steel — Single Raft", "PLATFORM", RAFT_NOTE + " " + SHUTTER_NOTE, [
        ("Y12 x 6350mm", "Y12 high-tensile bar, 6350 mm", "each", 12.0, "Steelbar", None),
        ("Y12 x 4200mm", "Y12 high-tensile bar, 4200 mm", "each", 20.0, "Steelbar", None),
        ("Y08 x 1560mm Stirrup", "Y08 high-tensile bar, 1560 mm, stirrup", "each", 98.0, "Steelbar", None),
        ("Y08 x 1180mm Stools", "Y08 high-tensile bar, 1180 mm, stools", "each", 10.0, "Steelbar", None),
        ("Y10 x 7500mm", "Y10 high-tensile bar, 7500 mm", "each", 4.0, "Steelbar", None),
        ("Y10 x 6350mm", "Y10 high-tensile bar, 6350 mm", "each", 3.0, "Steelbar", None),
    ]),

    ("Steel — Single Raft Stairs", "PLATFORM",
     "Source sub-heading 'Stairs:' under the single raft schedule.", [
        ("Y12 x 2650mm", "Y12 high-tensile bar, 2650 mm", "each", 12.0, "Steelbar", None),
        ("Y10 x 850mm", "Y10 high-tensile bar, 850 mm", "each", 14.0, "Steelbar", None),
        ("Y10 x 1470mm", "Y10 high-tensile bar, 1470 mm", "each", 5.0, "Steelbar", None),
        ("Y10 x 2000mm", "Y10 high-tensile bar, 2000 mm", "each", 24.0, "Steelbar", None),
    ]),

    ("Steel — Single Raft Mesh", "PLATFORM",
     "Source sub-heading 'Mesh:' under the single raft schedule.", [
        ("Mesh Ref 245", "Reference 245 mesh sheet", "sheet", 3.0, "Steelbar", None),
        ("Tying Wire 1.6mm", "1.6 mm tying wire, 50 kg", None, 1.0, "Steelbar",
         "Source: '1xTying Wire 1,6mm,50 Kg' — one 50 kg quantity."),
    ]),

    ("Steel — Double Raft", "PLATFORM", RAFT_NOTE + " " + SHUTTER_NOTE, [
        ("Y12 x 6350mm", "Y12 high-tensile bar, 6350 mm", "each", 16.0, "Steelbar", None),
        ("Y12 x 4500mm", "Y12 high-tensile bar, 4500 mm", "each", 30.0, "Steelbar", None),
        ("Y08 x 1650mm Stirrup", "Y08 high-tensile bar, 1650 mm, stirrup", "each", 135.0, "Steelbar", None),
        ("Y08 x 1180mm Stools", "Y08 high-tensile bar, 1180 mm, stools", "each", 12.0, "Steelbar",
         "Source reads '12xY08x1180 Stools' — 'mm' omitted in the source."),
        ("Y10 x 7500mm", "Y10 high-tensile bar, 7500 mm", "each", 4.0, "Steelbar", None),
        ("Y10 x 6350mm", "Y10 high-tensile bar, 6350 mm", "each", 3.0, "Steelbar", None),
    ]),

    ("Steel — Double Raft Stairs", "PLATFORM",
     "Source sub-heading 'Stairs:' under the double raft schedule.", [
        ("Y12 x 2650mm", "Y12 high-tensile bar, 2650 mm", "each", 12.0, "Steelbar", None),
        ("Y10 x 850mm", "Y10 high-tensile bar, 850 mm", "each", 14.0, "Steelbar", None),
        ("Y10 x 1470mm", "Y10 high-tensile bar, 1470 mm", "each", 5.0, "Steelbar", None),
        ("Y10 x 2000mm", "Y10 high-tensile bar, 2000 mm", "each", 24.0, "Steelbar", None),
    ]),

    ("Steel — Double Raft Mesh", "PLATFORM",
     "Source sub-heading 'Mesh:' under the double raft schedule.", [
        ("Mesh Ref 245", "Reference 245 mesh sheet", "sheet", 3.0, "Steelbar", None),
        ("Tying Wire 1.6mm", "1.6 mm tying wire, 50 kg", None, 1.0, "Steelbar",
         "Source: '1xTying Wire 1,6mm,50 Kg' — one 50 kg quantity."),
    ]),
]



# Supplier names this BOQ references, in first-appearance order.
SUPPLIER_NAMES = []
for _s in SECTIONS:
    for _i in _s[3]:
        if _i[4] and _i[4] not in SUPPLIER_NAMES:
            SUPPLIER_NAMES.append(_i[4])

EXPECTED_SECTIONS = len(SECTIONS)
EXPECTED_ITEMS = sum(len(s[3]) for s in SECTIONS)

DEMO_PROJECT_CODE = "HMH-COR-P1"   # demo data — must receive zero changes


def _db_label() -> str:
    """host:port/dbname of the target database — never the credentials."""
    from urllib.parse import urlsplit

    from app.core.config import settings
    u = urlsplit(settings.DATABASE_URL)
    return f"{u.hostname}:{u.port or 5432}{u.path}"


def _get_or_create_supplier(db, name: str, *, quiet: bool = False) -> uuid.UUID:
    s = db.query(Supplier).filter(Supplier.name == name).first()
    if s:
        return s.id
    now = datetime.now(timezone.utc)
    extra = next((e for e in EXTRA_SUPPLIERS if e["name"] == name), {})
    s = Supplier(name=name, notes=extra.get("notes"), is_active=True,
                 created_at=now, updated_at=now)
    db.add(s)
    db.flush()
    if not quiet:
        print(f"  + supplier created: {name}")
    return s.id


# stage_master is not shaped identically across HMH environments:
#   * the local dev DB and a fresh `alembic upgrade head` DB have a `code` column,
#     and even those disagree ('DOORS_&_WINDOWS' vs 'DOORS_WINDOWS');
#   * the 2026-07-13 production dump has NO `code` column at all — only
#     (id, name, sequence_order, description, created_at).
# So resolve by code where the column exists, and fall back to the stage name.
# Each entry: canonical key -> (acceptable codes, stage name).
STAGE_LOOKUP = {
    "PLATFORM":        (["PLATFORM"],                          "Platform"),
    "SLAB":            (["SLAB"],                              "Slab"),
    "WALLPLATE":       (["WALLPLATE"],                         "Wallplate"),
    "ROOF":            (["ROOF"],                              "Roof"),
    "PLUMBING":        (["PLUMBING"],                          "Plumbing"),
    "ELECTRICAL":      (["ELECTRICAL"],                        "Electrical"),
    "PLASTERING":      (["PLASTERING"],                        "Plastering"),
    "PAINT":           (["PAINT"],                             "Paint"),
    "TILING":          (["TILING"],                            "Tiling"),
    "DOORS_&_WINDOWS": (["DOORS_&_WINDOWS", "DOORS_WINDOWS"],  "Doors & Windows"),
    "TANK":            (["TANK"],                              "Tank"),
    "APRON":           (["APRON"],                             "Apron"),
    "SCREED":          (["SCREED"],                            "Screed"),
    "BEAM_FILLING":    (["BEAM_FILLING"],                      "Beam Filling"),
    "COMPLETION":      (["COMPLETION"],                        "Completion"),
}

_stage_cache: dict = {}


def _stage_has_code_column(db) -> bool:
    return bool(db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='stage_master' AND column_name='code'"
    )).fetchone())


def _stage_id(db, key: str):
    """Resolve a stage id, tolerating both stage_master schema shapes."""
    if key in _stage_cache:
        return _stage_cache[key][0]
    if key not in STAGE_LOOKUP:
        raise RuntimeError(f"no stage mapping defined for {key!r}")
    codes, name = STAGE_LOOKUP[key]

    row = how = None
    if _stage_has_code_column(db):
        for c in codes:
            row = db.execute(text("SELECT id FROM stage_master WHERE code = :c"),
                             {"c": c}).fetchone()
            if row:
                how = f"code={c!r}"
                break
    if row is None:
        row = db.execute(text("SELECT id FROM stage_master WHERE lower(name) = lower(:n)"),
                         {"n": name}).fetchone()
        if row:
            how = f"name={name!r}"
    if row is None:
        available = [r[0] for r in db.execute(text(
            "SELECT name FROM stage_master ORDER BY sequence_order"))]
        raise RuntimeError(
            f"stage_master has no stage matching {key!r} "
            f"(tried codes {codes}, name {name!r}). Available names: {available}"
        )
    _stage_cache[key] = (row[0], how)
    return row[0]


# ── Dry-run support ───────────────────────────────────────────────────────────

def _fingerprint(db) -> dict:
    """
    Row counts and updated_at values used to prove a --dry-run persisted nothing.
    Read before the simulated import and again after the rollback; the two must
    be identical.
    """
    q = lambda s, **p: db.execute(text(s), p).scalar()
    fp = {
        "projects":     q("SELECT count(*) FROM projects"),
        "sites":        q("SELECT count(*) FROM sites"),
        "lots":         q("SELECT count(*) FROM lots"),
        "suppliers":    q("SELECT count(*) FROM suppliers"),
        "boq_headers":  q("SELECT count(*) FROM boq_headers"),
        "boq_sections": q("SELECT count(*) FROM boq_sections"),
        "boq_items":    q("SELECT count(*) FROM boq_items"),
    }
    for code in (PROJECT_CODE, DEMO_PROJECT_CODE):
        pid = q("SELECT id FROM projects WHERE code = :c", c=code)
        key = code.lower().replace("-", "_")
        if pid is None:
            fp[f"{key}__present"] = False
            continue
        fp[f"{key}__present"] = True
        fp[f"{key}__updated_at"] = str(q("SELECT updated_at FROM projects WHERE id=:p", p=pid))
        fp[f"{key}__sites"] = q("SELECT count(*) FROM sites WHERE project_id=:p", p=pid)
        fp[f"{key}__site_updated_max"] = str(
            q("SELECT max(updated_at) FROM sites WHERE project_id=:p", p=pid))
        fp[f"{key}__lots"] = q("SELECT count(*) FROM lots WHERE project_id=:p", p=pid)
        fp[f"{key}__boq_headers"] = q("SELECT count(*) FROM boq_headers WHERE project_id=:p", p=pid)
        fp[f"{key}__boq_items"] = q("SELECT count(*) FROM boq_items WHERE project_id=:p", p=pid)
    return fp


def _similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _survey(db, project) -> dict:
    """Read-only survey of the target database, taken BEFORE any simulated write."""
    q = lambda s, **p: db.execute(text(s), p).scalar()
    pid = project.id

    sites = [dict(r) for r in db.execute(text(
        "SELECT id, name, site_type, updated_at FROM sites WHERE project_id=:p ORDER BY name"
    ), {"p": pid}).mappings()]

    headers = []
    for h in db.execute(text(
        "SELECT id, version_name, status, is_template, source_type, source_file_name, "
        "       is_active_version, uploaded_at "
        "FROM boq_headers WHERE project_id=:p ORDER BY uploaded_at"
    ), {"p": pid}).mappings():
        h = dict(h)
        h["sections"] = q("SELECT count(*) FROM boq_sections WHERE boq_header_id=:h", h=h["id"])
        h["items"] = q("SELECT count(*) FROM boq_items i JOIN boq_sections s "
                       "ON i.boq_section_id=s.id WHERE s.boq_header_id=:h", h=h["id"])
        headers.append(h)

    existing_names = [r[0] for r in db.execute(text("SELECT name FROM suppliers ORDER BY name"))]
    have = [n for n in SUPPLIER_NAMES if n in existing_names]
    missing = [n for n in SUPPLIER_NAMES if n not in existing_names]
    variants = []
    for n in missing:
        for e in existing_names:
            r = _similar(n, e)
            if r >= 0.6 or n.lower() in e.lower() or e.lower() in n.lower():
                variants.append((n, e, round(r, 2)))

    demo_pid = q("SELECT id FROM projects WHERE code=:c", c=DEMO_PROJECT_CODE)

    return {
        "sites": sites,
        "lots": q("SELECT count(*) FROM lots WHERE project_id=:p", p=pid),
        "headers": headers,
        "target_header": next(
            (h for h in headers if h["version_name"] == BOQ_VERSION_NAME), None),
        "pdf_already_imported": [
            h for h in headers if h["source_file_name"] == SOURCE_FILE_NAME],
        "suppliers_existing": have,
        "suppliers_to_create": missing,
        "supplier_variants": variants,
        "demo_project_id": demo_pid,
        "demo_boq_items": (q("SELECT count(*) FROM boq_items WHERE project_id=:p", p=demo_pid)
                           if demo_pid else None),
    }


def _report(project, survey, fp_before, fp_after, applied) -> None:
    line = "─" * 74
    P = print
    P("\n" + "=" * 74)
    P("  CORNUBIA BOQ — DRY RUN (no changes committed)")
    P("=" * 74)
    P(f"Target database : {_db_label()}")

    P(f"\n{line}\n1-2. TARGET PROJECT\n{line}")
    P(f"  uuid        : {project.id}")
    P(f"  name / code : {project.name!r} / {project.code!r}")
    for f in ("client_name", "company_id", "status", "start_date", "estimated_end_date",
              "go_live_date", "budget", "location"):
        P(f"  {f:<12}: {getattr(project, f)}")
    P(f"  description : {(project.description or '')[:100]!r}")

    P(f"\n{line}\n3-4. EXISTING SITES AND LOTS (will not be touched)\n{line}")
    if survey["sites"]:
        for s in survey["sites"]:
            P(f"  site {s['id']}  {s['name']!r}  type={s['site_type']}  updated_at={s['updated_at']}")
    else:
        P("  (no sites on this project)")
    P(f"  lots: {survey['lots']}")

    P(f"\n{line}\n5-7. EXISTING BOQs ON THIS PROJECT\n{line}")
    if survey["headers"]:
        for h in survey["headers"]:
            P(f"  {h['id']}  {h['version_name']!r}")
            P(f"      status={h['status']} template={h['is_template']} "
              f"source={h['source_type']} file={h['source_file_name']!r}")
            P(f"      sections={h['sections']} items={h['items']}")
    else:
        P("  (no BOQ versions on this project)")
    tgt = survey["target_header"]
    P(f"\n  A BOQ version named {BOQ_VERSION_NAME!r} already exists : {bool(tgt)}")
    if tgt:
        P(f"      uuid={tgt['id']} status={tgt['status']} "
          f"sections={tgt['sections']} items={tgt['items']}")
    P(f"  {SOURCE_FILE_NAME!r} already imported : "
      f"{bool(survey['pdf_already_imported'])}"
      + (f" ({len(survey['pdf_already_imported'])} header(s))"
         if survey["pdf_already_imported"] else ""))

    P(f"\n{line}\n8-9. WHAT THE REAL RUN WOULD WRITE\n{line}")
    if tgt:
        P(f"  REPLACE the existing {BOQ_VERSION_NAME!r} version (uuid {tgt['id']}):")
        P(f"    DELETE boq_items    : {tgt['items']}")
        P(f"    DELETE boq_sections : {tgt['sections']}")
        P(f"    UPDATE boq_headers  : 1  (notes + source_file_name only)")
    else:
        P(f"    INSERT boq_headers  : 1")
    P(f"    INSERT boq_sections : {applied['sections']}")
    P(f"    INSERT boq_items    : {applied['items']}")
    P(f"    INSERT suppliers    : {len(survey['suppliers_to_create'])}")
    P(f"    UPDATE projects     : 0")
    P(f"    UPDATE/INSERT sites : 0")
    P(f"    UPDATE/INSERT lots  : 0")
    P(f"  every boq_header.project_id and boq_item.project_id -> {project.id}")
    P(f"  every boq_item.site_id = NULL, lot_id = NULL  (project-level master BOQ)")

    P(f"\n{line}\nSTAGE RESOLUTION (stage_master shape differs between environments)\n{line}")
    P(f"  stage_master has a 'code' column : {applied['stage_has_code']}")
    for key in sorted(_stage_cache):
        sid, how = _stage_cache[key]
        P(f"  {key:<16} -> {sid}  matched on {how}")

    P(f"\n{line}\n10-12. SUPPLIERS\n{line}")
    P(f"  already present ({len(survey['suppliers_existing'])}): "
      f"{', '.join(survey['suppliers_existing']) or '-'}")
    P(f"  would be created ({len(survey['suppliers_to_create'])}): "
      f"{', '.join(survey['suppliers_to_create']) or '-'}")
    if survey["supplier_variants"]:
        P("  POSSIBLE DUPLICATES / VARIANTS — review before the real run:")
        for n, e, r in survey["supplier_variants"]:
            P(f"    would create {n!r}  ~  existing {e!r}   (similarity {r})")
    else:
        P("  no near-duplicate supplier names detected")

    P(f"\n{line}\n13-14. NO-CHANGE GUARANTEES (fingerprint before vs after rollback)\n{line}")
    diffs = {k: (fp_before.get(k), fp_after.get(k))
             for k in set(fp_before) | set(fp_after) if fp_before.get(k) != fp_after.get(k)}
    for k in sorted(fp_before):
        flag = "  DIFFERS" if k in diffs else ""
        P(f"  {k:<34} {str(fp_before[k]):<34}{flag}")
    P("")
    if diffs:
        P(f"  *** DRY RUN LEFT CHANGES BEHIND: {diffs} ***")
    else:
        P("  PASS — every row count and updated_at is identical after rollback.")
        P(f"  PASS — {DEMO_PROJECT_CODE} received zero changes"
          + ("" if survey["demo_project_id"] else " (not present in this database)"))
        P("  PASS — Cornubia project/site configuration received zero changes.")
    P("\n" + "=" * 74)
    P("  DRY RUN COMPLETE — transaction rolled back, nothing persisted.")
    P("=" * 74)


# ── Import ────────────────────────────────────────────────────────────────────

def _apply(db, *, dry_run: bool) -> dict:
    """Perform the import in the given session. Never commits."""
    now = datetime.now(timezone.utc)
    actor = db.query(User).first()
    _stage_cache.clear()
    stage_has_code = _stage_has_code_column(db)

    # ── Project ──────────────────────────────────────────────────────────────
    # This BOQ belongs to the EXISTING Cornubia project. Never create a Project
    # row here: doing so once produced a stray local project that shadowed the
    # real one. Look it up, or stop.
    project = db.query(Project).filter(Project.code == PROJECT_CODE).first()
    if project is None:
        raise RuntimeError(
            f"No project with code {PROJECT_CODE!r} exists in this database "
            f"({_db_label()}). This script attaches the Cornubia BOQ to the "
            f"existing Cornubia project and will not create one. Point "
            f"DATABASE_URL at the environment that holds the real Cornubia "
            f"project and re-run."
        )

    survey = _survey(db, project) if dry_run else None
    if not dry_run:
        print(f"Attaching to existing project {PROJECT_CODE} "
              f"id={project.id} name={project.name!r}")

    # Never modify the project's own configuration.
    project_before = {
        c: getattr(project, c) for c in
        ("name", "code", "description", "location", "client_name", "company_id",
         "start_date", "estimated_end_date", "go_live_date", "status", "budget")
    }

    # ── Suppliers ────────────────────────────────────────────────────────────
    supplier_cache: dict[str, uuid.UUID] = {}
    for name in SUPPLIER_NAMES:
        supplier_cache[name] = _get_or_create_supplier(db, name, quiet=dry_run)
    db.flush()

    # ── BOQ header ───────────────────────────────────────────────────────────
    header = (
        db.query(BOQHeader)
        .filter(BOQHeader.project_id == project.id,
                BOQHeader.version_name == BOQ_VERSION_NAME)
        .first()
    )
    if header:
        if not dry_run:
            print(f"Replacing contents of existing BOQ version id={header.id}")
        db.execute(text(
            "DELETE FROM boq_items WHERE boq_section_id IN "
            "(SELECT id FROM boq_sections WHERE boq_header_id = :hid)"
        ), {"hid": str(header.id)})
        db.execute(text("DELETE FROM boq_sections WHERE boq_header_id = :hid"),
                   {"hid": str(header.id)})
        header.notes = HEADER_NOTES
        header.source_file_name = SOURCE_FILE_NAME
        header.is_active_version = True
        db.flush()
    else:
        header = BOQHeader(
            id=uuid.uuid4(),
            project_id=project.id,
            version_name=BOQ_VERSION_NAME,
            source_file_name=SOURCE_FILE_NAME,
            source_type="manual",
            status=BoqStatus.DRAFT,
            is_active_version=True,
            is_template=False,
            uploaded_by=actor.id if actor else None,
            uploaded_at=now,
            notes=HEADER_NOTES,
        )
        db.add(header)
        db.flush()
        if not dry_run:
            print(f"Created BOQ version id={header.id}")

    # ── Sections and items ───────────────────────────────────────────────────
    total_items = 0
    for seq, (section_name, stage_code, section_notes, items) in enumerate(SECTIONS, 1):
        stage_id = _stage_id(db, stage_code)
        section = BOQSection(
            id=uuid.uuid4(),
            boq_header_id=header.id,
            section_name=section_name,
            sequence_order=seq,
            stage_id=stage_id,
            notes=section_notes,
            created_at=now,
            updated_at=now,
        )
        db.add(section)
        db.flush()

        for sort_idx, (desc, spec, unit, qty, sup_name, item_notes) in enumerate(items, 1):
            db.execute(_sa_insert(BOQItem).values(
                id=uuid.uuid4(),
                boq_section_id=section.id,
                project_id=project.id,
                site_id=None,     # project-level master BOQ — site/lot association
                lot_id=None,      # happens downstream via copy_boq/generate_lot_boqs
                stage_id=stage_id,
                supplier_id=supplier_cache.get(sup_name) if sup_name else None,
                raw_description=desc,
                specification=spec,
                item_type="MATERIAL",
                unit=unit,
                planned_quantity=qty,
                planned_rate=None,
                sort_order=sort_idx,
                is_active=True,
                notes=item_notes,
                created_at=now,
                updated_at=now,
            ))
            total_items += 1
    db.flush()

    # The project's own configuration must be exactly as we found it.
    changed = {k: (v, getattr(project, k))
               for k, v in project_before.items() if getattr(project, k) != v}
    if changed:
        raise RuntimeError(
            f"Refusing to proceed: this run would have altered the Cornubia "
            f"project's configuration: {changed}"
        )

    return {"project": project, "header": header, "survey": survey,
            "sections": len(SECTIONS), "items": total_items,
            "stage_has_code": stage_has_code}


def seed(dry_run: bool = False) -> None:
    if not dry_run:
        with db_session() as db:
            r = _apply(db, dry_run=False)
            db.commit()
            print(f"Done. {r['sections']} sections, {r['items']} items.")
            print(f"Project: {r['project'].name} ({PROJECT_CODE}) "
                  f"id={r['project'].id} (pre-existing, unmodified)")
            print(f"BOQ:     {BOQ_VERSION_NAME} id={r['header'].id}")
        return

    # ── Dry run ──────────────────────────────────────────────────────────────
    # The session is bound to a connection whose transaction we own and roll
    # back unconditionally, so nothing can reach disk even on an early error.
    from sqlalchemy.orm import Session

    from app.db.session import engine

    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn)
    try:
        fp_before = _fingerprint(db)
        r = _apply(db, dry_run=True)
        project, survey = r["project"], r["survey"]
        # Detach values we still need once the session is closed.
        project_view = type("P", (), {c: getattr(project, c) for c in (
            "id", "name", "code", "client_name", "company_id", "status", "start_date",
            "estimated_end_date", "go_live_date", "budget", "location", "description")})
    finally:
        db.close()
        outer.rollback()
        conn.close()

    # Fresh connection AFTER the rollback — proves nothing persisted.
    verify = Session(bind=engine)
    try:
        fp_after = _fingerprint(verify)
    finally:
        verify.close()

    _report(project_view, survey, fp_before, fp_after, r)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Import the Cornubia BOQ into the "
                                             "existing Cornubia project.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Inspect the target database and report exactly what "
                         "would change. Rolls back; commits nothing.")
    ap.add_argument("--version-name", default=BOQ_VERSION_NAME,
                    help="BOQ version to create or replace on the Cornubia "
                         f"project (default: {BOQ_VERSION_NAME!r}). Point this at "
                         "an existing version to replace its contents in place "
                         "instead of adding a second version.")
    args = ap.parse_args()
    BOQ_VERSION_NAME = args.version_name
    seed(dry_run=args.dry_run)
