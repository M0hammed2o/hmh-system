"""Fix remaining 21 critical column gaps after 0003.

Revision ID: 0004
Revises:     0003
Create Date: 2026-05-16

Tables patched:
  attachments          — stored_path, uploaded_at, is_active
  fuel_logs            — equipment_ref, fuelled_by, fuel_date
  item_aliases         — alias_name
  item_categories      — is_active
  items                — normalized_name, requires_remaining_photo, is_high_risk, notes
  payments             — payment_reference, amount_paid, approved_by, captured_by
  suppliers            — code, contact_person, whatsapp_number, payment_terms
  usage_remaining_proofs — photo_attachment_id

All additions are idempotent (ADD COLUMN IF NOT EXISTS via helper).
New columns that are NOT NULL in the ORM are added as nullable here so
existing rows are not rejected; the schema check will show warnings
(nullable mismatches) rather than criticals (missing columns).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0004"
down_revision = "0003"
branch_labels = None
depends_on    = None


# ── Helpers (same pattern as 0002 / 0003) ────────────────────────────────────

def _table_exists(insp: sa.Inspector, table: str) -> bool:
    return table in insp.get_table_names()


def _add_col(table: str, col_name: str, col_def: sa.Column) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, table):
        print(f"[0004] SKIP col '{col_name}': table '{table}' does not exist.")
        return
    existing = [c["name"] for c in insp.get_columns(table)]
    if col_name not in existing:
        op.add_column(table, col_def)
        print(f"[0004] ADDED col '{col_name}' → '{table}'.")
    else:
        print(f"[0004] SKIP col '{col_name}': already in '{table}'.")


def _create_idx(idx_name: str, table: str, cols: list, **kwargs) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, table):
        return
    existing = [i["name"] for i in insp.get_indexes(table)]
    if idx_name not in existing:
        op.create_index(idx_name, table, cols, **kwargs)


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:

    # ── attachments ───────────────────────────────────────────────────────────
    # ORM: stored_path NOT NULL, uploaded_at NOT NULL, is_active NOT NULL
    _add_col("attachments", "stored_path",
        sa.Column("stored_path", sa.Text, nullable=True))           # nullable — existing rows have file_url
    _add_col("attachments", "uploaded_at",
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()))    # safe default
    _add_col("attachments", "is_active",
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"))

    # ── fuel_logs ─────────────────────────────────────────────────────────────
    # ORM: equipment_ref nullable, fuelled_by nullable, fuel_date NOT NULL
    _add_col("fuel_logs", "equipment_ref",
        sa.Column("equipment_ref", sa.String(200), nullable=True))
    _add_col("fuel_logs", "fuelled_by",
        sa.Column("fuelled_by", sa.String(200), nullable=True))
    _add_col("fuel_logs", "fuel_date",
        sa.Column("fuel_date", sa.DateTime(timezone=True),
                  nullable=True))                                   # nullable — existing rows may use log_date

    # ── item_aliases ──────────────────────────────────────────────────────────
    # ORM: alias_name NOT NULL UNIQUE
    _add_col("item_aliases", "alias_name",
        sa.Column("alias_name", sa.String(255), nullable=True))     # nullable — existing rows have 'alias'
    _create_idx("ix_item_aliases_alias_name", "item_aliases", ["alias_name"], unique=True)

    # ── item_categories ───────────────────────────────────────────────────────
    _add_col("item_categories", "is_active",
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"))

    # ── items ─────────────────────────────────────────────────────────────────
    # ORM: normalized_name NOT NULL index, requires_remaining_photo NOT NULL,
    #      is_high_risk NOT NULL, notes nullable
    _add_col("items", "normalized_name",
        sa.Column("normalized_name", sa.String(255), nullable=True)) # nullable — no good default for existing rows
    _create_idx("ix_items_normalized_name", "items", ["normalized_name"])

    _add_col("items", "requires_remaining_photo",
        sa.Column("requires_remaining_photo", sa.Boolean, nullable=False, server_default="false"))
    _add_col("items", "is_high_risk",
        sa.Column("is_high_risk", sa.Boolean, nullable=False, server_default="false"))
    _add_col("items", "notes",
        sa.Column("notes", sa.Text, nullable=True))

    # ── payments ──────────────────────────────────────────────────────────────
    # ORM: payment_reference nullable, amount_paid NOT NULL,
    #      approved_by nullable FK, captured_by nullable FK
    _add_col("payments", "payment_reference",
        sa.Column("payment_reference", sa.String(100), nullable=True))
    _add_col("payments", "amount_paid",
        sa.Column("amount_paid", sa.Numeric(14, 2),
                  nullable=True))                                   # nullable — existing rows have 'amount'
    _add_col("payments", "approved_by",
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    _add_col("payments", "captured_by",
        sa.Column("captured_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))

    # ── suppliers ─────────────────────────────────────────────────────────────
    _add_col("suppliers", "code",
        sa.Column("code", sa.String(100), nullable=True))
    _add_col("suppliers", "contact_person",
        sa.Column("contact_person", sa.String(255), nullable=True))
    _add_col("suppliers", "whatsapp_number",
        sa.Column("whatsapp_number", sa.String(50), nullable=True))
    _add_col("suppliers", "payment_terms",
        sa.Column("payment_terms", sa.String(100), nullable=True))

    # ── usage_remaining_proofs ────────────────────────────────────────────────
    # ORM: photo_attachment_id NOT NULL FK → attachments
    _add_col("usage_remaining_proofs", "photo_attachment_id",
        sa.Column("photo_attachment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("attachments.id", ondelete="CASCADE"),
                  nullable=True))                                   # nullable — existing rows have image_url


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def _drop_col(table: str, col: str) -> None:
        if not _table_exists(insp, table):
            return
        if col in [c["name"] for c in insp.get_columns(table)]:
            op.drop_column(table, col)

    _drop_col("usage_remaining_proofs", "photo_attachment_id")

    _drop_col("suppliers", "payment_terms")
    _drop_col("suppliers", "whatsapp_number")
    _drop_col("suppliers", "contact_person")
    _drop_col("suppliers", "code")

    _drop_col("payments", "captured_by")
    _drop_col("payments", "approved_by")
    _drop_col("payments", "amount_paid")
    _drop_col("payments", "payment_reference")

    _drop_col("items", "notes")
    _drop_col("items", "is_high_risk")
    _drop_col("items", "requires_remaining_photo")
    _drop_col("items", "normalized_name")

    _drop_col("item_categories", "is_active")

    _drop_col("item_aliases", "alias_name")

    _drop_col("fuel_logs", "fuel_date")
    _drop_col("fuel_logs", "fuelled_by")
    _drop_col("fuel_logs", "equipment_ref")

    _drop_col("attachments", "is_active")
    _drop_col("attachments", "uploaded_at")
    _drop_col("attachments", "stored_path")
