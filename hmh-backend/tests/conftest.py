"""
Pytest fixtures for HMH backend tests.

Uses a dedicated test database (or the real DB if TEST_DATABASE_URL not set).
Each test that needs a clean slate uses the `db` fixture with rollback.
The FastAPI test client is provided via `client` fixture.
"""

import os
import uuid
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ── App imports ────────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
import app.models  # registers all models on Base.metadata
from main import app

# ── Test DB setup ──────────────────────────────────────────────────────────────
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", settings.DATABASE_URL)

engine = create_engine(TEST_DB_URL, pool_pre_ping=True, echo=False)
TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def ensure_tables():
    """Create all tables once per test session. Also relaxes NOT NULL on updated columns."""
    from sqlalchemy import text as _t
    Base.metadata.create_all(bind=engine)
    # ── Schema patches for test DB (create_all skips existing tables) ────────────
    with engine.begin() as conn:
        # material_request_items.item_id must be nullable (changed in ORM)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'material_request_items'
                    AND column_name = 'item_id' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE material_request_items ALTER COLUMN item_id DROP NOT NULL;
                END IF;
            END $$;
        """))
        # alert_recipients.last_inbound_at added in migration 0005
        conn.execute(_t("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'alert_recipients'
                    AND column_name = 'last_inbound_at'
                ) THEN
                    ALTER TABLE alert_recipients ADD COLUMN last_inbound_at TIMESTAMPTZ;
                END IF;
            END $$;
        """))
        # attachments.file_url: legacy NOT NULL column from migration 0001,
        # now in ORM model.  Add if missing (test DBs created via create_all
        # before today's model change won't have it).
        conn.execute(_t("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'attachments' AND column_name = 'file_url'
                ) THEN
                    ALTER TABLE attachments ADD COLUMN file_url VARCHAR(1000);
                ELSE
                    ALTER TABLE attachments ALTER COLUMN file_url DROP NOT NULL;
                END IF;
            END $$;
        """))
        # payments.amount: legacy NOT NULL from migration 0001, now in ORM model.
        conn.execute(_t("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'payments' AND column_name = 'amount'
                ) THEN
                    ALTER TABLE payments ADD COLUMN amount NUMERIC(14,2);
                ELSE
                    ALTER TABLE payments ALTER COLUMN amount DROP NOT NULL;
                END IF;
            END $$;
        """))
        # po_email_logs.sent_to must be nullable (migration 0008)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'po_email_logs'
                    AND column_name = 'sent_to' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE po_email_logs ALTER COLUMN sent_to DROP NOT NULL;
                END IF;
            END $$;
        """))
        # purchase_order_items.quantity must be nullable (migration 0007)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'purchase_order_items'
                    AND column_name = 'quantity' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE purchase_order_items ALTER COLUMN quantity DROP NOT NULL;
                END IF;
            END $$;
        """))
        # material_request_items.request_id must be nullable (migration 0006)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'material_request_items'
                    AND column_name = 'request_id' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE material_request_items ALTER COLUMN request_id DROP NOT NULL;
                END IF;
            END $$;
        """))
        # material_request_items.quantity_requested must be nullable (migration 0006)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'material_request_items'
                    AND column_name = 'quantity_requested' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE material_request_items ALTER COLUMN quantity_requested DROP NOT NULL;
                END IF;
            END $$;
        """))
    yield


@pytest.fixture()
def db():
    """Yield a DB session that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """Return a TestClient that uses the rolled-back test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Factory helpers ────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def make_user(db: Session, email: str = None, role: str = "OFFICE_USER", password: str = "Test@1234") -> dict:
    from app.models.user import User
    from app.models.enums import UserRole
    email = email or f"test_{uuid.uuid4().hex[:8]}@test.com"
    u = User(
        full_name="Test User",
        email=email,
        password_hash=hash_password(password),
        role=UserRole(role),
        is_active=True,
        must_reset_password=False,
        created_at=_now(), updated_at=_now(),
    )
    db.add(u)
    db.flush()
    return {"id": str(u.id), "email": email, "password": password, "role": role}


