# Fuel Management targeted gap closure

Date: 2026-08-02  
Migration head: `0070` (depends on `0069`)  
Scope: additive hardening of the existing Fuel Management module. This work does not replace its order, delivery, stock, issue, reconciliation, permission, reporting, or audit ledgers.

## Requirement-to-code gap matrix

| Requirement | Existing implementation retained | Confirmed gap | Implemented closure | Verification |
|---|---|---|---|---|
| Mobile site fuel request | Fuel order state machine and Fuel role permissions | Site roles could not reach Fuel Management; no one-step submitted request, intended-use/destination fields, next approver, or workflow history | `/site/fuel-request`, `POST .../requests`, `mine=true`, additive order fields and immutable `fuel_order_history`; destination-specific vehicle, site-storage or equipment-profile selection is project-scoped; `SITE_STAFF` is the site-clerk equivalent | All five destination types, cross-project rejection, request/history and self-approval tests; frontend type/build |
| Evidence by destination | Generic attachments and Fuel attachment entity types | New issue ledger accepted an optional URL and did not categorize or require evidence | Multipart issue capture requires asset + pump + odometer for vehicles; asset + pump and configured hour-meter evidence for equipment. Missing evidence requires `fuel.admin`, a reason, user and timestamp. Uploads are staged while issue, audit, attachment and evidence rows remain inside one savepoint; any failure rolls back those rows and performs supported local/Supabase object cleanup before a controlled retry response. | Missing-evidence, override, malformed multipart, second-upload failure, stock invariance, cleanup and duplicate-free retry tests |
| Configurable feasibility | Vehicle tank and L/100km; advisory anomaly alerts | Hard-coded 1.5/50/100 limits; no remaining-fuel estimate or configured override | Vehicle L/100km or L/hour, tolerance, tank, minimum interval and override setting; non-vehicle equipment profiles; estimates use last issue plus distance/hours and elapsed time; results use neutral `OK`, `REVIEW`, `OVERRIDE_REQUIRED`, `OVERRIDDEN` language | Profile-driven feasibility and override tests |
| Asset profiles | Existing `Vehicle` identity and assignment model | Tolerance/tracker/hour settings absent; no equipment profile | Extended `Vehicle` without duplicating it; added project-scoped `FuelEquipmentProfile` for named plant/generators/other equipment | Schema/API tests and type checking |
| Tracker boundary/provenance | Manual odometer/hour capture | No vendor-neutral integration boundary or stored reading source | `fuel_tracker_adapter.py` protocol and normalized reading contract; issue source supports manual, photograph verified, tracker verified and manager overridden provenance without coupling a provider | Import/compile and model/API coverage |
| Notification deep links | System alerts, verified authentication context, 401 `returnTo` interceptor | Alert type routing sent Fuel pending alerts to procurement; clicking acknowledged and hid the alert; context lacked access checks | Backend resolves canonical action URL from `reference_type`, verifies that the Fuel order exists and matches the alert project, checks target user/role/project/Fuel access, marks the alert read without changing workflow status, and retains history; frontend loads and highlights the referenced order with explicit 403/expired handling | Real-order backend access/read/not-found/cross-project tests; Playwright rendered Fuel order, MR, expired, 401 return, 403 and history cases |
| Fuel event emails | Generic SMTP/mock service that never raises | Fuel transitions did not send or persist email attempts | Durable `fuel_email_logs`, role/requester/supplier recipient resolution, non-blocking submission/approval/rejection/ordered/delivered dispatch, max-three-attempt retry endpoint and audit UI API. `FRONTEND_BASE_URL` is normalized to an origin; non-development values must be configured, HTTPS and non-local. | Failure-does-not-rollback, retry, localhost test mode, production URL, missing/localhost rejection, trailing-slash and unsafe-path tests; mock mode only |
| Mobile camera/PWA | PWA shell/asset caching and generic attachment storage | Issue UI had no camera workflow, progress or retry | Camera capture, preview, remove, retake, client-side JPEG resize/compression, progress, disabled duplicate submit and retry. Service worker continues to bypass API/uploads and only caches build assets | Type/build and Playwright private-image cache test |
| BOQ boundary | Fuel tables have no BOQ foreign keys | Future Non-BOQ scope was undocumented | Boundary documented below; no BOQ fields or totals were introduced | Structural no-BOQ-dependency test |

