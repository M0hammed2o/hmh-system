| File | Tests | Covers |
|---|---|---|
| test_ai_import_extraction.py | 32 | normalisation, SA formats, arithmetic, injection, provider failure, classifier, cost |
| test_ai_import_matching.py | 35 | supplier/project/site resolution, ambiguity, PO matching, units, catalogue, three-way |
| test_ai_import_pipeline.py | 52 | full pipeline, policy outcomes, corrections, worker, out-of-order, dashboard, access control |
| test_ai_import_posting.py | 28 | MR/PO/GRN/invoice via real services, stock assertions, idempotency, refusals, audit |
| test_ai_import_provider_contract.py | 25 | SDK surface, block shapes, size/page limits, schema, truncation, credentials |
| test_ai_import_safety.py | 19 | round-1 defects: post-commit failure, isolation, dashboard scoping, auto-post gate |
| test_ai_import_safety_round2.py | 22 | round-2 defects: stale matches, posting resolution, evidence-based release, site isolation |
| test_ai_import_scenarios.py | 15 | multi-page, multi-invoice, consolidated invoice, PO-before-MR, historical stock, cron auth |
| test_ai_import_storage_security.py | 24 | content verification, malware scanning, storage paths, signed URLs, retention |
| test_ai_import_workflow_e2e.py | 7 | the four-document transaction, run twice for idempotency, missing and conflicting documents |

# AI Document Import — Progress

Session continuity file. Updated after each meaningful phase.
Last updated: 2026-10-13 (Phase 2).

## Current phase

Phases 0–13 implemented. Phase 14 (delivery documentation) in progress.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository audit + plan | Complete — `docs/AI_DOCUMENT_IMPORT_IMPLEMENTATION.md` |
| 1 | Universal document inbox | Complete |
| 2 | Classification + extraction | Complete |
| 3 | Matching / reconciliation engine | Complete |
| 4 | Material request import | Complete |
| 5 | Purchase order import | Complete |
| 6 | Goods receipt + inventory | Complete, with one documented limitation (direct-to-lot) |
| 7 | Supplier invoices / AP | Complete, with one documented gap (credit notes) |
| 8 | Reconciliation dashboard | Complete |
| 9 | Processing policy + human review | Complete |
| 10 | Security + audit | Complete |
| 11 | Reliability + background processing | Complete |
| 12 | Automated testing | Complete — 259 tests |
| 13 | Existing system integration | Complete |
| 14 | Final delivery doc | In progress |

## Files added

Backend:
- `app/models/ai_import.py` — 7 tables
- `app/models/enums.py` — 6 new enums appended
- `app/schemas/ai_import.py` — versioned extraction schema + API contracts
- `app/services/ai_import_extraction_service.py` — classification/extraction, arithmetic verification, injection scan
- `app/services/ai_import_matching_service.py` — reconciliation engine
- `app/services/ai_import_policy_service.py` — AUTO_ELIGIBLE / NEEDS_REVIEW / BLOCKED
- `app/services/ai_import_posting_service.py` — posts via existing domain services
- `app/services/ai_import_service.py` — lifecycle, review, dashboard
- `app/services/ai_import_worker.py` — job queue drain
- `app/api/v1/ai_import.py` — 19 endpoints
- `alembic/versions/0076_ai_document_import.py`

Frontend:
- `src/api/aiImport.ts`
- `src/pages/AIDocumentImportPage.tsx`
- `src/components/aiImport/AIDocumentImportDetail.tsx`
- `src/components/aiImport/AIImportBadges.tsx`

Tests:
- `tests/ai_import_fixtures.py`, `tests/test_ai_import_extraction.py`,
  `tests/test_ai_import_matching.py`, `tests/test_ai_import_posting.py`,
  `tests/test_ai_import_pipeline.py`

## Files modified

- `app/core/config.py` — AI_IMPORT_* settings block
- `app/models/__init__.py` — register new models
- `main.py` — router, internal cron endpoint, worker startup loop
- `tests/conftest.py` — create AI import enum types before `create_all`, add the partial unique index
- `src/routes/AppRouter.tsx`, `src/components/layout/AppSidebar.tsx`, `src/components/layout/AppTopbar.tsx` — route and nav

