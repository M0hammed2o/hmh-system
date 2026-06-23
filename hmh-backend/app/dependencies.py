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

from app.core.logging_config import get_logger
from app.core.security import decode_token
from app.models.enums import UserRole

_auth_log = get_logger("hmh.auth")
from app.db.session import get_db
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
    allowed = [r.value for r in roles]

    def _check(payload: CurrentUserPayload) -> None:
        user_role = payload.get("role")
        if user_role not in allowed:
            _auth_log.warning(
                "access_denied role=%r allowed=%r user=%s",
                user_role, allowed, payload.get("sub"),
            )
            # Give a clear message to read-only accounts
            if user_role == "READ_ONLY":
                detail = (
                    "Owner account is read-only. "
                    "This action is not permitted in view-only mode. "
                    "Contact an admin if you need to make changes."
                )
            else:
                detail = f"Role '{user_role}' is not permitted. Required: {allowed}"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail,
            )
    return Depends(_check)


# ── Convenience role aliases ──────────────────────────────────────────────────
OWNER_ONLY = require_roles(UserRole.OWNER)
OFFICE_ADMIN_AND_ABOVE = require_roles(UserRole.OWNER, UserRole.OFFICE_ADMIN)
OFFICE_AND_ABOVE = require_roles(
    UserRole.OWNER, UserRole.OFFICE_ADMIN, UserRole.OFFICE_USER, UserRole.PROCUREMENT_LEAD
)
ALL_ROLES = require_roles(*list(UserRole))
# All roles that can perform write operations (excludes READ_ONLY view-only accounts)
WRITE_ROLES = require_roles(
    UserRole.OWNER,
    UserRole.OFFICE_ADMIN,
    UserRole.OFFICE_USER,
    UserRole.PROCUREMENT_LEAD,
    UserRole.SITE_MANAGER,
    UserRole.SITE_STAFF,
)
# Restricted to the procurement lead role — used for final MR approval and override
PROCUREMENT_LEAD_ONLY = require_roles(UserRole.OWNER, UserRole.PROCUREMENT_LEAD)


# ── Project isolation helper ──────────────────────────────────────────────────

def check_project_access(
    db: Session,
    user: User,
    project_id: uuid.UUID,
) -> None:
    """
    Raise HTTP 403 if the user does not have access to the given project.

    OWNERs bypass this check — they have system-wide access.
    All other roles must have an explicit UserProjectAccess record.

    Call this after fetching a resource by ID to enforce project isolation.
    Example::

        po = _get_po_or_404(db, po_id)
        check_project_access(db, current_user, po.project_id)
    """
    if user.role == UserRole.OWNER:
        return

    from app.models.access import UserProjectAccess
    access = (
        db.query(UserProjectAccess)
        .filter(
            UserProjectAccess.user_id == user.id,
            UserProjectAccess.project_id == project_id,
        )
        .first()
    )
    if not access:
        _auth_log.warning(
            "project_access_denied user=%s project=%s role=%s",
            user.id, project_id, user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project's resources.",
        )
