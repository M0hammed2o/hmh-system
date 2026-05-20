"""Add PAYMENT and FUEL_LOG to attachment_entity_enum.

Revision ID: 0014
Revises:     0013
Create Date: 2026-05-20
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'PAYMENT'")
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'FUEL_LOG'")


def downgrade() -> None:
    pass
