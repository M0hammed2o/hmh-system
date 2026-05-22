"""Add milestone completion fields to project_stage_status.

Revision ID: 0017
Revises:     0016
Create Date: 2026-05-21

Phase 3J — Milestones System Completion.

Changes (all additive, non-destructive):

  stage_status_enum: ADD VALUE 'BLOCKED'
    Milestone was blocked by an external dependency.
    NOTE: PostgreSQL enum values cannot be removed — this is intentional.

  project_stage_status columns:
    completion_notes   TEXT              nullable  — notes recorded at completion
    completed_by_name  VARCHAR(255)      nullable  — who marked it complete (free text)
    progress_pct       SMALLINT NOT NULL DEFAULT 0 — manual progress percentage (0-100)
    blocked_reason     TEXT              nullable  — reason milestone is blocked

ROLLBACK:
  ALTER TABLE project_stage_status
    DROP COLUMN blocked_reason,
    DROP COLUMN progress_pct,
    DROP COLUMN completed_by_name,
    DROP COLUMN completion_notes;
  (BLOCKED enum value cannot be removed but causes no harm)
"""

import sqlalchemy as sa
from alembic import op

revision      = "0017"
down_revision = "0016"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. Add BLOCKED to the stage status enum
    op.execute("ALTER TYPE stage_status_enum ADD VALUE IF NOT EXISTS 'BLOCKED'")

    # 2. Add completion tracking columns
    op.add_column(
        "project_stage_status",
        sa.Column("completion_notes",  sa.Text(),         nullable=True),
    )
    op.add_column(
        "project_stage_status",
        sa.Column("completed_by_name", sa.String(255),    nullable=True),
    )
    op.add_column(
        "project_stage_status",
        sa.Column(
            "progress_pct",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "project_stage_status",
        sa.Column("blocked_reason",    sa.Text(),         nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_stage_status", "blocked_reason")
    op.drop_column("project_stage_status", "progress_pct")
    op.drop_column("project_stage_status", "completed_by_name")
    op.drop_column("project_stage_status", "completion_notes")
    # BLOCKED enum value cannot be removed from PostgreSQL
