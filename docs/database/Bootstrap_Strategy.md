# Bootstrap Strategy

**Date:** 2026-07-15  
**Scope:** Long-term database bootstrap strategy for HMH System  
**Status:** Recommendation document only. No changes implemented.

---

## Section 1 — SQL Snapshot Audit (`hmh_v1_schema.sql`)

### 1.1 When was it last accurate?

`hmh_v1_schema.sql` was accurate at the time the original production database was created — before Alembic was introduced to the project. Based on schema analysis:

- The file defines `stage_master` without `code`, `is_active`, or `updated_at` — matching the original hand-crafted schema, not migration 0001.
- The file defines `project_stage_status` (singular), not `project_stage_statuses` (plural which migration 0001 creates).
- The file defines `payments.payment_date` as NULLABLE, matching pre-Alembic production state.
- The file defines `opening_financial_status_enum` and `opening_reference_type_enum` which production never received.
- The file does NOT define `vat_mode_enum`, though production has it (the original SQL file likely had it and it was later removed from the file as migrations took over).

The file has been modified after the database was bootstrapped — some types were added that production never received, and some were removed that production has. It has been inconsistently maintained.

**Best estimate of last accuracy:** Sometime between the project start and migration 0003, the file represented the live schema. After that point, it began diverging.

### 1.2 Which migration revision does it most closely represent?

The SQL schema is closest to the state between migrations 0003 and 0004 — after the initial tables and "missing tables" fixes were in place, but before the addition of ORM-replacement columns. However, it diverges from that state in key ways (missing `vat_mode_enum`, different `stage_master` definition). It does not accurately represent any single migration revision.

**Verdict: `hmh_v1_schema.sql` does not correspond to any specific Alembic revision.**

### 1.3 Can it be used for bootstrap today?

No. Every attempted bootstrap path using the SQL file has failed:

| Attempt | Failure point | Root cause |
|---------|--------------|-----------|
| Load SQL → stamp 0051 → upgrade head | `mr_quotes` column missing | Stamp skips migrations that add columns; subsequent migration expects column from earlier migration |
| Load SQL → stamp 0001 → upgrade head | `vat_mode_enum` does not exist | File missing the enum; migration 0003 uses it with `create_type=False` |
| Load SQL → upgrade head (no stamp) | `DuplicateTable` on first `op.create_table()` | Migration 0001 uses `op.create_table()` without `IF NOT EXISTS` |

### 1.4 Should it continue to exist?

Not as a bootstrap source. It should be retained **only as a historical reference** and clearly marked as such. Developers must be warned not to use it for any environment setup.

### 1.5 Should it be regenerated?

Yes — but as a **documentation artifact**, not as a bootstrap tool. A regenerated snapshot (produced by `pg_dump --schema-only` from the clean bootstrap at head) would serve as a readable reference for developers who want to understand the full schema without reading 67 migration files. This snapshot should be regenerated whenever the migration head advances.

### 1.6 How should it be maintained going forward?

If retained as a reference artifact:
1. Store it in `docs/database/` (not at the project root).
2. Add a header comment: "SCHEMA REFERENCE ONLY — Do not use for bootstrap. Generated from clean Alembic head on [date]."
3. Automate regeneration as part of the CI pipeline: `pg_dump --schema-only $TEST_DATABASE_URL > docs/database/schema_snapshot.sql`
4. Never commit a manually edited version — only pg_dump output is authoritative.

---

## Section 2 — Three Bootstrap Strategy Options

### Option A — Continue using SQL snapshot

**Description:** Maintain `hmh_v1_schema.sql` as the bootstrap source. Load it, stamp a specific revision, and run remaining migrations.

#### Pros
- Familiar to anyone who set up the current production database
- Fast to load (single SQL file vs 67 migration steps)
- Human-readable snapshot of the schema at a known state

#### Cons
- Currently broken — fails at every stamp point tested
- The file and production database have diverged from each other
- Requires manual maintenance to keep in sync with migrations
- Any `op.create_table()` call without `IF NOT EXISTS` in migrations will fail
- Developers must know which revision to stamp — this is not documented
- New columns added by "fix" migrations (0006, 0007, 0008, 0009) that the file doesn't include will cause failures
- Zero CI/CD suitability in current state
- Disaster recovery: fails

#### Maintenance effort
- High: every new migration must be reflected in the SQL file
- Any schema drift goes undetected until someone tries to bootstrap

#### Reliability
- Very low: proven broken in Gate B testing across all three stamp strategies

#### CI/CD suitability
- Not suitable. Cannot be reliably automated.

#### Disaster recovery suitability
- Not suitable. In a disaster scenario, restoring from this file would leave the DB in an unpredictable state relative to the migration history.

---

### Option B — Bootstrap entirely from Alembic migrations (recommended)

**Description:** Always start from an empty PostgreSQL database and run `alembic upgrade head`. The clean `hmh_bootstrap_check` database was created this way.

#### Pros
- Proven to work (demonstrated in Gate B)
- Single source of truth: the migration chain is the schema definition
- Fully automated — no manual intervention required
- CI/CD native: every test run, PR, and deployment can bootstrap from scratch
- Disaster recovery: predictable and reproducible
- New developers follow one command: `alembic upgrade head`
- No file maintenance burden beyond writing the migration itself

#### Cons
- Requires fixing migration 0001 (orphaned table, wrong `stage_master.code` NOT NULL for existing seed data)
- Requires fixing migration 0054 (missing `IF NOT EXISTS` on `mr_approvals`)
- Windows requires `PYTHONIOENCODING=utf-8` (migration 0003 Unicode issue)
- 67 migrations take time (~90–120 seconds on a local machine) — acceptable for dev, may need optimisation for CI
- Some SQL-schema-only indexes (e.g., `stage_master_name_key`) are not recreated — production has more indexes than a fresh bootstrap

