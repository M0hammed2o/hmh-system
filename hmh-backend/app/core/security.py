"""
JWT and password hashing utilities.
Auth routes are built in a later module; these helpers are the shared foundation.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of a plaintext password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    :param subject:      User UUID (stored as ``sub``).
    :param extra_claims: Additional payload fields (e.g. role, email).
    :param expires_delta: Override the default expiry window.
    """
    expire = _now_utc() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a longer-lived refresh token."""
    expire = _now_utc() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: Dict[str, Any] = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT.

    :raises JWTError: if the token is invalid or expired.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_temp_password(length: int = 12) -> str:
    """
    Generate a temporary password for new users.

    Uses only unambiguous characters — no 0/O, 1/l/I, or special symbols —
    so the password is easy to read aloud, type on a phone, or share via
    WhatsApp without transcription errors.

    Format: 12 alphanumeric chars, guaranteed to contain at least one
    uppercase letter, one lowercase letter, and one digit.
    """
    import secrets
    # Exclude visually ambiguous characters: 0, O, o, 1, l, I, i
    upper   = "ABCDEFGHJKMNPQRSTUVWXYZ"
    lower   = "abcdefghjkmnpqrstuvwxyz"
    digits  = "23456789"
    alphabet = upper + lower + digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c in upper  for c in pwd)
            and any(c in lower  for c in pwd)
            and any(c in digits for c in pwd)
        ):
            return pwd
