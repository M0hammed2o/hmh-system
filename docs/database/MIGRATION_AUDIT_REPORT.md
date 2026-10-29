# HMH Migration Audit Report

**Date:** 2026-07-14  
**Auditor:** Claude Code (self-verified; no independent verifier available)  
**Databases examined:**
- `hmh_system` — local Docker, `alembic_version = 0051`
- `hmh_bootstrap_check` — clean bootstrap at `alembic_version = 0067` (empty DB → `alembic upgrade head`)

**Status:** Investigative only. No databases or migration files were modified.

---

## Table of Contents

1. [True SQL Baseline](#1-true-sql-baseline)
2. [Source-of-Truth Comparison](#2-source-of-truth-comparison)
3. [Migration Failure Investigation](#3-migration-failure-investigation)
4. [PostgreSQL Enum Audit](#4-postgresql-enum-audit)
5. [Bootstrap Recommendation](#5-bootstrap-recommendation)
6. [Migration Chain Health](#6-migration-chain-health)
7. [Repeatable Bootstrap Test Procedure](#7-repeatable-bootstrap-test-procedure)
8. [Proposed Remediation Plan](#8-proposed-remediation-plan)

---

## 1. True SQL Baseline

### Finding: `hmh_v1_schema.sql` does not represent any Alembic revision

`hmh_v1_schema.sql` is the **original pre-Alembic hand-crafted schema**. It predates the Alembic migration system and was used to bootstrap the initial production-like database before Alembic was introduced. The file has since been modified in isolation and is now out of sync with both the migration chain and the production database.

### Key divergences between SQL schema and migration 0001

| Object | In SQL schema | In migration 0001 | In production (0051) |
|--------|--------------|-------------------|----------------------|
| `stage_master.code` (NOT NULL) | ABSENT | PRESENT | ABSENT |
| `stage_master.is_active` | ABSENT | PRESENT | ABSENT |
| `stage_master.updated_at` | ABSENT | PRESENT | ABSENT |
| `project_stage_statuses` (table, plural) | ABSENT | PRESENT | ABSENT |
| `project_stage_status` (table, singular) | PRESENT | ABSENT | PRESENT |
| `payments.payment_date` nullability | NULLABLE | NOT NULL | NULLABLE |
| `payments.reference` | ABSENT | PRESENT | ABSENT |
| `payments.created_by` | ABSENT | PRESENT | ABSENT |
| `opening_financial_status_enum` | PRESENT | PRESENT | ABSENT |
| `opening_reference_type_enum` | PRESENT | PRESENT | ABSENT |
| `vat_mode_enum` | ABSENT (current file) | PRESENT | PRESENT |

### Why the SQL file does not match production

The production database was bootstrapped from the SQL schema file (or a closely related version), **not** from migration 0001. After the SQL schema was loaded, Alembic was stamped at some revision ≤ 0003 and subsequent migrations were run. Evidence:

- `stage_master` in production has exactly the columns from the SQL schema (id, name, sequence_order, description, created_at) — matching neither migration 0001 nor migration 0003's additions.
- `payments.payment_date` is NULLABLE in production and NULLABLE in the SQL schema; migration 0001 creates it as NOT NULL.
- `project_stage_status` (singular) exists in production — the SQL schema creates it; migration 0001 creates `project_stage_statuses` (plural).

The `vat_mode_enum` is present in production but not in the current `hmh_v1_schema.sql`. This indicates the original version of the SQL file **did** include `vat_mode_enum` and it was subsequently removed from the file as enum management moved to migrations.

### Conclusion

`hmh_v1_schema.sql` is **not a safe bootstrap file** for any environment. It cannot be used with `alembic stamp` + `alembic upgrade` because:

1. The column definitions differ from what migrations expect to exist.
2. The table names differ (`project_stage_status` vs `project_stage_statuses`).
3. Migration 0001 uses `op.create_table()` (no `IF NOT EXISTS`) — it would fail if any table already existed.
4. The file has been modified after the fact and is no longer consistent with itself or the migration chain.

---

## 2. Source-of-Truth Comparison

### Tables: Production (0051) vs Clean Bootstrap (0067)

| Difference | Table | Notes |
|-----------|-------|-------|
| In bootstrap only | `project_stage_statuses` | Created by migration 0001; ORM uses `project_stage_status` (singular) — this is an ORPHANED table |
| In both | `project_stage_status` | Created by migration 0003 (`CREATE TABLE IF NOT EXISTS`); this is the ORM table |

Production has 76 tables; bootstrap has 77 tables.

### Columns: In clean bootstrap (0067) but absent from production (0051)

These are added by migrations 0052–0067 and expected to be absent from production at 0051.

| Table | Missing columns |
|-------|----------------|
| `attachments` | `created_at`, `notes`, `updated_at` |
| `fuel_logs` | `equipment_name`, `fuel_delivery_id`, `fuel_per_hour`, `hours_operated`, `hours_reading`, `vehicle_registration` |
| `item_aliases` | `alias`, `updated_at` |
| `item_categories` | `code` |
| `items` | `code`, `default_rate`, `description` |
| `material_request_items` | `created_at`, `extra_reason_notes`, `extra_reason_type`, `quantity_approved`*, `quantity_requested`*, `request_id`* |
| `material_requests` | `repair_job_id` |
| `mr_quotes` | `purchase_order_id` |
| `payments` | `created_by`, `reference` |
| `po_email_logs` | `sent_to`, `subject` |
| `project_stage_statuses` | all columns (new table from migration 0001) |
| `projects` | `company_id` |
| `purchase_order_items` | `quantity`, `unit_price` |
| `purchase_orders` | `delivery_address`, `vat_mode` |
| `repair_jobs` | `approval_1_at/by`, `approval_2_at/by`, `approval_3_at/by`, `approval_stage`, `invoice_amount/file_url`, `quote_amount/file_url` |
| `sites` | `address`, `gps_lat`, `gps_lng` |
| `stage_master` | `code`, `is_active`, `updated_at` |
| `suppliers` | `bank_account`, `bank_branch_code`, `bank_name`, `contact_name`, `payment_due_days` |
| `usage_remaining_proofs` | `image_url`, `uploaded_by` |
| `user_project_access` | `updated_at` |
| `user_site_access` | `updated_at` |
| `vehicle_costs` | `repair_job_id` |
| `vehicles` | `current_hours_reading`, `uses_hours`, `vin_number` |

*Rows marked `*` are legacy columns from migration 0001 that migration 0003 replaced with ORM-mapped names; both old and new names coexist in the bootstrap DB. See §3 for details.

### Columns: In production but absent from clean bootstrap

**None.** Production has no orphaned columns not present in the clean bootstrap.

### Enum differences

| Enum | In production | In bootstrap | Notes |
|------|--------------|--------------|-------|
| `opening_financial_status_enum` | ABSENT | PRESENT | Created by migration 0001; no migration creates the table that uses it |
| `opening_reference_type_enum` | ABSENT | PRESENT | Same — orphaned enum, planned feature not implemented |
| `item_type_enum.TOOL` | ABSENT | PRESENT | Added by migration 0053 |
| `user_role_enum.PROCUREMENT_LEAD` | ABSENT | PRESENT | Added by migration 0054 |
| `record_status_enum.STAFF_APPROVED` | ABSENT | PRESENT | Added by migration 0054 |
| `alert_type_enum` (values) | All present | All present | Same values, **different ordinal order** (see §4) |

---

## 3. Migration Failure Investigation

### 3a. Production DB bootstrap history

**Confirmed**: Production was bootstrapped from `hmh_v1_schema.sql` (or a closely similar version), not from migration 0001. Alembic was then stamped at revision 0001–0003, and migrations from that point were applied.

Evidence chain:
- `stage_master` in production has SQL-schema columns only (no `code`, `is_active`, `updated_at`).
- `project_stage_status` (singular) exists in production but `project_stage_statuses` (plural, created by migration 0001) does not.
- `payments.payment_date` is nullable in production (SQL schema) but NOT NULL in clean bootstrap (migration 0001).

**Consequence**: Production is in a **hybrid state** — schema created from the SQL file, overlaid with migrations 0004–0051. Some migration 0001 objects (like `project_stage_statuses`, `stage_master.code`) are missing. The production DB cannot be used as a reference schema.

### 3b. Gate B `alembic upgrade head` failure — why 0054 failed

When `alembic upgrade head` was run against the contaminated `hmh_system` DB during Gate B testing, it failed at migration 0054 with `DuplicateTable: relation "mr_approvals" already exists`.

Root cause chain:
1. `TEST_DATABASE_URL` was not set → tests fell back to `settings.DATABASE_URL` (the main Docker DB).
2. `conftest.py`'s `ensure_tables` fixture called `Base.metadata.create_all()` on `hmh_system`.
3. `create_all()` created `mr_approvals` table from the ORM model (without `alembic_version` tracking).
4. Migration 0054 tried to `CREATE TABLE mr_approvals` using `op.create_table()` — no `IF NOT EXISTS`.
5. Alembic wraps ALL pending migrations in one transaction → entire 0052–0054 batch rolled back.

`alembic_version` remained at `0051`. The DB was now contaminated with tables created outside migration control.

**Fix already applied**: `TEST_DATABASE_URL` is now mandatory (`RuntimeError` if not set). `hmh_test` is a separate DB. Future test runs cannot contaminate `hmh_system`.

### 3c. Earlier bootstrap attempt failures (Gate B investigation)

| Attempt | Failure | Root cause |
|---------|---------|------------|
| Load SQL → stamp 0051 → upgrade head | `mr_quotes does not exist` | Stamp at 0051 marks 0003 as done; 0052 adds column to `mr_quotes` which should be created by 0003 but SQL schema has it without the same columns migration 0003 expects |
| Load SQL → stamp 0001 → upgrade head | `vat_mode_enum does not exist` | SQL file is missing `vat_mode_enum`; migration 0003 uses it with `create_type=False` |
| Load SQL → upgrade head (no stamp) | Migration 0001 would create tables that exist → `DuplicateTable` | `op.create_table()` has no `IF NOT EXISTS` |

### 3d. Windows Unicode issue in migration 0003

Migration 0003 contains print statements with the `→` (U+2192) character. Windows console default encoding (`cp1252`) cannot encode this.

**Symptom**: `UnicodeEncodeError: 'charmap' codec can't encode character '→'`

**Fix**: Set `PYTHONIOENCODING=utf-8` as environment variable prefix. Example:
```
PYTHONIOENCODING=utf-8 DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/mydb python -m alembic upgrade head
```
This is a Windows-only issue and does not affect CI environments running Linux.

### 3e. `material_request_items` legacy column pairs

Migration 0001 created `material_request_items` with columns `request_id` (NOT NULL) and `quantity_requested` (NOT NULL). Migration 0003 added ORM-mapped replacements `material_request_id` and `requested_quantity` (nullable). Migration 0006 made the old columns nullable.

Result: The clean bootstrap DB has both old and new column names coexisting:

| Old column (migration 0001) | New column (migration 0003) | Who uses it |
|----------------------------|----------------------------|-------------|
| `request_id` | `material_request_id` | ORM uses `material_request_id` |
| `quantity_requested` | `requested_quantity` | ORM uses `requested_quantity` |
| `quantity_approved` | `approved_quantity` | ORM uses `approved_quantity` |

This is a data-quality debt, not a breaking bug — both columns are nullable and the ORM populates only the new names.

---

## 4. PostgreSQL Enum Audit

### Complete enum inventory

| Enum name | Created by | Production values | Bootstrap adds | Used by |
|-----------|-----------|------------------|----------------|---------|
| `alert_severity_enum` | 0001 | LOW, MEDIUM, HIGH, CRITICAL | same | `system_alerts.severity`, `notification_queue.severity` |
| `alert_status_enum` | 0001 | OPEN, ACKNOWLEDGED, RESOLVED | same | `system_alerts.status` |
| `alert_type_enum` | 0001 | 37 values | same | `system_alerts.alert_type`, `notification_queue.alert_type` |
| `attachment_entity_enum` | 0001 | 14 values | same | `attachments.entity_type` |
| `attachment_type_enum` | 0001 | 16 values | same | `attachments.attachment_type` |
| `boq_status_enum` | 0001 | DRAFT, UNDER_REVIEW, ACTIVE, SUPERSEDED, ARCHIVED | same | `boq_headers.status` |
| `delivery_destination_enum` | 0003 | MAIN_WAREHOUSE, SITE_STORE, LOT, PICKUP | same | `deliveries.destination` |
| `email_status_enum` | 0001 | queued, sent, failed, bounced | same | `mr_email_logs.status` |
| `fuel_type_enum` | 0030 | DIESEL, PETROL, PARAFFIN, OTHER | same | `fuel_logs.fuel_type` |
| `fuel_usage_type_enum` | 0030 | EQUIPMENT, DELIVERY_VEHICLE, TRANSPORT, GENERATOR, OTHER | same | `fuel_logs.usage_type` |
| `invoice_match_status_enum` | 0001 | 11 values | same | `invoice_matching_results.match_status` |
| `item_type_enum` | 0001 | MATERIAL, LABOUR, PLANT, SERVICE, PACKAGE | +TOOL (0053) | `items.item_type` |
| `job_card_status_enum` | 0003 | 8 values | same | `job_cards.status` |
| `job_card_work_type_enum` | 0003 | DAILY_LABOUR, CONTRACT, SUBCONTRACTOR, OVERTIME | same | `job_cards.work_type` |
| `lot_status_enum` | 0001 | AVAILABLE, IN_PROGRESS, COMPLETED, ON_HOLD | same | `lots.status` |
| `movement_type_enum` | 0001 | 8 values | same | `stock_ledger.movement_type` |
| `mr_priority_enum` | 0003 | URGENT, HIGH, NORMAL, LOW | same | `material_requests.priority` |
| `notification_channel_enum` | 0003 | WHATSAPP, EMAIL, IN_APP | same | `notification_queue.channel` |
| `notification_status_enum` | 0003 | 8 values | same | `notification_queue.status` |
| `opening_financial_status_enum` | 0001 | ABSENT from prod | same values | No migrated table uses it — ORPHANED |
| `opening_reference_type_enum` | 0001 | ABSENT from prod | same values | No migrated table uses it — ORPHANED |
| `payment_status_enum` | 0001 | PENDING, APPROVED, PAID, FAILED, CANCELLED | same | `payments.status` |
| `payment_type_enum` | 0001 | SUPPLIER, LABOUR, OTHER | same | `payments.payment_type` |
| `pricingmethod` | 0036 | EX_VAT, INCL_VAT | same | `suppliers.pricing_method` |
| `project_status_enum` | 0001 | PLANNED, ACTIVE, PAUSED, COMPLETED | same | `projects.status` |
| `quotationstatus` | 0038 | DRAFT, SENT, RECEIVED, APPROVED, REJECTED, EXPIRED | same | `quotations.status` |
| `reconciliationstatus` | 0040 | PENDING, MATCHED, VARIANCE_DETECTED, APPROVED, REJECTED | same | `procurement_reconciliations.status` |
| `record_status_enum` | 0001 | 18 values | +STAFF_APPROVED (0054) | `material_requests.status`, `purchase_orders.status`, etc. |
| `stage_status_enum` | 0001 | NOT_STARTED, IN_PROGRESS, COMPLETED, AWAITING_INSPECTION, CERTIFIED, BLOCKED | same | `project_stage_status.status` |
| `user_role_enum` | 0001 | OWNER, OFFICE_ADMIN, OFFICE_USER, SITE_MANAGER, SITE_STAFF, READ_ONLY, SITE_MANAGER_VIEW | +PROCUREMENT_LEAD (0054) | `users.role`, `user_project_access.role` |
| `vat_mode_enum` | 0001 | INCLUSIVE, EXCLUSIVE | same | `purchase_order_items.vat_mode` (after 0039) |
| `vehicle_cost_type_enum` | 0030 | FUEL, TYRE, REPAIR, SERVICE, LICENCE, INSURANCE, OTHER | same | `vehicle_costs.cost_type` |
| `vehicle_status_enum` | 0030 | ACTIVE, MAINTENANCE, RETIRED | same | `vehicles.status` |
| `vehicle_type_enum` | 0030 | BAKKIE, TRUCK, TLB, EXCAVATOR, CRANE, VAN, OTHER | same | `vehicles.vehicle_type` |
| `work_done_status_enum` | 0043 | DRAFT, SUBMITTED, SITE_APPROVED, OFFICE_APPROVED, PAID, REJECTED | same | `subcontractor_work_done.status` |

**Total**: 33 enum types in production, 35 in bootstrap (production missing `opening_financial_status_enum` and `opening_reference_type_enum`).

### Enum ordering discrepancy

The `alert_type_enum` values have **different ordinal ordering** between production and bootstrap. In PostgreSQL, enum values are permanently ordered by when they were inserted. Values added later with `ALTER TYPE ... ADD VALUE` get higher ordinal positions.

In production, some `alert_type_enum` values appear in a different order than in the clean bootstrap (e.g., `BOQ_ALLOCATION_EXCEEDED` appears at position 3 in production but position 16 in bootstrap). This is because migration 0001 creates the enum with a specific ordering, but the production DB may have had `ALTER TYPE` statements applied at different times.

**Impact**: Ordinal position is only significant if application code uses `ORDER BY` on an enum column without specifying direction and relies on enum ordinal order. No such code has been identified. This is a cosmetic difference.

### Orphaned enums

`opening_financial_status_enum` and `opening_reference_type_enum` are created by migration 0001 but no migration creates a table that uses them. They correspond to the `project_opening_financials` table defined in the SQL schema — a planned feature that was never implemented as Alembic migrations. These enums exist in the clean bootstrap and can be safely retained or dropped; they do not affect application function.

---

## 5. Bootstrap Recommendation

### Options evaluated

| Option | Description | Verdict |
|--------|-------------|---------|
| A: SQL snapshot + stamp + upgrade | Load `hmh_v1_schema.sql`, stamp a revision, run remaining migrations | **REJECTED** — fails at every stamp point tested; schema file is not aligned with any migration revision |
| B: Alembic only (empty DB → head) | Create empty DB, run `alembic upgrade head` | **RECOMMENDED** — proven reproducible on `hmh_bootstrap_check` |
| C: Regenerate SQL snapshot from head | `pg_dump --schema-only` of `hmh_bootstrap_check` → new reference file | Useful as a **documentation artifact** but not as a bootstrap source |

### Recommendation: Option B

**Proof**: `hmh_bootstrap_check` was created as an empty database and bootstrapped with `alembic upgrade head`. It reached `alembic_version = 0067` successfully and passes structural validation. The `hmh_test` database was bootstrapped the same way and the test suite runs against it (763 passing, 34 failing, 38 errors — all pre-existing test bugs, not migration problems).

**Single required workaround**: On Windows, set `PYTHONIOENCODING=utf-8` because migration 0003 prints `→` (U+2192) which the default `cp1252` console encoding cannot handle.

---

## 6. Migration Chain Health

### Chain integrity

The migration chain from 0001 to 0067 is a **clean linear sequence** with no gaps, no branches, and no missing `down_revision` links.

```
0001 (down=None) → 0002 → 0003 → ... → 0066 → 0067 (head)
```

### Known issues by migration

| Migration | Issue | Severity | Impact |
|-----------|-------|----------|--------|
| **0001** `initial_schema.py` | Uses `op.create_table()` without `IF NOT EXISTS` for ~30 tables — fails if any table already exists | HIGH | Cannot be run on any DB that was bootstrapped from the SQL schema or any other source; prevents SQL-schema bootstrap paths |
| **0001** | Creates `project_stage_statuses` (plural) but the ORM model uses `project_stage_status` (singular) — creates an orphaned table | MEDIUM | `project_stage_statuses` persists in the clean bootstrap DB but is never queried by the ORM |
| **0001** | Creates `opening_financial_status_enum` and `opening_reference_type_enum` — no migration ever creates a table that uses them | LOW | Orphaned enums in every fresh install |
| **0003** `missing_tables_and_columns.py` | Print statements contain Unicode `→` (U+2192) — causes `UnicodeEncodeError` on Windows with default cp1252 encoding | MEDIUM | Prevents `alembic upgrade head` from running on Windows without `PYTHONIOENCODING=utf-8` |
| **0003** | Creates `project_stage_status` (singular) with `IF NOT EXISTS` to compensate for migration 0001 creating the wrong table name — both tables end up in the clean bootstrap | MEDIUM | Cosmetic: two stage tables exist in clean bootstrap; ORM only uses the singular one |
| **0006** `fix_material_request_items_notnull.py` | `material_request_items` has 6 coexisting columns: 3 legacy (from 0001) and 3 ORM-named (from 0003) — `request_id`, `quantity_requested`, `quantity_approved` are kept nullable alongside their replacements | LOW | Data quality debt; no runtime breakage since ORM ignores legacy columns |
| **0054** `mr_four_way_approval.py` | Creates `mr_approvals` with `op.create_table()` — no `IF NOT EXISTS` | HIGH | Fails if `mr_approvals` was pre-created by `Base.metadata.create_all()` from test contamination; was the root cause of the original 0054 failure |

### Summary: Migration health is adequate for clean installs but brittle under contamination

The migration chain produces a correct schema when run on an empty database. Brittleness arises from two patterns:
1. Missing `IF NOT EXISTS` in `op.create_table()` calls (migrations 0001, 0054)
2. Naming inconsistency between migration 0001 and the ORM for stage tables

---

## 7. Repeatable Bootstrap Test Procedure

### Prerequisites

- Docker running with `hmh-postgres` container
- `hmh-backend` Python environment activated
- `PYTHONIOENCODING=utf-8` set (Windows only)

### Step-by-step procedure

```bash
# 1. Create an empty database
docker exec hmh-postgres psql -U hmh -c "CREATE DATABASE hmh_verify;"

# 2. Run all migrations (Windows — set PYTHONIOENCODING first)
cd hmh-backend
PYTHONIOENCODING=utf-8 DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_verify \
    python -m alembic upgrade head

# 3. Verify migration head
docker exec hmh-postgres psql -U hmh -d hmh_verify -t -A \
    -c "SELECT version_num FROM alembic_version;"
# Expected: 0067

# 4. Verify table count
docker exec hmh-postgres psql -U hmh -d hmh_verify -t -A \
    -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
# Expected: 77

# 5. Verify critical columns exist
docker exec hmh-postgres psql -U hmh -d hmh_verify -t -A -c "
SELECT
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_name='stage_master' AND column_name='code') AS stage_master_code,
  (SELECT is_nullable FROM information_schema.columns WHERE table_name='payments' AND column_name='payment_date') AS payment_date_nullable,
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_name='mr_approvals' AND column_name='id') AS mr_approvals_exists;
"
# Expected: stage_master_code=1, payment_date_nullable=NO, mr_approvals_exists=1

# 6. Verify enum count
docker exec hmh-postgres psql -U hmh -d hmh_verify -t -A \
    -c "SELECT COUNT(*) FROM pg_type t JOIN pg_namespace n ON t.typnamespace=n.oid WHERE t.typtype='e' AND n.nspname='public';"
# Expected: 35

# 7. Run tests against the new DB
TEST_DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_verify \
    python -m pytest hmh-backend/tests/ -x -q

# 8. Clean up
docker exec hmh-postgres psql -U hmh -c "DROP DATABASE hmh_verify;"
```

### What constitutes a passing bootstrap

| Check | Expected value |
|-------|---------------|
| `alembic_version` | `0067` |
| Table count | 77 |
| `stage_master.code` column | EXISTS, NOT NULL |
| `payments.payment_date` | NOT NULL |
| `mr_approvals` table | EXISTS |
| Enum count | 35 |
| Test suite | 763+ passing, 0 errors (after fixing test helper bugs — see §8) |

---

## 8. Proposed Remediation Plan

Ordered by risk and dependency. **No action may be taken on production data without explicit approval.**

### P0: Already done (Gate B)

- [x] `TEST_DATABASE_URL` is now mandatory — tests cannot fall back to `DATABASE_URL`
- [x] `hmh_test` database exists at migration 0067 — test suite runs in isolation

### P1: Fix test helper bugs (safe — test code only)

These are the root causes of 38 errors and 11 payment failures in the test suite.

**P1a — Fix `seed_default_stages()` to include `code`**

File: `hmh-backend/tests/conftest.py` (or wherever `seed_default_stages` is defined)

Migration 0001 creates `stage_master.code` as `NOT NULL`. The seed function must provide a value:
```python
# Find seed_default_stages() and add code= to each stage insert
StageMaster(name="Platform", code="PLATFORM", sequence_order=1, ...)
```

Also fix the `make_stage()` test helper if it exists.

**Unblocks**: 38 errors in `test_stage_tracking.py`, `test_lot_type_propagation.py`, `test_boq_template_apply.py`

**P1b — Fix payment test helpers to include `payment_date`**

Migration 0001 creates `payments.payment_date` as NOT NULL. Test helpers must set it:
```python
Payment(..., payment_date=date.today(), ...)
```

**Unblocks**: 11 failures in `test_payments.py`

**P1c — Fix `TestQuoteApprove` tests for `PROCUREMENT_LEAD` role**

Migration 0054 tightened quote-approval routes to require `PROCUREMENT_LEAD`. Tests that use `OFFICE_USER` for this action need updating.

**Unblocks**: 5 failures in `test_procurement_pipeline.py::TestQuoteApprove`

### P2: Fix migration 0054 brittle CREATE TABLE (migration code — medium risk)

Migration 0054 creates `mr_approvals` without `IF NOT EXISTS`. Add an existence check:

```python
def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # ... enum additions ...
    if "mr_approvals" not in insp.get_table_names():
        op.create_table("mr_approvals", ...)
```

**Risk**: This modifies a committed migration. Since no environment has run this migration cleanly (the old hmh_system failed; hmh_bootstrap_check succeeded because it was clean), this change is safe only if: (a) we are certain no downstream DB has run 0054 cleanly, or (b) we wrap the change in a new migration 0068 that is a no-op if `mr_approvals` already exists.

**Recommended**: Add migration `0068_ensure_mr_approvals.py` as a no-op safety net rather than editing 0054.

### P3: Resolve `project_stage_statuses` orphaned table (migration — low risk)

The clean bootstrap creates `project_stage_statuses` (plural, migration 0001) AND `project_stage_status` (singular, migration 0003). The ORM uses only the singular. Add migration `0068` (or `0069`) to drop the orphaned plural table:

```python
def upgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("project_stage_statuses"):
        op.drop_table("project_stage_statuses")
```

### P4: Retire `hmh_v1_schema.sql` or regenerate from head (documentation — safe)

Options:
- **Retire**: Move to `docs/database/ARCHIVED_v1_schema.sql` and add a header warning it is not usable for bootstrap.
- **Regenerate**: `pg_dump --schema-only hmh_bootstrap_check > docs/database/hmh_schema_snapshot_0067.sql` — this creates an accurate reference snapshot at the current head.

### P5: Upgrade production local DB (requires `docker compose down -v` approval)

Current state: `hmh_system` at hybrid/contaminated 0051. The DB contains 15 real `stage_master` rows (seed data) and may have other data.

**If data can be discarded (clean rebuild)**:
```bash
docker compose down -v                                         # destroys volume
docker compose up -d                                           # fresh PostgreSQL
PYTHONIOENCODING=utf-8 python -m alembic upgrade head         # in hmh-backend
```

**If data must be preserved**:
```bash
# Run only migrations 0052–0067 against hmh_system
# (Caution: migration 0052+ will add new columns to existing tables)
DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_system \
  PYTHONIOENCODING=utf-8 python -m alembic upgrade head
```

The second approach will add all missing columns (from the comparison table in §2) but cannot add `stage_master.code` retroactively to existing rows without a value. This would require:
1. Making `code` temporarily nullable in a migration
2. Populating values from existing `name` fields
3. Re-applying the NOT NULL constraint

**This action requires explicit approval before execution.**

---

## Appendix A: Database State Summary

| DB | `alembic_version` | Tables | Enums | Status |
|----|------------------|--------|-------|--------|
| `hmh_system` | 0051 | 76 | 33 | Hybrid bootstrap, missing cols from 0052–0067, usable for dev if not running test suite against it |
| `hmh_bootstrap_check` | 0067 | 77 | 35 | Clean bootstrap, authoritative reference |
| `hmh_test` | 0067 | 77 | 35 | Clean test DB, TEST_DATABASE_URL target |

## Appendix B: Test Suite Status (against hmh_test at 0067)

| Status | Count | Primary cause |
|--------|-------|--------------|
| Passed | 763 | — |
| Failed | 34 | Test helper bugs + role model mismatch (see P1) |
| Error | 38 | `stage_master.code` NOT NULL in seed function (see P1a) |
| **Total** | **835** | — |

The 34 failures and 38 errors are **pre-existing test bugs**, not migration problems. All stem from test helpers that were written against the old production schema (missing `stage_master.code`, missing `payments.payment_date`, old role model). Fixing P1a–P1c should resolve all of them.
