# Migration Remediation Plan

**Date:** 2026-07-15  
**Scope:** All 67 Alembic migrations (0001–0067) + remediation roadmap  
**Status:** Analysis only. No migrations modified.

---

## Section 1 — Migration Health Review

### Status codes

| Code | Meaning |
|------|---------|
| ✅ Healthy | Works correctly on both fresh and contaminated DBs |
| ⚠️ Needs review | Works in practice but has a pattern that could cause problems |
| 🔧 Needs cleanup | Contains technical debt that should be addressed |
| ❌ Needs fix | Known defect; blocks reliable bootstrap or test execution |

---

### Individual migration assessments

| Rev | Name | Status | Issues |
|-----|------|--------|--------|
| 0001 | initial_schema | ❌ Needs fix | (1) Creates `project_stage_statuses` (plural) — wrong name, orphaned table; (2) Creates `stage_master` WITH `code NOT NULL`, `is_active`, `updated_at` — these are absent in production, causing B-01; (3) All `op.create_table()` calls lack `IF NOT EXISTS` — fails on any DB with pre-existing tables; (4) Creates `opening_financial_status_enum` / `opening_reference_type_enum` which production never received; (5) Creates `payments.payment_date NOT NULL` — production has it nullable (B-02); (6) Creates `payments.created_by` — absent from production (B-03); (7) Migration is 779 lines — the largest migration; monolithic design |
| 0002 | vehicle_fuel_link_soft_delete | ✅ Healthy | Adds columns with `op.add_column` + `IF NOT EXISTS` guard via inspect. Clean pattern. |
| 0003 | missing_tables_and_columns | ⚠️ Needs review | (1) Title admits it was written to fix 0001 omissions; (2) Creates `project_stage_status` (singular) via `CREATE TABLE IF NOT EXISTS` — compensating for 0001's wrong name; (3) Print statements contain `→` (U+2192) — causes `UnicodeEncodeError` on Windows without `PYTHONIOENCODING=utf-8`; (4) 570 lines — the second largest migration; (5) Uses `_create_idx` helper with IF NOT EXISTS — good pattern |
| 0004 | remaining_column_gaps | ⚠️ Needs review | Adds ORM-replacement columns (`amount_paid`, `payment_reference`, `stored_path`, etc.) without dropping their predecessors. Leaves legacy columns in place. This was intentional for backwards compatibility but creates technical debt. |
| 0005 | alert_recipient_last_inbound | ✅ Healthy | Simple `add_column` with inspect guard |
| 0006 | fix_material_request_items_notnull | ⚠️ Needs review | Correctly drops NOT NULL from legacy columns after backfill. Title reveals this is a hotfix for migration 0001's NOT NULL on columns that the ORM doesn't write. Pattern of "fix migrations for earlier fix migrations" is a smell. |
| 0007 | fix_po_items_quantity_notnull | ⚠️ Needs review | Same pattern as 0006 — fixing 0001's NOT NULL on columns the ORM doesn't write. |
| 0008 | po_email_logs_sent_to_nullable | ⚠️ Needs review | Makes `sent_to` nullable. Title implies it was NOT NULL before; this was needed to allow PO logs without a send address. |
| 0009 | attachments_file_url_payments_amount_nullable | ⚠️ Needs review | Makes `file_url` and `payments.amount` nullable after backfilling from ORM columns. Same pattern as 0006/0007. Leaves legacy `amount` column with data. |
| 0010 | fuel_logs_log_date_nullable | ✅ Healthy | Simple nullable change |
| 0011 | add_read_only_role | ✅ Healthy | Adds enum value with `IF NOT EXISTS` guard |
| 0012 | fuel_evidence_photos | ✅ Healthy | Adds columns |
| 0013 | milestone_photos | ✅ Healthy | Adds columns |
| 0014 | attachment_entity_payment_fuel | ✅ Healthy | Adds enum values |
| 0015 | stock_ledger_site_nullable | ✅ Healthy | Makes column nullable |
| 0016 | lot_types | ✅ Healthy | Creates `lot_types` table cleanly |
| 0017 | milestone_completion_fields | 🔧 Needs cleanup | Adds and drops columns on `project_stage_status` in same migration. The dropped columns (`blocked_reason`, `progress_pct`, `completed_by_name`, `completion_notes`) suggest a design change happened mid-development. Functionally correct but leaves archaeology in the migration chain. |
| 0018 | procurement_attachments | ✅ Healthy | |
| 0019 | attachment_types | ✅ Healthy | |
| 0020 | partial_payments | ✅ Healthy | Adds `payment_method`, `lot_id` to payments |
| 0021 | supplier_confirmed_status | ✅ Healthy | |
| 0022 | notification_enhancements | ✅ Healthy | |
| 0023 | payment_due_alert_type | ✅ Healthy | |
| 0024 | performance_indexes | ✅ Healthy | Batch index creation with IF NOT EXISTS guards. Good pattern. |
| 0025 | data_consistency_constraints | ✅ Healthy | Adds `stock_balances` materialized view and unique constraints. Uses IF NOT EXISTS. |
| 0026 | milestone_planned_date | ✅ Healthy | |
| 0027 | attachment_enhancements | ✅ Healthy | |
| 0028 | gmail_ocr_alert_types | ✅ Healthy | |
| 0029 | document_extraction_review_status | ✅ Healthy | |
| 0030 | vehicle_detail_fields | ✅ Healthy | Adds vehicle enums and columns cleanly |
| 0031 | stock_ledger_nullable_project | ✅ Healthy | |
| 0032 | notification_queue_is_test | ✅ Healthy | |
| 0033 | user_pin_hash_and_site_manager_view | ✅ Healthy | |
| 0034 | notification_status_delivered_read | ✅ Healthy | |
| 0035 | mr_nullable_project_site | ✅ Healthy | |
| 0036 | supplier_vat_fields | ✅ Healthy | |
| 0037 | supplier_doc_types | ✅ Healthy | |
| 0038 | quotation_table | ✅ Healthy | |
| 0039 | po_quotation_invoice_vat | ⚠️ Needs review | Adds `purchase_orders.vat_mode`. This column is absent from production despite 0039 theoretically running. May have failed silently or may indicate a gap in production's migration application. Needs verification. |
| 0040 | procurement_reconciliation | ✅ Healthy | |
| 0041 | procurement_analytics_indexes | ✅ Healthy | |
| 0042 | ai_extraction_json | ✅ Healthy | |
| 0043 | subcontractor_work_done | ✅ Healthy | |
| 0044 | municipality_invoice | ✅ Healthy | |
| 0045 | vehicle_vin | ⚠️ Needs review | Adds `vin_number`. Column absent from production despite 0045 theoretically running (production is at 0051). Needs investigation — may indicate a gap in when this migration was written vs when it was applied to production. |
| 0046 | mr_quote_pipeline_fields | ✅ Healthy | |
| 0047 | issuing_company | ✅ Healthy | |
| 0048 | supplier_account_code | ✅ Healthy | |
| 0049 | delivery_driver_name | ✅ Healthy | |
| 0050 | delivery_destination_pickup | ✅ Healthy | |
| 0051 | mr_item_preferred_supplier | ✅ Healthy | Last migration applied to production |
| 0052 | mr_quote_po_link | ✅ Healthy | |
| 0053 | tool_item_type | ✅ Healthy | |
| 0054 | mr_four_way_approval | ❌ Needs fix | `op.create_table("mr_approvals")` lacks `IF NOT EXISTS`. Root cause of the original test-contamination failure on `hmh_system`. On a clean DB this works; on a contaminated DB it fails with `DuplicateTable`. Resolution: add migration 0068 as a no-op safety check, OR wrap the create with an inspect guard. Do NOT edit migration 0054 — it may already have run on some environments. |
| 0055 | mr_quote_votes | ✅ Healthy | |
| 0056 | repair_jobs | ✅ Healthy | |
| 0057 | vehicle_site_features | ✅ Healthy | |
| 0058 | workshop | ✅ Healthy | Large migration (workshop module) but uses safe DDL patterns |
| 0059 | workshop_mr_approvals | ✅ Healthy | |
| 0060 | workshop_mr_email_logs | ✅ Healthy | |
| 0061 | workshop_quotes | ✅ Healthy | |
| 0062 | workshop_phase_d | ✅ Healthy | |
| 0063 | fuel_per_hour | ✅ Healthy | |
| 0064 | mr_extra_reason | ✅ Healthy | |
| 0065 | companies | ✅ Healthy | |
| 0066 | warehouse_transfer_requests | ✅ Healthy | |
| 0067 | supplier_payment_due_days | ✅ Healthy | |

