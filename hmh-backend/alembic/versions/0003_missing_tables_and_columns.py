"""Add missing tables and columns to reach zero schema criticals.

Revision ID: 0003
Revises:     0002
Create Date: 2026-05-16

Idempotent:
- New tables   → CREATE TABLE IF NOT EXISTS (raw SQL)
- New columns  → _add_col() helper (ADD COLUMN IF NOT EXISTS)
- New enums    → DO $$ IF NOT EXISTS $$ pattern
- Enum values  → ALTER TYPE ... ADD VALUE IF NOT EXISTS

Tables added (13):
  alert_recipients, boq_adjustments, delivery_verification_items,
  delivery_verifications, document_extractions, expense_records,
  incoming_emails, incoming_email_attachments, job_cards,
  mr_email_logs, mr_quotes, notification_queue, project_stage_status

Columns added to existing tables:
  sites, material_requests, material_request_items,
  purchase_orders, purchase_order_items, po_email_logs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0003"
down_revision = "0002"
branch_labels = None
depends_on    = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _table_exists(insp: sa.Inspector, table: str) -> bool:
    return table in insp.get_table_names()


def _add_col(table: str, col_name: str, col_def: sa.Column) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, table):
        print(f"[0003] SKIP col '{col_name}': table '{table}' does not exist.")
        return
    existing = [c["name"] for c in insp.get_columns(table)]
    if col_name not in existing:
        op.add_column(table, col_def)
        print(f"[0003] ADDED col '{col_name}' → '{table}'.")
    else:
        print(f"[0003] SKIP col '{col_name}': already in '{table}'.")


def _create_idx(idx_name: str, table: str, cols: list, **kwargs) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, table):
        return
    existing = [i["name"] for i in insp.get_indexes(table)]
    if idx_name not in existing:
        op.create_index(idx_name, table, cols, **kwargs)


def _create_enum(type_name: str, values: list) -> None:
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{type_name}') THEN
        CREATE TYPE {type_name} AS ENUM ({vals});
    END IF;
END$$;
"""))