## Fuel email configuration

Fuel email delivery uses the existing shared mail configuration:

- `SMTP_ENABLED=true` enables real SMTP only when credentials are also present.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_SSL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_FROM_NAME` configure the sender.
- `FRONTEND_BASE_URL` supplies the public frontend origin for absolute Fuel email deep links.
- `EMAIL_MOCK_MODE=true` records `MOCK_SENT` without external delivery.
- Pytest forces mock behavior unless a test explicitly replaces the sender.

Every intended recipient gets a separate log row. SMTP failures update that row to `FAILED`, schedule a bounded retry, and never roll back the Fuel state change. `POST /api/v1/fuel-management/email-queue/retry` is restricted to `fuel.admin`. Tests verify mock/failure behavior only; this document makes no claim that production SMTP credentials or delivery have been validated.

Outside development/test, startup rejects an empty `FRONTEND_BASE_URL`, localhost/loopback hosts, non-HTTPS URLs, credentials, paths, queries and fragments. A single trailing slash is normalized away. Fuel links are then constructed only from fixed local application paths, preventing protocol-relative or external-path injection.

## Deployment-readiness review corrections

The post-implementation code review confirmed and corrected these issues on 2026-08-02:

- Site requests had treated every non-vehicle destination as equipment. Validation and the mobile selector now distinguish `VEHICLE`, `SITE_STORAGE`, `GENERATOR`, `PLANT` and `OTHER_EQUIPMENT`, and verify project ownership.
- Submit, reject, mark-ordered, cancel and close had returned non-enriched schemas. Every transition now returns requester, current next approver and complete persisted history; verified delivery status changes also append history.
- Evidence metadata was committed once per attachment and then compensated by reversing an issue. The replacement stages storage writes, uses a database savepoint, commits once after all evidence succeeds, and deletes staged objects on failure where supported. Failed captures leave no issue, active attachment metadata or stock reduction.
- Multipart JSON/Pydantic failures are converted to descriptive HTTP 422 responses. Storage failures return a retryable 503 that explicitly states no issue was recorded.
- Audit tests now query `audit_events` for actor, entity, action, reason, timestamp and relevant before/after values for evidence override, feasibility override, excess delivery, issue reversal, reconciliation approval and adjustment.
- Fuel notification tests now reference real orders and cover missing/cross-project records. The frontend test verifies the exact order card and history are rendered after navigation and after the 401 login return.

Latest focused result: **28/28 Fuel backend tests**, **5/5 notification-link Playwright tests**, and **6/6 PWA/login/cache/mobile Playwright tests**. Production SMTP delivery is still unverified and must not be inferred from mock/configuration tests.

## Release-readiness corrections (2026-08-03)

A pre-deployment review (2026-08-02 16:55) classified the release **NOT READY** and listed, among other blockers, two release-safety defects unrelated to Fuel business logic. Both are now fixed and independently re-verified:

- **Fail-open migration startup.** `main.py` ran `alembic upgrade head` from a FastAPI `@app.on_event("startup")` hook, caught any exception, logged it, and let the app start regardless — so a failed migration could serve traffic against a stale schema. The hook was removed. `render.yaml`'s `startCommand` now runs `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`, matching `RUNBOOK.md`'s documented production start command, so migration failure aborts the deploy instead of being swallowed. This also removes the risk of multiple app instances/workers racing an in-process migration.
- **Migration `0069` swallowed all enum-add errors.** The four `attachment_entity_enum` additions (`FUEL_ORDER`, `FUEL_DELIVERY`, `FUEL_ISSUE`, `FUEL_RECONCILIATION`) were wrapped in `DO $$ BEGIN ... EXCEPTION WHEN others THEN NULL; END $$;`, which hides genuine failures (permissions, a typo'd type name, a locked type) behind the same silence used for "already exists." Replaced with an explicit `pg_enum` existence check per value before the `ALTER TYPE ... ADD VALUE`, so only the "already present" case is suppressed and any real DDL error now propagates and fails the migration.

Verification for both: two disposable local PostgreSQL 15 databases were created, upgraded fresh from `0001` through `0070`, queried directly against `pg_enum` to confirm all four Fuel values are present, and dropped. `python -m compileall app tests` was clean. `tests/test_fuel_management.py` was re-run against the dedicated `hmh_test` database: 28/28 passed. `alembic heads` reports a single head, `0070`. `git diff --check` reported only line-ending notices. No production database was accessed and no commit was created.

This correction did not touch Fuel evidence storage privacy, canonical frontend/backend origin configuration, the production preflight validator, full-suite test sharding, the curated release commit, or live SMTP/notification/PWA UAT — those blockers from the 2026-08-02 review remain open.

## Evidence storage privacy and persistence (2026-08-03)

Direct inspection (not the earlier session log) confirmed the 2026-08-02 16:55 review's storage-privacy concern was real and worse than described:

- `AttachmentRead.download_url` returned the **raw, permanent public Supabase URL** directly for every Supabase-stored attachment — the "protected" `GET /attachments/{id}/download` endpoint was never actually reached for those files; anyone holding the URL (network tab, browser history, a shared screenshot) could fetch it forever, unauthenticated.
- The `/uploads` static mount (`main.py`) served every local-disk file with **no authentication or project check at all**, bypassing the protected download endpoint entirely for local storage.
- A failed Supabase upload silently fell back to local disk (`_save_to_supabase` → `_save_to_disk`) with no distinction for production, and the documented bucket-provisioning instructions told operators to create it **public**.
- The same exposure applies to five other upload call sites that write into the shared `attachments` table directly (`deliveries.py` delivery notes, `stock.py` usage evidence, `stages.py` milestone/evidence photos ×2, `email_service.py` generated MR/PO PDFs) — see Residual scope below.

**Architecture chosen:** a second, private Supabase bucket (`SUPABASE_PRIVATE_BUCKET`, default `hmh-evidence-private`) alongside the existing public `hmh-uploads` bucket, rather than flipping the single shared bucket to private. Flipping the shared bucket would have broken the five un-migrated call sites (their stored public URLs would 403). The private bucket is used exclusively by `attachment_service.save_attachment()` (`save_upload(..., private=True)`), which is the only path Fuel evidence uses (`create_issue_with_evidence`) and is also used by the generic `POST /attachments/upload` endpoint (MR/PO/payment/etc. uploads made through that route).

- `stored_path` for a private upload is `supabase://<key>` — never a fetchable URL — or `/uploads/...` on local disk (development/test only).
- `GET /attachments/{id}/download` is the sole access path. It re-verifies project/entity access, then: redirects to a fresh short-lived signed URL (`create_signed_url`, default 300s, `EVIDENCE_SIGNED_URL_EXPIRY_SECONDS`) for `supabase://` paths; redirects unchanged to the existing public URL for legacy `http` records (no new exposure, no regression); streams the file for local disk.
- `AttachmentRead.download_url` now unconditionally returns `/api/v1/attachments/{id}/download` — it never returns a raw storage URL, for any stored-path format.
- Outside development/test, `Settings.validate_production_storage` requires `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` — application startup fails if either is missing. `save_upload(..., private=True)` raises `StorageError` (503) instead of writing to local disk when Supabase is unreachable outside development/test; the existing Fuel evidence savepoint/cleanup transaction (unchanged) converts that into "no fuel issue was recorded, no stock reduced, retry the capture."
- `/uploads` is no longer mounted outside development/test (defense-in-depth; nothing should be written there in production given the point above).
- `storage.verify_private_storage()` checks the private bucket exists, is reachable, and is actually marked private (via Supabase's bucket-metadata `public` field) — surfaced through `GET /admin/storage-status` (OWNER only) alongside the existing legacy-bucket check.

**Residual scope (not touched, documented so it is not mistaken for closed):** `deliveries.py` (delivery notes, receiver/driver signatures), `stock.py` (usage evidence), `stages.py` (milestone photo endpoint), and `email_service.py` (generated MR/PO PDF auto-attach) still call `save_upload(..., private=False)` and remain on the legacy public bucket, unchanged by this pass. They were out of scope for "Fuel evidence and attachment storage" — migrating them touches raw model columns (e.g. `Delivery.delivery_note_image_url`) and additional frontend rendering paths, not the shared `Attachment` table. Tracked in `KNOWN_BUGS.md`.

**Production prerequisite not completed here:** the `hmh-evidence-private` Supabase bucket must be created manually (public: **false**) before `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are set in production — no Supabase credentials or dashboard access were available in this session.

Verification: 27 pre-existing Fuel tests + 2 new config-validation tests in `test_fuel_management.py` (28 total after a `Settings(...)` fixture update for the new production-storage validator interacting with the existing `FRONTEND_BASE_URL` test), all passing; 44/45 in `test_attachments.py` (22 new tests added for signed-URL generation/expiry, permission/project-isolation on `/download`, fail-closed `save_upload`, legacy-URL passthrough, and private-bucket cleanup — the one failure, `test_stage_status_attachment_requires_project_access`, was confirmed via `git stash` to fail identically on the pre-session code and is unrelated to this change). `python -m compileall app tests`: clean. Mock-only — no real Supabase network calls were made in tests.

**Follow-up (2026-08-03, same day):** investigating that one pre-existing failure surfaced a genuine, separate access-control gap — `_entity_project_id()` (the same resolver `GET /attachments/{id}/download` relies on for the signed-URL/permission checks above) never resolved `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, or `WEEKLY_PLAN` to a project, so those three entity types bypassed project isolation entirely. Fixed; the original test failure itself turned out to be a test-persona defect, not a code defect (see `KNOWN_BUGS.md`). `test_attachments.py` is now 48/48.

## Tracker and reading provenance

The Fuel ledger owns normalized business readings, not tracker credentials or vendor payloads. A provider implementation must conform to `FuelTrackerAdapter.latest_reading()` and return a timestamped `TrackerReading` containing only normalized odometer, trip distance, engine hours, ignition duration and optional GPS provenance. The default adapter returns no reading, so manual and photo-verified site operation remains available.

## PWA and attachment privacy

The service worker caches the application shell, manifest/icons and compiled `/assets/` only. It deliberately does not intercept `/api/`, `/uploads/`, cross-origin storage URLs, POST requests or multipart evidence uploads. Fuel evidence therefore is never placed in the service-worker cache. Normal browser/network storage policy remains the responsibility of the deployment environment.

## Non-BOQ boundary

Fuel remains an operational, non-BOQ ledger. Fuel quantities, delivery variances, issues and stock adjustments must not change BOQ quantities, BOQ valuation, material stock or procurement totals. A future “Non-BOQ cost” reporting layer may reference immutable Fuel records by ID for consolidated cost reporting, but must not add BOQ foreign keys to Fuel tables or mutate Fuel records from BOQ workflows.

## Operational verification commands

```powershell
# Backend (dedicated test database only)
$env:DEBUG='false'
$env:TEST_DATABASE_URL='postgresql://hmh:hmhdev@localhost:55432/hmh_test'
python -m pytest -q tests/test_fuel_management.py
python -m compileall app tests
python -m alembic heads

# Frontend
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:pwa
npm.cmd run test:notifications
```

No deployment is part of this change.
