"""
Seed script: populates stage_master with the locked V1 stage list.

Run from the hmh-backend directory:
    python scripts/seed_stages.py

Requires .env to be present and DATABASE_URL to be set.
The script is idempotent — re-running it is safe.
"""

import sys
import os

# Ensure the hmh-backend directory is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from app.db.session import db_session
from app.models.stage import StageMaster

# ── Locked V1 stage list ──────────────────────────────────────────────────────
# These are the only stages used in V1.
# sequence_order determines the display/workflow order.
STAGES = [
    {"name": "Platform",     "sequence_order": 1},
    {"name": "Slab",         "sequence_order": 2},
    {"name": "Wallplate",    "sequence_order": 3},
    {"name": "Roof",         "sequence_order": 4},
    {"name": "Completion",   "sequence_order": 5},
    {"name": "Plumbing",     "sequence_order": 6},
    {"name": "Paint",        "sequence_order": 7},
    {"name": "Tank",         "sequence_order": 8},
    {"name": "Apron",        "sequence_order": 9},
    {"name": "Screed",       "sequence_order": 10},
    {"name": "Beam Filling", "sequence_order": 11},
]


def seed() -> None:
    with db_session() as db:
        inserted = 0
        skipped = 0

        for stage_data in STAGES:
            existing = (
                db.query(StageMaster)
                .filter(StageMaster.name == stage_data["name"])
                .first()
            )
            if existing:
                skipped += 1
                continue

            db.add(
                StageMaster(
                    name=stage_data["name"],
                    sequence_order=stage_data["sequence_order"],
                    created_at=datetime.now(tz=timezone.utc),
                )
            )
            inserted += 1

        print(f"stage_master: {inserted} inserted, {skipped} already existed.")


if __name__ == "__main__":
    seed()
