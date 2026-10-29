# Schema Reconciliation Report

**Date:** 2026-07-15  
**Scope:** Full comparison — Production (`hmh_system` at 0051) vs Clean Bootstrap (`hmh_bootstrap_check` at 0067) vs Alembic Migration Chain (0001–0067)  
**Method:** Live database inspection + migration file analysis  
**Status:** Documentation and analysis only. No schema changes made.

---

## Classification Key

| Code | Meaning |
|------|---------|
| **EXP** | Expected — object exists because of newer migrations (0052–0067). Production will gain it once those migrations run. No action needed now. |
| **LEG** | Legacy — exists for backwards compatibility. Safe to retain. Document removal conditions. |
| **RED** | Redundant — two objects represent the same concept. Needs canonical choice. |
| **BUG** | Schema differs because something is incorrect. |
| **MAN** | Requires manual migration — cannot safely automate. |
| **BIZ** | Business decision required before action. |

---

## Section 1 — Tables

### 1.1 Tables present in both databases

All 76 production tables are present in the clean bootstrap. The 76-table set is internally consistent.

### 1.2 Tables in clean bootstrap but NOT in production

| Table | Classification | Responsible Migration | Notes |
|-------|---------------|-----------------------|-------|
| `project_stage_statuses` | **BUG** | 0001 | Created by migration 0001 with the wrong name. ORM uses `project_stage_status` (singular). Migration 0003 created the correct table. Both now coexist in the clean bootstrap. This is an orphaned table that no ORM model or query ever touches. See §7 for resolution. |

### 1.3 Tables in production but NOT in clean bootstrap

None. Production has no tables absent from the clean bootstrap.

### 1.4 All workshop tables (0058–0062)

The following tables exist in both databases (added by migrations 0058–0062 and run against production at 0051 before the contamination):

`workshop_categories`, `workshop_delivery_notes`, `workshop_invoices`, `workshop_issuances`, `workshop_items`, `workshop_mr_approvals`, `workshop_mr_email_logs`, `workshop_mr_lines`, `workshop_mrs`, `workshop_purchase_orders`, `workshop_quote_approvals`, `workshop_quotes`, `workshop_stock`, `workshop_supplier_links`

---

## Section 2 — Column Differences by Table

### 2.1 Key: every column in bootstrap absent from production

All differences are classified **EXP** (added by migrations 0052–0067) unless noted otherwise.

---

#### `attachments`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | 0027 | EXP |
| `notes` | TEXT NULL | 0027 | EXP |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | 0027 | EXP |

---

#### `fuel_logs`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `equipment_name` | VARCHAR(255) NULL | 0063 | EXP |
| `fuel_delivery_id` | UUID NULL FK→fuel_deliveries | 0063 | EXP |
| `fuel_per_hour` | NUMERIC(8,3) NULL | 0063 | EXP |
| `hours_operated` | NUMERIC(8,2) NULL | 0063 | EXP |
| `hours_reading` | NUMERIC(10,2) NULL | 0063 | EXP |
| `vehicle_registration` | VARCHAR(20) NULL | 0063 | EXP |

---

#### `item_aliases`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `alias` | VARCHAR(255) NULL | 0028 | EXP |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | 0028 | EXP |

---

#### `item_categories`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `code` | VARCHAR(50) NULL | 0053 | EXP |

---

#### `items`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `code` | VARCHAR(50) NULL | 0053 | EXP |
| `default_rate` | NUMERIC(14,2) NULL | 0053 | EXP |
| `description` | TEXT NULL | 0053 | EXP |

---

#### `material_request_items` — See also Legacy Field Analysis

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | 0003 | **RED** — exists in bootstrap from migration 0003; absent in production. Production DB has this table from the SQL schema which predates this column. Running migration 0003 against the SQL-schema-bootstrapped DB applied the `_add_col IF NOT EXISTS` logic correctly. This column is a new addition that production simply never received because it was applied via IF NOT EXISTS against an already-existing table that had no `created_at`. Verify this column exists in production before Phase 1 begins. |
| `extra_reason_notes` | TEXT NULL | 0064 | EXP |
| `extra_reason_type` | VARCHAR(50) NULL | 0064 | EXP |
| `quantity_approved` | NUMERIC(14,3) NULL | 0001 | **RED** — Legacy name. ORM uses `approved_quantity`. See Legacy Field Analysis. |
| `quantity_requested` | NUMERIC(14,3) NULL | 0001 | **RED** — Legacy name. ORM uses `requested_quantity`. See Legacy Field Analysis. |
| `request_id` | UUID NULL FK→material_requests | 0001 | **RED** — Legacy FK column. ORM uses `material_request_id`. See Legacy Field Analysis. |

