"""
Domain exceptions.
Each exception maps to a specific HTTP status code via FastAPI exception handlers
(registered in main.py as the API layer grows).
"""

from typing import Any, Dict, Optional


class HMHException(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(HMHException):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(HMHException):
    status_code = 409
    error_code = "CONFLICT"


class ValidationError(HMHException):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class AuthenticationError(HMHException):
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(HMHException):
    status_code = 403
    error_code = "FORBIDDEN"


class AccountLockedError(HMHException):
    status_code = 423
    error_code = "ACCOUNT_LOCKED"


class InvalidStateError(HMHException):
    """Raised when a state transition is not allowed (e.g. approving a DRAFT invoice)."""
    status_code = 422
    error_code = "INVALID_STATE"


class AlreadyPostedError(HMHException):
    """Raised when attempting to re-post an already-posted opening balance."""
    status_code = 422
    error_code = "ALREADY_POSTED"
