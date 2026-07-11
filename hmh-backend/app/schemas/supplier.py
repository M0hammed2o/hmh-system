"""Pydantic v2 schemas for Supplier."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    whatsapp_number: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_due_days: Optional[int] = None
    notes: Optional[str] = None
    customer_account_code: Optional[str] = None
    is_active: bool
    vat_registered: bool = False
    pricing_method: str = "EX_VAT"
    default_vat_rate: float = 15.0
    created_at: datetime
    updated_at: datetime


class SupplierCreate(BaseModel):
    name: str
    code: Optional[str] = None
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    whatsapp_number: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_due_days: Optional[int] = None
    notes: Optional[str] = None
    customer_account_code: Optional[str] = None
    # Defaults to False so quick-create forms don't require a VAT number.
    # VAT configuration is done via the supplier profile page.
    vat_registered: bool = False
    pricing_method: str = "EX_VAT"
    default_vat_rate: float = 15.0

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("email is required")
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("email must be a valid email address")
        return v.lower()

    @model_validator(mode="after")
    def vat_number_required_when_registered(self) -> "SupplierCreate":
        if self.vat_registered and not (self.vat_number or "").strip():
            raise ValueError(
                "vat_number is required when vat_registered is true"
            )
        return self


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    whatsapp_number: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_due_days: Optional[int] = None
    notes: Optional[str] = None
    customer_account_code: Optional[str] = None
    is_active: Optional[bool] = None
    vat_registered: Optional[bool] = None
    pricing_method: Optional[str] = None
    default_vat_rate: Optional[float] = None

    @model_validator(mode="after")
    def vat_number_required_when_registered(self) -> "SupplierUpdate":
        fields = self.model_fields_set
        # Only fire when both fields are being set in the same request
        if "vat_registered" in fields and "vat_number" in fields:
            if self.vat_registered and not (self.vat_number or "").strip():
                raise ValueError(
                    "vat_number is required when vat_registered is true"
                )
        return self
