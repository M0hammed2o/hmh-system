"""Item catalogue service."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.item import Item, ItemCategory
from app.schemas.item import ItemCreate, ItemUpdate


def list_items(db: Session, include_inactive: bool = False) -> list[Item]:
    q = db.query(Item)
    if not include_inactive:
        q = q.filter(Item.is_active == True)  # noqa: E712
    return q.order_by(Item.name).all()


def get_item(db: Session, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise NotFoundError(f"Item {item_id} not found.")
    return item


def create_item(db: Session, data: ItemCreate) -> Item:
    normalized = data.name.strip().lower()
    existing = db.query(Item).filter(Item.normalized_name == normalized).first()
    if existing:
        raise ConflictError(f"Item '{data.name.strip()}' already exists.")

    item = Item(
        name=data.name.strip(),
        normalized_name=normalized,
        category_id=data.category_id,
        default_unit=data.default_unit,
        item_type=data.item_type,
        requires_remaining_photo=data.requires_remaining_photo,
        is_high_risk=data.is_high_risk,
        notes=data.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: uuid.UUID, data: ItemUpdate) -> Item:
    item = get_item(db, item_id)
    fields = data.model_fields_set

    if "name" in fields and data.name is not None:
        normalized = data.name.strip().lower()
        dup = (
            db.query(Item)
            .filter(Item.normalized_name == normalized)
            .filter(Item.id != item_id)
            .first()
        )
        if dup:
            raise ConflictError(f"Item '{data.name.strip()}' already exists.")
        item.name = data.name.strip()
        item.normalized_name = normalized
    if "category_id" in fields:
        item.category_id = data.category_id
    if "default_unit" in fields:
        item.default_unit = data.default_unit
    if "item_type" in fields and data.item_type is not None:
        item.item_type = data.item_type
    if "requires_remaining_photo" in fields and data.requires_remaining_photo is not None:
        item.requires_remaining_photo = data.requires_remaining_photo
    if "is_high_risk" in fields and data.is_high_risk is not None:
        item.is_high_risk = data.is_high_risk
    if "is_active" in fields and data.is_active is not None:
        item.is_active = data.is_active
    if "notes" in fields:
        item.notes = data.notes

    db.commit()
    db.refresh(item)
    return item


def list_categories(db: Session) -> list[ItemCategory]:
    return db.query(ItemCategory).filter(ItemCategory.is_active == True).order_by(ItemCategory.name).all()  # noqa: E712
