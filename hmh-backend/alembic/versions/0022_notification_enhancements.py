"""Phase 3Q.1 — notification infrastructure enhancements.

Revision ID: 0022
Revises:     0021
Create Date: 2026-05-22

Changes:

  alert_type_enum — 9 new operational alert types:
    MR_APPROVED, PO_SENT_ALERT, DELIVERY_RECEIVED_ALERT,
    WAREHOUSE_TRANSFER_COMPLETED, INVOICE_CAPTURED,
    PAYMENT_COMPLETED, PARTIAL_PAYMENT_RECORDED,
    MILESTONE_COMPLETED_ALERT, MILESTONE_DELAYED_ALERT

  alert_recipients — 4 new columns:
    receives_procurement_alerts  BOOLEAN NOT NULL DEFAULT FALSE
    receives_milestone_alerts    BOOLEAN NOT NULL DEFAULT FALSE
    receives_payment_alerts      BOOLEAN NOT NULL DEFAULT FALSE
    project_id                   UUID nullable FK projects(id) SET NULL
      NULL = recipient gets alerts from ALL projects
      Non-NULL = recipient only gets alerts for that project

  notification_queue — 3 new columns:
    project_id   UUID nullable  (context for filtering and display)
    entity_type  VARCHAR(50)    (e.g. 'purchase_order', 'invoice')
    entity_id    UUID nullable  (deep-link to triggering record)

ROLLBACK:
  DROP COLUMN for the 7 new columns.
  alert_type_enum values cannot be removed.
"""

from alembic import op

revision      = "0022"
down_revision = "0021"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── New alert types ───────────────────────────────────────────────────────
    for val in [
        "MR_APPROVED",
        "PO_SENT_ALERT",
        "DELIVERY_RECEIVED_ALERT",
        "WAREHOUSE_TRANSFER_COMPLETED",
        "INVOICE_CAPTURED",
        "PAYMENT_COMPLETED",
        "PARTIAL_PAYMENT_RECORDED",
        "MILESTONE_COMPLETED_ALERT",
        "MILESTONE_DELAYED_ALERT",
    ]:
        op.execute(f"ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS '{val}'")

    # ── alert_recipients: new category flags + project scope ─────────────────
    # Use ADD COLUMN IF NOT EXISTS so this migration is idempotent when run
    # on a DB that already has these columns (e.g. dev DB patched by conftest).
    op.execute("""
        ALTER TABLE alert_recipients
        ADD COLUMN IF NOT EXISTS receives_procurement_alerts BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE alert_recipients
        ADD COLUMN IF NOT EXISTS receives_milestone_alerts BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE alert_recipients
        ADD COLUMN IF NOT EXISTS receives_payment_alerts BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE alert_recipients
        ADD COLUMN IF NOT EXISTS project_id UUID
    """)

    # FK — idempotent via exception handler
    op.execute("""
        DO $body$ BEGIN
            ALTER TABLE alert_recipients
            ADD CONSTRAINT alert_recipients_project_id_fkey
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $body$
    """)

    # ── notification_queue: entity context columns ────────────────────────────
    op.execute("""
        ALTER TABLE notification_queue
        ADD COLUMN IF NOT EXISTS project_id UUID
    """)
    op.execute("""
        ALTER TABLE notification_queue
        ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50)
    """)
    op.execute("""
        ALTER TABLE notification_queue
        ADD COLUMN IF NOT EXISTS entity_id UUID
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_notification_queue_project_id
        ON notification_queue(project_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notification_queue_project_id")
    op.execute("ALTER TABLE notification_queue DROP COLUMN IF EXISTS entity_id")
    op.execute("ALTER TABLE notification_queue DROP COLUMN IF EXISTS entity_type")
    op.execute("ALTER TABLE notification_queue DROP COLUMN IF EXISTS project_id")

    op.execute("""
        ALTER TABLE alert_recipients
        DROP CONSTRAINT IF EXISTS alert_recipients_project_id_fkey
    """)
    op.execute("ALTER TABLE alert_recipients DROP COLUMN IF EXISTS project_id")
    op.execute("ALTER TABLE alert_recipients DROP COLUMN IF EXISTS receives_payment_alerts")
    op.execute("ALTER TABLE alert_recipients DROP COLUMN IF EXISTS receives_milestone_alerts")
    op.execute("ALTER TABLE alert_recipients DROP COLUMN IF EXISTS receives_procurement_alerts")
    # alert_type_enum values cannot be removed
