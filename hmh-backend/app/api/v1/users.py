"""User management routes — CRUD and access control."""

import math
import uuid

from fastapi import APIRouter, Query

from app.dependencies import (
    CurrentUser,
    DbSession,
    OFFICE_ADMIN_AND_ABOVE,
    OWNER_ONLY,
    ALL_ROLES,  # DEMO: any authenticated active user
)
from app.schemas.common import ApiSuccess, PaginatedResult
from app.schemas.user import (
    ProjectAccessGrant,
    SiteAccessGrant,
    UserCreate,
    UserCreatedResponse,
    UserProjectAccessRead,
    UserRead,
    UserSiteAccessRead,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=ApiSuccess[UserRead])
def get_me(current_user: CurrentUser):
    return ApiSuccess(data=UserRead.model_validate(current_user))


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=ApiSuccess[PaginatedResult[UserRead]],
    dependencies=[ALL_ROLES],  # DEMO: was OFFICE_ADMIN_AND_ABOVE
)
def list_users(
    db: DbSession,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    users, total = user_service.list_users(db, page, limit)
    return ApiSuccess(
        data=PaginatedResult(
            items=[UserRead.model_validate(u) for u in users],
            total=total,
            page=page,
            limit=limit,
            total_pages=math.ceil(total / limit) if total else 1,
        )
    )


@router.post(
    "/",
    response_model=ApiSuccess[UserCreatedResponse],
    status_code=201,
    dependencies=[ALL_ROLES],  # DEMO: was OWNER_ONLY
)
def create_user(body: UserCreate, db: DbSession, current_user: CurrentUser):
    user, temp_pwd = user_service.create_user(db, body, current_user.id)
    return ApiSuccess(
        data=UserCreatedResponse(
            **UserRead.model_validate(user).model_dump(),
            temp_password=temp_pwd,
        ),
        message="User created. Share the temp_password with the user — it will not be shown again.",
    )


@router.get(
    "/{user_id}",
    response_model=ApiSuccess[UserRead],
    dependencies=[ALL_ROLES],  # DEMO: was OFFICE_ADMIN_AND_ABOVE
)
def get_user(user_id: uuid.UUID, db: DbSession):
    user = user_service.get_user(db, user_id)
    return ApiSuccess(data=UserRead.model_validate(user))


@router.patch(
    "/{user_id}",
    response_model=ApiSuccess[UserRead],
    dependencies=[ALL_ROLES],  # DEMO: was OWNER_ONLY
)
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession):
    user = user_service.update_user(db, user_id, body)
    return ApiSuccess(data=UserRead.model_validate(user))


@router.delete(
    "/{user_id}",
    response_model=ApiSuccess[UserRead],
    dependencies=[ALL_ROLES],  # DEMO: was OWNER_ONLY
)
def deactivate_user(user_id: uuid.UUID, db: DbSession):
    user = user_service.deactivate_user(db, user_id)
    return ApiSuccess(data=UserRead.model_validate(user), message="User deactivated.")


@router.post(
    "/{user_id}/reset-password",
    response_model=ApiSuccess[UserCreatedResponse],
    dependencies=[ALL_ROLES],  # DEMO: was OWNER_ONLY
)
def reset_user_password(user_id: uuid.UUID, db: DbSession):
    user, temp_pwd = user_service.reset_password(db, user_id)
    return ApiSuccess(
        data=UserCreatedResponse(
            **UserRead.model_validate(user).model_dump(),
            temp_password=temp_pwd,
        ),
        message="Password reset. Share the temp_password with the user — it will not be shown again.",
    )


# ── Project access ────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/project-access",
    response_model=ApiSuccess[UserProjectAccessRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def grant_project_access(user_id: uuid.UUID, body: ProjectAccessGrant, db: DbSession):
    access = user_service.grant_project_access(db, user_id, body)
    return ApiSuccess(data=UserProjectAccessRead.model_validate(access))


@router.delete(
    "/{user_id}/project-access/{project_id}",
    response_model=ApiSuccess[None],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def revoke_project_access(user_id: uuid.UUID, project_id: uuid.UUID, db: DbSession):
    user_service.revoke_project_access(db, user_id, project_id)
    return ApiSuccess(data=None, message="Project access revoked.")


# ── Site access ───────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/site-access",
    response_model=ApiSuccess[UserSiteAccessRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def grant_site_access(user_id: uuid.UUID, body: SiteAccessGrant, db: DbSession):
    access = user_service.grant_site_access(db, user_id, body)
    return ApiSuccess(data=UserSiteAccessRead.model_validate(access))


@router.delete(
    "/{user_id}/site-access/{site_id}",
    response_model=ApiSuccess[None],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def revoke_site_access(user_id: uuid.UUID, site_id: uuid.UUID, db: DbSession):
    user_service.revoke_site_access(db, user_id, site_id)
    return ApiSuccess(data=None, message="Site access revoked.")
