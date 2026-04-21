-- =============================================================================
-- HMH Construction Management System — Demo Migration
-- Apply this ONCE against the demo database before starting the backend.
-- Safe to run on a fresh schema (uses IF NOT EXISTS / DO blocks).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. NEW ENUM TYPES
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vat_mode_enum') THEN
        CREATE TYPE vat_mode_enum AS ENUM ('INCLUSIVE', 'EXCLUSIVE');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'fuel_type_enum') THEN
        CREATE TYPE fuel_type_enum AS ENUM ('DIESEL', 'PETROL', 'PARAFFIN', 'OTHER');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'fuel_usage_type_enum') THEN
        CREATE TYPE fuel_usage_type_enum AS ENUM (
            'EQUIPMENT',
            'DELIVERY_VEHICLE',
            'TRANSPORT',
            'GENERATOR',
            'OTHER'
        );
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- 2. ADD VAT COLUMNS TO purchase_order_items
--    Existing rows default to INCLUSIVE / 15% to match the historical assumption.
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'purchase_order_items' AND column_name = 'vat_mode'
    ) THEN
        ALTER TABLE purchase_order_items
            ADD COLUMN vat_mode vat_mode_enum NOT NULL DEFAULT 'INCLUSIVE';
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'purchase_order_items' AND column_name = 'vat_rate'
    ) THEN
        ALTER TABLE purchase_order_items
            ADD COLUMN vat_rate NUMERIC(5, 2) NOT NULL DEFAULT 15.00;
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- 3. CREATE fuel_logs TABLE
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fuel_logs (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope
    project_id      UUID            NOT NULL
                                    REFERENCES projects(id) ON DELETE CASCADE,
    site_id         UUID            REFERENCES sites(id) ON DELETE SET NULL,

    -- Fuel detail
    fuel_type       fuel_type_enum  NOT NULL DEFAULT 'DIESEL',
    usage_type      fuel_usage_type_enum NOT NULL DEFAULT 'EQUIPMENT',
    equipment_ref   VARCHAR(200),           -- vehicle / plant / generator ref
    litres          NUMERIC(10, 2)  NOT NULL,
    cost_per_litre  NUMERIC(10, 4),
    total_cost      NUMERIC(14, 2)
        GENERATED ALWAYS AS (
            CASE
                WHEN cost_per_litre IS NOT NULL
                THEN ROUND(litres * cost_per_litre, 2)
                ELSE NULL
            END
        ) STORED,

    -- Accountability
    fuelled_by      VARCHAR(200),           -- person name who received the fuel
    recorded_by     UUID            NOT NULL
                                    REFERENCES users(id) ON DELETE RESTRICT,
    fuel_date       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Notes
    notes           TEXT,

    -- Audit
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 4. INDEXES FOR fuel_logs
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_fuel_logs_project_id
    ON fuel_logs(project_id);

CREATE INDEX IF NOT EXISTS idx_fuel_logs_site_id
    ON fuel_logs(site_id);

CREATE INDEX IF NOT EXISTS idx_fuel_logs_fuel_date
    ON fuel_logs(fuel_date DESC);

CREATE INDEX IF NOT EXISTS idx_fuel_logs_recorded_by
    ON fuel_logs(recorded_by);

-- -----------------------------------------------------------------------------
-- 5. AUTO-UPDATE updated_at ON fuel_logs
--    Reuses the same pattern as other tables in the schema.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_update_fuel_log_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fuel_logs_updated_at ON fuel_logs;

CREATE TRIGGER trg_fuel_logs_updated_at
BEFORE UPDATE ON fuel_logs
FOR EACH ROW EXECUTE FUNCTION fn_update_fuel_log_timestamp();

-- =============================================================================
-- END OF MIGRATION
-- =============================================================================
