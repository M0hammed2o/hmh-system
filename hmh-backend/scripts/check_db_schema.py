"""
Database schema diagnostic tool.

Compares SQLAlchemy ORM model definitions against the live connected database
and reports discrepancies that would cause runtime failures.

Run locally or in Render Shell:
    python scripts/check_db_schema.py

Exit codes:
    0 — schema matches (safe to deploy)
    1 — warnings found (review before deploying)
    2 — critical issues found (fix before deploying)
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal

import app.models  # noqa: F401 — registers all models on Base.metadata


# ── Columns that are GENERATED ALWAYS AS STORED — never writable ──────────────
# These must be in the DB as computed/generated columns.
KNOWN_GENERATED = {
    "boq_items": {"planned_total"},
    "fuel_logs":  {"total_cost"},
}


def _get_alembic_revision(bind) -> Optional[str]:
    try:
        result = bind.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).fetchone()
        return str(result[0]) if result else None
    except Exception:
        return None


def _get_generated_columns(inspector: sa.Inspector, table: str) -> set[str]:
    """
    Return the set of column names that are GENERATED ALWAYS in the live DB.
    Works on PostgreSQL; returns empty set on other dialects.
    """
    try:
        result = inspector._bind.execute(sa.text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND is_generated = 'ALWAYS'
        """)).fetchall()
        return {r[0] for r in result}
    except Exception:
        return set()


def run_check() -> int:
    """
    Returns:
        0 = all OK
        1 = warnings (non-blocking)
        2 = critical errors (will cause 500s in production)
    """
    print("=" * 65)
    print("HMH Database Schema Check")
    print(f"DATABASE_URL: {settings.DATABASE_URL[:40]}...")
    print("=" * 65)

    engine = sa.create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    inspector = sa.inspect(engine)

    with engine.connect() as conn:
        revision = _get_alembic_revision(conn)
    print(f"Alembic revision : {revision or 'UNKNOWN / NOT APPLIED'}")
    print()

    live_tables = set(inspector.get_table_names())
    orm_tables  = set(Base.metadata.tables.keys())

    warnings  = []
    criticals = []

    # ── 1. Missing tables ─────────────────────────────────────────────────────
    missing_tables = orm_tables - live_tables
    extra_tables   = live_tables - orm_tables - {"alembic_version"}
    if missing_tables:
        for t in sorted(missing_tables):
            criticals.append(f"TABLE MISSING in DB: '{t}' — run 'alembic upgrade head'")
    if extra_tables:
        for t in sorted(extra_tables):
            warnings.append(f"Extra table in DB (no ORM model): '{t}'")

    # ── 2. Per-table column checks ────────────────────────────────────────────
    for table_name in sorted(orm_tables & live_tables):
        orm_table     = Base.metadata.tables[table_name]
        live_cols_raw = inspector.get_columns(table_name)
        live_cols     = {c["name"]: c for c in live_cols_raw}

        # Generated columns in the live DB
        gen_live = _get_generated_columns(inspector, table_name)

        for col in orm_table.columns:
            col_name = col.name
            is_computed_in_model = hasattr(col, "computed") and col.computed is not None

            if col_name not in live_cols:
                criticals.append(
                    f"COLUMN MISSING in DB: '{table_name}.{col_name}' — "
                    f"run 'alembic upgrade head'"
                )
                continue

            lc = live_cols[col_name]

            # Check nullable mismatch
            orm_nullable  = col.nullable
            live_nullable = lc.get("nullable", True)
            if orm_nullable != live_nullable:
                warnings.append(
                    f"NULLABLE MISMATCH: '{table_name}.{col_name}' "
                    f"ORM={orm_nullable} DB={live_nullable}"
                )

            # Check generated column consistency
            known_gen = KNOWN_GENERATED.get(table_name, set())
            if col_name in known_gen:
                if col_name not in gen_live:
                    warnings.append(
                        f"GENERATED COLUMN NOT GENERATED in DB: "
                        f"'{table_name}.{col_name}' — "
                        f"model says GENERATED ALWAYS but DB has plain column"
                    )
                if not is_computed_in_model:
                    criticals.append(
                        f"ORM MISSING Computed(): '{table_name}.{col_name}' — "
                        f"add Computed(persisted=True) to the ORM model so "
                        f"SQLAlchemy never inserts this column"
                    )
            elif col_name in gen_live and not is_computed_in_model:
                warnings.append(
                    f"UNEXPECTED GENERATED COLUMN: '{table_name}.{col_name}' is "
                    f"GENERATED ALWAYS in DB but ORM model does not declare it — "
                    f"ORM inserts will fail with 'cannot insert into column'"
                )

        # Extra columns (in DB but not in ORM) — informational only
        orm_col_names = {c.name for c in orm_table.columns}
        for lc_name in live_cols:
            if lc_name not in orm_col_names:
                warnings.append(
                    f"Extra column in DB (no ORM field): '{table_name}.{lc_name}'"
                )

    # ── 3. Print results ──────────────────────────────────────────────────────
    print(f"ORM tables       : {len(orm_tables)}")
    print(f"Live DB tables   : {len(live_tables)}")
    print(f"Criticals        : {len(criticals)}")
    print(f"Warnings         : {len(warnings)}")
    print()

    if criticals:
        print("CRITICAL ISSUES (will cause 500 errors in production):")
        for c in criticals:
            print(f"  [CRITICAL] {c}")
        print()

    if warnings:
        print("WARNINGS (review before deploying):")
        for w in warnings:
            print(f"  [WARN]     {w}")
        print()

    if not criticals and not warnings:
        print("  All OK — ORM models match live database schema.")
    elif not criticals:
        print("  No critical issues. Review warnings above.")

    print("=" * 65)

    if criticals:
        return 2
    if warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_check())
