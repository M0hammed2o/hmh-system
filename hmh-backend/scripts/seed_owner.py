"""
Seed script: ensures an OWNER user exists and is always usable.

- Creates owner if missing
- If owner exists:
    - resets password
    - unlocks account
    - restores full permissions

Run:
    python scripts/seed_owner.py
"""

import sys
import os

# Ensure backend path is available
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
        user = db.query(User).filter(User.email == _EMAIL).first()

        if user:
            # 🔥 FIX EXISTING USER
            user.full_name = _FULL_NAME
            user.password_hash = hash_password(_PASSWORD)
            user.role = UserRole.OWNER
            user.is_active = True
            user.must_reset_password = False

            # 🚨 CRITICAL FIXES (your issue)
            user.failed_login_attempts = 0
            user.locked_until = None

            db.commit()

            print(f"Owner RESET: {user.email}")
            print("Password:", _PASSWORD)
            return

        # ✅ CREATE NEW USER
        owner = User(
            full_name=_FULL_NAME,
            email=_EMAIL,
            password_hash=hash_password(_PASSWORD),
            role=UserRole.OWNER,
            is_active=True,
            must_reset_password=False,
            failed_login_attempts=0,
            locked_until=None,
            created_by=None,
        )

        db.add(owner)
        db.commit()
        db.refresh(owner)

        print(f"Owner CREATED: {owner.email}")
        print("Password:", _PASSWORD)


if __name__ == "__main__":
    seed()