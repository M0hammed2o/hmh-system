"""companies — Company model, company_supplier_links, and projects.company_id

Revision ID: 0065
Revises: 0064
Create Date: 2026-07-09
"""

from alembic import op
from sqlalchemy import text

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS companies (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                VARCHAR(255) NOT NULL UNIQUE,
            registration_number VARCHAR(100),
            contact_email       VARCHAR(255),
            contact_phone       VARCHAR(50),
            address             TEXT,
            notes               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS company_supplier_links (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            CONSTRAINT uq_company_supplier_links UNIQUE (company_id, supplier_id)
        );

        CREATE INDEX IF NOT EXISTS ix_company_supplier_links_company_id
            ON company_supplier_links (company_id);
        CREATE INDEX IF NOT EXISTS ix_company_supplier_links_supplier_id
            ON company_supplier_links (supplier_id);

        ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS company_id UUID
                REFERENCES companies(id) ON DELETE SET NULL;

        CREATE INDEX IF NOT EXISTS ix_projects_company_id ON projects (company_id);
    """))


def downgrade() -> None:
    op.execute(text("""
        ALTER TABLE projects DROP COLUMN IF EXISTS company_id;
        DROP TABLE IF EXISTS company_supplier_links;
        DROP TABLE IF EXISTS companies;
    """))
