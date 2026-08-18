"""
Health check endpoints.
GET /health — process liveness only, no DB call. This is what Render's
    healthCheckPath probes; it must stay fast and independent of the DB
    connection pool, or a burst of application traffic that exhausts the
    pool takes the liveness check down with it and triggers a restart on
    top of the original problem.
GET /health/db — DB readiness check, for manual/monitoring use. Uses the
    same pool as application requests, so it can time out under load —
    that's expected and is why Render's restart trigger must not depend on it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Liveness only — the process is up and serving requests. No DB call, and
    defined as `async def` (not `def`) on purpose: FastAPI runs plain `def`
    routes in Starlette's threadpool executor, which is a separate finite
    resource from the DB pool — a burst of synchronous, DB-blocked route
    handlers can saturate that threadpool too, and a `def` health check
    would queue behind them right along with everything else. `async def`
    with no `await` runs directly on the event loop, so it stays responsive
    regardless of what the threadpool or DB pool are doing.
    """
    return {
        "success": True,
        "data": {
            "status": "ok",
            "env": settings.APP_ENV,
            "version": "1.0.0",
        },
    }


@router.get("/health/db")
def health_check_db(db: Session = Depends(get_db)) -> dict:
    """
    Readiness — confirms the DB is reachable through the application's own
    connection pool. Returns "degraded" (not an error status) if the pool is
    exhausted or the DB is unreachable, so callers can distinguish "process
    is down" (checked by /health) from "DB is unavailable right now".
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "success": True,
        "data": {
            "status": "ok" if db_status == "connected" else "degraded",
            "db": db_status,
            "env": settings.APP_ENV,
            "version": "1.0.0",
        },
    }
