"""0068 - Municipality Progress Claim, Programme Activities, Weekly Plans

Revision ID: 0068
Revises: 0067
Create Date: 2026-07-19

Adds three new feature areas:
  1. municipality_progress_claims + progress_claim_lines + progress_claim_evidence
  2. programme_activities (Gantt/timeline)
  3. weekly_plans + weekly_plan_items

Also adds new enum values to alert_type_enum and attachment_entity_enum.

All ALTER TABLE statements use IF NOT EXISTS guards.
CREATE TABLE statements check has_table() before running.
"""

from alembic import op
from sqlalchemy import text, inspect


revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def upgrade():
    conn = op.get_bind()

    # ── New alert_type_enum values ─────────────────────────────────────────────
    for val in ["CLAIM_READY_FOR_PRICING", "CLAIM_APPROVED", "WEEKLY_PLAN_DUE"]:
        conn.execute(text(f"""
            DO $$ BEGIN
                ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS '{val}';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))

    # ── New attachment_entity_enum values ──────────────────────────────────────
    for val in ["PROGRESS_CLAIM", "PROGRAMME_ACTIVITY", "WEEKLY_PLAN"]:
        conn.execute(text(f"""
            DO $$ BEGIN
                ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS '{val}';
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))

    # ── municipality_progress_claims ───────────────────────────────────────────
    if not _has_table(conn, "municipality_progress_claims"):
        conn.execute(text("""
            CREATE TABLE municipality_progress_claims (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                claim_number VARCHAR(50) NOT NULL,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
                claim_title VARCHAR(200) NOT NULL,
                municipality_name VARCHAR(200) NOT NULL DEFAULT 'Ethekweni Municipality',
                cert_number VARCHAR(100),
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                reporting_cutoff_date DATE NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                generation_summary JSONB,
                snapshot_json JSONB,
                linked_invoice_id UUID REFERENCES municipality_invoices(id) ON DELETE SET NULL,
                generated_at TIMESTAMPTZ,
                approved_at TIMESTAMPTZ,
                exported_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_progress_claim_number UNIQUE (claim_number)
            )
        """))
        conn.execute(text("CREATE INDEX ix_progress_claims_project_id ON municipality_progress_claims(project_id)"))
        conn.execute(text("CREATE INDEX ix_progress_claims_status ON municipality_progress_claims(status)"))

    # ── progress_claim_lines ───────────────────────────────────────────────────
    if not _has_table(conn, "progress_claim_lines"):
        conn.execute(text("""
            CREATE TABLE progress_claim_lines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                claim_id UUID NOT NULL REFERENCES municipality_progress_claims(id) ON DELETE CASCADE,
                source_type VARCHAR(30) NOT NULL,
                lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
                stage_status_id UUID REFERENCES project_stage_status(id) ON DELETE SET NULL,
                work_done_id UUID REFERENCES subcontractor_work_done(id) ON DELETE SET NULL,
                job_card_id UUID REFERENCES job_cards(id) ON DELETE SET NULL,
                description TEXT NOT NULL,
                stage_name VARCHAR(200),
                lot_number VARCHAR(50),
                work_date DATE,
                quantity VARCHAR(50),
                unit VARCHAR(50),
                progress_pct SMALLINT,
                is_included BOOLEAN NOT NULL DEFAULT TRUE,
                is_system_generated BOOLEAN NOT NULL DEFAULT TRUE,
                reviewer_notes TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT uq_claim_line_lot_stage_source
                    UNIQUE (claim_id, lot_id, stage_status_id, source_type)
            )
        """))
        conn.execute(text("CREATE INDEX ix_claim_lines_claim_id ON progress_claim_lines(claim_id)"))

    # ── progress_claim_evidence ────────────────────────────────────────────────
    if not _has_table(conn, "progress_claim_evidence"):
        conn.execute(text("""
            CREATE TABLE progress_claim_evidence (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                claim_id UUID NOT NULL REFERENCES municipality_progress_claims(id) ON DELETE CASCADE,
                line_id UUID REFERENCES progress_claim_lines(id) ON DELETE CASCADE,
                attachment_id UUID REFERENCES attachments(id) ON DELETE SET NULL,
                evidence_type VARCHAR(50),
                caption VARCHAR(500),
                is_included BOOLEAN NOT NULL DEFAULT TRUE,
                added_by UUID REFERENCES users(id) ON DELETE SET NULL,
                added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX ix_claim_evidence_claim_id ON progress_claim_evidence(claim_id)"))

    # ── programme_activities ───────────────────────────────────────────────────
    if not _has_table(conn, "programme_activities"):
        conn.execute(text("""
            CREATE TABLE programme_activities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                activity_number VARCHAR(80) NOT NULL,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
                lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
                stage_status_id UUID REFERENCES project_stage_status(id) ON DELETE SET NULL,
                title VARCHAR(300) NOT NULL,
                description TEXT,
                activity_type VARCHAR(30) NOT NULL DEFAULT 'CONSTRUCTION',
                planned_start_date DATE NOT NULL,
                planned_finish_date DATE NOT NULL,
                actual_start_date DATE,
                actual_finish_date DATE,
                baseline_start_date DATE,
                baseline_finish_date DATE,
                duration_days INTEGER,
                progress_pct SMALLINT NOT NULL DEFAULT 0,
                status VARCHAR(30) NOT NULL DEFAULT 'NOT_STARTED',
                predecessor_id UUID REFERENCES programme_activities(id) ON DELETE SET NULL,
                lag_days INTEGER NOT NULL DEFAULT 0,
                is_critical_path BOOLEAN NOT NULL DEFAULT FALSE,
                is_milestone BOOLEAN NOT NULL DEFAULT FALSE,
                responsible_team VARCHAR(200),
                notes TEXT,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_activity_number UNIQUE (activity_number)
            )
        """))
        conn.execute(text("CREATE INDEX ix_programme_activities_project_id ON programme_activities(project_id)"))
        conn.execute(text("CREATE INDEX ix_programme_activities_status ON programme_activities(status)"))

    # ── weekly_plans ───────────────────────────────────────────────────────────
    if not _has_table(conn, "weekly_plans"):
        conn.execute(text("""
            CREATE TABLE weekly_plans (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                plan_number VARCHAR(80) NOT NULL,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
                week_start_date DATE NOT NULL,
                week_end_date DATE NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                submitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
                approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
                submitted_at TIMESTAMPTZ,
                approved_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_plan_number UNIQUE (plan_number),
                CONSTRAINT uq_weekly_plan_project_site_week UNIQUE (project_id, site_id, week_start_date)
            )
        """))
        conn.execute(text("CREATE INDEX ix_weekly_plans_project_id ON weekly_plans(project_id)"))

    # ── weekly_plan_items ──────────────────────────────────────────────────────
    if not _has_table(conn, "weekly_plan_items"):
        conn.execute(text("""
            CREATE TABLE weekly_plan_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                plan_id UUID NOT NULL REFERENCES weekly_plans(id) ON DELETE CASCADE,
                programme_activity_id UUID REFERENCES programme_activities(id) ON DELETE SET NULL,
                stage_status_id UUID REFERENCES project_stage_status(id) ON DELETE SET NULL,
                lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
                description TEXT NOT NULL,
                planned_progress_pct SMALLINT NOT NULL DEFAULT 0,
                actual_progress_pct SMALLINT,
                carry_forward BOOLEAN NOT NULL DEFAULT FALSE,
                completion_notes TEXT,
                completed_at TIMESTAMPTZ,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text("CREATE INDEX ix_weekly_plan_items_plan_id ON weekly_plan_items(plan_id)"))


def downgrade():
    conn = op.get_bind()
    for tbl in [
        "weekly_plan_items",
        "weekly_plans",
        "programme_activities",
        "progress_claim_evidence",
        "progress_claim_lines",
        "municipality_progress_claims",
    ]:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
