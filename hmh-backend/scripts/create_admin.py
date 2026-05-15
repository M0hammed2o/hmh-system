"""
Create or reset the system administrator account.

Usage (local DB):
    python scripts/create_admin.py

Usage (production Render DB):
    DATABASE_URL=postgresql://... python scripts/create_admin.py

The highest available role in this system is OWNER.
There is no SUPER_ADMIN role — OWNER has unrestricted access.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import db_session
from app.models.enums import UserRole
from app.models.user import User
from app.core.security import hash_password

# ── Credentials ───────────────────────────────────────────────────────────────
_EMAIL     = "admin@hmhgroup.co.za"
_FULL_NAME = "System Administrator"
_PASSWORD  = "Admin@123456"
_ROLE      = UserRole.OWNER        # Highest available role


def run() -> None:
    print("=" * 60)
    print("HMH — Create / Reset System Administrator")
    print("=" * 60)
    print(f"Email    : {_EMAIL}")
    print(f"Role     : {_ROLE.value}  (highest available role)")
    print(f"Active   : True")
    print(f"Password : {_PASSWORD}")
    print("-" * 60)

    with db_session() as db:
        existing = db.query(User).filter(User.email == _EMAIL).first()

        if existing:
            # Reset all security fields to ensure clean login
            existing.full_name             = _FULL_NAME
            existing.password_hash         = hash_password(_PASSWORD)
            existing.role                  = _ROLE
            existing.is_active             = True
            existing.must_reset_password   = False
            existing.failed_login_attempts = 0
            existing.locked_until          = None

            db.commit()
            db.refresh(existing)

            print(f"[OK] UPDATED existing user -- id={existing.id}")
            print(f"  Password reset to:  {_PASSWORD}")
            print(f"  Account unlocked:   Yes")
            print(f"  must_reset_password: False")
        else:
            new_user = User(
                full_name             = _FULL_NAME,
                email                 = _EMAIL,
                password_hash         = hash_password(_PASSWORD),
                role                  = _ROLE,
                is_active             = True,
                must_reset_password   = False,
                failed_login_attempts = 0,
                locked_until          = None,
                created_by            = None,
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            print(f"[OK] CREATED new user -- id={new_user.id}")
            print(f"  Password set to:    {_PASSWORD}")
            print(f"  Account is active:  True")

        # ── Verify by re-reading from DB ────────────────────────────────────────
        verified = db.query(User).filter(User.email == _EMAIL).first()
        print("-" * 60)
        print("VERIFICATION (re-read from database):")
        print(f"  id                   : {verified.id}")
        print(f"  email                : {verified.email}")
        print(f"  full_name            : {verified.full_name}")
        print(f"  role                 : {verified.role.value}")
        print(f"  is_active            : {verified.is_active}")
        print(f"  must_reset_password  : {verified.must_reset_password}")
        print(f"  failed_login_attempts: {verified.failed_login_attempts}")
        print(f"  locked_until         : {verified.locked_until}")
        print(f"  password_hash starts : {verified.password_hash[:20]}...")
        print("=" * 60)
        print("DONE — account ready to use.")
        print("=" * 60)


if __name__ == "__main__":
    run()
