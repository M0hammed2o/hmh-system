"""
Request context middleware.

For every incoming HTTP request:
  1. Generates or propagates X-Request-ID (from client header if present).
  2. Sets contextvars so all downstream log calls include rid=<id>.
  3. Logs slow requests (>1 000 ms WARNING, >3 000 ms ERROR).
  4. Echoes X-Request-ID back in the response headers.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import get_logger, set_request_context

logger = get_logger("hmh.requests")

# Paths that produce high log volume at DEBUG and are not useful for tracing
_SKIP_LOG_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Accept caller-supplied ID (e.g. from frontend) or generate a short one
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        corr = request.headers.get("X-Correlation-ID") or rid

        set_request_context(request_id=rid, correlation_id=corr)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Let FastAPI exception handlers deal with it — just time and re-raise
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "UNHANDLED_EXCEPTION method=%s path=%s duration_ms=%.0f rid=%s",
                request.method,
                request.url.path,
                duration_ms,
                rid,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid

        path = request.url.path
        if path not in _SKIP_LOG_PATHS:
            if duration_ms > 3000:
                logger.error(
                    "VERY_SLOW_REQUEST method=%s path=%s status=%d duration_ms=%.0f",
                    request.method, path, response.status_code, duration_ms,
                )
            elif duration_ms > 1000:
                logger.warning(
                    "SLOW_REQUEST method=%s path=%s status=%d duration_ms=%.0f",
                    request.method, path, response.status_code, duration_ms,
                )

        return response
