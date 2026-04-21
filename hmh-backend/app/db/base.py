"""
SQLAlchemy declarative base.
All ORM models import from here — this is what Alembic's env.py imports
to detect all mapped tables during autogenerate.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all HMH models."""
    pass
