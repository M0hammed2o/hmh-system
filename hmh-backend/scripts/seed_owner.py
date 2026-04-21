"""
Seed script: creates the initial OWNER user if one does not already exist.

Run from the hmh-backend directory:
    python scripts/seed_owner.py

Requires .env to be present and DATABASE_URL to be set.
The script is idempotent — re-running it is safe.
"""

import sys
import os

# Ensure the hmh-backend directory is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import db_session
from app.models.enums import UserRole
from app.models.user import User
from app.core.security import hash_password

_EMAIL = "admin@hmhgroup.com"
_FULL_NAME = "HMH Owner"
_PASSWORD = "Admin@12345"


def seed() -> None:
    with db_session() as db:
        existing = db.query(User).filter(User.email == _EMAIL).first()
        if existing:
            print(f"Owner already exists: {existing.email} (id={existing.id})")
            return

        owner = User(
            full_name=_FULL_NAME,
            email=_EMAIL,
            password_hash=hash_password(_PASSWORD),
            role=UserRole.OWNER,
            is_active=True,
            must_reset_password=False,
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
        print(f"Owner created: {owner.email} (id={owner.id})")


if __name__ == "__main__":
    seed()
