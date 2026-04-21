"""
Health check endpoint.
GET /health — returns DB connectivity status and app info.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """
    Returns:
    - ``status``: "ok" if the DB is reachable, "degraded" otherwise.
    - ``db``: "connected" or error message.
    - ``env``: current APP_ENV.
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
