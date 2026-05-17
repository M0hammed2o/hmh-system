"""
Seed the items catalog from BOQ template descriptions.

For every BOQItem that has no item_id, create a matching Item in the catalog
(if one with the same normalized name does not already exist), then link it back
to the BOQItem.  This allows deliveries to update stock for items that were
received against a BOQ that had no catalog link.

Run:
    python scripts/seed_catalog_from_boq.py

Idempotent: safe to run multiple times.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import db_session
from app.models.boq import BOQItem
from app.models.item import Item, ItemCategory
from app.models.enums import ItemType


# Map BOQ item_type → catalog ItemType
_ITYPE = {
    "MATERIAL": ItemType.MATERIAL,
    "LABOUR":   ItemType.LABOUR,
    "PLANT":    ItemType.PLANT,
    "SERVICE":  ItemType.SERVICE,
    "PACKAGE":  ItemType.PACKAGE,
}


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


def seed(db: Session) -> None:
    # Ensure a default category exists
    cat = db.query(ItemCategory).filter(ItemCategory.name == "General").first()
    if not cat:
        cat = ItemCategory(name="General", description="Auto-seeded from BOQ")
        db.add(cat)
        db.flush()

    # Find all BOQ items without a catalog link
    unlinked = (
        db.query(BOQItem)
        .filter(BOQItem.item_id.is_(None), BOQItem.is_active == True)
        .all()
    )

    print(f"Found {len(unlinked)} unlinked BOQ items.", flush=True)

    created = 0
    linked  = 0
    skipped = 0

    for bi in unlinked:
        desc = (bi.raw_description or "").strip()
        if not desc:
            skipped += 1
            continue

        norm = _normalize(desc)
        itype_str = bi.item_type.value if hasattr(bi.item_type, "value") else str(bi.item_type)
        itype = _ITYPE.get(itype_str.upper(), ItemType.MATERIAL)

        # Find existing catalog item with same normalized name
        item = db.query(Item).filter(Item.normalized_name == norm).first()

        if not item:
            item = Item(
                name=desc,
                normalized_name=norm,
                category_id=cat.id,
                item_type=itype,
                default_unit=bi.unit,
                is_active=True,
                requires_remaining_photo=False,
                is_high_risk=False,
            )
            db.add(item)
            db.flush()
            created += 1
            print(f"  CREATED item: {desc!r} ({itype_str})", flush=True)
        else:
            skipped += 1

        # Link the BOQ item to the catalog item
        bi.item_id = item.id
        linked += 1

    db.commit()
    print(f"\nDone. created={created} linked={linked} skipped={skipped}", flush=True)


if __name__ == "__main__":
    with db_session() as db:
        seed(db)
