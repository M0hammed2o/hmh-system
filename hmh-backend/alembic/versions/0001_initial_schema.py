"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def create_enum_if_not_exists(enum_name: str, values: list[str]) -> None:
    values_sql = ", ".join(f"'{value}'" for value in values)
    op.execute(f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
        CREATE TYPE {enum_name} AS ENUM ({values_sql});
    END IF;
END
$$;
""")


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    create_enum_if_not_exists("user_role_enum", ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "SITE_MANAGER", "SITE_STAFF"])
    create_enum_if_not_exists("project_status_enum", ["PLANNED", "ACTIVE", "PAUSED", "COMPLETED"])
    create_enum_if_not_exists("record_status_enum", ["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "SENT", "RECEIVED", "MATCHED", "PAID", "CANCELLED"])
    create_enum_if_not_exists("stage_status_enum", ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "AWAITING_INSPECTION", "CERTIFIED"])
    create_enum_if_not_exists("lot_status_enum", ["AVAILABLE", "IN_PROGRESS", "COMPLETED", "ON_HOLD"])
    create_enum_if_not_exists("item_type_enum", ["MATERIAL", "LABOUR", "PLANT", "SERVICE", "PACKAGE"])
    create_enum_if_not_exists("movement_type_enum", ["OPENING_BALANCE", "DELIVERY_RECEIVED", "USAGE", "ADJUSTMENT_ADD", "ADJUSTMENT_SUBTRACT", "RETURN_TO_STORE", "TRANSFER_IN", "TRANSFER_OUT"])
    create_enum_if_not_exists("invoice_match_status_enum", ["MATCHED", "PARTIALLY_MATCHED", "MISMATCH", "UNLINKED"])
    create_enum_if_not_exists("alert_status_enum", ["OPEN", "ACKNOWLEDGED", "RESOLVED"])
    create_enum_if_not_exists("alert_severity_enum", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    create_enum_if_not_exists("alert_type_enum", ["MATERIAL_OVERUSE", "BOQ_VARIANCE_OVERUSE", "DELIVERY_WITHOUT_PO", "INVOICE_MISMATCH", "INVOICE_MISSING_DELIVERY_NOTE", "NEGATIVE_STOCK", "LOW_STOCK", "MISSING_REMAINING_STOCK_PHOTO", "OVERDUE_PAYMENT", "REQUEST_PENDING_TOO_LONG", "DELIVERY_DISCREPANCY", "DELIVERY_SIGNATURE_MISSING", "VEHICLE_REPAIR_LOGGED", "SITE_DELAY", "PROJECT_OVER_BUDGET"])
    create_enum_if_not_exists("payment_type_enum", ["SUPPLIER", "LABOUR", "OTHER"])
    create_enum_if_not_exists("payment_status_enum", ["PENDING", "APPROVED", "PAID", "FAILED", "CANCELLED"])
    create_enum_if_not_exists("boq_status_enum", ["DRAFT", "UNDER_REVIEW", "ACTIVE", "SUPERSEDED", "ARCHIVED"])
    create_enum_if_not_exists("attachment_entity_enum", ["BOQ_HEADER", "PURCHASE_ORDER", "DELIVERY", "INVOICE", "USAGE_LOG", "CERTIFICATION"])
    create_enum_if_not_exists("attachment_type_enum", ["PHOTO", "PDF", "DELIVERY_NOTE", "INVOICE_COPY", "PROOF", "CERTIFICATE"])
    create_enum_if_not_exists("email_status_enum", ["queued", "sent", "failed", "bounced"])
    create_enum_if_not_exists("vat_mode_enum", ["INCLUSIVE", "EXCLUSIVE"])
    create_enum_if_not_exists("fuel_type_enum", ["DIESEL", "PETROL", "PARAFFIN", "OTHER"])
    create_enum_if_not_exists("fuel_usage_type_enum", ["EQUIPMENT", "DELIVERY_VEHICLE", "TRANSPORT", "GENERATOR", "OTHER"])
    create_enum_if_not_exists("opening_financial_status_enum", ["OUTSTANDING", "PARTIALLY_PAID", "PAID", "DISPUTED"])
    create_enum_if_not_exists("opening_reference_type_enum", ["INVOICE", "PO", "PAYMENT", "OTHER"])
    create_enum_if_not_exists("vehicle_type_enum", ["BAKKIE", "TRUCK", "TLB", "EXCAVATOR", "CRANE", "VAN", "OTHER"])
    create_enum_if_not_exists("vehicle_status_enum", ["ACTIVE", "MAINTENANCE", "RETIRED"])
    create_enum_if_not_exists("vehicle_cost_type_enum", ["FUEL", "TYRE", "REPAIR", "SERVICE", "LICENCE", "INSURANCE", "OTHER"])

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("role", sa.Enum("OWNER","OFFICE_ADMIN","OFFICE_USER","SITE_MANAGER","SITE_STAFF", name="user_role_enum", create_type=False), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("must_reset_password", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # ── projects ───────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("estimated_end_date", sa.Date, nullable=True),
        sa.Column("go_live_date", sa.Date, nullable=True),
        sa.Column("budget", sa.Numeric(16, 2), nullable=True),
        sa.Column("status", sa.Enum("PLANNED","ACTIVE","PAUSED","COMPLETED", name="project_status_enum", create_type=False), nullable=False, server_default="PLANNED"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_projects_code", "projects", ["code"], unique=True)
    op.create_index("ix_projects_status", "projects", ["status"])

    # ── stage_master ───────────────────────────────────────────────────────────
    op.create_table(
        "stage_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("sequence_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stage_master_code", "stage_master", ["code"], unique=True)

    # ── sites ──────────────────────────────────────────────────────────────────
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lng", sa.Float, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sites_project_id", "sites", ["project_id"])

    # ── boq_headers (before lots — lots FK boq_headers) ───────────────────────
    op.create_table(
        "boq_headers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_name", sa.String(255), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("status", sa.Enum("DRAFT","UNDER_REVIEW","ACTIVE","SUPERSEDED","ARCHIVED", name="boq_status_enum", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("is_active_version", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_template", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("template_name", sa.String(255), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_boq_headers_project_id", "boq_headers", ["project_id"])
    op.create_index("ix_boq_headers_is_template", "boq_headers", ["is_template"])

    # ── lots ───────────────────────────────────────────────────────────────────
    op.create_table(
        "lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_number", sa.String(100), nullable=False),
        sa.Column("unit_type", sa.String(100), nullable=True),
        sa.Column("block_number", sa.String(100), nullable=True),
        sa.Column("status", sa.Enum("AVAILABLE","IN_PROGRESS","COMPLETED","ON_HOLD", name="lot_status_enum", create_type=False), nullable=False, server_default="AVAILABLE"),
        sa.Column("buyer_name", sa.String(255), nullable=True),
        sa.Column("manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("boq_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_headers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("expected_completion_date", sa.Date, nullable=True),
        sa.Column("actual_completion_date", sa.Date, nullable=True),
        sa.Column("budgeted_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "lot_number", name="uq_lots_project_lot_number"),
    )
    op.create_index("ix_lots_project_id", "lots", ["project_id"])
    op.create_index("ix_lots_site_id", "lots", ["site_id"])

    # ── user_project_access ────────────────────────────────────────────────────
    op.create_table(
        "user_project_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("can_view", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("can_edit", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_approve", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "project_id", name="uq_user_project_access"),
    )

    # ── user_site_access ───────────────────────────────────────────────────────
    op.create_table(
        "user_site_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("can_receive_delivery", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_record_usage", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_request_stock", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_update_stage", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "site_id", name="uq_user_site_access"),
    )

    # ── project_stage_statuses ─────────────────────────────────────────────────
    op.create_table(
        "project_stage_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stage_master.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("NOT_STARTED","IN_PROGRESS","COMPLETED","AWAITING_INSPECTION","CERTIFIED", name="stage_status_enum", create_type=False), nullable=False, server_default="NOT_STARTED"),
        sa.Column("planned_start", sa.Date, nullable=True),
        sa.Column("planned_end", sa.Date, nullable=True),
        sa.Column("actual_start", sa.Date, nullable=True),
        sa.Column("actual_end", sa.Date, nullable=True),
        sa.Column("delay_reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── suppliers ──────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("bank_account", sa.String(50), nullable=True),
        sa.Column("bank_branch_code", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── item_categories ────────────────────────────────────────────────────────
    op.create_table(
        "item_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── items ──────────────────────────────────────────────────────────────────
    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("item_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("item_type", sa.Enum("MATERIAL","LABOUR","PLANT","SERVICE","PACKAGE", name="item_type_enum", create_type=False), nullable=False, server_default="MATERIAL"),
        sa.Column("default_unit", sa.String(50), nullable=True),
        sa.Column("default_rate", sa.Numeric(14, 2), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── item_aliases ───────────────────────────────────────────────────────────
    op.create_table(
        "item_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── boq_sections ──────────────────────────────────────────────────────────
    op.create_table(
        "boq_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("boq_header_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_headers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stage_master.id", ondelete="SET NULL"), nullable=True),
        sa.Column("section_name", sa.String(255), nullable=False),
        sa.Column("sequence_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_boq_sections_boq_header_id", "boq_sections", ["boq_header_id"])

    # ── boq_items ──────────────────────────────────────────────────────────────
    op.create_table(
        "boq_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("boq_section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stage_master.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_description", sa.Text, nullable=False),
        sa.Column("normalized_description", sa.Text, nullable=True),
        sa.Column("specification", sa.Text, nullable=True),
        sa.Column("item_type", sa.Enum("MATERIAL","LABOUR","PLANT","SERVICE","PACKAGE", name="item_type_enum", create_type=False), nullable=False, server_default="MATERIAL"),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("planned_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("planned_rate", sa.Numeric(14, 2), nullable=True),
        sa.Column("planned_total", sa.Numeric(14, 2), sa.Computed("planned_quantity * planned_rate", persisted=True), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_boq_items_boq_section_id", "boq_items", ["boq_section_id"])
    op.create_index("ix_boq_items_project_id", "boq_items", ["project_id"])
    op.create_index("ix_boq_items_item_id", "boq_items", ["item_id"])
    op.create_index("ix_boq_items_lot_id", "boq_items", ["lot_id"])

    # ── material_requests ──────────────────────────────────────────────────────
    op.create_table(
        "material_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_number", sa.String(100), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Enum("DRAFT","SUBMITTED","APPROVED","REJECTED","SENT","RECEIVED","MATCHED","PAID","CANCELLED", name="record_status_enum", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── material_request_items ─────────────────────────────────────────────────
    op.create_table(
        "material_request_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity_requested", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantity_approved", sa.Numeric(14, 3), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── purchase_orders ────────────────────────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("po_number", sa.String(100), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("material_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("material_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Enum("DRAFT","SUBMITTED","APPROVED","REJECTED","SENT","RECEIVED","MATCHED","PAID","CANCELLED", name="record_status_enum", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("vat_mode", sa.Enum("INCLUSIVE","EXCLUSIVE", name="vat_mode_enum", create_type=False), nullable=False, server_default="EXCLUSIVE"),
        sa.Column("subtotal_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column("delivery_address", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_orders_project_id", "purchase_orders", ["project_id"])

    # ── purchase_order_items ───────────────────────────────────────────────────
    op.create_table(
        "purchase_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── po_email_logs ──────────────────────────────────────────────────────────
    op.create_table(
        "po_email_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sent_to", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("status", sa.Enum("queued","sent","failed","bounced", name="email_status_enum", create_type=False), nullable=False, server_default="queued"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── deliveries ─────────────────────────────────────────────────────────────
    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_number", sa.String(100), nullable=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("received_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supplier_delivery_note_number", sa.String(100), nullable=True),
        sa.Column("delivery_status", sa.Enum("DRAFT","SUBMITTED","APPROVED","REJECTED","SENT","RECEIVED","MATCHED","PAID","CANCELLED", name="record_status_enum", create_type=False), nullable=False, server_default="RECEIVED"),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("delivery_note_image_url", sa.String(500), nullable=True),
        sa.Column("signature_image_url", sa.String(500), nullable=True),
        sa.Column("receiver_name", sa.String(255), nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lng", sa.Float, nullable=True),
        sa.Column("ocr_raw_data", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_deliveries_project_id", "deliveries", ["project_id"])
    op.create_index("ix_deliveries_site_id", "deliveries", ["site_id"])

    # ── delivery_items ─────────────────────────────────────────────────────────
    op.create_table(
        "delivery_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_order_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity_expected", sa.Numeric(14, 3), nullable=True),
        sa.Column("quantity_received", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("discrepancy_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_delivery_items_delivery_id", "delivery_items", ["delivery_id"])

    # ── stock_ledger ───────────────────────────────────────────────────────────
    op.create_table(
        "stock_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("movement_type", sa.Enum("OPENING_BALANCE","DELIVERY_RECEIVED","USAGE","ADJUSTMENT_ADD","ADJUSTMENT_SUBTRACT","RETURN_TO_STORE","TRANSFER_IN","TRANSFER_OUT", name="movement_type_enum", create_type=False), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quantity_in", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("quantity_out", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("movement_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stock_ledger_project_id", "stock_ledger", ["project_id"])
    op.create_index("ix_stock_ledger_item_id", "stock_ledger", ["item_id"])
    op.create_index("ix_stock_ledger_lot_id", "stock_ledger", ["lot_id"])

    # ── usage_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stage_master.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("boq_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity_used", sa.Numeric(14, 3), nullable=False),
        sa.Column("used_by_person_name", sa.String(255), nullable=True),
        sa.Column("used_by_team_name", sa.String(255), nullable=True),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("usage_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_logs_project_id", "usage_logs", ["project_id"])
    op.create_index("ix_usage_logs_site_id", "usage_logs", ["site_id"])
    op.create_index("ix_usage_logs_item_id", "usage_logs", ["item_id"])

    # ── invoices ───────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_date", sa.Date, nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.Enum("DRAFT","SUBMITTED","APPROVED","REJECTED","SENT","RECEIVED","MATCHED","PAID","CANCELLED", name="record_status_enum", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invoices_supplier_id", "invoices", ["supplier_id"])
    op.create_index("ix_invoices_project_id", "invoices", ["project_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])

    # ── invoice_matching_results ───────────────────────────────────────────────
    op.create_table(
        "invoice_matching_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_status", sa.Enum("MATCHED","PARTIALLY_MATCHED","MISMATCH","UNLINKED", name="invoice_match_status_enum", create_type=False), nullable=False, server_default="UNLINKED"),
        sa.Column("quantity_match", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("amount_match", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("supplier_match", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("checked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invoice_matching_results_invoice_id", "invoice_matching_results", ["invoice_id"])
    op.create_index("ix_invoice_matching_results_po_id", "invoice_matching_results", ["purchase_order_id"])

    # ── payments ───────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_type", sa.Enum("SUPPLIER","LABOUR","OTHER", name="payment_type_enum", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("PENDING","APPROVED","PAID","FAILED","CANCELLED", name="payment_status_enum", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payments_project_id", "payments", ["project_id"])

    # ── attachments ────────────────────────────────────────────────────────────
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Enum("BOQ_HEADER","PURCHASE_ORDER","DELIVERY","INVOICE","USAGE_LOG","CERTIFICATION", name="attachment_entity_enum", create_type=False), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_type", sa.Enum("PHOTO","PDF","DELIVERY_NOTE","INVOICE_COPY","PROOF","CERTIFICATE", name="attachment_type_enum", create_type=False), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_url", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── usage_remaining_proofs ─────────────────────────────────────────────────
    op.create_table(
        "usage_remaining_proofs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usage_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usage_logs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_url", sa.String(1000), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── system_alerts ──────────────────────────────────────────────────────────
    op.create_table(
        "system_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reference_type", sa.String(100), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.Enum("MATERIAL_OVERUSE","BOQ_VARIANCE_OVERUSE","DELIVERY_WITHOUT_PO","INVOICE_MISMATCH","INVOICE_MISSING_DELIVERY_NOTE","NEGATIVE_STOCK","LOW_STOCK","MISSING_REMAINING_STOCK_PHOTO","OVERDUE_PAYMENT","REQUEST_PENDING_TOO_LONG","DELIVERY_DISCREPANCY","DELIVERY_SIGNATURE_MISSING","VEHICLE_REPAIR_LOGGED","SITE_DELAY","PROJECT_OVER_BUDGET", name="alert_type_enum", create_type=False), nullable=False),
        sa.Column("severity", sa.Enum("LOW","MEDIUM","HIGH","CRITICAL", name="alert_severity_enum", create_type=False), nullable=False, server_default="MEDIUM"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.Enum("OPEN","ACKNOWLEDGED","RESOLVED", name="alert_status_enum", create_type=False), nullable=False, server_default="OPEN"),
        sa.Column("target_role", sa.Enum("OWNER","OFFICE_ADMIN","OFFICE_USER","SITE_MANAGER","SITE_STAFF", name="user_role_enum", create_type=False), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notification_channel", sa.String(50), nullable=False, server_default="in_app"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_system_alerts_project_id", "system_alerts", ["project_id"])
    op.create_index("ix_system_alerts_alert_type", "system_alerts", ["alert_type"])
    op.create_index("ix_system_alerts_status", "system_alerts", ["status"])

    # ── fuel_logs ──────────────────────────────────────────────────────────────
    op.create_table(
        "fuel_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fuel_type", sa.Enum("DIESEL","PETROL","PARAFFIN","OTHER", name="fuel_type_enum", create_type=False), nullable=False),
        sa.Column("usage_type", sa.Enum("EQUIPMENT","DELIVERY_VEHICLE","TRANSPORT","GENERATOR","OTHER", name="fuel_usage_type_enum", create_type=False), nullable=False),
        sa.Column("litres", sa.Numeric(10, 2), nullable=False),
        sa.Column("cost_per_litre", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("vehicle_registration", sa.String(50), nullable=True),
        sa.Column("equipment_name", sa.String(255), nullable=True),
        sa.Column("odometer_reading", sa.Numeric(10, 1), nullable=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fuel_logs_project_id", "fuel_logs", ["project_id"])

    # ── vehicles ───────────────────────────────────────────────────────────────
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("registration", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("vehicle_type", sa.Enum("BAKKIE","TRUCK","TLB","EXCAVATOR","CRANE","VAN","OTHER", name="vehicle_type_enum", create_type=False), nullable=False, server_default="OTHER"),
        sa.Column("status", sa.Enum("ACTIVE","MAINTENANCE","RETIRED", name="vehicle_status_enum", create_type=False), nullable=False, server_default="ACTIVE"),
        sa.Column("assigned_project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_service_date", sa.Date, nullable=True),
        sa.Column("next_service_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vehicles_registration", "vehicles", ["registration"], unique=True)
    op.create_index("ix_vehicles_assigned_project_id", "vehicles", ["assigned_project_id"])

    # ── vehicle_costs ──────────────────────────────────────────────────────────
    op.create_table(
        "vehicle_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_type", sa.Enum("FUEL","TYRE","REPAIR","SERVICE","LICENCE","INSURANCE","OTHER", name="vehicle_cost_type_enum", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proof_image_url", sa.String(500), nullable=True),
        sa.Column("cost_date", sa.Date, nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vehicle_costs_vehicle_id", "vehicle_costs", ["vehicle_id"])
    op.create_index("ix_vehicle_costs_project_id", "vehicle_costs", ["project_id"])

    # ── audit_events ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_value", postgresql.JSON, nullable=True),
        sa.Column("after_value", postgresql.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    # ── stock_balances materialized view ───────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW stock_balances AS
        SELECT
            project_id,
            site_id,
            lot_id,
            item_id,
            SUM(quantity_in) - SUM(quantity_out) AS balance,
            MAX(movement_date) AS last_movement_date
        FROM stock_ledger
        GROUP BY project_id, site_id, lot_id, item_id
        WITH DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX ix_stock_balances_unique
        ON stock_balances (project_id, site_id, item_id, COALESCE(lot_id, '00000000-0000-0000-0000-000000000000'::uuid))
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS stock_balances")
    op.drop_table("audit_events")
    op.drop_table("vehicle_costs")
    op.drop_table("vehicles")
    op.drop_table("fuel_logs")
    op.drop_table("system_alerts")
    op.drop_table("usage_remaining_proofs")
    op.drop_table("attachments")
    op.drop_table("payments")
    op.drop_table("invoice_matching_results")
    op.drop_table("invoices")
    op.drop_table("usage_logs")
    op.drop_table("stock_ledger")
    op.drop_table("delivery_items")
    op.drop_table("deliveries")
    op.drop_table("po_email_logs")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("material_request_items")
    op.drop_table("material_requests")
    op.drop_table("boq_items")
    op.drop_table("boq_sections")
    op.drop_table("lots")
    op.drop_table("boq_headers")
    op.drop_table("user_site_access")
    op.drop_table("user_project_access")
    op.drop_table("project_stage_statuses")
    op.drop_table("item_aliases")
    op.drop_table("items")
    op.drop_table("item_categories")
    op.drop_table("suppliers")
    op.drop_table("sites")
    op.drop_table("stage_master")
    op.drop_table("projects")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS vehicle_cost_type_enum")
    op.execute("DROP TYPE IF EXISTS vehicle_status_enum")
    op.execute("DROP TYPE IF EXISTS vehicle_type_enum")
    op.execute("DROP TYPE IF EXISTS opening_reference_type_enum")
    op.execute("DROP TYPE IF EXISTS opening_financial_status_enum")
    op.execute("DROP TYPE IF EXISTS fuel_usage_type_enum")
    op.execute("DROP TYPE IF EXISTS fuel_type_enum")
    op.execute("DROP TYPE IF EXISTS vat_mode_enum")
    op.execute("DROP TYPE IF EXISTS email_status_enum")
    op.execute("DROP TYPE IF EXISTS attachment_type_enum")
    op.execute("DROP TYPE IF EXISTS attachment_entity_enum")
    op.execute("DROP TYPE IF EXISTS boq_status_enum")
    op.execute("DROP TYPE IF EXISTS payment_status_enum")
    op.execute("DROP TYPE IF EXISTS payment_type_enum")
    op.execute("DROP TYPE IF EXISTS alert_type_enum")
    op.execute("DROP TYPE IF EXISTS alert_severity_enum")
    op.execute("DROP TYPE IF EXISTS alert_status_enum")
    op.execute("DROP TYPE IF EXISTS invoice_match_status_enum")
    op.execute("DROP TYPE IF EXISTS movement_type_enum")
    op.execute("DROP TYPE IF EXISTS item_type_enum")
    op.execute("DROP TYPE IF EXISTS lot_status_enum")
    op.execute("DROP TYPE IF EXISTS stage_status_enum")
    op.execute("DROP TYPE IF EXISTS record_status_enum")
    op.execute("DROP TYPE IF EXISTS project_status_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
