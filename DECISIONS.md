# DECISIONS — architecture choices and lessons
<!-- One dated line per non-obvious choice. Use Lesson entries for repeated-mistake patterns. -->

## Architecture decisions

**2026-08-03 — A second private Supabase bucket for evidence, not a flipped shared bucket.**
Fuel evidence and generic `/attachments/upload` records now go to a new private bucket (`SUPABASE_PRIVATE_BUCKET`) instead of making the existing `hmh-uploads` bucket private. Five other call sites (delivery notes/signatures, stock usage evidence, stage milestone photos, generated MR/PO PDFs) still write directly into the shared `attachments` table using the old public bucket and would have broken if it were flipped private. `stored_path` for a private upload is an internal `supabase://<key>` reference, never a fetchable URL; access is exclusively through `GET /attachments/{id}/download`, which redirects to a fresh signed URL. Outside development/test, `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are required at startup for this reason — see `KNOWN_BUGS.md`.

**2026-08-02 — Fuel feasibility is profile-driven, explainable and advisory by default.**
The ledger estimates remaining fuel from the prior issue and distance/hours/elapsed time. A profile may require a manager override, but warnings never make fraud/theft assertions. Vehicle identity remains in `vehicles`; named non-vehicle assets use a small project-scoped consumption profile.

**2026-08-02 — Notification read state is independent of workflow acknowledgement.**
Opening a notification sets `read_at` only. Canonical server action URLs are resolved from the referenced entity after target-user/role/project authorization, preventing Fuel alerts from being misrouted by a shared alert type.

**2026-08-02 — Fuel email delivery is durable and cannot own the business transaction.**
Recipient attempts are committed to `fuel_email_logs`, then delivered best-effort with bounded retry. A provider/configuration failure records `FAILED` and does not roll back submission, approval, rejection, ordering or delivery.

**2026-04 — Python/FastAPI chosen over Node/Express.**
Prior Node+TS backend exists in `hmh-backend-archive-node/` (archived). Python was chosen for SQLAlchemy 2.0 ORM ergonomics, Alembic migration tooling, and the Anthropic + Google Vision Python SDKs being first-class. Node backend is archived for reference only — never merge it back.

**2026-04 — Canonical schema lives in `hmh-docs/hmh_v1_schema.sql`; Alembic only for incremental changes.**
PostgreSQL-native types (enum types, `GENERATED ALWAYS AS STORED`, `UNIQUE NULLS NOT DISTINCT`) cannot be safely round-tripped by Alembic autogenerate. Initial schema is applied via `psql < hmh_v1_schema.sql`; Alembic handles all subsequent incremental migrations. Never apply Alembic autogenerate to a live database without review.

**2026-04 — `ApiSuccess[T]` wrapper on all API responses.**
All endpoints return `{"success": true, "data": ..., "message": ...}` via `app/schemas/common.py:ApiSuccess`. This provides a stable envelope for frontend error handling and pagination. Never return naked JSON from a route handler.

**2026-04 — JWT roles embedded in token payload; no per-request DB role lookup.**
`UserRole` is written into the JWT at login time. Role guards (`OWNER_ONLY`, `OFFICE_AND_ABOVE`, etc.) validate `payload["role"]` without a DB call. Trade-off: role changes don't take effect until the user re-logs in. Accepted for an internal B2B tool.

**2026-04 — `StockLedger` is append-only; no balance mutation.**
Stock movements write paired `TRANSFER_OUT`/`TRANSFER_IN` rows with a shared `reference_id`. `stock_balances` is a materialized view. This prevents accidental balance drift and makes audit trivial. Never write a service that mutates a stock balance directly.

**2026-05 — No Redis; asyncio event + DB `SKIP LOCKED` for notification queue drain.**
The notification queue is drained by an in-process asyncio task (`_queue_drain_loop` in main.py) and backed by a Render cron job. PostgreSQL `SKIP LOCKED` prevents duplicate sends if both run concurrently. Rejected: Redis/Celery — operational cost without benefit for a single-server deployment.

**2026-05 — Auto-apply Alembic migrations on startup.**
`run_db_migrations()` in `main.py` runs `alembic upgrade head` at every startup. This ensures Render deploys are zero-touch. Downside: a bad migration will block startup. Mitigation: Render rollback restores the prior deploy + DB backup for data recovery.

**2026-06 — `native_enum=False` for all new Python-only enums.**
`WarehouseTransferStatus` (and similar local enums) use `native_enum=False` so SQLAlchemy stores as VARCHAR. This avoids creating new PostgreSQL enum types that require `CREATE TYPE` in migrations and cannot be easily altered. Existing PostgreSQL enums (from `hmh_v1_schema.sql`) are kept as-is.

**2026-06 — `check_project_access()` applied at resource fetch, not at router level.**
Project isolation for site-level roles is enforced after fetching the resource (e.g., after loading a PO, check `po.project_id`). This allows flexible routing while ensuring no resource belonging to an unauthorised project is returned. Must be called in every route that touches project-scoped data.

**2026-07-10 — Two companies hardcoded in frontend dropdown, not DB-configurable.**
"HMH Group" and "Minerat Construction & Civils" are fixed options in the project create/edit forms. A `companies` table and `CompaniesPage` exist for company management but the project form uses a simpler select. Rationale: only two trading entities; DB-configurable dropdown adds complexity with no current benefit.

**2026-07-11 — Warehouse transfer auto-executes on third vote; no separate APPROVED state.**
When a transfer accumulates 3 votes it immediately writes ledger rows and marks itself EXECUTED. Rejected: a separate APPROVED state requiring manual execution — adds a step with no benefit since office approval IS the trigger. Stock quantity re-checked at execution time to prevent race conditions between request and vote.

**2026-07-08 — Workshop MR reuses the same 3-person approval pattern as regular MR.**
Workshop repair requests go through a vote-gated approval (3 OFFICE_AND_ABOVE votes or OWNER override) matching the existing `STAFF_VOTES_REQUIRED` / `TRANSFER_VOTES_REQUIRED` pattern. Consistency: code reviewers and ops can reason about all approval flows the same way.

**2026-07-19 — No pricing fields on ProgressClaimLine; pricing is a downstream step.**
`rate`, `unit_price`, `claim_amount` are deliberately absent from `progress_claim_lines`. A municipality progress claim shows what work was done; a subsequent municipality invoice (separate model) adds rates and calculates amounts. Rationale: prevents premature pricing by site staff; maintains clean separation between evidence of completion and financial valuation. Never add monetary fields to `ProgressClaimLine` without explicit business sign-off.

**2026-07-19 — Progress propagation chain is one-directional and never decreases.**
`progress_propagation_service` updates WeeklyPlanItem → ProgrammeActivity → StageStatus → Lot → Project. Progress values are only written if the new value exceeds the current value. Rationale: progress reporting should only move forward; a lower reported value is a data-entry error, not a genuine regression. Admin override required for actual rollback.

**2026-07-19 — Claim line uniqueness enforced via DB constraint, not application logic.**
`UniqueConstraint("claim_id", "lot_id", "stage_status_id", "source_type")` on `progress_claim_lines` prevents double-counting at the DB level. Application `_exists()` check is a performance optimisation only.

**2026-08-02 — Fuel Management is structurally separate from BOQ and uses a derived ledger balance.**
Fuel tables have no BOQ dependency. Opening stock, verified deliveries, non-reversed issues and authorised adjustments derive the balance. Completed movements are immutable; corrections are explicit reversals/adjustments. This prevents fuel from changing BOQ quantities or hiding losses through edits.

**2026-08-02 — PWA navigation is network-first; private API responses are never cached.**
Only the public app shell, offline document, icons and hashed frontend assets are cached. API, auth, cross-origin and non-GET requests bypass the worker. New workers wait for user acceptance before activation, avoiding mid-session asset mismatches.

**2026-08-02 — Keep `/site-login` as a supported site workflow, with `/login` as universal entry.**
The site route is not removed because it contains phone/PIN access and may be bookmarked. Both routes use the same verified AuthContext and safe return-destination rules; role checks prevent cross-portal navigation.

---

## Lessons (repeated-mistake register)

**Lesson 2026-07-19 — ORM model must declare all NOT NULL columns with no server default.**
`StageMaster` in `app/models/stage.py` was missing `code`, `is_active`, and `updated_at` columns that exist in the DB. The test suite hit `NotNullViolation` errors when inserting. Going forward: before writing tests that create model instances, verify the model matches the live migration SQL with `\d <table>` or inspect the migration that created the table. If a column has a server default in SQL (`server_default=func.now()`), add that to the ORM mapped column too so the model can be used without explicitly supplying the value.