### Summary

| Status | Count | Percentage |
|--------|-------|-----------|
| ✅ Healthy | 51 | 76% |
| ⚠️ Needs review | 10 | 15% |
| 🔧 Needs cleanup | 1 | 1% |
| ❌ Needs fix | 2 | 3% |

The migration chain is **76% healthy**. The two critical defects (0001 and 0054) are concentrated at the beginning and middle of the chain. The rest of the chain (0010–0051 and 0055–0067) is solid.

---

## Section 2 — Migration Patterns Analysis

### Pattern 1: "Fix" migrations for earlier fix migrations (0006, 0007, 0009)

Migration 0001 created tables with NOT NULL columns that the ORM never wrote. This generated a cascade of "fix" migrations (0006, 0007, 0009) that drop those NOT NULL constraints after backfilling from ORM-mapped replacement columns. This is technically correct but means the clean bootstrap has legacy columns with nullable constraints that serve no purpose.

**Resolution:** Legacy column cleanup in §3 roadmap.

### Pattern 2: Conditional DDL via `inspect()` (good pattern)

Migrations 0002, 0005, 0006, 0007, 0008, 0009, 0024 and many others use `sa.inspect(bind)` to check column/table existence before adding. This is the correct pattern for idempotent migrations and should be the standard for all new migrations.

