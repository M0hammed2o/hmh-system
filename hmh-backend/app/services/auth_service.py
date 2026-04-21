"""Authentication service — login, token refresh, password change."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import AccountLockedError, AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 30


def login(db: Session, email: str, password: str) -> tuple[User, str, str]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("Account is disabled.")

    now = datetime.now(tz=timezone.utc)
    if user.locked_until and user.locked_until > now:
        raise AccountLockedError(
            f"Account is locked until {user.locked_until.strftime('%Y-%m-%d %H:%M UTC')}."
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=_LOCKOUT_MINUTES)
        db.commit()
        raise AuthenticationError("Invalid email or password.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )
    refresh_token = create_refresh_token(subject=str(user.id))
    return user, access_token, refresh_token


def refresh(db: Session, token: str) -> tuple[User, str, str]:
    try:
        payload = decode_token(token)
    except JWTError:
        raise AuthenticationError("Invalid or expired refresh token.")

    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type.")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, AttributeError):
        raise AuthenticationError("Invalid token subject.")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User not found or account is disabled.")

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )
    new_refresh = create_refresh_token(subject=str(user.id))
    return user, access_token, new_refresh


def change_password(
    db: Session, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    user.must_reset_password = False
    db.commit()
