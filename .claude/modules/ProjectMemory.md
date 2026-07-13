# Project Memory — HMH Construction OS

Live state facts that are not derivable from code alone.

## Stack (verified 2026-07-12)

| Component | Version |
|---|---|
| Python | 3.11.9 (not 3.12 — README is stale) |
| FastAPI | 0.115.6 |
| Alembic | 1.14.0, head = migration **0067** |
| PostgreSQL | 15 (Docker local port 55432) |
| React | 18.3.1 |
| TypeScript | 5.8.3 |
| Vite | 5.4.19 |

## Approved business rules (2026-07-12)

These rules are authoritative for all Phase 1 work. Do not implement anything that contradicts them.

### Material quantities
- `TRANSFER_IN` to a lot = material **issued** to the lot (assigned, reserved).
- `USAGE` = material **physically consumed** on the lot.
- Issued ≠ used. BOQ consumption tracking must count **USAGE only**.
- Lot remaining stock = issued − used (TRANSFER_IN − USAGE in ledger for that lot+item).
- `allocation_service.get_lot_allocation()` must NOT count TRANSFER_IN as consumption.

### WorkDone and milestones
- WorkDone approval or payment must **never** set milestone to COMPLETED or CERTIFIED.
- WorkDone approval linked to a milestone may set milestone to AWAITING_INSPECTION only.
- Only an authorised verification action (OFFICE_AND_ABOVE, cannot be the submitter) may set COMPLETED or CERTIFIED.

### Budget
- Active BOQ version (`BOQHeader.is_active_version = True`) is the construction budget.
- `project.budget` is a separately-labelled management budget.
- Never combine or substitute the two. Both must appear with distinct labels in cost summary.

### Cost categories (eight, all separate)
| Category | Source |
|---|---|
| materials/procurement | Payment where payment_type != LABOUR |
| subcontractor labour | SubcontractorWorkDone PAID amounts (table: `subcontractor_work_done`, not `work_done`) |
| direct labour | JobCard amounts (OWNER_APPROVED, PAYMENT_APPROVED, PAID) |
| plant/vehicles | VehicleCost.amount where project_id set |
| fuel | FuelLog.total_cost |
| workshop | WorkshopInvoice (total_amount) — joined via: WorkshopInvoice.workshop_mr_id → WorkshopMR.vehicle_id → Vehicle.assigned_project_id |
| municipality | MunicipalityInvoice.**total_due** (not `.amount`) |
| general expenses | No `Expense` model exists — deferred until a model is defined |

A Payment with `payment_type=LABOUR` must **never** appear in `procurement_spend`.
Workshop cost must only be included if `Vehicle.assigned_project_id` is reliably set — no guessing.

## Test database isolation (required)

- `TEST_DATABASE_URL` must be set explicitly to a separate `hmh_test` database before running pytest.
- Tests must **never** fall back to `DATABASE_URL` (the main local Docker DB). The conftest.py must enforce this.
- Reason: `Base.metadata.create_all()` in the test session creates tables from ORM models, which pre-empts Alembic migrations on the main DB and causes migration conflicts.

## Schema facts (verified 2026-07-13)

- `company_id` is an optional FK column on the `projects` table only (added by migration 0065). It is NOT a universal tenant key across all tables.
- The project-isolation mechanism is `project_id`, not `company_id`.
- `alembic_version` on the local Docker DB is currently `0051` (last clean state). The DB is in a hybrid state due to prior `create_all` runs during test sessions.
- `alembic upgrade head` on the current Docker DB will fail without first clearing conflicting tables. Gate B (approved with conditions) handles this.

## Known integration gaps (as of 2026-07-12)

| Gap | P-level | Status |
|---|---|---|
| cost_summary BOQ budget counts ALL versions, not just active | P0 | Open — approved for Phase 1 |
| Stage service never writes AuditEvent — activity feed empty | P0 | Open — approved for Phase 1 |
| Workshop financial pipeline isolated from cost summary | P0 | Open — approved for Phase 1 |
| Expenses and MunicipalityInvoice excluded from cost summary | P1 | Open — approved for Phase 1 |
| WorkDone payments appear in procurement_spend (wrong category) | P1 | Open — approved for Phase 1 |
| WorkDone paid only sets milestone IN_PROGRESS (never COMPLETED) | P1 | Open — approved for Phase 1 (rule above governs) |
| material issued (TRANSFER_IN) and used (USAGE) both decrement allocation | P1 | Open — approved for Phase 1 |

## Test coverage gaps

- `tests/test_warehouse_transfer_flow.py` — does not exist. Transfers are untested.
- `tests/test_payment_due_scan.py` — does not exist.

## Environments

| | URL | DB | Notes |
|---|---|---|---|
| Local dev | localhost:8000 / :5173 | Docker port 55432 | Use for all testing |
| Production | (see Render) | External PostgreSQL | **No production changes without explicit confirmation** |

## Untracked files classification (2026-07-12)

| File | Classification |
|---|---|
| `ARCHITECTURE.md`, `CHANGELOG.md`, `DECISIONS.md`, `KNOWN_BUGS.md`, `PROJECT.md`, `TESTING.md`, `TODO.md`, `WORKLOG.md` | Project documentation — commit separately with explicit confirmation |
| `HMH_Payroll_System_Proposal.md` | Business proposal — user to decide |
| `hmh-backend/gen_invoice.py` | Local dev tool — Excel invoice layout generator; not part of app |
| `hmh-backend/query` | Local note containing PostgreSQL service name (`postgresql-x64-18`) |
| `ocr_test.png` | Local OCR test image |
| `package.json` + `package-lock.json` (root) | Playwright screenshot dev dependency |
| `screenshot_analytics.js` | Playwright screenshot script |
| `.claude/` | Claude Code project config — `scheduled_tasks.lock` only |

## Phase 1 scope (approved 2026-07-12)

Implement only these four sub-phases in order:
1. **P1A** — Active BOQ budget filter
2. **P1B** — Milestone audit events
3. **P1C** — Material quantity semantics (issued vs used)
4. **P1D** — Financial cost categories

Site Work Plan: **deferred** until P1A–P1D are complete and tested.
