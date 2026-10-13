# AI Document Import — Deployment Readiness

Assessed 2026-10-13 against branch `feat/ai-document-import`.

**Status: ready to deploy to TEST. Not ready for production.**

The code is complete and verified as far as it can be without external
credentials. What stands between here and production is not engineering work
— it is three credentials and one measurement nobody has taken yet.

---

## 1. Readiness by area

| Area | Status | Evidence |
|---|---|---|
| Code complete | **Ready** | 2 commits on `feat/ai-document-import`; no unrelated files, no secrets |
| Automated tests | **Ready** | 259 AI-import tests pass; full backend 1296 pass / 3 pre-existing failures |
| Database migration | **Ready** | `alembic upgrade head` (the exact Render start command) applies 76 migrations to `0076` on an empty database; a second run applies 0; downgrade removes all 7 tables and 6 enum types; re-upgrade clean |
| Background worker | **Ready** | `_start_ai_import_worker` registered; drain runs clean; stale-job reclaim, retry backoff and duplicate-job prevention all tested |
| Permissions | **Ready** | All 24 routes carry a role guard; the 2 internal cron routes use `CRON_SECRET` with `compare_digest`. Project isolation enforced on every project-scoped path |
| Storage — code | **Ready** | Private writes refuse local disk outside dev/test; production **refuses to boot** without Supabase configured; private paths are `supabase://` references, never fetchable URLs; access is signed-URL only and audited |
| Storage — live bucket | **NOT VERIFIED** | No Supabase credentials available. Upload → signed URL → expiry → delete has never been exercised against a real bucket |
| Anthropic — request contract | **Ready** | SDK 0.109.1 accepts every parameter sent; block shapes, size and page limits, output schema, truncation and refusal handling all verified offline (25 tests) |
| Anthropic — live extraction | **NOT VERIFIED** | **The API has never been called.** No key in any session. Extraction accuracy on real documents is unmeasured |
| Malware scanning | **Partial** | Magic-byte content verification runs unconditionally and rejects renamed executables, archives and scripts. No actual virus scanner exists; `AI_IMPORT_SCAN_URL` is the integration point |
| Automatic posting | **Disabled** | `AI_IMPORT_AUTO_POST_ENABLED=false` in code default, in `render.test.yaml` and in `render.yaml` |
| Frontend | **Ready** | Builds; 0 type errors in new files; Playwright 32/32 |

---

## 2. Genuine blockers

Only these. Everything else is done.

| # | Blocker | Needed from | Clears by |
|---|---|---|---|
| **B1** | **No Anthropic API key.** Without it the engine runs in degraded mode: it stores, hashes, deduplicates and routes documents, but reads almost nothing. A pilot on that would fail for the wrong reason. | You | Creating a TEST-only key and setting it in the Render dashboard |
| **B2** | **Extraction accuracy unmeasured.** Nobody knows how well the model reads an HMH invoice. Piloting before measuring means staff discover the error rate on real paperwork. | Whoever runs the pilot | `LIVE_VALIDATION.md` §4 (fictional samples, ~10 min) then §5 (~20 historical invoices) |
| **B3** | **Supabase TEST credentials not verified.** `SUPABASE_SERVICE_KEY` for the TEST project must be set, and the signed-URL round trip confirmed once. | You | Setting the key, then `LIVE_VALIDATION.md` §6 (~10 min) |

Not blockers, but decisions you should make knowingly:

- **No virus scanner.** Acceptable while documents come only from HMH staff.
  Procure one before accepting documents from outside the organisation.
- **Imported historical stock movements are dated today**, not the original
  delivery date. A review reason warns about it. Changing it means changing
  `delivery_service`, which the manual screens share.
- **Credit notes are not postable** — the system has no credit-note record.

---

## 3. Required Render environment variables

### `hmh-test-backend` (the pilot environment)

Already in `render.test.yaml` — nothing to type:

| Variable | Value |
|---|---|
| `AI_IMPORT_ENABLED` | `true` |
| `AI_IMPORT_MODEL` | `claude-opus-5-5` |
| `AI_IMPORT_AUTO_POST_ENABLED` | `false` |
| `AI_IMPORT_WORKER_ENABLED` | `true` |
| `AI_IMPORT_WORKER_BATCH_SIZE` | `2` |
| `AI_IMPORT_WORKER_INTERVAL_SECONDS` | `20` |
| `AI_IMPORT_MAX_UPLOAD_MB` | `20` |
| `AI_IMPORT_SCAN_ENABLED` | `false` |