def _add_enum_value(type_name: str, value: str) -> None:
    op.execute(sa.text(f"""
DO $$
BEGIN
    ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}';
EXCEPTION WHEN others THEN NULL;
END$$;
"""))


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:

    # ── 1. New enum types ─────────────────────────────────────────────────────
    _create_enum("mr_priority_enum",          ["URGENT", "HIGH", "NORMAL", "LOW"])
    _create_enum("delivery_destination_enum", ["MAIN_WAREHOUSE", "SITE_STORE", "LOT"])
    _create_enum("job_card_status_enum", [
        "DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED",
        "OWNER_APPROVED", "PAYMENT_APPROVED", "PAID", "REJECTED",
    ])
    _create_enum("job_card_work_type_enum",   ["DAILY_LABOUR", "CONTRACT", "SUBCONTRACTOR", "OVERTIME"])
    _create_enum("notification_channel_enum", ["WHATSAPP", "EMAIL", "IN_APP"])
    _create_enum("notification_status_enum",  ["PENDING", "SENT", "FAILED", "MOCK_SENT", "ACKNOWLEDGED", "CANCELLED"])

    # ── 2. Extend existing enum types ─────────────────────────────────────────
    for v in ("PENDING_APPROVAL", "CONVERTED_TO_PO", "ORDERED", "PARTIALLY_RECEIVED", "CLOSED"):
        _add_enum_value("record_status_enum", v)

    for v in (
        "BOQ_ALLOCATION_EXCEEDED", "DELIVERY_MISMATCH", "DELIVERY_NOTE_MISSING",
        "SIGNATURE_MISSING", "INVOICE_UNMATCHED", "FUEL_USAGE_HIGH",
        "LOT_DELAYED", "STAGE_DELAYED", "DAILY_SUMMARY", "WEEKLY_SUMMARY",
    ):
        _add_enum_value("alert_type_enum", v)

    for v in (
        "QUANTITY_MISMATCH", "PRICE_MISMATCH", "MISSING_DELIVERY_NOTE",
        "MISSING_SIGNATURE", "MISSING_INVOICE", "AWAITING_APPROVAL", "APPROVED_FOR_PAYMENT",
    ):
        _add_enum_value("invoice_match_status_enum", v)

    # ── 3. Missing columns on existing tables ─────────────────────────────────

    # sites
    _add_col("sites", "site_type",
        sa.Column("site_type", sa.String(100), nullable=False, server_default="construction_site"))
    _add_col("sites", "location_description",
        sa.Column("location_description", sa.Text, nullable=True))

    # material_requests
    _add_col("material_requests", "stage_id",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("stage_master.id", ondelete="SET NULL"), nullable=True))
    _add_col("material_requests", "preferred_supplier_id",
        sa.Column("preferred_supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True))
    _add_col("material_requests", "requested_date",
        sa.Column("requested_date", sa.DateTime(timezone=True), nullable=True))
    _add_col("material_requests", "needed_by_date",
        sa.Column("needed_by_date", sa.Date, nullable=True))
    _add_col("material_requests", "reviewed_by",
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    _add_col("material_requests", "reviewed_at",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    _add_col("material_requests", "rejection_reason",
        sa.Column("rejection_reason", sa.Text, nullable=True))
    _add_col("material_requests", "priority",
        sa.Column("priority",
                  postgresql.ENUM("URGENT", "HIGH", "NORMAL", "LOW",
                                  name="mr_priority_enum", create_type=False),
                  nullable=False, server_default="NORMAL"))
    _add_col("material_requests", "delivery_destination",
        sa.Column("delivery_destination",
                  postgresql.ENUM("MAIN_WAREHOUSE", "SITE_STORE", "LOT",
                                  name="delivery_destination_enum", create_type=False),
                  nullable=False, server_default="SITE_STORE"))
    _add_col("material_requests", "over_boq",
        sa.Column("over_boq", sa.Boolean, nullable=False, server_default="false"))
    _add_col("material_requests", "over_boq_reason",
        sa.Column("over_boq_reason", sa.Text, nullable=True))
    _add_col("material_requests", "approved_by",
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    _add_col("material_requests", "approved_at",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    _add_col("material_requests", "converted_to_po_at",
        sa.Column("converted_to_po_at", sa.DateTime(timezone=True), nullable=True))

    # material_request_items (0001 used request_id / quantity_requested; ORM uses different names)
    _add_col("material_request_items", "material_request_id",
        sa.Column("material_request_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=True))
    _add_col("material_request_items", "requested_quantity",
        sa.Column("requested_quantity", sa.Numeric(14, 3), nullable=True))
    _add_col("material_request_items", "approved_quantity",
        sa.Column("approved_quantity", sa.Numeric(14, 3), nullable=True))
    _add_col("material_request_items", "over_boq_quantity",
        sa.Column("over_boq_quantity", sa.Numeric(14, 3), nullable=True))
    _add_col("material_request_items", "remarks",
        sa.Column("remarks", sa.Text, nullable=True))

    # purchase_orders
    _add_col("purchase_orders", "po_date",
        sa.Column("po_date", sa.DateTime(timezone=True), nullable=True))
    _add_col("purchase_orders", "approved_by",
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    _add_col("purchase_orders", "sent_at",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    _add_col("purchase_orders", "lot_id",
        sa.Column("lot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True))
    _add_col("purchase_orders", "delivery_destination",
        sa.Column("delivery_destination",
                  postgresql.ENUM("MAIN_WAREHOUSE", "SITE_STORE", "LOT",
                                  name="delivery_destination_enum", create_type=False),
                  nullable=True))

    # purchase_order_items (0001 used 'quantity'/'unit_price'; ORM expects 'quantity_ordered'/'rate')
    _add_col("purchase_order_items", "quantity_ordered",
        sa.Column("quantity_ordered", sa.Numeric(14, 3), nullable=True))
    _add_col("purchase_order_items", "rate",
        sa.Column("rate", sa.Numeric(14, 2), nullable=True))
    _add_col("purchase_order_items", "vat_mode",
        sa.Column("vat_mode",
                  postgresql.ENUM("INCLUSIVE", "EXCLUSIVE", name="vat_mode_enum", create_type=False),
                  nullable=False, server_default="INCLUSIVE"))
    _add_col("purchase_order_items", "quantity_received",
        sa.Column("quantity_received", sa.Numeric(14, 3), nullable=False, server_default="0"))
    _add_col("purchase_order_items", "lot_id",
        sa.Column("lot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True))
    _add_col("purchase_order_items", "stage_id",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("stage_master.id", ondelete="SET NULL"), nullable=True))

    # po_email_logs (0001 used 'sent_to'/'subject'; ORM expects 'sent_to_email'/'email_subject')
    _add_col("po_email_logs", "sent_to_email",
        sa.Column("sent_to_email", sa.String(255), nullable=True))
    _add_col("po_email_logs", "sent_by",
        sa.Column("sent_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    _add_col("po_email_logs", "email_subject",
        sa.Column("email_subject", sa.String(255), nullable=True))
    _add_col("po_email_logs", "provider_message_id",
        sa.Column("provider_message_id", sa.String(255), nullable=True))
    _add_col("po_email_logs", "email_body",
        sa.Column("email_body", sa.Text, nullable=True))
    _add_col("po_email_logs", "material_request_id",
        sa.Column("material_request_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("material_requests.id", ondelete="SET NULL"), nullable=True))

    # ── 4. New tables ─────────────────────────────────────────────────────────

    # 4a. document_extractions
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS document_extractions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type              VARCHAR(50)  NOT NULL,
    source_id                UUID,
    file_path                TEXT         NOT NULL,
    document_type            VARCHAR(50)  NOT NULL DEFAULT 'OTHER',
    status                   VARCHAR(50)  NOT NULL DEFAULT 'NEEDS_REVIEW',
    raw_text                 TEXT,
    extracted_json           TEXT,
    manually_corrected_json  TEXT,
    confidence_score         NUMERIC(5,2),
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    corrected_at             TIMESTAMPTZ,
    corrected_by             UUID REFERENCES users(id) ON DELETE SET NULL
)
"""))
    _create_idx("ix_document_extractions_source_type", "document_extractions", ["source_type"])
    _create_idx("ix_document_extractions_status",      "document_extractions", ["status"])

    # 4b. delivery_verifications (depends on document_extractions)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS delivery_verifications (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_note_id     UUID REFERENCES deliveries(id) ON DELETE SET NULL,
    purchase_order_id    UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
    extraction_id        UUID REFERENCES document_extractions(id) ON DELETE SET NULL,
    site_id              UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    lot_id               UUID REFERENCES lots(id) ON DELETE SET NULL,
    received_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    verified_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    verification_status  VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    supplier_name        VARCHAR(255),
    delivery_note_number VARCHAR(100),
    vehicle_reg          VARCHAR(50),
    driver_name          VARCHAR(255),
    notes                TEXT,
    photo_path           TEXT,
    signature_path       TEXT,
    signed_at            TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_delivery_verifications_site_id", "delivery_verifications", ["site_id"])
    _create_idx("ix_delivery_verifications_status",  "delivery_verifications", ["verification_status"])

    # 4c. delivery_verification_items (depends on delivery_verifications)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS delivery_verification_items (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_verification_id UUID NOT NULL REFERENCES delivery_verifications(id) ON DELETE CASCADE,
    description              TEXT NOT NULL,
    unit                     VARCHAR(50),
    expected_qty             NUMERIC(14,3),
    ocr_qty                  NUMERIC(14,3),
    actual_received_qty      NUMERIC(14,3) NOT NULL DEFAULT 0,
    accepted_qty             NUMERIC(14,3) NOT NULL DEFAULT 0,
    rejected_qty             NUMERIC(14,3) NOT NULL DEFAULT 0,
    mismatch_reason          TEXT,
    matched_po_item_id       UUID REFERENCES purchase_order_items(id) ON DELETE SET NULL
)
"""))
    _create_idx("ix_dvi_delivery_verification_id", "delivery_verification_items", ["delivery_verification_id"])

    # 4d. expense_records (depends on document_extractions, vehicles)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS expense_records (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID REFERENCES projects(id) ON DELETE SET NULL,
    site_id        UUID REFERENCES sites(id) ON DELETE SET NULL,
    lot_id         UUID REFERENCES lots(id) ON DELETE SET NULL,
    vehicle_id     UUID REFERENCES vehicles(id) ON DELETE SET NULL,
    category       VARCHAR(50)  NOT NULL DEFAULT 'OTHER',
    supplier_name  VARCHAR(255) NOT NULL,
    invoice_number VARCHAR(100),
    amount         NUMERIC(14,2),
    file_path      TEXT,
    status         VARCHAR(50)  NOT NULL DEFAULT 'UPLOADED',
    uploaded_by    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approved_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at    TIMESTAMPTZ,
    signature_path TEXT,
    notes          TEXT,
    extraction_id  UUID REFERENCES document_extractions(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_expense_records_status",     "expense_records", ["status"])
    _create_idx("ix_expense_records_project_id", "expense_records", ["project_id"])

    # 4e. alert_recipients
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS alert_recipients (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     VARCHAR(255) NOT NULL,
    phone_number             VARCHAR(30)  NOT NULL UNIQUE,
    label                    VARCHAR(100),
    receives_critical_alerts BOOLEAN NOT NULL DEFAULT true,
    receives_daily_summary   BOOLEAN NOT NULL DEFAULT true,
    receives_invoice_alerts  BOOLEAN NOT NULL DEFAULT false,
    receives_delivery_alerts BOOLEAN NOT NULL DEFAULT false,
    receives_vehicle_alerts  BOOLEAN NOT NULL DEFAULT false,
    receives_material_alerts BOOLEAN NOT NULL DEFAULT false,
    is_active                BOOLEAN NOT NULL DEFAULT true,
    created_by               UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))

    # 4f. notification_queue (depends on alert_recipients, system_alerts)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS notification_queue (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id                 UUID REFERENCES system_alerts(id) ON DELETE CASCADE,
    recipient_id             UUID REFERENCES alert_recipients(id) ON DELETE SET NULL,
    channel                  notification_channel_enum NOT NULL DEFAULT 'WHATSAPP',
    phone_number             VARCHAR(30) NOT NULL,
    message_body             TEXT NOT NULL,
    status                   notification_status_enum NOT NULL DEFAULT 'PENDING',
    attempt_count            INTEGER NOT NULL DEFAULT 0,
    last_attempt_at          TIMESTAMPTZ,
    next_attempt_at          TIMESTAMPTZ,
    provider_message_id      VARCHAR(255),
    error_message            TEXT,
    requires_acknowledgement BOOLEAN NOT NULL DEFAULT false,
    acknowledged_at          TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_notification_queue_alert_id",        "notification_queue", ["alert_id"])
    _create_idx("ix_notification_queue_recipient_id",    "notification_queue", ["recipient_id"])
    _create_idx("ix_notification_queue_status",          "notification_queue", ["status"])
    _create_idx("ix_notification_queue_next_attempt_at", "notification_queue", ["next_attempt_at"])

    # 4g. incoming_emails
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS incoming_emails (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id        VARCHAR(500) UNIQUE,
    from_email        VARCHAR(255) NOT NULL,
    subject           TEXT,
    body_snippet      TEXT,
    received_at       TIMESTAMPTZ,
    has_attachments   BOOLEAN NOT NULL DEFAULT false,
    processed_status  VARCHAR(50) NOT NULL DEFAULT 'UNPROCESSED',
    matched_po_number VARCHAR(100),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_incoming_emails_processed_status", "incoming_emails", ["processed_status"])

    # 4h. incoming_email_attachments (depends on incoming_emails)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS incoming_email_attachments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incoming_email_id UUID NOT NULL REFERENCES incoming_emails(id) ON DELETE CASCADE,
    filename          VARCHAR(500)  NOT NULL,
    file_path         VARCHAR(1000) NOT NULL,
    content_type      VARCHAR(200),
    detected_type     VARCHAR(50)  NOT NULL DEFAULT 'OTHER',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_incoming_email_attachments_email_id",      "incoming_email_attachments", ["incoming_email_id"])
    _create_idx("ix_incoming_email_attachments_detected_type", "incoming_email_attachments", ["detected_type"])

    # 4i. job_cards (includes is_active so 0002's skipped add_column is a no-op)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS job_cards (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_card_number          VARCHAR(50) NOT NULL UNIQUE,
    project_id               UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    site_id                  UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    lot_id                   UUID REFERENCES lots(id) ON DELETE SET NULL,
    stage_id                 UUID REFERENCES stage_master(id) ON DELETE SET NULL,
    work_description         TEXT NOT NULL,
    work_type                job_card_work_type_enum NOT NULL DEFAULT 'DAILY_LABOUR',
    worker_name              VARCHAR(255),
    team_name                VARCHAR(255),
    quantity                 NUMERIC(10,2) NOT NULL DEFAULT 1,
    unit                     VARCHAR(50),
    rate                     NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_amount             NUMERIC(14,2) NOT NULL DEFAULT 0,
    owner_approval_required  BOOLEAN NOT NULL DEFAULT false,
    status                   job_card_status_enum NOT NULL DEFAULT 'DRAFT',
    is_active                BOOLEAN NOT NULL DEFAULT true,
    submitted_by             UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at             TIMESTAMPTZ,
    site_approved_by         UUID REFERENCES users(id) ON DELETE SET NULL,
    site_approved_at         TIMESTAMPTZ,
    office_approved_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    office_approved_at       TIMESTAMPTZ,
    owner_approved_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_approved_at        TIMESTAMPTZ,
    payment_approved_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    payment_approved_at      TIMESTAMPTZ,
    rejection_reason         TEXT,
    work_date                DATE,
    notes                    TEXT,
    created_by               UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_job_cards_project_id",      "job_cards", ["project_id"])
    _create_idx("ix_job_cards_job_card_number", "job_cards", ["job_card_number"])
    _create_idx("ix_job_cards_status",          "job_cards", ["status"])

    # 4j. mr_email_logs
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS mr_email_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_request_id UUID NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
    supplier_id         UUID REFERENCES suppliers(id) ON DELETE SET NULL,
    sent_to_email       VARCHAR(255) NOT NULL,
    email_subject       VARCHAR(255),
    email_body          TEXT,
    status              VARCHAR(50) NOT NULL,
    error_message       TEXT,
    sent_by             UUID REFERENCES users(id) ON DELETE SET NULL,
    sent_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_mr_email_logs_material_request_id", "mr_email_logs", ["material_request_id"])
    _create_idx("ix_mr_email_logs_status",              "mr_email_logs", ["status"])

    # 4k. mr_quotes
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS mr_quotes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_request_id UUID NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
    supplier_id         UUID NOT NULL REFERENCES suppliers(id),
    item_id             UUID REFERENCES items(id) ON DELETE SET NULL,
    description         VARCHAR(500) NOT NULL,
    quoted_quantity     NUMERIC(14,3) NOT NULL,
    unit                VARCHAR(50),
    unit_price          NUMERIC(14,2) NOT NULL,
    total_price         NUMERIC(14,2),
    delivery_date       DATE,
    validity_date       DATE,
    notes               TEXT,
    is_selected         BOOLEAN NOT NULL DEFAULT false,
    created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_mr_quotes_material_request_id", "mr_quotes", ["material_request_id"])

    # 4l. boq_adjustments
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS boq_adjustments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID REFERENCES projects(id) ON DELETE SET NULL,
    site_id           UUID REFERENCES sites(id) ON DELETE SET NULL,
    lot_id            UUID REFERENCES lots(id) ON DELETE SET NULL,
    boq_item_id       UUID REFERENCES boq_items(id) ON DELETE SET NULL,
    item_id           UUID REFERENCES items(id) ON DELETE SET NULL,
    purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
    invoice_id        UUID REFERENCES invoices(id) ON DELETE SET NULL,
    delivery_id       UUID REFERENCES deliveries(id) ON DELETE SET NULL,
    supplier_id       UUID REFERENCES suppliers(id) ON DELETE SET NULL,
    adjustment_type   VARCHAR(50) NOT NULL,
    quantity          NUMERIC(14,3),
    amount            NUMERIC(14,2),
    reason            TEXT NOT NULL,
    notes             TEXT,
    created_by        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_boq_adjustments_item_id",         "boq_adjustments", ["item_id"])
    _create_idx("ix_boq_adjustments_adjustment_type", "boq_adjustments", ["adjustment_type"])

    # 4m. project_stage_status
    # ORM uses __tablename__ = "project_stage_status" (no trailing 's').
    # Migration 0001 created "project_stage_statuses" (different table, legacy).
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS project_stage_status (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id               UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    site_id                  UUID REFERENCES sites(id) ON DELETE SET NULL,
    lot_id                   UUID REFERENCES lots(id) ON DELETE SET NULL,
    stage_id                 UUID NOT NULL REFERENCES stage_master(id),
    status                   stage_status_enum NOT NULL DEFAULT 'NOT_STARTED',
    started_at               TIMESTAMPTZ,
    completed_at             TIMESTAMPTZ,
    certified_at             TIMESTAMPTZ,
    inspection_required      BOOLEAN NOT NULL DEFAULT false,
    certification_required   BOOLEAN NOT NULL DEFAULT false,
    ready_for_labour_payment BOOLEAN NOT NULL DEFAULT false,
    notes                    TEXT,
    updated_by               UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    _create_idx("ix_project_stage_status_project_id", "project_stage_status", ["project_id"])
    _create_idx("ix_project_stage_status_site_id",    "project_stage_status", ["site_id"])
    _create_idx("ix_project_stage_status_lot_id",     "project_stage_status", ["lot_id"])


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def _drop_col(table: str, col: str) -> None:
        if not _table_exists(insp, table):
            return
        if col in [c["name"] for c in insp.get_columns(table)]:
            op.drop_column(table, col)

    # Drop new tables in reverse dependency order
    for tbl in (
        "project_stage_status",
        "boq_adjustments",
        "mr_quotes",
        "mr_email_logs",
        "job_cards",
        "incoming_email_attachments",
        "incoming_emails",
        "notification_queue",
        "alert_recipients",
        "expense_records",
        "delivery_verification_items",
        "delivery_verifications",
        "document_extractions",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))

    # Drop new enum types (tables referencing them were dropped above)
    for t in (
        "notification_status_enum",
        "notification_channel_enum",
        "job_card_work_type_enum",
        "job_card_status_enum",
        "delivery_destination_enum",
        "mr_priority_enum",
    ):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {t}"))

    # Remove added columns from existing tables
    _drop_col("po_email_logs", "material_request_id")
    _drop_col("po_email_logs", "email_body")
    _drop_col("po_email_logs", "provider_message_id")
    _drop_col("po_email_logs", "email_subject")
    _drop_col("po_email_logs", "sent_by")
    _drop_col("po_email_logs", "sent_to_email")

    _drop_col("purchase_order_items", "stage_id")
    _drop_col("purchase_order_items", "lot_id")
    _drop_col("purchase_order_items", "quantity_received")
    _drop_col("purchase_order_items", "vat_mode")
    _drop_col("purchase_order_items", "rate")
    _drop_col("purchase_order_items", "quantity_ordered")

    _drop_col("purchase_orders", "delivery_destination")
    _drop_col("purchase_orders", "lot_id")
    _drop_col("purchase_orders", "sent_at")
    _drop_col("purchase_orders", "approved_by")
    _drop_col("purchase_orders", "po_date")

    _drop_col("material_request_items", "remarks")
    _drop_col("material_request_items", "over_boq_quantity")
    _drop_col("material_request_items", "approved_quantity")
    _drop_col("material_request_items", "requested_quantity")
    _drop_col("material_request_items", "material_request_id")

    _drop_col("material_requests", "converted_to_po_at")
    _drop_col("material_requests", "approved_at")
    _drop_col("material_requests", "approved_by")
    _drop_col("material_requests", "over_boq_reason")
    _drop_col("material_requests", "over_boq")
    _drop_col("material_requests", "delivery_destination")
    _drop_col("material_requests", "priority")
    _drop_col("material_requests", "rejection_reason")
    _drop_col("material_requests", "reviewed_at")
    _drop_col("material_requests", "reviewed_by")
    _drop_col("material_requests", "needed_by_date")
    _drop_col("material_requests", "requested_date")
    _drop_col("material_requests", "preferred_supplier_id")
    _drop_col("material_requests", "stage_id")

    _drop_col("sites", "location_description")
    _drop_col("sites", "site_type")