---

#### `material_requests`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `repair_job_id` | UUID NULL FK→repair_jobs | 0057 | EXP |

---

#### `mr_quotes`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `purchase_order_id` | UUID NULL FK→purchase_orders | 0052 | EXP |

---

#### `payments` — See also Legacy Field Analysis

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `created_by` | UUID NULL FK→users | 0001 | **BUG** — Migration 0001 defines this; absent from production because production was bootstrapped from the SQL schema (which doesn't have it). ORM maps this column. If the production DB ever needs to be upgraded rather than rebuilt, this column must be added via migration. |
| `reference` | VARCHAR(255) NULL | 0001 | **RED** — Legacy alias for `payment_reference`. Dead in application code. See Legacy Field Analysis. |
| `payment_date` | DATE **NOT NULL** | 0001 | **BUG** — NOT NULL in bootstrap; NULLABLE in production. Production received this column from the SQL schema where it was nullable. All test failures in `test_payments.py` originate here. See §8. |

---

#### `po_email_logs`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `sent_to` | TEXT NULL | 0008 | **BUG** — Present in bootstrap; absent in production. This column was added by migration 0008 using `op.add_column` without `IF NOT EXISTS`, which would fail silently against a table where the column already existed via a different path. Likely the SQL schema had this table differently. Verify whether the column is needed in production. |
| `subject` | TEXT NULL | 0008 | **BUG** — Same issue as `sent_to`. |

---

#### `projects`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `company_id` | UUID NULL FK→companies | 0065 | EXP |

---

#### `purchase_order_items`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `quantity` | NUMERIC(14,3) NULL | 0007 | **BUG** — Migration 0007 title is `fix_po_items_quantity_notnull`. This column was expected to be in the DB already (created by migration 0001 as NOT NULL) but is missing from production. Same SQL-schema bootstrap issue as other migration 0001 columns. |
| `unit_price` | NUMERIC(14,2) NULL | 0007 | **BUG** — Same issue as `quantity`. |

---

#### `purchase_orders`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `delivery_address` | TEXT NULL | 0057 | EXP |
| `vat_mode` | vat_mode_enum NULL | 0039 | **BUG** — Migration 0039 adds this column. Its absence in production suggests migration 0039 either failed silently or the column was already present then removed. Needs investigation. |

---

#### `repair_jobs`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `approval_1_at/by`, `approval_2_at/by`, `approval_3_at/by`, `approval_stage` | Various | 0056 | EXP |
| `invoice_amount`, `invoice_file_url`, `quote_amount`, `quote_file_url` | Various | 0056 | EXP |

---

#### `sites`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `address` | TEXT NULL | 0001 | **BUG** — Defined by migration 0001. Absent in production because migration 0001 was never run (SQL schema bootstrap). |
| `gps_lat` | FLOAT NULL | 0001 | **BUG** — Same. |
| `gps_lng` | FLOAT NULL | 0001 | **BUG** — Same. |

---

#### `stage_master`

| Column | Production type | Bootstrap type | Classification |
|--------|----------------|----------------|----------------|
| `code` | ABSENT | VARCHAR(50) NOT NULL | **BUG** — Root cause of 38 test errors. Migration 0001 creates `stage_master` WITH `code NOT NULL`. Production has `stage_master` from the SQL schema WITHOUT `code`. `seed_default_stages()` does not provide `code`. Three-part fix needed: (1) add `code` to production via migration, (2) populate all 15 existing rows, (3) fix `seed_default_stages()`. |
| `is_active` | ABSENT | BOOLEAN NOT NULL DEFAULT true | **BUG** — Same origin. |
| `updated_at` | ABSENT | TIMESTAMPTZ NOT NULL DEFAULT now() | **BUG** — Same origin. |

---

#### `suppliers`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `bank_account` | VARCHAR(50) NULL | 0067 | EXP |
| `bank_branch_code` | VARCHAR(20) NULL | 0067 | EXP |
| `bank_name` | VARCHAR(100) NULL | 0067 | EXP |
| `contact_name` | VARCHAR(255) NULL | 0067 | EXP |
| `payment_due_days` | INTEGER NULL | 0067 | EXP |

---

#### `usage_remaining_proofs`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `image_url` | TEXT NULL | 0012/0013 | **BUG** — Early migration column absent from production. |
| `uploaded_by` | UUID NULL FK→users | 0012/0013 | **BUG** — Same. |

---

#### `user_project_access`, `user_site_access`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | 0057 | EXP |

---

#### `vehicle_costs`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `repair_job_id` | UUID NULL FK→repair_jobs | 0056 | EXP |

---

#### `vehicles`

| Column | Bootstrap type | Migration | Classification |
|--------|---------------|-----------|----------------|
| `current_hours_reading` | NUMERIC(10,2) NULL | 0057 | EXP |
| `uses_hours` | BOOLEAN NOT NULL DEFAULT false | 0057 | EXP |
| `vin_number` | VARCHAR(50) NULL | 0045 | **BUG** — Migration 0045 adds this; absent from production suggests a migration application gap. |

### 2.2 Columns present in production but absent from clean bootstrap

**None.** All production columns exist in the clean bootstrap. Production has no orphaned columns.

---

## Section 3 — Enum Differences

### 3.1 Enum types present in bootstrap but absent from production

| Enum | Classification | Notes |
|------|---------------|-------|
| `opening_financial_status_enum` | **LEG** | Created by migration 0001 via `create_enum_if_not_exists`. Never received by production because it was in the SQL schema at bootstrap time — EXCEPT the SQL schema did NOT define it. Most likely this enum was added to migration 0001 after production was bootstrapped, so production never got it. No current migration creates a table that uses it. The planned `project_opening_financials` table exists in the SQL schema but has no Alembic migration. Retain until the feature is implemented. |
| `opening_reference_type_enum` | **LEG** | Same situation as above. |

### 3.2 Enum values present in bootstrap but absent from production

| Enum | Missing value | Migration | Classification |
|------|--------------|-----------|----------------|
| `item_type_enum` | `TOOL` | 0053 | EXP |
| `user_role_enum` | `PROCUREMENT_LEAD` | 0054 | EXP |
| `record_status_enum` | `STAFF_APPROVED` | 0054 | EXP |

### 3.3 Enum ordinal ordering difference

`alert_type_enum` contains identical values in both databases but in different ordinal order. Values added via `ALTER TYPE ... ADD VALUE` always append to the end, so the order reflects insertion history rather than logical grouping. No application code depends on ordinal position of enum values.

**Classification: LEG** — cosmetic only; no action required.

---

## Section 4 — Index Differences

### 4.1 Indexes in bootstrap but NOT in production (from migrations 0052–0067)

All EXP unless noted.

`mr_quotes.ix_mr_quotes_purchase_order_id` (0052), `mr_quotes.ix_mr_quotes_source/.status` (0046), `stage_master.ix_stage_master_code` (**BUG** — from 0001; absent because stage_master.code column missing from production), `projects.ix_projects_company_id` (0065), workshop indexes (0058–0062), warehouse indexes (0066), `material_requests.ix_material_requests_repair_job_id` (0057), `user_project_access.uq_user_project_access` / `user_site_access.uq_user_site_access` (renamed versions from 0025), `lot_types.uq_lot_types_project_code` (0016), `lots.ix_lots_lot_type_id` (0016), `fuel_logs.ix_fuel_logs_fuel_delivery_id` (0063), `vehicle_costs.ix_vehicle_costs_repair_job_id` (0056).

### 4.2 Indexes in production but NOT in bootstrap (SQL-schema legacy)

These indexes exist from the original SQL schema bootstrap and have no equivalent migration to recreate them on a fresh install.

| Index | Table | Classification | Notes |
|-------|-------|---------------|-------|
| `stage_master_name_key` | stage_master | **LEG** | SQL schema: `UNIQUE NOT NULL` on `name`. Migration 0001 creates `stage_master` differently — no unique-name constraint, uses unique `code` instead. Production has uniqueness on name (SQL schema); bootstrap has uniqueness on code (migration 0001). Functional difference. |
| `stage_master_sequence_order_key` | stage_master | **LEG** | SQL schema: `UNIQUE NOT NULL` on `sequence_order`. Bootstrap has no equivalent. |
| `item_categories.item_categories_name_key` | item_categories | **LEG** | SQL-schema unique on category name. Missing from bootstrap. |
| `item_aliases.ix_item_aliases_item_id` | item_aliases | **LEG** | SQL-schema index. Missing from bootstrap. |
| `material_requests.*` several indexes | material_requests | **RED** | Bootstrap has fewer material_request indexes; production has more from SQL schema. Bootstrap creates them differently in 0003. |
| `uq_pss_project_site_lot_stage` | project_stage_status | **RED** | Production has a regular UNIQUE constraint. Bootstrap constraint is identical but named differently (`uq_user_project_access` vs `uq_upa_user_project`). Functionally equivalent. |
| `delivery_verifications.ix_delivery_verifications_verification_status` | delivery_verifications | **LEG** | Column named `verification_status` in production; `status` in bootstrap (or index references different column). |
| `payments.ix_payments_invoice_id` / `ix_payments_status` | payments | **LEG** | Present in production from SQL schema; not in bootstrap. Missing index is a performance risk for queries filtering payments by invoice or status. |

### 4.3 Index naming divergences (same function, different names)

| Production name | Bootstrap name | Table | Classification |
|----------------|----------------|-------|----------------|
| `uq_upa_user_project` | `uq_user_project_access` | user_project_access | **LEG** |
| `uq_usa_user_site` | `uq_user_site_access` | user_site_access | **LEG** |
| `ix_incoming_emails_message_id` | `incoming_emails_message_id_key` | incoming_emails | **LEG** |
| `ix_delivery_verifications_verification_status` | `ix_delivery_verifications_status` | delivery_verifications | **LEG** |
| Various `ix_purchase_orders_*` and `ix_po_*` | Same semantics, different names | purchase_orders | **LEG** |

---

## Section 5 — Views, Materialized Views, Triggers, Sequences

### 5.1 Materialized views

| Object | Present in production | Present in bootstrap | Notes |
|--------|----------------------|---------------------|-------|
| `stock_balances` | YES | YES | Created by migration 0025. Identical in both databases. |

### 5.2 Views, triggers, sequences

**None** in either database. No user-defined triggers or sequences exist.

---

## Section 6 — Constraints

### 6.1 Check constraints

No non-trivial check constraints (beyond NOT NULL) exist in either database.

### 6.2 Foreign key counts

Bootstrap has 268 FK relationships (from information_schema query). Production has fewer (exact count from the SQL schema bootstrap subset). All production FKs are present in bootstrap; bootstrap has additional FKs from columns added by migrations 0052–0067.

### 6.3 Unique constraint naming divergences

See §4.3 above. The functional uniqueness is identical; only constraint names differ between SQL-schema-bootstrapped production and Alembic-bootstrapped clean install.

---

## Section 7 — Critical Finding: `project_stage_statuses` Orphaned Table

The clean bootstrap contains TWO stage-status tables:

| Table | Created by | ORM mapped | Currently queried |
|-------|-----------|------------|------------------|
| `project_stage_statuses` | Migration 0001 | NO | NO |
| `project_stage_status` | SQL schema + migration 0003 | YES (`__tablename__ = "project_stage_status"`) | YES |

Migration 0001 introduced the plural name (`project_stage_statuses`) but the ORM model uses the singular name (`project_stage_status`). Migration 0003 added the singular table using `CREATE TABLE IF NOT EXISTS` to compensate. The plural table is entirely orphaned — no query, no ORM model, no FK ever references it.

**Recommendation:** Add migration 0068 to drop `project_stage_statuses` if it exists.

---

## Section 8 — Bug Summary

| ID | Table.Column | Root Cause | Impact |
|----|-------------|-----------|--------|
| B-01 | `stage_master.code` (absent in production) | SQL-schema bootstrap predates migration 0001 which adds this column NOT NULL | 38 test errors; seeding fails; stage-tracking features unusable on production until column is added and populated |
| B-02 | `payments.payment_date` nullability mismatch | Production: NULLABLE (from SQL schema); Bootstrap: NOT NULL (from migration 0001) | 11 test failures on hmh_test; inconsistent contract between environments |
| B-03 | `payments.created_by` absent in production | Migration 0001 column; SQL-schema bootstrap skipped it | ORM tries to read this column; will fail on queries that select it if production DB is used in testing |
| B-04 | `purchase_orders.vat_mode` absent in production | Migration 0039 likely applied correctly but column absent — needs investigation | VAT mode functionality broken in production environment |
| B-05 | `sites.address`, `gps_lat`, `gps_lng` absent | Migration 0001 columns; SQL-schema bootstrap skipped them | Geolocation features unavailable in production |
| B-06 | `vehicles.vin_number` absent | Migration 0045 may have failed or been skipped | VIN tracking unavailable in production |
| B-07 | `project_stage_statuses` orphaned table | Migration 0001 used wrong table name; compensated by migration 0003 without cleanup | Dead weight in schema; confusing to developers |
| B-08 | `summary_service.py` uses `Payment.amount` | Code inconsistency — uses legacy column, not `amount_paid` | Payment totals in summary view may differ from those in other views; silent data quality risk |
