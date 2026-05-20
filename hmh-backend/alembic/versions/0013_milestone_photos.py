"""Add STAGE_STATUS to attachment_entity_enum for milestone photo storage.

Revision ID: 0013
Revises:     0012
Create Date: 2026-05-20
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the new enum value to the existing PostgreSQL enum type.
    # ALTER TYPE ... ADD VALUE is transactional in Postgres 12+.
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'STAGE_STATUS'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