No existing table, column, service signature or endpoint was changed.

## Migration status

`0076` is the new head (`0075 -> 0076`). Applied, downgraded and re-applied
against a clean PostgreSQL 15 database; additive only, fully reversible.

## Tests executed

Command (from `hmh-backend`):

```
TEST_DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_test APP_ENV=test \
  python -m pytest tests/test_ai_import_*.py -q
```

Result: **259 passed**.

| File | Tests |
|---|---|
| test_ai_import_extraction.py | 32 |
| test_ai_import_matching.py | 35 |
| test_ai_import_posting.py | 28 |
| test_ai_import_pipeline.py | 52 |
| test_ai_import_scenarios.py | 15 |
| test_ai_import_safety.py | 19 |

Frontend: `npx tsc --noEmit -p tsconfig.app.json` reports **0 errors in the new
files** (the repository has 119 pre-existing errors in unrelated files).

## Phase 2 additions

- `tests/test_ai_import_provider_contract.py`, `test_ai_import_storage_security.py`,
  `test_ai_import_safety_round2.py`, `test_ai_import_workflow_e2e.py`
- `app/core/upload_scanning.py` — content verification + scanner integration point
- `scripts/generate_ai_import_samples.py` — fictional four-document sample set
- `docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` — the live-test runbook
- `src/components/aiImport/ManualLinkPanel.tsx` — manual PO/MR linking
- Resolution workflow for interrupted postings (2 endpoints)
- Schedulable retention endpoint (`/api/v1/internal/ai-import-retention`)
- Reason-code worklist filter; dashboard queue counts are now clickable

## Independent verification

Two independent reviews, both returning **FAIL**.

Round 1 found nine defects, two proven by executed tests (a retry creating a
second stock movement; a site manager relocating a document into another
project). Round 2 found nine more, including stale auto-confirmed matches
that could book a goods receipt against a superseded purchase order, and
interrupted postings with no resolution path. All eighteen are fixed, with
regression tests in `test_ai_import_safety.py` and
`test_ai_import_safety_round2.py`; the critical ones were confirmed to fail
against the pre-fix code. Detail in `AI_DOCUMENT_IMPORT_COMPLETION.md` §8b.

`tests/conftest.py` now binds its session with
`join_transaction_mode="create_savepoint"` so a rollback in application code
behaves as it does in production. The previous behaviour hid one of the
defects and made correct code look broken.

## Outstanding errors

None known in the new code.

## Next precise task

Finish `docs/AI_DOCUMENT_IMPORT_COMPLETION.md` and confirm the full
pre-existing backend suite shows no regression.

## Blockers requiring human intervention

1. **No `ANTHROPIC_API_KEY` in either session.** Every test stubs the provider.
   The request contract is now verified offline in detail, but the live
   model's behaviour on real scans is still **unmeasured**. Run
   `docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` with a key.
2. **No real HMH supplier documents available** to measure extraction accuracy.
   A fictional sample set is generated by
   `scripts/generate_ai_import_samples.py` so the first live test needs none.
3. **No Supabase credentials**, so the remote storage paths are exercised with
   the storage layer stubbed, not against a live bucket.
4. **Docker Desktop could not be started** in session 2 (no admin rights for
   `com.docker.service`). Tests ran against a private PostgreSQL 16 cluster
   initialised from the native install on port 55433; the user's own clusters
   were untouched. See "Test environment" below.

## Test environment (session 2)

```
initdb -D <scratch>/pgdata -U hmh --pwfile=... -E UTF8 --locale=C
pg_ctl -D <scratch>/pgdata -o "-p 55433 -c listen_addresses=127.0.0.1" start
TEST_DATABASE_URL=postgresql://hmh:hmhdev@127.0.0.1:55433/hmh_test
```
The 181-test session-1 baseline reproduced exactly on this fresh cluster,
which also confirms the suite depends on no leftover state.
