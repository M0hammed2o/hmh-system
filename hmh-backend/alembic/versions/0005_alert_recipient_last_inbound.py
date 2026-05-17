"""Add last_inbound_at to alert_recipients for 24-hour window tracking.

Revision ID: 0005
Revises:     0004
Create Date: 2026-05-17

Adds alert_recipients.last_inbound_at (nullable TIMESTAMPTZ).
Set by the WhatsApp webhook every time a registered recipient sends us
a message. Used by notification_service to decide whether to send a
free-form text (within 24h) or an approved template (outside 24h).

NULL means the recipient has never messaged us — always use template.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0005"
down_revision = "0004"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = [c["name"] for c in insp.get_columns("alert_recipients")]
    if "last_inbound_at" not in cols:
        op.add_column(
            "alert_recipients",
            sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        )
        print("[0005] ADDED col 'last_inbound_at' → 'alert_recipients'.", flush=True)
    else:
        print("[0005] SKIP col 'last_inbound_at': already exists.", flush=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = [c["name"] for c in insp.get_columns("alert_recipients")]
    if "last_inbound_at" in cols:
        op.drop_column("alert_recipients", "last_inbound_at")
