"""
Seed the fuel storage scenario that tests/audit/fuel-storage-manage.spec.mjs
drives in a browser.

Four tanks, because the screen behaves differently for each and the difference
is the whole point of the change:

  Audit Diesel Tank      1000 L recorded at R18.00/L — priced, so the card
                         shows an average, and spoken for, so its fuel type is
                         locked and removing it deactivates rather than deletes.
  Audit Unused Tank      nothing ever recorded — the only case that can be
                         deleted outright.
  Audit Write-Off Tank   800 L at no recorded price — the reported case:
                         removing it has to write those litres off with a
                         reason, or they leave every stock figure in silence
                         while the adjustment that put them there stays.
  Audit Petrol Tank      empty, and a second fuel type, so the fuel-type
                         dropdown has something to offer.

Everything here is fictional. Run it against a throwaway database only — it
refuses anything that is not a local host. Credentials come from the
environment; this script never contains one.

Run:
    AUDIT_EMAIL=... AUDIT_PASSWORD=... \
    DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/hmh_audit \
    python scripts/seed_fuel_storage_audit.py
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password
from app.db.session import db_session
from app.models.enums import ProjectStatus, UserRole
from app.models.fuel_management import FuelTypeDefinition
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.schemas.fuel_management import FuelStorageCreate
from app.services import fuel_management_service as service

PROJECT_NAME = os.environ.get("AUDIT_FUEL_PROJECT", "Fuel Audit Project")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _now():
    return datetime.now(timezone.utc)


def _guard_local_database() -> None:
    """The audit stack exists so that nothing has to be trusted to remember
    which database it is pointed at. This is that check."""
    url = os.environ.get("DATABASE_URL", "")
    host = urlparse(url).hostname
    if host not in LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to seed: DATABASE_URL host is {host!r}, not a local host. "
            "This script writes fictional fuel records and belongs on a throwaway database only."
        )


def _owner(db) -> User:
    email = os.environ.get("AUDIT_EMAIL")
    password = os.environ.get("AUDIT_PASSWORD")
    if not email or not password:
        raise SystemExit("Set AUDIT_EMAIL and AUDIT_PASSWORD.")
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(full_name="Fuel Audit Owner", email=email, password_hash=hash_password(password),
                role=UserRole.OWNER, is_active=True, must_reset_password=False,
                failed_login_attempts=0, locked_until=None, created_by=None)
    db.add(user); db.flush()
    print(f"Created owner {email}")
    return user


def _fuel_type(db, code: str, name: str) -> FuelTypeDefinition:
    row = db.query(FuelTypeDefinition).filter_by(code=code).first()
    if not row:
        row = FuelTypeDefinition(code=code, name=name, is_active=True)
        db.add(row); db.flush()
    return row


def _tank(db, project_id, owner_id, *, name, site_id, fuel_type_id, capacity,
          opening=0, price=None):
    """Created through the service, not by INSERT: the opening balance has to
    be a real adjustment row, or the screen's "has anything been recorded
    against this?" would be wrong and the write-off path untested."""
    existing = [s for s in service.list_storage(db, project_id, include_inactive=True)
                if s.name == name]
    if existing:
        print(f"  {name} already present")
        return existing[0]
    body = FuelStorageCreate(site_id=site_id, fuel_type_id=fuel_type_id, name=name,
                             capacity_litres=capacity, low_stock_threshold_litres=100,
                             opening_stock_litres=opening, opening_cost_per_litre=price)
    tank = service.create_storage(db, project_id, body, owner_id)
    print(f"  {name}: {opening} L"
          + (f" at R{price}/L" if price else " at no recorded price"))
    return tank


def seed() -> None:
    _guard_local_database()
    with db_session() as db:
        owner = _owner(db)
        project = db.query(Project).filter(Project.name == PROJECT_NAME).first()
        if not project:
            project = Project(name=PROJECT_NAME, code=f"FUEL-{uuid.uuid4().hex[:5].upper()}",
                              status=ProjectStatus.ACTIVE, created_by=owner.id,
                              created_at=_now(), updated_at=_now())
            db.add(project); db.flush()
            print(f"Created project {PROJECT_NAME} ({project.code})")

        site = db.query(Site).filter_by(project_id=project.id, name="Fuel Audit Site").first()
        if not site:
            site = Site(project_id=project.id, name="Fuel Audit Site",
                        site_type="construction_site", is_active=True,
                        created_at=_now(), updated_at=_now())
            db.add(site); db.flush()

        diesel = _fuel_type(db, "DIESEL", "Diesel")
        petrol = _fuel_type(db, "PETROL_95", "Petrol 95")
        db.commit()

        print("Tanks:")
        _tank(db, project.id, owner.id, name="Audit Diesel Tank", site_id=site.id,
              fuel_type_id=diesel.id, capacity=5000, opening=1000, price=18)
        _tank(db, project.id, owner.id, name="Audit Unused Tank", site_id=site.id,
              fuel_type_id=diesel.id, capacity=2000)
        _tank(db, project.id, owner.id, name="Audit Write-Off Tank", site_id=site.id,
              fuel_type_id=diesel.id, capacity=1000, opening=800)
        _tank(db, project.id, owner.id, name="Audit Petrol Tank", site_id=site.id,
              fuel_type_id=petrol.id, capacity=1000)
        print(f"\nProject: {PROJECT_NAME}")


if __name__ == "__main__":
    seed()