#### Maintenance effort
- Low: each feature requires one migration file. No additional maintenance.

#### Developer experience
- Excellent once the broken migrations are fixed. Single command, deterministic result.

#### Reliability
- High (proven on empty database)

#### CI/CD suitability
- Excellent. The test suite already uses `hmh_test`, which was bootstrapped this way.

#### Disaster recovery suitability
- Excellent. Any developer can recreate the full schema from git history.

---

### Option C — Generate a fresh SQL snapshot automatically from migration head

**Description:** Use Option B as the authoritative bootstrap, but additionally generate a SQL snapshot automatically (via `pg_dump --schema-only`) after every successful `alembic upgrade head`. Store this snapshot in the repository as a reference artifact.

#### Pros
- Combines the reproducibility of Option B with the readability of a SQL snapshot
- Human-readable schema reference without needing to read 67 files
- Can be used by DBAs for review without running Python
- Enables schema diffing between releases (diff two snapshots)
- Can serve as the source for a `CREATE DATABASE IF NOT EXISTS` fast path (restore + upgrade from snapshot to head, rather than from scratch)

#### Cons
- Requires pipeline automation to keep the snapshot current
- If the snapshot is not updated, it misleads developers (same problem as Option A)
- Snapshot is large and binary-compatible only with the PostgreSQL version used to generate it
- Does not solve the problem for developers without the pipeline

#### Maintenance effort
- Medium: requires a CI step; failure to update means snapshot drift

#### Reliability
- High as a reference. Cannot be used as a primary bootstrap source (same failure modes as Option A if used that way).

#### CI/CD suitability
- Good for documentation; not suitable as the bootstrap mechanism itself.

---

## Section 3 — Single Source of Truth Recommendation

### Recommendation: Option B — Alembic is the single source of truth

Alembic migrations are already the de facto schema authority. Every structural change since the project started has been expressed as a migration. The clean bootstrap on `hmh_bootstrap_check` proves the migration chain produces a correct, reproducible schema.

The SQL snapshot file should be **retired as a bootstrap tool** and optionally regenerated as a documentation artifact (Option C) once the migration chain is clean.

### If Alembic becomes the formal single source of truth:

#### How SQL snapshots should be generated
```bash
# After every migration head advance:
PYTHONIOENCODING=utf-8 DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_verify \
    python -m alembic upgrade head
pg_dump --schema-only --no-owner --no-acl \
    postgresql://hmh:hmhdev@localhost:55432/hmh_verify \
    > docs/database/schema_snapshot_$(python -m alembic current 2>/dev/null | head -1).sql
docker exec hmh-postgres psql -U hmh -c "DROP DATABASE hmh_verify;"
```
This snapshot is committed alongside the migration that generated it.

#### How production stays synchronised
```bash
# On each deployment:
PYTHONIOENCODING=utf-8 DATABASE_URL=$PRODUCTION_DATABASE_URL python -m alembic upgrade head
```
Alembic is idempotent — if already at head, nothing runs.

#### Release workflow
1. Developer writes feature → creates migration via `alembic revision`
2. Migration passes local testing on `hmh_test` (from clean bootstrap)
3. PR merged → CI runs `alembic upgrade head` on a fresh database, runs full test suite
4. Deploy → CI/CD runs `alembic upgrade head` on production database

#### Developer onboarding workflow
```bash
# New developer setup:
git clone <repo>
cd hmh-backend
pip install -r requirements.txt
# Create database
docker exec hmh-postgres psql -U hmh -c "CREATE DATABASE hmh_local;"
# Bootstrap (Windows):
PYTHONIOENCODING=utf-8 DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_local \
    python -m alembic upgrade head
# Start server
DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_local uvicorn app.main:app --reload
```

One command. No SQL files. No stamp decisions. No manual choices.

---

## Section 4 — Production Migration Path

The current production database (`hmh_system`) is at `alembic_version = 0051` with a hybrid schema (SQL-schema base + migrations 0004–0051 applied). Two paths exist:

### Path 1 — Rebuild (preferred, requires explicit approval)

```bash
docker compose down -v                    # destroy current volume
docker compose up -d                      # fresh PostgreSQL
PYTHONIOENCODING=utf-8 python -m alembic upgrade head  # from hmh-backend
```

**Advantages:** Clean, reproducible, no drift, no legacy columns  
**Risk:** All production data lost. Only acceptable if:
- The database contains no live customer data, OR
- A verified backup exists and has been tested for restore

**Current status:** Requires explicit user approval. 15 seed rows exist in `stage_master`. No business data confirmed.

### Path 2 — In-place upgrade (safe for data, results in hybrid schema)

```bash
PYTHONIOENCODING=utf-8 DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_system \
    python -m alembic upgrade head
```

**Advantages:** Preserves data, no downtime  
**Risk:**
- `stage_master.code` column will be added by migration — but existing 15 rows have no `code` value and the column is NOT NULL. **This will fail** unless migration 0001's `CREATE TABLE stage_master` logic is not re-applied (it isn't, since production is stamped past 0001).
- Columns added by intermediate migrations (e.g., `stage_master.code`) are expected by the ORM but have no values in existing rows. A separate data-population step is needed.
- `mr_approvals` table will be created by migration 0054 without conflict (the contamination was from `create_all()`, not migration 0054 itself — hmh_system is at 0051 now, so 0054 will run cleanly).

**Verdict:** Path 2 is viable but requires a supplementary migration to populate `stage_master.code` for existing rows before the NOT NULL constraint is enforced.
