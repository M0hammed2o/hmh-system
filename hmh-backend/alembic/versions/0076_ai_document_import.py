"""AI Document Import & Reconciliation Engine

Adds the ingestion layer for scanned/uploaded procurement paperwork.

Strictly additive: seven new tables and six new enum types. No existing
table, column, constraint or row is modified or removed, so the migration
is safe to apply to a live database and the downgrade is a clean drop of
only what this revision created.

The engine owns no business balances. Material requests, purchase orders,
goods receipts and supplier invoices continue to be created by the existing
domain services; ai_import_postings merely records that a posting happened
so a retry cannot produce a second one (enforced by the UNIQUE index on
idempotency_key).

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-12
"""
from alembic import op
from sqlalchemy import text

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


_ENUMS = {
    "ai_import_batch_status_enum": [
        "OPEN", "PROCESSING", "COMPLETE", "CANCELLED",
    ],
    "ai_import_document_type_enum": [
        "MATERIAL_REQUEST", "PURCHASE_ORDER", "SUPPLIER_INVOICE", "DELIVERY_NOTE",
        "GOODS_RECEIVED_NOTE", "SUPPLIER_CREDIT_NOTE", "PAYMENT_PROOF", "UNKNOWN",
    ],
    "ai_import_document_status_enum": [
        "UPLOADED", "QUEUED", "PROCESSING", "EXTRACTED", "CLASSIFIED", "MATCHING",
        "AWAITING_REVIEW", "AWAITING_AUTHORISATION", "READY_TO_POST", "POSTED",
        "PARTIALLY_POSTED", "FAILED", "REJECTED", "DUPLICATE",
    ],
    "ai_import_processing_outcome_enum": [
        "AUTO_ELIGIBLE", "NEEDS_REVIEW", "BLOCKED",
    ],
    "ai_import_match_status_enum": [
        "PROPOSED", "CONFIRMED", "REJECTED", "AMBIGUOUS",
    ],
    "ai_import_job_status_enum": [
        "PENDING", "RUNNING", "COMPLETED", "FAILED", "DEAD",
    ],
}


