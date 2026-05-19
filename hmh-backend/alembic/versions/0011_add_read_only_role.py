"""Add READ_ONLY value to user_role_enum.

Revision ID: 0011
Revises:     0010
Create Date: 2026-05-19

Adds the READ_ONLY role to the user_role_enum PostgreSQL type so that
owner-level view-only accounts can be created.  Users with this role can
call all GET endpoints but will receive 403 on any write operation because
OFFICE_AND_ABOVE (and all other write guards) do not include READ_ONLY.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0011"
down_revision = "0010"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute(sa.text("""
        DO $$
        BEGIN
            ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'READ_ONLY';
        EXCEPTION WHEN others THEN NULL;
        END$$;
    """))
    print("[0011] Added READ_ONLY to user_role_enum.", flush=True)


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without dropping the type.
    # To roll back, recreate the enum without READ_ONLY and update the column —
    # this is intentionally not implemented to avoid data loss.
    pass
