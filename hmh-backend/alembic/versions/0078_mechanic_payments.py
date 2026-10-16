"""Mechanic payment tracking.

Revision ID: 0078
Revises: 0077
Create Date: 2026-10-16

Records payments made to mechanics and workshops for vehicle repairs, so the
office can see what is still owed on each job.

Additive only: one new table. Nothing existing is altered, so a backend
running the previous build is unaffected by this migration.

What is owed is NOT stored here — it is derived from the repair's invoiced
amount, quoted amount or booked costs. A stored copy would be free to drift
from the figure the books use, and would risk recognising the same repair
cost a second time.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mechanic_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("repair_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mechanic_name", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("proof_file_url", sa.String(500), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        # RESTRICT, not CASCADE: a repair or supplier with payments recorded
        # against it is financial history and must not be deletable out from
        # under them.
        sa.ForeignKeyConstraint(["repair_job_id"], ["repair_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("amount > 0", name="ck_mechanic_payments_amount_positive"),
    )

    op.create_index("ix_mechanic_payments_repair_job_id", "mechanic_payments", ["repair_job_id"])
    op.create_index("ix_mechanic_payments_repair", "mechanic_payments",
                    ["repair_job_id", "payment_date"])
    op.create_index("ix_mechanic_payments_supplier", "mechanic_payments", ["supplier_id"])

    # A double-tapped submit or retried request must not record the same
    # payment twice. Only where a reference was given — cash payments often
    # have none and blanks must not collide — and only while the payment
    # stands, so a reversed one can be re-captured correctly.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_mechanic_payments_live_reference
            ON mechanic_payments (repair_job_id, lower(trim(payment_reference)))
            WHERE payment_reference IS NOT NULL AND reversed_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("uq_mechanic_payments_live_reference", table_name="mechanic_payments")
    op.drop_index("ix_mechanic_payments_supplier", table_name="mechanic_payments")
    op.drop_index("ix_mechanic_payments_repair", table_name="mechanic_payments")
    op.drop_index("ix_mechanic_payments_repair_job_id", table_name="mechanic_payments")
    op.drop_table("mechanic_payments")