Set by hand in the Render dashboard (`sync: false` — never in the file):

| Variable | What it is | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | TEST-only Anthropic key | **Not the production key.** Own spend limit, revocable separately |
| `CRON_SECRET` | Random string, 32+ chars | Drives both AI-import cron jobs. Generate with `openssl rand -hex 32` |
| `SUPABASE_SERVICE_KEY` | TEST project service key | Already required by the existing blueprint |
| `DATABASE_URL` | TEST Supavisor session-mode URL, port 5432 | Already required |
| `SECRET_KEY` | TEST-only, 64+ chars | Already required |

### `hmh-backend` (production) — deliberately off

| Variable | Value | Why |
|---|---|---|
| `AI_IMPORT_ENABLED` | `false` | Explicit. The code default is `true`, so without this the feature would become available to staff on the next production deploy, before the pilot has measured anything |
| `AI_IMPORT_AUTO_POST_ENABLED` | `false` | Stays false even after the pilot, until a business decision says otherwise |

Nothing else is needed in production until you turn it on.

---

## 4. How to set the Anthropic key securely

1. In the Anthropic Console, create a **new API key named for TEST**
   (e.g. `hmh-test-ai-import`). Do not reuse the production key — the point
   is that this one can be revoked without touching anything else.
2. Set a **monthly spend limit** on it. The pilot should cost single-digit
   dollars; a limit of $20–50 bounds any mistake.
3. In Render → `hmh-test-backend` → **Environment**, add
   `ANTHROPIC_API_KEY`. Render stores it encrypted and masks it in the UI.
4. **Do not** put it in `.env`, `render.test.yaml`, a commit, a ticket or a
   chat message. `.env` is gitignored, but the dashboard is the right place
   because Render injects it without it ever existing in a file.
5. Confirm the backend log on restart shows the AI import worker started.
   The key itself is never logged.
6. To rotate: replace the value in the dashboard and redeploy. To revoke:
   delete the key in the Anthropic Console — the engine immediately falls
   back to degraded mode rather than failing.

Same approach for `CRON_SECRET` and `SUPABASE_SERVICE_KEY`.

---

## 5. Deployment sequence

Each step is verifiable before the next.

1. **Merge the branch** (or deploy it directly to TEST from the branch).
   Nothing changes in production behaviour: `AI_IMPORT_ENABLED=false` there.
2. **Create the TEST Blueprint** from `render.test.yaml`, or sync the
   existing one. It brings the two cron jobs with it.
3. **Set the five dashboard secrets** on `hmh-test-backend` (§3).
4. **Deploy TEST.** The start command runs `alembic upgrade head`, which
   applies `0076`. Confirm `GET /health` reports `env=test`, then
   `GET /health/db` reports `db=connected`.
5. **Confirm the startup log** shows
   `ai_import_worker=started ... auto_post=False`.
6. **Run `LIVE_VALIDATION.md` §4** against the fictional samples. This is the
   step that clears B1 and B2 in part.
7. **Run `LIVE_VALIDATION.md` §6** for storage. Clears B3.
8. **Measure accuracy** on ~20 closed historical invoices (§5). Post nothing.
9. **Run the pilot** per `AI_DOCUMENT_IMPORT_PILOT.md`.
10. **Production** only after the pilot: set `AI_IMPORT_ENABLED=true`, add
    the key and cron secret, add the two cron jobs. Leave auto-posting off.

---

## 6. Rollback

- **Fastest:** `AI_IMPORT_ENABLED=false` and redeploy. Uploads are refused,
  the worker stops. Records already posted are unaffected — they are ordinary
  material requests, purchase orders, deliveries and invoices owned by their
  own modules.
- **Code:** redeploy the previous build. The `0076` tables simply go unused.
- **Schema:** `alembic downgrade 0075` drops the seven tables. This destroys
  the import audit trail; the business records survive. Prefer disabling.

---

## 7. What would make me call this production-ready

All three, in order:

1. `LIVE_VALIDATION.md` §4 passes on the fictional samples — the model reads
   a clean invoice correctly.
2. Measured accuracy ≥95% on supplier and total across ~20 real historical
   documents.
3. Storage round trip verified against the live TEST bucket.

Until then the honest status is: **the engine is built and verified; its two
external integrations are not.**