def upgrade() -> None:
    conn = op.get_bind()

    for name, values in _ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
                    CREATE TYPE {name} AS ENUM ({labels});
                END IF;
            END $$;
        """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_batches (
            id              UUID PRIMARY KEY,
            reference       VARCHAR(50) NOT NULL UNIQUE,
            project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
            site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
            is_legacy       BOOLEAN NOT NULL DEFAULT FALSE,
            status          ai_import_batch_status_enum NOT NULL DEFAULT 'OPEN',
            notes           TEXT,
            uploaded_by     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_batches_status ON ai_import_batches (status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_batches_project_id ON ai_import_batches (project_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_batches_uploaded_by ON ai_import_batches (uploaded_by)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_documents (
            id                          UUID PRIMARY KEY,
            batch_id                    UUID NOT NULL REFERENCES ai_import_batches(id) ON DELETE CASCADE,
            file_name                   VARCHAR(255) NOT NULL,
            stored_path                 TEXT NOT NULL,
            mime_type                   VARCHAR(100) NOT NULL,
            file_size_bytes             INTEGER NOT NULL DEFAULT 0,
            checksum_sha256             VARCHAR(64) NOT NULL,
            page_count                  INTEGER,
            status                      ai_import_document_status_enum NOT NULL DEFAULT 'UPLOADED',
            processing_outcome          ai_import_processing_outcome_enum,
            outcome_reasons             JSONB,
            document_type               ai_import_document_type_enum NOT NULL DEFAULT 'UNKNOWN',
            classification_confidence   NUMERIC(5, 4),
            document_type_confirmed_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            project_id                  UUID REFERENCES projects(id) ON DELETE SET NULL,
            site_id                     UUID REFERENCES sites(id) ON DELETE SET NULL,
            supplier_id                 UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            is_legacy                   BOOLEAN NOT NULL DEFAULT FALSE,
            duplicate_of_id             UUID REFERENCES ai_import_documents(id) ON DELETE SET NULL,
            failure_reason              TEXT,
            retry_count                 INTEGER NOT NULL DEFAULT 0,
            reviewed_by                 UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at                 TIMESTAMPTZ,
            authorised_by               UUID REFERENCES users(id) ON DELETE SET NULL,
            authorised_at               TIMESTAMPTZ,
            rejection_reason            TEXT,
            uploaded_by                 UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    for col in ("batch_id", "checksum_sha256", "status", "document_type",
                "project_id", "supplier_id", "uploaded_by", "processing_outcome"):
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_ai_import_documents_{col} ON ai_import_documents ({col})"
        ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_extractions (
            id                  UUID PRIMARY KEY,
            document_id         UUID NOT NULL REFERENCES ai_import_documents(id) ON DELETE CASCADE,
            schema_version      VARCHAR(20) NOT NULL,
            prompt_version      VARCHAR(20) NOT NULL,
            provider            VARCHAR(50) NOT NULL,
            model               VARCHAR(100),
            extraction_mode     VARCHAR(30) NOT NULL,
            fields              JSONB,
            line_items          JSONB,
            arithmetic_checks   JSONB,
            warnings            JSONB,
            raw_text            TEXT,
            raw_response        TEXT,
            overall_confidence  NUMERIC(5, 4),
            is_current          BOOLEAN NOT NULL DEFAULT TRUE,
            input_tokens        INTEGER,
            output_tokens       INTEGER,
            cost_usd            NUMERIC(10, 6),
            duration_ms         INTEGER,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_extractions_document_id ON ai_import_extractions (document_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_extractions_is_current ON ai_import_extractions (is_current)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_matches (
            id            UUID PRIMARY KEY,
            document_id   UUID NOT NULL REFERENCES ai_import_documents(id) ON DELETE CASCADE,
            target_type   VARCHAR(50) NOT NULL,
            target_id     UUID,
            target_label  VARCHAR(255),
            status        ai_import_match_status_enum NOT NULL DEFAULT 'PROPOSED',
            method        VARCHAR(50) NOT NULL,
            score         NUMERIC(5, 4),
            explanation   TEXT,
            evidence      JSONB,
            decided_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at    TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    for col in ("document_id", "target_type", "target_id", "status"):
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_ai_import_matches_{col} ON ai_import_matches ({col})"
        ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_postings (
            id               UUID PRIMARY KEY,
            document_id      UUID NOT NULL REFERENCES ai_import_documents(id) ON DELETE CASCADE,
            idempotency_key  VARCHAR(200) NOT NULL,
            entity_type      VARCHAR(50) NOT NULL,
            entity_id        UUID,
            entity_label     VARCHAR(255),
            project_id       UUID REFERENCES projects(id) ON DELETE SET NULL,
            payload          JSONB,
            posted_by        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            posted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            reversed_at      TIMESTAMPTZ,
            reversed_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            reversal_reason  TEXT,
            CONSTRAINT uq_ai_import_postings_idempotency_key UNIQUE (idempotency_key)
        )
    """))
    for col in ("document_id", "entity_type", "entity_id", "project_id"):
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_ai_import_postings_{col} ON ai_import_postings ({col})"
        ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_jobs (
            id               UUID PRIMARY KEY,
            document_id      UUID NOT NULL REFERENCES ai_import_documents(id) ON DELETE CASCADE,
            job_type         VARCHAR(50) NOT NULL DEFAULT 'process',
            status           ai_import_job_status_enum NOT NULL DEFAULT 'PENDING',
            attempt_count    INTEGER NOT NULL DEFAULT 0,
            max_attempts     INTEGER NOT NULL DEFAULT 3,
            next_attempt_at  TIMESTAMPTZ,
            last_attempt_at  TIMESTAMPTZ,
            last_error       TEXT,
            locked_at        TIMESTAMPTZ,
            locked_by        VARCHAR(100),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at     TIMESTAMPTZ
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_jobs_document_id ON ai_import_jobs (document_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_jobs_status ON ai_import_jobs (status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_jobs_next_attempt_at ON ai_import_jobs (next_attempt_at)"))
    # One live job per document per type — the structural guard against a
    # double enqueue creating two concurrent extractions of the same file.
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_import_jobs_active
        ON ai_import_jobs (document_id, job_type)
        WHERE status IN ('PENDING', 'RUNNING')
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_import_corrections (
            id             UUID PRIMARY KEY,
            document_id    UUID NOT NULL REFERENCES ai_import_documents(id) ON DELETE CASCADE,
            extraction_id  UUID REFERENCES ai_import_extractions(id) ON DELETE SET NULL,
            field_path     VARCHAR(200) NOT NULL,
            before_value   TEXT,
            after_value    TEXT,
            reason         TEXT,
            corrected_by   UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_import_corrections_document_id ON ai_import_corrections (document_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "ai_import_corrections",
        "ai_import_jobs",
        "ai_import_postings",
        "ai_import_matches",
        "ai_import_extractions",
        "ai_import_documents",
        "ai_import_batches",
    ):
        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    for name in _ENUMS:
        conn.execute(text(f"DROP TYPE IF EXISTS {name}"))
