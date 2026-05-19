"""
Seed HMH Group supplier list.

Creates all suppliers referenced in the HMH Master BOQ template.
Safe to run multiple times — skips suppliers that already exist (matched by name).

Run from the hmh-backend directory:
    python scripts/seed_hmh_suppliers.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from app.db.session import db_session
from app.models.supplier import Supplier

# HMH supplier list from the Master BOQ template
SUPPLIERS = [
    {"name": "RMC",         "notes": "Ready-mix concrete supplier"},
    {"name": "Midlands",    "notes": "General building materials"},
    {"name": "Steelbar",    "notes": "Steel reinforcement supplier"},
    {"name": "Yane",        "notes": "Frames and carpentry"},
    {"name": "Killarney",   "notes": "Lintels and concrete products"},
    {"name": "Alpine",      "notes": "Cement and aggregate"},
    {"name": "Buco",        "notes": "Building hardware and hoop iron"},
    {"name": "Ally Blocks", "notes": "Masonry blocks"},
    {"name": "SDS Blocks",  "notes": "Masonry blocks"},
    {"name": "Afristar",    "notes": "Roofing tiles and ridging"},
    {"name": "Exodus",      "notes": "Screws and fasteners"},
    {"name": "Africote",    "notes": "Paint and waterproofing"},
    {"name": "Fusion",      "notes": "Staircases and handrails"},
    {"name": "Global",      "notes": "Tanks and water storage"},
    {"name": "Diksol",      "notes": "Electrical installations"},
]


def seed() -> None:
    now = datetime.now(timezone.utc)
    created = skipped = 0

    with db_session() as db:
        for sup_data in SUPPLIERS:
            existing = db.query(Supplier).filter(
                Supplier.name == sup_data["name"]
            ).first()

            if existing:
                skipped += 1
                continue

            db.add(Supplier(
                name=sup_data["name"],
                notes=sup_data.get("notes"),
                is_active=True,
                created_at=now,
                updated_at=now,
            ))
            created += 1

        db.commit()

    print(f"HMH suppliers: created={created} skipped={skipped}")


if __name__ == "__main__":
    seed()
