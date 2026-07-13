# DECISIONS — architecture choices and lessons
<!-- One dated line per non-obvious choice. Use Lesson entries for repeated-mistake patterns. -->

## Architecture decisions

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

---

## Lessons (repeated-mistake register)

_No repeated mistakes have been logged yet. When the same class of error occurs twice, add a Lesson entry here._
