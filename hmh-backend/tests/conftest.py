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
        # fuel_logs evidence photo columns (migration 0012)
        for _col in ["photo_odometer VARCHAR(1000)", "photo_pump VARCHAR(1000)",
                     "photo_invoice VARCHAR(1000)", "distance_km NUMERIC(10,1)",
                     "efficiency_kpl NUMERIC(8,3)", "l_per_100km NUMERIC(8,3)"]:
            _cn = _col.split()[0]
            conn.execute(_t(f"""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_name='fuel_logs' AND column_name='{_cn}')
                    THEN ALTER TABLE fuel_logs ADD COLUMN {_col}; END IF;
                END $$;
            """))
        # user_role_enum: add READ_ONLY if missing (migration 0011)
        conn.execute(_t("""
            DO $$
            BEGIN
                ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'READ_ONLY';
            EXCEPTION WHEN others THEN NULL;
            END$$;
        """))
        # attachment_entity_enum: add values from migrations 0013-0019
        for _val in ["STAGE_STATUS", "PAYMENT", "FUEL_LOG", "MATERIAL_REQUEST", "SUPPLIER", "LOT", "PROJECT"]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))
        # attachment_type_enum: add values from migration 0019
        for _val in ["PROGRESS_PHOTO", "PROOF_OF_WORK", "FUEL_SLIP", "QUOTATION", "PO_DOCUMENT"]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))
        # migration 0021: record_status_enum SUPPLIER_CONFIRMED
        conn.execute(_t("""
            DO $$ BEGIN
                ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS 'SUPPLIER_CONFIRMED';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))

        # migration 0022: alert_type_enum new operational values
        for _val in [
            "MR_APPROVED", "PO_SENT_ALERT", "DELIVERY_RECEIVED_ALERT",
            "WAREHOUSE_TRANSFER_COMPLETED", "INVOICE_CAPTURED",
            "PAYMENT_COMPLETED", "PARTIAL_PAYMENT_RECORDED",
            "MILESTONE_COMPLETED_ALERT", "MILESTONE_DELAYED_ALERT",
        ]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))

        # migration 0023: PAYMENT_DUE alert type
        conn.execute(_t("""
            DO $$ BEGIN
                ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS 'PAYMENT_DUE';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))

        # migration 0028: Phase E Gmail OCR pipeline alert types
        for _val in ["DUPLICATE_INVOICE", "OCR_EXTRACTION_FAILED", "SUPPLIER_MISMATCH"]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))

        # migration 0022: alert_recipients new category flags + project_id
        conn.execute(_t("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='alert_recipients' AND column_name='receives_procurement_alerts')
                THEN ALTER TABLE alert_recipients
                    ADD COLUMN receives_procurement_alerts BOOLEAN NOT NULL DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='alert_recipients' AND column_name='receives_milestone_alerts')
                THEN ALTER TABLE alert_recipients
                    ADD COLUMN receives_milestone_alerts BOOLEAN NOT NULL DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='alert_recipients' AND column_name='receives_payment_alerts')
                THEN ALTER TABLE alert_recipients
                    ADD COLUMN receives_payment_alerts BOOLEAN NOT NULL DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='alert_recipients' AND column_name='project_id')
                THEN ALTER TABLE alert_recipients ADD COLUMN project_id UUID; END IF;
            END $$;
        """))

        # migration 0022: notification_queue entity context columns
        conn.execute(_t("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='notification_queue' AND column_name='project_id')
                THEN ALTER TABLE notification_queue ADD COLUMN project_id UUID; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='notification_queue' AND column_name='entity_type')
                THEN ALTER TABLE notification_queue ADD COLUMN entity_type VARCHAR(50); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='notification_queue' AND column_name='entity_id')
                THEN ALTER TABLE notification_queue ADD COLUMN entity_id UUID; END IF;
            END $$;
        """))

        # record_status_enum: add INVOICED (0018), PARTIALLY_PAID, OVERPAID (0020)
        for _val in ["INVOICED", "PARTIALLY_PAID", "OVERPAID"]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))
        # payments.payment_method and payments.lot_id (migration 0020)
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='payments' AND column_name='payment_method')
                THEN ALTER TABLE payments ADD COLUMN payment_method VARCHAR(50);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='payments' AND column_name='lot_id')
                THEN ALTER TABLE payments ADD COLUMN lot_id UUID;
                END IF;
            END $$;
        """))
        # fuel_logs.log_date must be nullable (migration 0010)
        conn.execute(_t("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'fuel_logs'
                    AND column_name = 'log_date' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE fuel_logs ALTER COLUMN log_date DROP NOT NULL;
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
        # migration 0015: stock_ledger.site_id and usage_logs.site_id must be nullable
        # (project-level warehouse entries have site_id=NULL)
        for _tbl in ["stock_ledger", "usage_logs"]:
            conn.execute(_t(f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{_tbl}'
                        AND column_name = 'site_id' AND is_nullable = 'NO'
                    ) THEN
                        ALTER TABLE {_tbl} ALTER COLUMN site_id DROP NOT NULL;
                    END IF;
                END $$;
            """))

        # migration 0017: milestone completion fields on project_stage_status
        conn.execute(_t("""
            DO $$
            BEGIN
                ALTER TYPE stage_status_enum ADD VALUE IF NOT EXISTS 'BLOCKED';
            EXCEPTION WHEN others THEN NULL;
            END$$;
        """))
        for _col, _type in [
            ("completion_notes",  "TEXT"),
            ("completed_by_name", "VARCHAR(255)"),
            ("blocked_reason",    "TEXT"),
        ]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_name='project_stage_status'
                        AND column_name='{_col}')
                    THEN ALTER TABLE project_stage_status ADD COLUMN {_col} {_type};
                    END IF;
                END $$;
            """))
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='project_stage_status'
                    AND column_name='progress_pct')
                THEN ALTER TABLE project_stage_status
                    ADD COLUMN progress_pct SMALLINT NOT NULL DEFAULT 0;
                END IF;
            END $$;
        """))

        # migration 0016: lot_types table + new columns on lots and boq_items
        # create_all creates the table (from ORM), but guard existing DBs
        conn.execute(_t("""
            DO $$
            BEGIN
                -- lots.lot_type_id
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'lots' AND column_name = 'lot_type_id'
                ) THEN
                    ALTER TABLE lots ADD COLUMN lot_type_id UUID;
                    -- FK added conditionally below
                END IF;

                -- lots.boq_customized_at
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'lots' AND column_name = 'boq_customized_at'
                ) THEN
                    ALTER TABLE lots ADD COLUMN boq_customized_at TIMESTAMPTZ;
                END IF;

                -- boq_items.generated_from_lot_type_id
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'boq_items'
                    AND column_name = 'generated_from_lot_type_id'
                ) THEN
                    ALTER TABLE boq_items ADD COLUMN generated_from_lot_type_id UUID;
                END IF;
            END $$;
        """))

        # migration 0024: performance indexes (CREATE INDEX IF NOT EXISTS is safe on existing DB)
        for _idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_stock_ledger_site_id ON stock_ledger(site_id)",
            "CREATE INDEX IF NOT EXISTS ix_stock_ledger_movement_date ON stock_ledger(movement_date)",
            "CREATE INDEX IF NOT EXISTS ix_stock_ledger_lot_item ON stock_ledger(lot_id, item_id)",
            "CREATE INDEX IF NOT EXISTS ix_system_alerts_project_status_type ON system_alerts(project_id, status, alert_type)",
            "CREATE INDEX IF NOT EXISTS ix_notification_queue_status_next_attempt ON notification_queue(status, next_attempt_at)",
        ]:
            try:
                conn.execute(_t(_idx_sql))
            except Exception:
                pass

        # migration 0025: data consistency partial unique indexes
        for _idx_sql in [
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_supplier_invoice_number
               ON invoices(supplier_id, invoice_number)
               WHERE supplier_id IS NOT NULL AND invoice_number IS NOT NULL""",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_project_reference
               ON payments(project_id, payment_reference)
               WHERE payment_reference IS NOT NULL""",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_queue_provider_message_id
               ON notification_queue(provider_message_id)
               WHERE provider_message_id IS NOT NULL""",
        ]:
            try:
                conn.execute(_t(_idx_sql))
            except Exception:
                pass

    # migration 0026 — separate connection to avoid inheriting any aborted
    # transaction state from the try/except blocks above
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='project_stage_status'
                    AND column_name='planned_completion_date')
                THEN ALTER TABLE project_stage_status ADD COLUMN planned_completion_date DATE;
                END IF;
            END $$;
        """))

    # migration 0027 — attachment enhancements: caption, uploaded_role, 4 new type enum values
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='attachments' AND column_name='caption')
                THEN ALTER TABLE attachments ADD COLUMN caption VARCHAR(500);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='attachments' AND column_name='uploaded_role')
                THEN ALTER TABLE attachments ADD COLUMN uploaded_role VARCHAR(50);
                END IF;
            END $$;
        """))
        for _val in ["BEFORE_PHOTO", "COMPLETION_PHOTO", "ISSUE_PHOTO", "DELIVERY_EVIDENCE"]:
            conn.execute(_t(f"""
                DO $$ BEGIN
                    ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS '{_val}';
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """))

    # migration 0031: stock_ledger.project_id nullable
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='stock_ledger'
                    AND column_name='project_id' AND is_nullable='NO'
                ) THEN
                    ALTER TABLE stock_ledger ALTER COLUMN project_id DROP NOT NULL;
                END IF;
            END $$;
        """))

    # migration 0032: notification_queue.is_test
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='notification_queue' AND column_name='is_test')
                THEN ALTER TABLE notification_queue ADD COLUMN is_test BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """))

    # migration 0033: users.pin_hash + SITE_MANAGER_VIEW role enum value
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='pin_hash')
                THEN ALTER TABLE users ADD COLUMN pin_hash TEXT;
                END IF;
            END $$;
        """))
        conn.execute(_t("""
            DO $$ BEGIN
                ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'SITE_MANAGER_VIEW';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))

    # migration 0034: DELIVERED + READ notification_status_enum values
    with engine.begin() as conn:
        conn.execute(_t("""
            DO $$ BEGIN
                ALTER TYPE notification_status_enum ADD VALUE IF NOT EXISTS 'DELIVERED';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))
        conn.execute(_t("""
            DO $$ BEGIN
                ALTER TYPE notification_status_enum ADD VALUE IF NOT EXISTS 'READ';
            EXCEPTION WHEN others THEN NULL;
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


def make_lot(db: Session, project_id: str, site_id, lot_number: str = "1") -> dict:
    """site_id may be None for freestanding lots."""
    from app.models.lot import Lot
    from app.models.enums import LotStatus
    l = Lot(
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id) if site_id else None,
        lot_number=lot_number,
        status=LotStatus.IN_PROGRESS,
        created_at=_now(), updated_at=_now(),
    )
    db.add(l)
    db.flush()
    return {"id": str(l.id), "lot_number": lot_number, "site_id": site_id}


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


def make_stock(db: Session, project_id: str, site_id, item_id: str,
               qty: float = 100.0, lot_id: str = None) -> None:
    """Add opening balance to stock ledger.

    site_id may be None for project-level (warehouse) entries.
    """
    from app.models.stock import StockLedger
    from app.models.enums import MovementType
    db.add(StockLedger(
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id) if site_id else None,
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


def make_user_project_access(
    db: Session,
    user_id: str,
    project_id: str,
    can_view: bool = True,
    can_edit: bool = True,
    can_approve: bool = True,
) -> None:
    """Grant a non-OWNER user explicit access to a project.

    Required for any test that uses a non-OWNER user to access project-scoped
    resources.  OWNER role bypasses the check automatically; all other roles
    need a UserProjectAccess record.
    """
    from app.models.access import UserProjectAccess
    db.add(UserProjectAccess(
        user_id=uuid.UUID(user_id),
        project_id=uuid.UUID(project_id),
        can_view=can_view,
        can_edit=can_edit,
        can_approve=can_approve,
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
