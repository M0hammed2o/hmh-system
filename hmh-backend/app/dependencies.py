"""
FastAPI dependency functions.

These are the shared building blocks that route handlers inject via Depends().
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

# Re-export get_db so route files only need to import from dependencies
DbSession = Annotated[Session, Depends(get_db)]

# ── JWT bearer extraction ─────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)

BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_bearer)
]


def _extract_token_payload(credentials: BearerCredentials) -> dict:
    """Decode and validate the Bearer token from the Authorization header."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_user_payload(
    credentials: BearerCredentials,
) -> dict:
    """
    Dependency: returns the decoded JWT payload dict.
    Use this in route handlers until a full User ORM object is needed.
    """
    return _extract_token_payload(credentials)


CurrentUserPayload = Annotated[dict, Depends(get_current_user_payload)]


def get_current_user(
    payload: CurrentUserPayload,
    db: DbSession,
) -> User:
    """
    Dependency: resolves the JWT payload to a live User ORM object.
    Raises 401 if the user is missing or inactive.
    """
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """
    Dependency factory — restricts a route to users with one of the given roles.

    Usage::

        @router.get("/admin")
        def admin_only(
            payload: CurrentUserPayload,
            _: None = Depends(require_roles(UserRole.OWNER, UserRole.OFFICE_ADMIN)),
        ):
            ...
    """
    def _check(payload: CurrentUserPayload) -> None:
        user_role = payload.get("role")
        if user_role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
    return Depends(_check)


# ── Convenience role aliases ──────────────────────────────────────────────────
OWNER_ONLY = require_roles(UserRole.OWNER)
OFFICE_ADMIN_AND_ABOVE = require_roles(UserRole.OWNER, UserRole.OFFICE_ADMIN)
OFFICE_AND_ABOVE = require_roles(
    UserRole.OWNER, UserRole.OFFICE_ADMIN, UserRole.OFFICE_USER
)
ALL_ROLES = require_roles(*list(UserRole))
