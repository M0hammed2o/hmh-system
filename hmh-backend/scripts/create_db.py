"""
Direct database setup script — idempotent, safe to re-run.

Creates all NEW tables, adds new enum values, adds new columns on existing
tables (all with IF NOT EXISTS / DO NOTHING guards).

Run from hmh-backend directory:
    python scripts/create_db.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.base import Base
from app.db.session import engine
import app.models  # registers every model on Base.metadata


# ── New enum values on existing PG enum types ─────────────────────────────────
_RECORD_STATUS_NEW_VALUES = [
    "PENDING_APPROVAL", "CONVERTED_TO_PO", "ORDERED",
    "PARTIALLY_RECEIVED", "CLOSED",
]

_INVOICE_MATCH_STATUS_NEW_VALUES = [
    "QUANTITY_MISMATCH", "PRICE_MISMATCH", "MISSING_DELIVERY_NOTE",
    "MISSING_SIGNATURE", "MISSING_INVOICE", "AWAITING_APPROVAL",
    "APPROVED_FOR_PAYMENT",
]

_ALERT_TYPE_NEW_VALUES = [
    "MATERIAL_OVERUSE", "BOQ_ALLOCATION_EXCEEDED", "DELIVERY_MISMATCH",
    "DELIVERY_NOTE_MISSING", "SIGNATURE_MISSING", "INVOICE_UNMATCHED",
    "LOT_DELAYED", "STAGE_DELAYED", "FUEL_USAGE_HIGH",
    "DAILY_SUMMARY", "WEEKLY_SUMMARY",
]

# New PG enum types to create (Python enums not yet in initial migration)
_NEW_PG_ENUMS = {
    "delivery_destination_enum": ["MAIN_WAREHOUSE", "SITE_STORE", "LOT", "PICKUP"],
    "mr_priority_enum": ["URGENT", "HIGH", "NORMAL", "LOW"],
    "notification_channel_enum": ["WHATSAPP", "EMAIL", "IN_APP"],
    "notification_status_enum": [
        "PENDING", "SENT", "FAILED", "MOCK_SENT", "ACKNOWLEDGED", "CANCELLED"
    ],
    "job_card_status_enum": [
        "DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED",
        "OWNER_APPROVED", "PAYMENT_APPROVED", "PAID", "REJECTED",
    ],
    "job_card_work_type_enum": ["DAILY_LABOUR", "CONTRACT", "SUBCONTRACTOR", "OVERTIME"],
    "vehicle_type_enum": ["BAKKIE", "TRUCK", "TLB", "EXCAVATOR", "CRANE", "VAN", "OTHER"],
    "vehicle_status_enum": ["ACTIVE", "MAINTENANCE", "RETIRED"],
    "vehicle_cost_type_enum": [
        "FUEL", "TYRE", "REPAIR", "SERVICE", "LICENCE", "INSURANCE", "OTHER"
    ],
}

# New nullable columns to add to existing tables (table, column, type_sql, default_sql)
_NEW_COLUMNS = [
    # material_requests
    ("material_requests", "priority", "VARCHAR(20)", "'NORMAL'"),
    ("material_requests", "delivery_destination", "VARCHAR(30)", "'SITE_STORE'"),
    ("material_requests", "over_boq", "BOOLEAN", "false"),
    ("material_requests", "over_boq_reason", "TEXT", "NULL"),
    ("material_requests", "approved_by", "UUID", "NULL"),
    ("material_requests", "approved_at", "TIMESTAMPTZ", "NULL"),
    ("material_requests", "converted_to_po_at", "TIMESTAMPTZ", "NULL"),
    # material_request_items
    ("material_request_items", "description", "VARCHAR(500)", "''"),
    ("material_request_items", "approved_quantity", "NUMERIC(14,3)", "NULL"),
    ("material_request_items", "over_boq_quantity", "NUMERIC(14,3)", "NULL"),
    # suppliers
    ("suppliers", "whatsapp_number", "VARCHAR(50)", "NULL"),
    ("suppliers", "vat_number", "VARCHAR(50)", "NULL"),
    # purchase_orders
    ("purchase_orders", "lot_id", "UUID", "NULL"),
    ("purchase_orders", "delivery_destination", "VARCHAR(30)", "NULL"),
    # purchase_order_items
    ("purchase_order_items", "quantity_received", "NUMERIC(14,3)", "0"),
    # po_email_logs
    ("po_email_logs", "email_body", "TEXT", "NULL"),
    ("po_email_logs", "material_request_id", "UUID", "NULL"),
    # deliveries
    ("deliveries", "delivery_note_image_url", "VARCHAR(500)", "NULL"),
    ("deliveries", "signature_image_url", "VARCHAR(500)", "NULL"),
    ("deliveries", "receiver_name", "VARCHAR(255)", "NULL"),
    ("deliveries", "gps_lat", "FLOAT", "NULL"),
    ("deliveries", "gps_lng", "FLOAT", "NULL"),
    ("deliveries", "ocr_raw_data", "JSONB", "NULL"),
    # lots
    ("lots", "buyer_name", "VARCHAR(255)", "NULL"),
    ("lots", "manager_user_id", "UUID", "NULL"),
    ("lots", "boq_template_id", "UUID", "NULL"),
    ("lots", "start_date", "DATE", "NULL"),
    ("lots", "expected_completion_date", "DATE", "NULL"),
    ("lots", "actual_completion_date", "DATE", "NULL"),
    ("lots", "budgeted_cost", "NUMERIC(14,2)", "NULL"),
    ("lots", "notes", "TEXT", "NULL"),
    # boq_headers
    ("boq_headers", "is_template", "BOOLEAN", "false"),
    ("boq_headers", "template_name", "VARCHAR(255)", "NULL"),
    # projects
    ("projects", "budget", "NUMERIC(16,2)", "NULL"),
]


def _add_enum_value(conn, type_name: str, value: str) -> None:
    """Add a value to an existing PG enum if not already present."""
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = '{type_name}' AND e.enumlabel = '{value}'
            ) THEN
                ALTER TYPE {type_name} ADD VALUE '{value}';
            END IF;
        END $$;
    """))


