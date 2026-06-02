"""Make material_requests.project_id and site_id nullable for main warehouse MRs

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # project_id: drop NOT NULL, keep CASCADE FK
    op.execute("ALTER TABLE material_requests ALTER COLUMN project_id DROP NOT NULL")

    # site_id: drop NOT NULL, switch FK to SET NULL so deleting a site doesn't cascade-delete MRs
    op.execute("ALTER TABLE material_requests ALTER COLUMN site_id DROP NOT NULL")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.referential_constraints
                WHERE constraint_name = 'material_requests_site_id_fkey'
            ) THEN
                ALTER TABLE material_requests DROP CONSTRAINT material_requests_site_id_fkey;
            END IF;
            ALTER TABLE material_requests
                ADD CONSTRAINT material_requests_site_id_fkey
                FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END
        $$
    """)


def downgrade() -> None:
    op.alter_column("material_requests", "project_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column("material_requests", "site_id", existing_type=sa.UUID(), nullable=False)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.referential_constraints
                WHERE constraint_name = 'material_requests_site_id_fkey'
            ) THEN
                ALTER TABLE material_requests DROP CONSTRAINT material_requests_site_id_fkey;
            END IF;
            ALTER TABLE material_requests
                ADD CONSTRAINT material_requests_site_id_fkey
                FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END
        $$
    """)
