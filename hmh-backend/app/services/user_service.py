"""User management service — CRUD and access control."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_temp_password, hash_password
from app.models.access import UserProjectAccess, UserSiteAccess
from app.models.user import User
from app.schemas.user import ProjectAccessGrant, SiteAccessGrant, UserCreate, UserUpdate

_MAX_PAGE_SIZE = 100


def create_user(db: Session, data: UserCreate, created_by_id: uuid.UUID) -> tuple[User, str]:
    if db.query(User).filter(User.email == data.email).first():
        raise ConflictError(f"A user with email '{data.email}' already exists.")

    temp_pwd = generate_temp_password()
    user = User(
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        password_hash=hash_password(temp_pwd),
        is_active=True,
        must_reset_password=True,
        created_by=created_by_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, temp_pwd


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found.")
    return user


def list_users(db: Session, page: int, limit: int) -> tuple[list[User], int]:
    limit = min(limit, _MAX_PAGE_SIZE)
    offset = (page - 1) * limit
    total = db.query(User).count()
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return users, total


def update_user(db: Session, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = get_user(db, user_id)
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.phone is not None:
        user.phone = data.phone
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, user_id: uuid.UUID) -> tuple[User, str]:
    user = get_user(db, user_id)
    temp_pwd = generate_temp_password()
    user.password_hash = hash_password(temp_pwd)
    user.must_reset_password = True
    db.commit()
    db.refresh(user)
    return user, temp_pwd


def deactivate_user(db: Session, user_id: uuid.UUID) -> User:
    user = get_user(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def grant_project_access(
    db: Session, user_id: uuid.UUID, data: ProjectAccessGrant
) -> UserProjectAccess:
    get_user(db, user_id)
    existing = (
        db.query(UserProjectAccess)
        .filter(
            UserProjectAccess.user_id == user_id,
            UserProjectAccess.project_id == data.project_id,
        )
        .first()
    )
    if existing:
        existing.can_view = data.can_view
        existing.can_edit = data.can_edit
        existing.can_approve = data.can_approve
        db.commit()
        db.refresh(existing)
        return existing

    access = UserProjectAccess(
        user_id=user_id,
        project_id=data.project_id,
        can_view=data.can_view,
        can_edit=data.can_edit,
        can_approve=data.can_approve,
    )
    db.add(access)
    db.commit()
    db.refresh(access)
    return access


def revoke_project_access(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    access = (
        db.query(UserProjectAccess)
        .filter(
            UserProjectAccess.user_id == user_id,
            UserProjectAccess.project_id == project_id,
        )
        .first()
    )
    if not access:
        raise NotFoundError("Project access record not found.")
    db.delete(access)
    db.commit()


def grant_site_access(
    db: Session, user_id: uuid.UUID, data: SiteAccessGrant
) -> UserSiteAccess:
    get_user(db, user_id)
    existing = (
        db.query(UserSiteAccess)
        .filter(
            UserSiteAccess.user_id == user_id,
            UserSiteAccess.site_id == data.site_id,
        )
        .first()
    )
    if existing:
        existing.can_receive_delivery = data.can_receive_delivery
        existing.can_record_usage = data.can_record_usage
        existing.can_request_stock = data.can_request_stock
        existing.can_update_stage = data.can_update_stage
        db.commit()
        db.refresh(existing)
        return existing

    access = UserSiteAccess(
        user_id=user_id,
        site_id=data.site_id,
        can_receive_delivery=data.can_receive_delivery,
        can_record_usage=data.can_record_usage,
        can_request_stock=data.can_request_stock,
        can_update_stage=data.can_update_stage,
    )
    db.add(access)
    db.commit()
    db.refresh(access)
    return access


def revoke_site_access(
    db: Session, user_id: uuid.UUID, site_id: uuid.UUID
) -> None:
    access = (
        db.query(UserSiteAccess)
        .filter(
            UserSiteAccess.user_id == user_id,
            UserSiteAccess.site_id == site_id,
        )
        .first()
    )
    if not access:
        raise NotFoundError("Site access record not found.")
    db.delete(access)
    db.commit()
