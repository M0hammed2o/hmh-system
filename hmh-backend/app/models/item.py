"""Item catalogue models: ItemCategory, Item, ItemAlias."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import ItemType


class ItemCategory(TimestampMixin, Base):
    __tablename__ = "item_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    items: Mapped[list["Item"]] = relationship("Item", back_populates="category")

    def __repr__(self) -> str:
        return f"<ItemCategory {self.name}>"


class Item(TimestampMixin, Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("item_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    default_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType, name="item_type_enum", create_type=False),
        nullable=False,
        default=ItemType.MATERIAL,
    )
    requires_remaining_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    category: Mapped[Optional["ItemCategory"]] = relationship("ItemCategory", back_populates="items")
    aliases: Mapped[list["ItemAlias"]] = relationship(
        "ItemAlias", back_populates="item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Item {self.name}>"


class ItemAlias(Base):
    __tablename__ = "item_aliases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    from sqlalchemy import DateTime
    from datetime import datetime
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    item: Mapped["Item"] = relationship("Item", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<ItemAlias {self.alias_name} → {self.item_id}>"
