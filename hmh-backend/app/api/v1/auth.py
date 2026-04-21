"""Auth routes — login, token refresh, password change."""

from fastapi import APIRouter

from app.core.config import settings
from app.dependencies import CurrentUser, DbSession
from app.schemas.common import ApiSuccess
from app.schemas.user import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: DbSession):
    user, access_token, refresh_token = auth_service.login(db, body.email, body.password)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        must_reset_password=user.must_reset_password,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: DbSession):
    user, access_token, refresh_token = auth_service.refresh(db, body.refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        must_reset_password=user.must_reset_password,
    )


@router.post("/change-password", response_model=ApiSuccess[None])
def change_password(
    body: ChangePasswordRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    auth_service.change_password(db, current_user, body.current_password, body.new_password)
    return ApiSuccess(data=None, message="Password updated successfully.")
