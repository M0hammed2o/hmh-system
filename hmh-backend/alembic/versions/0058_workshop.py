"""Add workshop module — categories, items, stock, supplier links, MRs, issuances.

Revision ID: 0058
Revises:     0057
Create Date: 2026-07-06
"""

from alembic import op
from sqlalchemy import text

revision      = "0058"
down_revision = "0057"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_categories (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_items (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id     UUID NOT NULL REFERENCES workshop_categories(id) ON DELETE RESTRICT,
            name            VARCHAR(300) NOT NULL,
            part_number     VARCHAR(100),
            unit            VARCHAR(50) NOT NULL DEFAULT 'each',
            description     TEXT,
            reorder_level   NUMERIC(14,3),
            is_active       BOOLEAN NOT NULL DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_workshop_items_category_id ON workshop_items(category_id)"
    ))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_stock (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id           UUID NOT NULL UNIQUE REFERENCES workshop_items(id) ON DELETE CASCADE,
            quantity_on_hand  NUMERIC(14,3) NOT NULL DEFAULT 0,
            last_updated      TIMESTAMPTZ
        )
    """))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_supplier_links (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id  UUID NOT NULL REFERENCES workshop_categories(id) ON DELETE CASCADE,
            supplier_id  UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            is_preferred BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT uq_workshop_supplier_category UNIQUE (category_id, supplier_id)
        )
    """))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_workshop_supplier_links_category_id ON workshop_supplier_links(category_id)"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_workshop_supplier_links_supplier_id ON workshop_supplier_links(supplier_id)"
    ))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_mrs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mr_number        VARCHAR(50) NOT NULL UNIQUE,
            site_id          UUID NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
            vehicle_id       UUID NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
            reason           TEXT NOT NULL,
            status           record_status_enum NOT NULL DEFAULT 'DRAFT',
            priority         mr_priority_enum NOT NULL DEFAULT 'NORMAL',
            needed_by_date   DATE,
            requested_by     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            approved_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at      TIMESTAMPTZ,
            rejection_reason TEXT,
            notes            TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_mrs_site_id    ON workshop_mrs(site_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_mrs_vehicle_id ON workshop_mrs(vehicle_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_mrs_status     ON workshop_mrs(status)"))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_mr_lines (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id       UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            item_id              UUID NOT NULL REFERENCES workshop_items(id) ON DELETE RESTRICT,
            quantity_requested   NUMERIC(14,3) NOT NULL,
            quantity_approved    NUMERIC(14,3),
            preferred_supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            remarks              TEXT
        )
    """))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_workshop_mr_lines_workshop_mr_id ON workshop_mr_lines(workshop_mr_id)"
    ))

    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_issuances (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id          UUID NOT NULL REFERENCES workshop_items(id) ON DELETE RESTRICT,
            vehicle_id       UUID NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
            workshop_mr_id   UUID REFERENCES workshop_mrs(id) ON DELETE SET NULL,
            quantity_issued  NUMERIC(14,3) NOT NULL,
            issued_by        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            issued_at        TIMESTAMPTZ NOT NULL,
            notes            TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_issuances_item_id        ON workshop_issuances(item_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_issuances_vehicle_id     ON workshop_issuances(vehicle_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_workshop_issuances_workshop_mr_id ON workshop_issuances(workshop_mr_id)"))

    print("[0058] Workshop module tables created.", flush=True)


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS workshop_issuances"))
    op.execute(text("DROP TABLE IF EXISTS workshop_mr_lines"))
    op.execute(text("DROP TABLE IF EXISTS workshop_mrs"))
    op.execute(text("DROP TABLE IF EXISTS workshop_supplier_links"))
    op.execute(text("DROP TABLE IF EXISTS workshop_stock"))
    op.execute(text("DROP TABLE IF EXISTS workshop_items"))
    op.execute(text("DROP TABLE IF EXISTS workshop_categories"))
