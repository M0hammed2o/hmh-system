"""
Database session factory.
Use `get_db()` as a FastAPI dependency for request-scoped sessions.
Use `SessionLocal` directly in scripts and seed tasks.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # drop stale connections
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,         # log SQL in dev mode
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,      # avoid lazy-load issues after commit
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency — yields a DB session and closes it after the request.

    Usage in a route::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context-manager version for use in scripts and background tasks::

        with db_session() as db:
            db.add(...)
            db.commit()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
