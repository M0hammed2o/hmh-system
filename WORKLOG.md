# WORKLOG — append-only, newest first

## 2026-08-04 — Close three original site-clerk/PWA/dual-access requirements

Changed: `hmh-frontend/src/pages/SiteFuelRequestPage.tsx` (Fuel balance section — "Estimated fuel remaining", storage name, fuel type, and a clear message when no storage location is configured for the selected fuel type/site); `hmh-frontend/tailwind.config.ts` + `src/index.css` (real `pb-safe`/`pt-safe-top` safe-area spacing — `pb-safe` was already referenced by `MobileNav.tsx` but was never defined, so it silently produced no CSS; added `overflow-x: hidden` defense); `hmh-frontend/src/components/layout/AppTopbar.tsx` + `src/pages/SiteDashboardPage.tsx` (`env(safe-area-inset-top)` applied to sticky headers via `max()`, not a bare replacement, so non-notched viewports keep their existing padding); `hmh-frontend/public/icon-maskable-512.png` (rescaled — measured content extended to radius 257px against a 512px-icon safe-zone requirement of ≤204.8px; rescaled via PIL to 195px max radius, no AI image generation used); `hmh-frontend/src/pages/LoginPage.tsx` (added a "Go to Site Dashboard" link to `/site-login`); `hmh-frontend/src/lib/constants.ts` (new `DUAL_ACCESS_ROLE_SET` = OWNER, OFFICE_ADMIN, mirroring the backend's `_PROJECT_ACCESS_BYPASS`); `hmh-frontend/src/routes/SiteRoute.tsx` (admits dual-access roles into `/site`); `hmh-frontend/src/routes/authNavigation.ts` (`landingForRole` honours a `returnTo=/site` request for dual-access roles, not just `SITE_ROLE_SET`); `hmh-frontend/src/pages/SiteLoginPage.tsx` (dual-access roles no longer hit the "Site portal access only" dead end); `hmh-frontend/src/components/layout/AppTopbar.tsx` (topbar + mobile-drawer "Go to Site Dashboard" link, gated on `DUAL_ACCESS_ROLE_SET`).

Root-cause note: fixing `SiteRoute` alone would have created a login loop for dual-access users — `SiteLoginPage`'s post-login role check and `landingForRole`'s `returnTo` handling both still only recognised `SITE_ROLE_SET`, so a dual-access user whose session expired on `/site` would have been bounced to `/site-login`, redirected back to `/site-login` again after entering valid credentials (shown "Site portal access only"), or landed on `/` instead of back on `/site`. All three were fixed together.

Verification: `hmh-backend` `test_fuel_management.py` (29/29) + `test_site_dashboard.py` (16/16) unaffected (no backend files touched this pass). `hmh-frontend` `npm run typecheck`: clean. `npm run build`: clean (Playwright's `webServer` serves the built `dist/`, not live source — tests were run against a rebuild). `npm run test:pwa`: 19/19, including 6 new mobile-viewport tests (360×640, 390×844, 412×915) across `/site/fuel-request` and `/site` checking for horizontal overflow and clipped header/submit-button bounding boxes, 2 new Fuel-balance tests, and 5 new dual-access routing/login-loop tests. `npm run test:notifications`: 5/5, unaffected. `git diff --check`: clean.

Unresolved: the office `/` dashboard showed transient DOM churn (element briefly detaches/reattaches) immediately after a fresh login in one test run, unrelated to this session's changes (no files in that render path were touched) — worth a follow-up investigation, not chased further here; the affected test was rewritten to avoid depending on element stability across ticks rather than papering over a real defect. Physical Android/iPhone device UAT was not performed — all PWA layout claims are simulated-viewport (Playwright) or static-measurement (PIL) verified only.

## 2026-08-03 — Attachment project-isolation audit and fix

Changed: `hmh-backend/app/api/v1/attachments.py` (`_entity_project_id`: added resolution for `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, `WEEKLY_PLAN`; removed `BOQ_HEADER` from a stale "not project-scoped" comment — it was already correctly handled); `hmh-backend/tests/test_attachments.py` (fixed `test_stage_status_attachment_requires_project_access`'s outsider persona from `OFFICE_USER` to `SITE_STAFF`; added `test_previously_unresolved_entity_types_now_enforce_project_isolation`).

Root cause, investigated per a follow-up task after the storage-privacy pass: `test_stage_status_attachment_requires_project_access` was failing before AND after the storage work (confirmed via `git stash` in the prior session). Investigation found two independent things, not one: (1) the test itself used `OFFICE_USER` as its "outsider," but office-level roles are intentionally company-wide across the entire app (`_PROJECT_ACCESS_BYPASS` in `app/dependencies.py`) — confirmed by cross-checking a `SITE_STAFF` outsider against the identical STAGE_STATUS record, which was correctly blocked with 403. STAGE_STATUS's own project resolution was never broken. (2) Auditing every `AttachmentEntity` value against `_entity_project_id()` found a real, separate, previously undocumented gap: `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, and `WEEKLY_PLAN` (all project-scoped, migration 0068) fell through to unrestricted access for every attachment operation, any role, any project.

Verification: `test_attachments.py` 48/48 (was 44/45); `test_fuel_management.py` 29/29; `test_progress_claims.py` 38/38 (regression check, unaffected); `python -m compileall app tests` clean; `git diff --check` clean. Details in `KNOWN_BUGS.md`.

Unresolved: origin canonicalisation, the production preflight validator, full backend-suite sharding, and the curated release commit remain untouched.

## 2026-08-03 — Release-prep: Fuel evidence and attachment storage privacy hardening

Changed: `hmh-backend/app/core/storage.py` (private-bucket support: `save_upload(..., private=True)`, `create_signed_url()`, `verify_private_storage()`, `delete_upload()` for `supabase://` paths; removed the now-unused `public_url()`); `app/core/config.py` (`SUPABASE_PRIVATE_BUCKET`, `EVIDENCE_SIGNED_URL_EXPIRY_SECONDS`, new `validate_production_storage` model_validator); `app/core/exceptions.py` (`StorageError`, 503); `app/services/attachment_service.py` (routes through the private bucket); `app/schemas/attachment.py` (`download_url` always returns the protected endpoint, never a raw storage URL); `app/api/v1/attachments.py` (`download_attachment` redirects to a signed URL for private objects, unchanged legacy-URL passthrough, unchanged local streaming); `main.py` (`/uploads` static mount no longer registered outside development/test); `app/api/v1/admin.py` (`storage-status` reports the private bucket too); `.env.example`; `hmh-backend/tests/test_fuel_management.py` (added `test_production_storage_validation`, updated the existing `FRONTEND_BASE_URL` test's direct `Settings(...)` constructions for the new validator); `hmh-backend/tests/test_attachments.py` (22 new tests appended to the existing suite).

Behaviour: Fuel evidence (`create_issue_with_evidence`, the only path Fuel evidence uses) and the generic `/attachments/upload` endpoint now store objects in a private Supabase bucket, never a fetchable public URL. Access is only via `GET /attachments/{id}/download`, which re-checks project/entity permission on every call, then redirects to a short-lived signed URL. Outside development/test, missing Supabase credentials now fail application startup (not just a log warning), and a failed private upload raises `StorageError` (503) instead of silently writing to local disk — the existing Fuel evidence savepoint/cleanup transaction (unchanged) converts that into a clean "no issue recorded, retry" response. Five other upload call sites (delivery notes/signatures, stock usage evidence, stage milestone photos, generated MR/PO PDFs) remain on the legacy public bucket, unchanged — documented as a residual gap in `KNOWN_BUGS.md`, not silently left implicit.

Verification: `test_fuel_management.py` 28/28 (was 27/28 immediately after the change, until the pre-existing `FRONTEND_BASE_URL` test was updated for the new validator); `test_attachments.py` 44/45, sole failure (`test_stage_status_attachment_requires_project_access`) confirmed via `git stash` to fail identically on unmodified pre-session code — pre-existing, not a regression. `python -m compileall app tests`: clean. No real Supabase network calls in tests (all mocked via `monkeypatch`). No production database or Supabase account was accessed. The `hmh-evidence-private` bucket itself has not been created in any real Supabase project — that requires dashboard access not available this session.

Unresolved: the private bucket must be manually provisioned before production deploy; five legacy-public-bucket upload flows remain out of scope; origin canonicalisation, the production preflight validator, full backend-suite sharding, and the curated release commit are untouched, per the task's explicit scope boundary for this pass.

## 2026-08-03 — Release-prep: fail-closed migrations + hardened 0069 enum handling

Changed: `hmh-backend/main.py` (removed the `run_db_migrations` startup hook that ran `alembic upgrade head` in-process, logged failures and let the app start anyway); `render.yaml` (`startCommand` is now `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`, matching `RUNBOOK.md`); `hmh-backend/RUNBOOK.md` (step 4 clarified); `hmh-backend/alembic/versions/0069_fuel_management.py` (replaced the `DO $$ ... EXCEPTION WHEN others THEN NULL END $$` enum-add wrapper with an explicit `pg_enum` existence check per value, so a real failure — permissions, typo, wrong type — now aborts the migration instead of being silently swallowed).

Verification: created two disposable local PostgreSQL databases (`hmh_enum_probe`, `hmh_enum_probe2`, both dropped after use) against the local `hmh-postgres` (PG 15) container. Confirmed empirically that the *original* wrapper did correctly add `FUEL_ORDER`/`FUEL_DELIVERY`/`FUEL_ISSUE`/`FUEL_RECONCILIATION` to `attachment_entity_enum` (ruling out a suspected PL/pgSQL subtransaction failure mode) — the risk was purely "hides a *future* real error," not "already silently failing." Re-ran a fresh `0001 → 0070` upgrade with the hardened migration: passed, `alembic current` reports `0070`, and `pg_enum` shows all four Fuel values present. `python -m compileall app tests`: clean. `python -m pytest tests/test_fuel_management.py`: 28/28 passed against `hmh_test`. `git diff --check`: clean (line-ending notices only). No production database was touched; no commit was created.

Unresolved: the remaining blockers from the 2026-08-02 16:55 pre-deployment review (curated release commit for ~54 untracked files, Fuel evidence storage privacy, canonical frontend/backend origin config, production preflight validator, sharded full backend suite, live SMTP/notification/PWA UAT) are untouched and still block release.

## 2026-08-02 — Fuel targeted gap closure

Changed: additive Fuel models/API/service/UI, alert open/read routing, vehicle profiles, tracker boundary, durable email log/retry, camera evidence, migration `0070`, focused backend and Playwright tests, and implementation documentation.

Verification: the deployment-readiness review expanded Fuel coverage to 28 passing tests for destination ownership, enriched transitions, staged evidence rollback/retry, controlled multipart errors, real audit rows, real-record notification authorization and email-origin validation; 5 notification-link and 6 PWA/mobile Playwright tests passed. TypeScript, compile/import, Vite production build and clean `0001 -> 0070` migration passed. Real SMTP delivery and physical-device UAT were not claimed. No deployment performed.

## 2026-08-02 — Standalone Fuel Management + PWA/login recovery
Changed: migration 0069; Fuel models/schemas/service/API/permissions/tests; legacy fuel access/delete safeguards; six Fuel frontend routes/API/sidebar group; manifest/icons/service worker/offline/update UI; verified auth context, retained return destinations and production host fallback; Playwright config/tests; implementation and memory docs.
Behaviour: Fuel request → approval → order → partial/verified delivery → auditable stock issue/reversal/reconciliation/reporting is separate from BOQ. Installed app starts at universal login, supports direct site login and nested-route refresh/offline shell, and never caches private API responses.
Tests: migration upgrade/downgrade/re-upgrade PASS; Fuel 14/14; Fuel + progress/programme/weekly 51/51; TypeScript 0 errors; Vite production build PASS; Playwright PWA/login 4/4. Full 873-test backend run reached 86% before 900s timeout and exposed pre-existing failures tracked in KNOWN_BUGS.
Verdict: Implementation and automated verification complete; real deployed Android/iOS install/update UAT remains an operational release step.
Unresolved: baseline full-suite failures and production device/deployment verification.
<!-- Template: ## [date] — [task in one line] / Changed: / Behaviour: / Tests: / Verdict: / Unresolved: -->
<!-- Past 30 entries → compress oldest 15 into one "Earlier work" summary block. -->

## 2026-07-19 — Municipality Progress Claim + Programme Planning + Weekly Plans
Changed: `app/models/{progress_claim,programme,weekly_plan}.py`, `app/models/stage.py` (added `code`/`is_active`/`updated_at`), `app/models/__init__.py`, `alembic/versions/0068_*.py`, `app/schemas/{progress_claim,programme,weekly_plan}.py`, `app/services/{progress_claim,programme,weekly_plan,progress_propagation}_service.py`, `app/api/v1/{progress_claims,programme,weekly_plans}.py`, `main.py`, `tests/test_progress_claims.py`, `tests/conftest.py`, `app/models/enums.py` (new enums + alert/attachment values), frontend: 4 pages + 3 API clients + AppRouter + AppSidebar.
Behaviour: Progress claims generated from operational data (stage milestones, work-done, job cards) with no monetary fields; full state machine (DRAFT→GENERATED→UNDER_REVIEW→READY_FOR_PRICING→APPROVED→EXPORTED); PDF export via reportlab; programme activity CRUD with baseline freeze; weekly plans with item-level progress propagation to project.
Tests: 38 tests (T01-T38) — 38/38 pass. Environment: `TEST_DATABASE_URL=postgresql://hmh:hmhdev@localhost:55432/hmh_test`.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-11 — Warehouse transfer approval + supplier payment due alerts
Changed: `hmh-backend/app/models/warehouse_transfer.py` (NEW), `alembic/versions/0066_warehouse_transfer_requests.py` (NEW), `alembic/versions/0067_supplier_payment_due_days.py` (NEW), `app/schemas/warehouse_transfer.py` (NEW), `app/services/warehouse_transfer_service.py` (NEW), `app/api/v1/warehouse_transfers.py` (NEW), `app/services/payment_due_service.py` (NEW), `app/services/invoice_service.py` (auto-compute due_date), `app/models/supplier.py` (+payment_due_days), `app/schemas/supplier.py` (+payment_due_days), `app/api/v1/notification_settings.py` (+scan endpoint), `main.py` (+2 cron endpoints, +2 routers), `app/models/__init__.py`, `hmh-frontend/src/api/warehouseTransfers.ts` (NEW), `hmh-frontend/src/api/suppliers.ts` (+payment_due_days), `hmh-frontend/src/api/notificationSettings.ts` (+scanPaymentDue), `hmh-frontend/src/pages/ProjectWarehousePage.tsx`, `hmh-frontend/src/pages/SupplierProfilePage.tsx`, `hmh-frontend/src/pages/NotificationSettingsPage.tsx`
Behaviour: Site clerk submits project-to-project transfer request with reason; 3 OFFICE_AND_ABOVE votes execute it; OWNER override bypasses vote count; rejected with reason. Supplier payment_due_days drives invoice due_date auto-compute; daily scan fires PAYMENT_DUE (within 7 days) and OVERDUE_PAYMENT alerts with 23h deduplication.
Tests: TypeScript tsc clean; Python import check OK. No new automated tests added.
Verdict: Self-verified; no independent verifier available.
Unresolved: No automated test coverage for warehouse transfer flow or payment due scan.

## 2026-07-10 — Replace client name free-text with Company dropdown + autofill issuing company
Changed: `hmh-frontend/src/pages/ProjectsPage.tsx`, `hmh-frontend/src/pages/ProjectDetailPage.tsx`, `hmh-frontend/src/pages/ProcurementPage.tsx`
Behaviour: Project create/edit forms show a select with two fixed options ("HMH Group" / "Minerat Construction & Civils") stored in `client_name`. Procurement pipeline pre-selects issuing company from project `client_name` via `clientNameToIssuingKey()`.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: Company list is hardcoded in frontend; not DB-configurable.

## 2026-07-10 — Project Cost Summary page
Changed: `hmh-frontend/src/pages/ProjectCostSummaryPage.tsx` (NEW), `hmh-frontend/src/api/costSummary.ts`, `hmh-frontend/src/routes/AppRouter.tsx`
Behaviour: New route `/projects/:projectId/cost-summary` shows full project cost breakdown in one view.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-10 — Machine hours field + L/hr display in fuel log
Changed: Backend fuel model/schema/API, `alembic/versions/0063_fuel_per_hour.py`, frontend fuel form and table
Behaviour: Fuel log entries accept `hours_operated` (optional float); table shows litres-per-hour when hours are set.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-09 — BOQ access control, fuel/hr, extra order reasons, WhatsApp cron, company-project linking
Changed: `app/api/v1/boq.py` (role guard), `app/api/v1/companies.py` (project linking), misc frontend pages
Behaviour: BOQ write operations gated to OFFICE_AND_ABOVE; companies can be linked to projects; WhatsApp cron authenticated trigger endpoint added.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-08 — Workshop complete pipeline (Phases A–D)
Changed: `app/models/` (mr_quote.py, mr_quote_vote.py, mr_email_log.py additions), `alembic/versions/0056_repair_jobs.py` through `0062_workshop_phase_d.py`, `app/api/v1/workshop.py`, `app/services/workshop_service.py`, `hmh-frontend/src/pages/WorkshopPage.tsx`, `hmh-frontend/src/pages/VehiclesPage.tsx`
Behaviour: Workshop MR → 3-person vote approval → email suppliers for quotes → quote upload with 3-person approval → PO → delivery note → invoice. Parts issuance from stock. Site dashboard Workshop tab for site staff.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-06 to 2026-07-07 — Vehicle fleet management
Changed: Multiple vehicle-related files, `alembic/versions/0045_vehicle_vin.py`, `0057_vehicle_site_features.py`, site dashboard vehicles tab, fuel via procurement
Behaviour: Vehicles assignable to projects; office assigns/unassigns; site dashboard shows vehicles read-only; bulk fuel, repair workflow, transfer requests from site.
Tests: TypeScript tsc clean.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-01 — Test: delivery → site dashboard BOQ update integration
Changed: `hmh-backend/tests/test_delivery_boq_update.py`
Behaviour: Integration test confirms stock delivery triggers correct BOQ quantity update.
Tests: New integration test added; passed.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-07-01 — BOQ deduplication + delivery note extraction fixes
Changed: `app/services/boq_service.py`, `app/services/document_ai_service.py`
Behaviour: Unit case normalisation prevents duplicate BOQ entries on delivery; BOQ specificity matching improved; PDF table row re-joining for multi-line cells.
Tests: Existing BOQ tests pass.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## 2026-06-30 — Procurement quote extraction + supplier Document Centre fixes
Changed: `app/services/gmail_ocr_pipeline_service.py`, `app/api/v1/suppliers.py`
Behaviour: Alphanumeric units parsed; per-item idempotency on quote extraction; email body MR match improved; supplier Document Centre MR lookup uses MREmailLog not PO chain.
Tests: Relevant pipeline tests pass.
Verdict: Self-verified; no independent verifier available.
Unresolved: none

## Earlier work (2026-04 through 2026-06-29)

Core system build-out covering: initial FastAPI + PostgreSQL schema (0001–0015), lot types and attachments (0016–0020), notification enhancements (0021–0023), performance indexes (0024–0025), milestone tracking (0026), attachment enhancements (0027), procurement pipeline (MR→PO→Delivery→Invoice→Payment), stock ledger, WhatsApp notification system, alert recipients, Gmail OCR pipeline (IMAP reader + Document AI), site dashboard portal, subcontractor work-done module, municipality invoices, audit log, procurement analytics, proof packs / invoice reconciliation, admin tools, Supabase storage integration, security hardening (Phase B audit — all CRITICAL/HIGH/6 MEDIUM fixed, 2 MEDIUM and 1 LOW accepted risk), Phase 3V upload MIME validation + admin hardening, Phase 3M procurement pipeline 7 production bug fixes + 41-test e2e suite.
