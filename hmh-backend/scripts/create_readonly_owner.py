"""
Create or reset the read-only owner account.

This account can view everything but cannot create, edit, delete, approve,
submit, capture, upload, or perform any write action.  The backend enforces
this at the API level — all write endpoints will return 403 for READ_ONLY users.

Usage:
    python scripts/create_readonly_owner.py

Or against the production Render DB:
    DATABASE_URL=postgresql://... python scripts/create_readonly_owner.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import db_session
from app.models.enums import UserRole
from app.models.user import User
from app.core.security import hash_password

_EMAIL     = "view@hmhgroup.co.za"
_FULL_NAME = "HMH Owner (View Only)"
_PASSWORD  = "View@HMH2026"
_ROLE      = UserRole.READ_ONLY


def seed() -> None:
    print("=" * 60)
    print("HMH — Create / Reset Read-Only Owner Account")
    print("=" * 60)
    print(f"Email    : {_EMAIL}")
    print(f"Role     : {_ROLE.value}  (view-only, cannot write)")
    print(f"Password : {_PASSWORD}")
    print("-" * 60)

    with db_session() as db:
        user = db.query(User).filter(User.email == _EMAIL).first()

        if user:
            user.full_name             = _FULL_NAME
            user.password_hash         = hash_password(_PASSWORD)
            user.role                  = _ROLE
            user.is_active             = True
            user.must_reset_password   = False
            user.failed_login_attempts = 0
            user.locked_until          = None
            db.commit()
            db.refresh(user)
            print(f"[OK] UPDATED  id={user.id}")
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
            print(f"[OK] CREATED  id={new_user.id}")

        print(f"Email    : {_EMAIL}")
        print(f"Password : {_PASSWORD}")
        print("=" * 60)
        print("This account is VIEW-ONLY. Any write attempt returns 403.")
        print("=" * 60)


if __name__ == "__main__":
    seed()