def _create_enum_if_not_exists(conn, type_name: str, values: list[str]) -> None:
    values_sql = ", ".join(f"'{v}'" for v in values)
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{type_name}') THEN
                CREATE TYPE {type_name} AS ENUM ({values_sql});
            END IF;
        END $$;
    """))


def _add_column_if_not_exists(
    conn, table: str, column: str, col_type: str, default: str
) -> None:
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{column}'
            ) THEN
                ALTER TABLE {table}
                ADD COLUMN {column} {col_type}
                {f"DEFAULT {default}" if default not in ("NULL", "''") else ""}
                {" NOT NULL" if default not in ("NULL",) and col_type == "BOOLEAN" else ""};
            END IF;
        END $$;
    """))


def create_all() -> None:
    print("Connecting to database...")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Connected.")

    # ── 1. New PG enum types ──────────────────────────────────────────────────
    print("Ensuring new enum types...")
    with engine.begin() as conn:
        for type_name, values in _NEW_PG_ENUMS.items():
            _create_enum_if_not_exists(conn, type_name, values)

    # ── 2. New values on existing enums ───────────────────────────────────────
    # Must be outside a transaction that already made DDL changes
    print("Adding new enum values...")
    for value in _RECORD_STATUS_NEW_VALUES:
        with engine.begin() as conn:
            _add_enum_value(conn, "record_status_enum", value)

    for value in _INVOICE_MATCH_STATUS_NEW_VALUES:
        with engine.begin() as conn:
            try:
                _add_enum_value(conn, "invoice_match_status_enum", value)
            except Exception:
                pass  # type may not exist yet on fresh DB

    for value in _ALERT_TYPE_NEW_VALUES:
        with engine.begin() as conn:
            try:
                _add_enum_value(conn, "alert_type_enum", value)
            except Exception:
                pass

    # ── 3. Create all NEW tables from models ──────────────────────────────────
    print("Creating tables (new ones only)...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    # ── 4. Add new columns to existing tables ─────────────────────────────────
    print("Adding new columns to existing tables...")
    for table, column, col_type, default in _NEW_COLUMNS:
        with engine.begin() as conn:
            try:
                _add_column_if_not_exists(conn, table, column, col_type, default)
            except Exception as exc:
                print(f"  Warning: {table}.{column} — {exc}")

    # ── 4b. Drop NOT NULL constraints on columns we made nullable ────────────────
    print("Relaxing NOT NULL constraints on updated columns...")
    nullable_fixes = [
        # (table, column) — remove NOT NULL if column was made nullable in the ORM
        ("material_request_items", "item_id"),
    ]
    for table, column in nullable_fixes:
        with engine.begin() as conn:
            try:
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = '{table}'
                            AND column_name = '{column}'
                            AND is_nullable = 'NO'
                        ) THEN
                            ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL;
                        END IF;
                    END $$;
                """))
            except Exception as exc:
                print(f"  Warning: relax {table}.{column} NOT NULL — {exc}")

    # ── 5. Materialized view ──────────────────────────────────────────────────
    print("Ensuring stock_balances materialized view...")
    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_matviews WHERE matviewname = 'stock_balances'
                ) THEN
                    CREATE MATERIALIZED VIEW stock_balances AS
                    SELECT
                        project_id,
                        site_id,
                        lot_id,
                        item_id,
                        SUM(quantity_in) - SUM(quantity_out) AS balance,
                        MAX(movement_date) AS last_movement_date
                    FROM stock_ledger
                    GROUP BY project_id, site_id, lot_id, item_id;

                    CREATE UNIQUE INDEX ix_stock_balances_unique
                    ON stock_balances (
                        project_id, site_id, item_id,
                        COALESCE(lot_id, '00000000-0000-0000-0000-000000000000'::uuid)
                    );
                END IF;
            END $$;
        """))
    print("Materialized view ready.")
    print("\nDatabase setup complete.")


if __name__ == "__main__":
    create_all()
