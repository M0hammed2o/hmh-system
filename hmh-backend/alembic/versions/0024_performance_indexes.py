"""Performance indexes — Phase 3R.1

Adds missing indexes identified in production audit:

stock_ledger:
  - ix_stock_ledger_site_id           : warehouse site queries use site_id in WHERE
  - ix_stock_ledger_movement_date     : history queries ORDER BY movement_date DESC
  - ix_stock_ledger_lot_item          : composite (lot_id, item_id) for lot-level aggregations

system_alerts:
  - ix_system_alerts_project_status_type : _already_open() uses (project_id, status, alert_type)

notification_queue:
  - ix_notification_queue_status_next_attempt : queue processor filters (status, next_attempt_at)

All CREATE INDEX statements use IF NOT EXISTS for idempotency.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_ledger_site_id "
        "ON stock_ledger(site_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_ledger_movement_date "
        "ON stock_ledger(movement_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_ledger_lot_item "
        "ON stock_ledger(lot_id, item_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_system_alerts_project_status_type "
        "ON system_alerts(project_id, status, alert_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_queue_status_next_attempt "
        "ON notification_queue(status, next_attempt_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notification_queue_status_next_attempt")
    op.execute("DROP INDEX IF EXISTS ix_system_alerts_project_status_type")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_lot_item")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_movement_date")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_site_id")