### Pattern 3: Windows Unicode issue (migration 0003)

Print statements using `→` (U+2192) fail on Windows with the default `cp1252` encoding. **Workaround:** Set `PYTHONIOENCODING=utf-8` before running alembic. **Fix:** Replace `→` with `->`in migration 0003 print statements (cosmetic change to migration, not a schema change).

### Pattern 4: `op.create_table()` without IF NOT EXISTS (migrations 0001, 0054)

This is the root cause of all contamination failures. The standard Alembic `op.create_table()` raises `DuplicateTable` if the table exists. Every new migration that creates a table should use the inspect-guard pattern:

```python
def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("my_new_table"):
        op.create_table("my_new_table", ...)
```

This pattern must be adopted as the project standard going forward.

### Pattern 5: Large monolithic migrations (0001, 0003)

Migrations 0001 (779 lines) and 0003 (570+ lines) create the entire initial schema in a single migration. While these work correctly on a clean database, they are difficult to review, debug, and maintain. Future large features (like the workshop module in 0058) correctly use a single focused migration per feature rather than one giant file.

### Pattern 6: Alembic single-transaction wrapper (`env.py`)

`alembic/env.py` wraps ALL pending migrations in a single `context.begin_transaction()`. This means:
- If any migration fails, ALL pending DDL rolls back.
- This protects against partial schema upgrades.
- **Trade-off:** A failure in migration 0054 also rolls back migrations 0052 and 0053.

This is the correct behaviour for DDL safety. It was the correct design choice; it only became a problem because `create_all()` contaminated the database before migrations ran.

---

## Section 3 — Prioritised Remediation Roadmap

### Priority 1 — Blocking development now

These issues prevent tests from passing or features from working correctly. Must be resolved before AI Emails module development.

| ID | Issue | Action | Risk | Effort |
|----|-------|--------|------|--------|
| R-01 | 38 test errors: `seed_default_stages()` does not set `stage_master.code` | Add `code=` to each stage in `seed_default_stages()` and `make_stage()` test helper | Very low — test code only | 1 hour |
| R-02 | 11 test failures: payment test helpers do not set `payment_date` | Add `payment_date=date.today()` to payment test helpers | Very low — test code only | 30 minutes |
| R-03 | 5 test failures: `TestQuoteApprove` tests use OFFICE_USER but route requires PROCUREMENT_LEAD | Update affected tests to use PROCUREMENT_LEAD role | Very low — test code only | 1 hour |
| R-04 | `summary_service.py:66` uses `Payment.amount` instead of `Payment.amount_paid` | Change to `Payment.amount_paid` | Very low — no DB change | 15 minutes |

**Dependencies:** None. These can all be done independently.  
**Combined effort:** ~3 hours.  
**Expected result after R-01–R-04:** Test suite reaches 835/835 (or close to it, pending investigation of the remaining 18 failures).

---

### Priority 2 — Technical debt before production deployment

These should be resolved before any real data is written to the production database.

| ID | Issue | Action | Risk | Effort | Dependencies |
|----|-------|--------|------|--------|-------------|
| R-05 | `project_stage_statuses` orphaned table in clean bootstrap | Add migration 0068: `DROP TABLE IF EXISTS project_stage_statuses` | Low — table is empty and unmapped | 30 minutes | None |
| R-06 | Migration 0001 creates `project_stage_statuses` (wrong name) | Add comment to migration 0001 documenting the naming error; do NOT edit the migration itself | Very low — documentation only | 15 minutes | None |
| R-07 | `stage_master.code` absent from production | Design a migration that adds `code` column, populates it for all 15 existing rows, then enforces NOT NULL. This must be a new migration (0069+), not modification of 0001. | Medium — requires populating existing rows | 2 hours | R-05, database rebuild decision |
| R-08 | `payments.payment_date` nullability mismatch | Add migration that runs `ALTER TABLE payments ALTER COLUMN payment_date SET NOT NULL` with a pre-check that no existing rows have NULL `payment_date` | Low — data check first | 1 hour | None |
| R-09 | Migration 0054 `mr_approvals` without IF NOT EXISTS | Add migration 0068 or 0069 that is a no-op if `mr_approvals` exists (already created by 0054 on clean DBs) | Very low — no-op on all current DBs | 30 minutes | None |
| R-10 | Migration 0003 Unicode print statements | Change `→` to `->` in print statements | Very low | 15 minutes | None |