def make_project(db: Session, owner_id: str) -> dict:
    from app.models.project import Project
    from app.models.enums import ProjectStatus
    code = f"TST-{uuid.uuid4().hex[:6].upper()}"
    p = Project(
        name=f"Test Project {code}",
        code=code,
        status=ProjectStatus.ACTIVE,
        created_by=uuid.UUID(owner_id),
        created_at=_now(), updated_at=_now(),
    )
    db.add(p)
    db.flush()
    return {"id": str(p.id), "code": code}


def make_site(db: Session, project_id: str, name: str = "Test Site") -> dict:
    from app.models.site import Site
    s = Site(
        project_id=uuid.UUID(project_id),
        name=name,
        site_type="construction_site",
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(s)
    db.flush()
    return {"id": str(s.id), "name": name}


def make_lot(db: Session, project_id: str, site_id: str, lot_number: str = "1") -> dict:
    from app.models.lot import Lot
    from app.models.enums import LotStatus
    l = Lot(
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        lot_number=lot_number,
        status=LotStatus.IN_PROGRESS,
        created_at=_now(), updated_at=_now(),
    )
    db.add(l)
    db.flush()
    return {"id": str(l.id), "lot_number": lot_number}


def make_item(db: Session, name: str = "Test Cement", unit: str = "bag", item_type: str = "MATERIAL") -> dict:
    from app.models.item import Item
    from app.models.enums import ItemType
    normalized = name.lower().replace(" ", "_")
    # Avoid unique constraint on normalized_name
    normalized = f"{normalized}_{uuid.uuid4().hex[:4]}"
    it = Item(
        name=name,
        normalized_name=normalized,
        default_unit=unit,
        item_type=ItemType(item_type),
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(it)
    db.flush()
    return {"id": str(it.id), "name": name, "unit": unit}


def make_boq_item(db: Session, project_id: str, lot_id: str, item_id: str,
                  qty: float = 10.0, rate: float = 300.0) -> dict:
    """Create a BOQ allocation for a lot without triggering the GENERATED column."""
    from sqlalchemy import insert
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus

    # Header
    h = BOQHeader(
        project_id=uuid.UUID(project_id),
        version_name="Test BOQ",
        source_type="test",
        status=BoqStatus.ACTIVE,
        is_active_version=True,
        is_template=False,
        uploaded_by=None,
        uploaded_at=_now(),
    )
    db.add(h)
    db.flush()

    # Section
    s = BOQSection(
        boq_header_id=h.id,
        section_name="Test Section",
        sequence_order=1,
        created_at=_now(), updated_at=_now(),
    )
    db.add(s)
    db.flush()

    # Item — core INSERT to skip GENERATED column
    item_id_obj = uuid.uuid4()
    db.execute(
        insert(BOQItem).values(
            id=item_id_obj,
            boq_section_id=s.id,
            project_id=uuid.UUID(project_id),
            lot_id=uuid.UUID(lot_id),
            item_id=uuid.UUID(item_id),
            raw_description="Test Item",
            item_type="MATERIAL",
            unit="bag",
            planned_quantity=qty,
            planned_rate=rate,
            sort_order=1,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()
    return {"boq_item_id": str(item_id_obj), "header_id": str(h.id), "section_id": str(s.id)}


def make_supplier(db: Session, name: str = None) -> dict:
    from app.models.supplier import Supplier
    name = name or f"Test Supplier {uuid.uuid4().hex[:6]}"
    s = Supplier(
        name=name,
        email=f"supplier_{uuid.uuid4().hex[:6]}@test.com",
        is_active=True,
        created_at=_now(), updated_at=_now(),
    )
    db.add(s)
    db.flush()
    return {"id": str(s.id), "name": name}


def make_stock(db: Session, project_id: str, site_id: str, item_id: str,
               qty: float = 100.0, lot_id: str = None) -> None:
    """Add opening balance to stock ledger."""
    from app.models.stock import StockLedger
    from app.models.enums import MovementType
    db.add(StockLedger(
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        lot_id=uuid.UUID(lot_id) if lot_id else None,
        item_id=uuid.UUID(item_id),
        movement_type=MovementType.OPENING_BALANCE,
        reference_type="test_opening",
        quantity_in=qty,
        quantity_out=0,
        unit="bag",
        movement_date=_now(),
        entered_by=None,
        created_at=_now(),
    ))
    db.flush()


def login(client: TestClient, email: str, password: str) -> str:
    """Return bearer token."""
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
