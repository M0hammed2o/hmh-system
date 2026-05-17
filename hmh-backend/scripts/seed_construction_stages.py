"""
Seed construction stages into stage_master.

Run from the hmh-backend directory:
    python scripts/seed_construction_stages.py

The script is fully idempotent using PostgreSQL UPSERT (ON CONFLICT DO UPDATE):
  - If code column exists (production DB, from migration 0001): upsert by code.
  - If code column is absent (dev/test DB created via Base.metadata.create_all):
    upsert by sequence_order instead.
  - Never deletes rows it doesn't own.

Prints: created=X updated=Y skipped=Z
"""

import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import text
from app.db.session import db_session

# ── Stage definitions ─────────────────────────────────────────────────────────
# (code, name, sequence_order, description)
STAGES = [
    ("PLATFORM",      "Platform",        1,  "Site preparation and levelling"),
    ("SLAB",          "Slab",            2,  "Foundation slab / ground floor slab"),
    ("WALLPLATE",     "Wallplate",       3,  "Brickwork up to wallplate height"),
    ("ROOF",          "Roof",            4,  "Roof structure and covering"),
    ("PLUMBING",      "Plumbing",        5,  "Water supply and drainage installation"),
    ("ELECTRICAL",    "Electrical",      6,  "Electrical wiring and fittings"),
    ("PLASTERING",    "Plastering",      7,  "Internal and external plastering"),
    ("PAINT",         "Paint",           8,  "Painting and finishing"),
    ("TILING",        "Tiling",          9,  "Floor and wall tiling"),
    ("DOORS_WINDOWS", "Doors & Windows", 10, "Door and window installation"),
    ("TANK",          "Tank",            11, "Water tank installation"),
    ("APRON",         "Apron",           12, "Concrete apron / perimeter paving"),
    ("SCREED",        "Screed",          13, "Floor screed"),
    ("BEAM_FILLING",  "Beam Filling",    14, "Beam filling between roof trusses"),
    ("COMPLETION",    "Completion",      15, "Final inspection and handover"),
]


def _col_exists(db, table: str, column: str) -> bool:
    row = db.execute(text("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column}).fetchone()
    return row is not None


def _count_before(db) -> int:
    return db.execute(text("SELECT COUNT(*) FROM stage_master")).scalar() or 0


def seed() -> None:
    now = datetime.now(timezone.utc)

    with db_session() as db:
        has_code       = _col_exists(db, "stage_master", "code")
        has_is_active  = _col_exists(db, "stage_master", "is_active")
        has_updated_at = _col_exists(db, "stage_master", "updated_at")
        has_description = _col_exists(db, "stage_master", "description")

        print(f"schema: code={has_code} is_active={has_is_active} "
              f"updated_at={has_updated_at} description={has_description}")

        before = _count_before(db)

        for code, name, seq, desc in STAGES:
            params: dict = {
                "id":   str(uuid.uuid4()),
                "name": name,
                "seq":  seq,
                "now":  now,
            }

            # Build column lists dynamically
            ins_cols = ["id", "name", "sequence_order", "created_at"]
            ins_vals = [":id", ":name", ":seq",          ":now"]
            upd_parts = ["name = EXCLUDED.name"]

            if has_code:
                ins_cols.append("code");    ins_vals.append(":code");    params["code"] = code
                upd_parts.append("code = EXCLUDED.code")
            if has_description:
                ins_cols.append("description"); ins_vals.append(":desc"); params["desc"] = desc
                upd_parts.append("description = EXCLUDED.description")
            if has_is_active:
                ins_cols.append("is_active"); ins_vals.append("true")
                upd_parts.append("is_active = true")
            if has_updated_at:
                ins_cols.append("updated_at"); ins_vals.append(":now")
                upd_parts.append("updated_at = EXCLUDED.updated_at")

            # Conflict target: prefer code (unique) else sequence_order (unique)
            conflict_col = "code" if has_code else "sequence_order"

            sql = (
                f"INSERT INTO stage_master ({', '.join(ins_cols)}) "
                f"VALUES ({', '.join(ins_vals)}) "
                f"ON CONFLICT ({conflict_col}) DO UPDATE SET "
                f"{', '.join(upd_parts)}"
            )
            db.execute(text(sql), params)

        db.commit()
        after = _count_before(db)

    new_rows = after - before
    updated  = len(STAGES) - new_rows
    print(f"stage_master seeded: created={new_rows} updated={updated} skipped=0")


if __name__ == "__main__":
    seed()
