"""Pydantic v2 schemas for User and access control."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models.enums import UserRole


# ── Read schemas (returned by API) ────────────────────────────────────────────

class UserRead(BaseModel):
    """Safe user representation — never includes password_hash."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool
    must_reset_password: bool
    last_login_at: Optional[datetime] = None
    failed_login_attempts: int
    locked_until: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class UserSummary(BaseModel):
    """Minimal user info for embedded references."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole


# ── Write schemas (accepted by API) ──────────────────────────────────────────

class UserCreate(BaseModel):
    """Body for POST /users — OWNER only."""
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("full_name cannot be blank")
        return v.strip()


class UserUpdate(BaseModel):
    """Body for PATCH /users/:id — OWNER only."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserCreatedResponse(UserRead):
    """Returned after POST /users — includes one-time temp password."""
    temp_password: str


# ── Access control schemas ────────────────────────────────────────────────────

class ProjectAccessGrant(BaseModel):
    project_id: uuid.UUID
    can_view: bool = True
    can_edit: bool = False
    can_approve: bool = False


class SiteAccessGrant(BaseModel):
    site_id: uuid.UUID
    can_receive_delivery: bool = False
    can_record_usage: bool = False
    can_request_stock: bool = False
    can_update_stage: bool = False


# ── Auth schemas ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int        # seconds
    must_reset_password: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("new_password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("new_password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("new_password must contain at least one digit")
        return v


# ── Access read schemas ───────────────────────────────────────────────────────

class UserProjectAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    can_view: bool
    can_edit: bool
    can_approve: bool
    created_at: datetime


class UserSiteAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    site_id: uuid.UUID
    can_receive_delivery: bool
    can_record_usage: bool
    can_request_stock: bool
    can_update_stage: bool
    created_at: datetime
