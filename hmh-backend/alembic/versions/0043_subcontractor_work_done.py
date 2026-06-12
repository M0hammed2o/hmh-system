"""0043_subcontractor_work_done

Phase 6B — Subcontractor Work Done / Progress Claim module.

Creates:
  - work_done_status_enum PostgreSQL type
  - subcontractor_work_done table

Extends:
  - attachment_entity_enum: adds WORK_DONE value

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum only if it does not already exist.
    # Production may have a partial version of this type from a failed prior attempt.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'work_done_status_enum') THEN
                CREATE TYPE work_done_status_enum AS ENUM (
                    'DRAFT', 'SUBMITTED', 'SITE_APPROVED', 'OFFICE_APPROVED', 'PAID', 'REJECTED'
                );
            END IF;
        END
        $$
    """)

    # Ensure every required value is present — no-op if value already exists.
    # This handles the case where the type existed with a different set of values.
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'DRAFT'")
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'SUBMITTED'")
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'SITE_APPROVED'")
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'OFFICE_APPROVED'")
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'PAID'")
    op.execute("ALTER TYPE work_done_status_enum ADD VALUE IF NOT EXISTS 'REJECTED'")

    # Extend attachment entity enum
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'WORK_DONE'")

    # Main table
    op.create_table(
        "subcontractor_work_done",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("work_done_number", sa.String(60), nullable=False, unique=True, index=True),

        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("site_id",    UUID(as_uuid=True), sa.ForeignKey("sites.id",    ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id",     UUID(as_uuid=True), sa.ForeignKey("lots.id",     ondelete="SET NULL"), nullable=True),
        sa.Column("stage_status_id", UUID(as_uuid=True), sa.ForeignKey("project_stage_status.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("job_card_id", UUID(as_uuid=True), sa.ForeignKey("job_cards.id", ondelete="SET NULL"), nullable=True),

        sa.Column("work_description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False, server_default="1"),
        sa.Column("unit",     sa.String(50), nullable=True),
        sa.Column("rate",     sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("amount",   sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("month",    sa.Date, nullable=False, index=True),
        sa.Column("comments", sa.Text, nullable=True),

        sa.Column("status", sa.Enum(name="work_done_status_enum", create_type=False), nullable=False, server_default="DRAFT", index=True),

        # Approval chain
        sa.Column("submitted_by",      UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("site_approved_by",  UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("site_approved_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("office_approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("office_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by",           UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paid_at",           sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason",  sa.Text, nullable=True),
        sa.Column("created_by",        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("subcontractor_work_done")
    op.execute("DROP TYPE IF EXISTS work_done_status_enum")
    # Note: attachment_entity_enum WORK_DONE value cannot be removed from PostgreSQL
