"""Pydantic v2 schemas for PurchaseOrder."""

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models.enums import RecordStatus, VatMode


class POItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purchase_order_id: uuid.UUID
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    description: str
    quantity_ordered: float
    unit: Optional[str] = None
    rate: Optional[float] = None
    vat_mode: VatMode = VatMode.INCLUSIVE
    vat_rate: float = 15.0
    line_total: Optional[float] = None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def unit_price_excl(self) -> Optional[float]:
        if self.rate is None:
            return None
        r = Decimal(str(self.rate))
        if self.vat_mode == VatMode.INCLUSIVE:
            factor = Decimal("1") + Decimal(str(self.vat_rate)) / Decimal("100")
            return float((r / factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        return float(r)

    @computed_field  # type: ignore[misc]
    @property
    def unit_price_incl(self) -> Optional[float]:
        if self.rate is None:
            return None
        r = Decimal(str(self.rate))
        if self.vat_mode == VatMode.EXCLUSIVE:
            factor = Decimal("1") + Decimal(str(self.vat_rate)) / Decimal("100")
            return float((r * factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        return float(r)

    @computed_field  # type: ignore[misc]
    @property
    def line_vat_amount(self) -> Optional[float]:
        if self.line_total is None or self.rate is None:
            return None
        lt = Decimal(str(self.line_total))
        vr = Decimal(str(self.vat_rate))
        if self.vat_mode == VatMode.INCLUSIVE:
            return float((lt * vr / (Decimal("100") + vr)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return float((lt * vr / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @computed_field  # type: ignore[misc]
    @property
    def line_excl_vat(self) -> Optional[float]:
        if self.line_total is None:
            return None
        vat = self.line_vat_amount or 0.0
        if self.vat_mode == VatMode.INCLUSIVE:
            return float(Decimal(str(self.line_total)) - Decimal(str(vat)))
        return self.line_total


class POItemCreate(BaseModel):
    description: str
    quantity_ordered: float
    unit: Optional[str] = None
    rate: Optional[float] = None
    vat_mode: VatMode = VatMode.INCLUSIVE
    vat_rate: float = 15.0
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None

    @field_validator("description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description cannot be blank")
        return v.strip()


class POItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity_ordered: Optional[float] = None
    unit: Optional[str] = None
    rate: Optional[float] = None
    vat_mode: Optional[VatMode] = None
    vat_rate: Optional[float] = None
    item_id: Optional[uuid.UUID] = None
    boq_item_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    po_number: str
    project_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    supplier_id: uuid.UUID
    material_request_id: Optional[uuid.UUID] = None
    status: RecordStatus
    po_date: datetime
    expected_delivery_date: Optional[date] = None
    subtotal_amount: float
    vat_amount: float
    total_amount: float
    created_by: uuid.UUID
    approved_by: Optional[uuid.UUID] = None
    sent_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    order_items: list[POItemRead] = []


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    site_id: Optional[uuid.UUID] = None
    material_request_id: Optional[uuid.UUID] = None
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    items: list[POItemCreate] = []


class PurchaseOrderUpdate(BaseModel):
    status: Optional[RecordStatus] = None
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    site_id: Optional[uuid.UUID] = None