---

### Priority 3 — Cleanup work (schedule for next maintenance window)

| ID | Issue | Action | Risk | Effort | Can be done independently |
|----|-------|--------|------|--------|--------------------------|
| R-11 | Backfill `material_request_items.approved_quantity ← quantity_approved` for old rows | Data audit + backfill migration | Low | 1 hour | Yes |
| R-12 | Retire `hmh_v1_schema.sql` as bootstrap source | Move to `docs/database/ARCHIVED_v1_schema.sql`; add warning header | Very low | 15 minutes | Yes |
| R-13 | Regenerate schema snapshot from current head | `pg_dump --schema-only` of bootstrap DB → `docs/database/schema_snapshot_0067.sql` | None | 15 minutes | Yes |
| R-14 | Add inspect-guard standard to `CLAUDE.md` project modules | Document the `has_table()` check pattern as required for new migrations | None | 30 minutes | Yes |
| R-15 | Verify `purchase_orders.vat_mode` and `vehicles.vin_number` absence from production | Query production DB for these columns; if absent, determine if migration was applied | Low | 30 minutes | Yes |

---

### Priority 4 — Future improvements

| ID | Issue | Action | Risk | Effort | Prerequisite |
|----|-------|--------|------|--------|-------------|
| R-16 | Drop `material_request_items.request_id` | Migration: `DROP COLUMN IF EXISTS request_id` | Low | 30 minutes | Production rebuilt from Alembic |
| R-17 | Drop `material_request_items.quantity_requested` (DB column only; keep AliasChoices) | Migration: `DROP COLUMN IF EXISTS quantity_requested` | Low–Medium | 30 minutes | Verify no external clients use the old key |
| R-18 | Drop `material_request_items.quantity_approved` | Backfill migration first (R-11), then `DROP COLUMN IF EXISTS quantity_approved` | Medium | 1 hour | R-11 completed |
| R-19 | Drop `payments.reference` | Data audit + `DROP COLUMN IF EXISTS reference` | Low | 30 minutes | Production rebuilt from Alembic |
| R-20 | Drop `payments.amount` and remove double-write | Data consistency check + ORM change + migration | Medium | 2 hours | R-04 done; data equality verified |
| R-21 | Remove `payments.created_by` from production gap | Already in bootstrap; production will get it on upgrade | None | 0 | R-07 (production upgrade) |
| R-22 | Implement `project_opening_financials` table migration or drop orphaned enums | Business decision: is the feature wanted? If not, `DROP TYPE IF EXISTS opening_financial_status_enum` | Low | 1 hour | Business decision |
| R-23 | CI/CD pipeline: automate schema snapshot generation | Add step to CI: bootstrap → pg_dump → commit snapshot | Low | 2 hours | Option B adopted as strategy |
| R-24 | Add migration timing/profiling | Log migration execution time per revision | None | 1 hour | None |

---

## Section 4 — New Migration Standards

All future migrations (0068+) must follow these standards:

### Required patterns

```python
def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Table creation — always guard
    if not insp.has_table("new_table"):
        op.create_table("new_table", ...)

    # 2. Column addition — always guard
    cols = {c["name"] for c in insp.get_columns("existing_table")}
    if "new_column" not in cols:
        op.add_column("existing_table", sa.Column("new_column", ...))

    # 3. Enum value addition — always guard
    op.execute(sa.text("""
        DO $$ BEGIN
            ALTER TYPE my_enum ADD VALUE IF NOT EXISTS 'NEW_VALUE';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # 4. Index creation — always use IF NOT EXISTS
    op.execute("CREATE INDEX IF NOT EXISTS ix_name ON table(col)")

    # 5. Print statements — ASCII only (no Unicode arrows or special chars)
    print("[NNNN] Migration description.", flush=True)
```

### Required downgrade()

Every migration must have a complete `downgrade()`. Empty or pass-only downgrades are not acceptable for new migrations.

### Windows compatibility

All print statements must use ASCII characters only. Do not use `→`, `←`, `✓`, `×`, or any non-ASCII character.

---

## Section 5 — Phase 1 Development Clearance

Before the AI Emails module implementation may begin, the following must be resolved:

| Check | Required by | Status |
|-------|-------------|--------|
| R-01: seed_default_stages fixed | Test suite | ⏳ Pending |
| R-02: payment test helpers fixed | Test suite | ⏳ Pending |
| R-03: TestQuoteApprove role fixed | Test suite | ⏳ Pending |
| R-04: summary_service.py amount fix | Code quality | ⏳ Pending |
| Test suite passes at 835/835 (or documented residual) | Development confidence | ⏳ Pending |

Items R-05 through R-24 are **not blocking** AI Emails development — they are background tasks that can proceed in parallel.
