"""
Centralised logging configuration for HMH backend.

Usage:
    from app.core.logging_config import get_logger, set_request_context

    logger = get_logger(__name__)
    logger.info("item created id=%s", item_id)

Context vars are injected by RequestContextMiddleware and included
in every log line automatically — no manual passing required.
"""

import logging
import sys
from contextvars import ContextVar

# ── Request-scoped context variables ─────────────────────────────────────────
# Set by RequestContextMiddleware on every incoming request.
# Readable anywhere in the call chain via get_*() helpers.

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_ctx_user_id: ContextVar[str] = ContextVar("ctx_user_id", default="-")
_ctx_project_id: ContextVar[str] = ContextVar("ctx_project_id", default="-")


def set_request_context(
    *,
    request_id: str,
    correlation_id: str,
    user_id: str = "-",
    project_id: str = "-",
) -> None:
    _request_id.set(request_id)
    _correlation_id.set(correlation_id)
    _ctx_user_id.set(user_id)
    _ctx_project_id.set(project_id)


def get_request_id() -> str:
    return _request_id.get()


def get_correlation_id() -> str:
    return _correlation_id.get()


# ── Formatter ─────────────────────────────────────────────────────────────────

class _HMHFormatter(logging.Formatter):
    """Adds request-context fields to every log record."""

    _FMT = (
        "%(asctime)s %(levelname)-8s [%(name)s] "
        "rid=%(request_id)s %(message)s"
    )

    def __init__(self) -> None:
        super().__init__(fmt=self._FMT, datefmt="%Y-%m-%dT%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = _request_id.get()
        return super().format(record)


# ── Public configuration entry point ─────────────────────────────────────────

def configure_logging(level: str = "INFO") -> None:
    """
    Configure the root logger. Call once at application startup.
    Subsequent calls are idempotent — will not add duplicate handlers.
    """
    root = logging.getLogger()
    # Avoid adding a second handler if configure_logging is called again
    # (e.g. during testing with multiple test-session setups).
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_HMHFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for _noisy in ("httpx", "httpcore", "uvicorn.access", "multipart"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Use instead of logging.getLogger()."""
    return logging.getLogger(name)
