"""In-memory sliding-window rate limiter.

Suitable for single-instance deployments (no external store required).
Keys are (endpoint_tag, ip_address) so limits are isolated per endpoint group.
Automatically disabled when pytest sets PYTEST_CURRENT_TEST so tests are unaffected.
"""

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class _SlidingWindow:
    def __init__(self, max_calls: int, window_seconds: int):
        self._max = max_calls
        self._window = window_seconds
        self._buckets: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self._window
        dq = self._buckets[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please try again later.",
                headers={"Retry-After": str(self._window)},
            )
        dq.append(now)


# 10 login/refresh attempts per IP per 60 s — brute-force protection
_login_window = _SlidingWindow(max_calls=10, window_seconds=60)

# 20 OCR/vision calls per IP per 60 s — expensive AI-API calls
_ocr_window = _SlidingWindow(max_calls=20, window_seconds=60)


def _ip(request: Request) -> str:
    # Honour X-Forwarded-For set by Render/Nginx proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _in_test() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def login_rate_limit(request: Request) -> None:
    """FastAPI dependency — enforce login brute-force limit."""
    if not _in_test():
        _login_window.check(f"login:{_ip(request)}")


def ocr_rate_limit(request: Request) -> None:
    """FastAPI dependency — enforce OCR/vision call limit."""
    if not _in_test():
        _ocr_window.check(f"ocr:{_ip(request)}")
