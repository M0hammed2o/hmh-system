# CHANGELOG — HMH Construction OS

## [2026-08-04] — Site-clerk Fuel balance, PWA mobile layout, dual-access Site Dashboard entry points

- Site Fuel request page now shows "Estimated fuel remaining" with the fuel type and storage location for the selected project/site, or a clear message when no storage location has been configured — this was previously invisible to the site clerk.
- Fixed a dead `pb-safe` Tailwind class (referenced by the bottom mobile nav but never defined) and added real `env(safe-area-inset-*)` handling to sticky headers and the mobile nav, plus defensive `overflow-x: hidden`.
- Rescaled the maskable PWA icon — measured content extended past the W3C maskable safe-zone radius (257px vs a 204.8px limit on a 512px icon); corrected via image scaling, no AI regeneration.
- Added a "Go to Site Dashboard" link on the universal login page, and on the main dashboard for OWNER/OFFICE_ADMIN (new dual-access role concept, mirroring the backend's company-wide role bypass). Fixed three places (`SiteRoute`, `landingForRole`, `SiteLoginPage`) that would otherwise have produced a login loop for these roles.
- Added Playwright coverage at 360×640, 390×844 and 412×915 for `/site/fuel-request` and `/site` (no horizontal overflow, no clipped header/submit controls), plus dual-access routing and Fuel-balance display tests. 19/19 in `pwa-login.spec.mjs`.

## [2026-08-03] — Fix: three attachment entity types bypassed project isolation

- `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, and `WEEKLY_PLAN` attachments (list/upload/delete/download) were reachable by any authenticated user regardless of project membership — `_entity_project_id()` didn't resolve them to a project, so the project-access check was silently skipped. Fixed by adding the missing resolution.
- Separately corrected a test (`test_stage_status_attachment_requires_project_access`) that used a company-wide office role as its "unauthorised outsider" — that role is intentionally company-wide everywhere in the app, so the test's premise was wrong, not the access-control code. No production code changed for that item.
- `test_attachments.py`: 48/48 passing (was 44/45).

## [2026-08-03] — Release-prep hardening: private Fuel evidence and attachment storage

- Fuel evidence and generic attachment uploads (`/attachments/upload`) now go to a private Supabase bucket, never a permanent public URL. `stored_path` is an internal `supabase://<key>` reference; access is only through `GET /attachments/{id}/download`, which re-checks project/entity permission and redirects to a fresh short-lived signed URL.
- The `/uploads` static file mount no longer serves files outside development/test — it previously exposed every local-disk upload with no authentication.
- Outside development/test, missing `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` now fails application startup; a failed private upload raises a controlled error instead of silently falling back to local (ephemeral, unauthenticated) disk.
- Five upload flows that write directly into the shared attachments table outside the Fuel/attachment_service path (delivery notes/signatures, stock usage evidence, stage milestone photos, generated MR/PO PDFs) are unchanged and documented as a residual gap in `KNOWN_BUGS.md`.
- 22 new backend tests added; no production database or Supabase account accessed.

## [2026-08-03] — Release-prep hardening: fail-closed migrations, safer enum DDL

- Backend no longer runs `alembic upgrade head` from a FastAPI startup hook; a migration failure previously logged an error and let the process start anyway, serving traffic against a stale schema. The release/start command is now the sole migration path: `alembic upgrade head && uvicorn ...`.
- Migration `0069`'s `attachment_entity_enum` additions no longer swallow every exception; each value is checked against `pg_enum` first and added only if missing, so a genuine DDL failure now aborts the migration instead of being hidden.
- No deployment performed; verified against disposable local databases only.

## [2026-08-02] — Fuel targeted gap closure (migration 0070)

- Added site-clerk one-step Fuel requests with “my requests”, approval history and next approver.
- Added destination-specific mandatory evidence, audited admin override, configurable vehicle/equipment feasibility and reading provenance.
- Added access-checked notification deep links with independent read state, safe 401 return and clear 403 behavior.
- Added durable non-blocking Fuel workflow emails with recipient resolution, failure logs and bounded retry.
- Added mobile capture compression/progress/retry and verified private evidence is absent from PWA caches.
- No deployment performed.

## [2026-08-02] — Fuel Management, installable PWA and reliable login routing (migration 0069)

- Added independent configurable fuel types, storage, order workflow, partial/verified deliveries, issues/reversals, calculated stock, thresholded reconciliation, adjustments, monitoring and CSV reports.
- Added explicit `fuel.*` permissions, project isolation, audit/notification integration, attachment entities and immutable legacy transaction protection.
- Added six responsive Fuel routes and a dedicated navigation group; legacy page remains at `/fuel-legacy`.
- Added valid branded icons, manifest scope/start URL, service worker, offline fallback, safe update prompt and no-cache deployment headers.
- Hardened `/login`, retained `/site-login` phone/PIN compatibility, server-verified guards, role-safe return destinations, session-expiry handling and production hostname resolution.
- Added 14 backend integration tests and 4 Playwright PWA/login browser tests.
- Migration cycle, 51-test focused backend regression, TypeScript and production Vite build pass.
<!-- Newest first. Dates and commits verified from `git log --format="%h %ad %s" --date=short`. -->

## [2026-07-19] — Municipality Progress Claim + Programme Planning + Weekly Plans (migration 0068)

New modules: municipality progress claims, programme activities, and weekly work plans.

**Backend**
- Alembic migration 0068: `municipality_progress_claims`, `progress_claim_lines`, `progress_claim_evidence`, `programme_activities`, `weekly_plans`, `weekly_plan_items` tables; `CLAIM_READY_FOR_PRICING`, `CLAIM_APPROVED`, `WEEKLY_PLAN_DUE` alert types; `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, `WEEKLY_PLAN` attachment entities
- Models: `MunicipalityProgressClaim`, `ProgressClaimLine`, `ProgressClaimEvidence`, `ProgrammeActivity`, `WeeklyPlan`, `WeeklyPlanItem` (anti-double-count unique constraint on claim lines)
- Services: `progress_claim_service` (generate from 3 sources, state machine, PDF export), `programme_service`, `weekly_plan_service`, `progress_propagation_service` (WeeklyPlanItem → ProgrammeActivity → StageStatus → Lot → Project chain)
- API: 6 routers registered in `main.py` (`/projects/{id}/progress-claims`, `/progress-claims`, `/projects/{id}/programme`, `/programme`, `/projects/{id}/weekly-plans`, `/weekly-plans`)
- **No-pricing rule enforced**: `rate`, `unit_price`, `claim_amount` deliberately absent from `ProgressClaimLine`
- AP-02 / AP-04 / AP-15 compliance maintained

**Frontend**
- `ProgressClaimsPage` + `ProgressClaimDetailPage`: project picker, claim CRUD, generate lines, status transitions, Export PDF, no-pricing notice
- `ProgrammePlanPage`: activity CRUD, baseline lock, progress bars, critical path/milestone indicators
- `WeeklyPlanPage`: dual-column plan list + item detail, mark-done, submit/approve flow
- API clients: `progressClaims.ts`, `programme.ts`, `weeklyPlans.ts`
- AppRouter: 4 new routes; AppSidebar: 3 new items under "Progress" group

**Tests**
- 38 tests (T01-T38) in `tests/test_progress_claims.py` — all pass
- `StageMaster` model corrected: added `code`, `is_active`, `updated_at` columns to match live DB schema

---

## [2026-07-11] ec5d1f2 — Warehouse Transfer Approval + Supplier Payment Due Alerts

**Warehouse Transfer (project-to-project stock movement):**
- Site clerk submits transfer request with mandatory reason; office notified via WhatsApp
- 3 OFFICE_AND_ABOVE votes required; auto-executes on third vote (writes paired TRANSFER_OUT/TRANSFER_IN ledger rows)
- OWNER single-vote override
- Reject with reason supported
- Pending transfers panel visible on ProjectWarehousePage

**Supplier Payment Due Alerts:**
- `payment_due_days` integer field added to suppliers (e.g., 30 = Net 30)
- Invoice `due_date` auto-computed from `invoice_date + payment_due_days` when not manually set
- Daily scan: `PAYMENT_DUE` alert when due within 7 days; `OVERDUE_PAYMENT` alert when overdue; 23h deduplication
- Manual trigger button in Notification Settings page
- Cron endpoint `POST /api/v1/internal/scan-payment-due` for Task Scheduler / Render cron
- Migrations: 0066 (warehouse transfer tables) + 0067 (supplier payment_due_days column)

---

## [2026-07-10] b4b5e2e — Company Dropdown + Issuing Company Autofill

- Project create/edit forms: "Client Name" free-text replaced with Company select (HMH Group / Minerat Construction & Civils)
- Procurement pipeline: issuing company selector pre-fills from `project.client_name` via `clientNameToIssuingKey()` helper

## [2026-07-10] b648872 — Project Cost Summary Page

- New route `/projects/:projectId/cost-summary`
- Full project cost breakdown in a single view

## [2026-07-10] f75a5ba — Machine Hours in Fuel Log

- `hours_operated` optional float field added to fuel log entries
- Table shows L/hr calculation when hours are recorded
- Migration: 0063 (fuel_per_hour)

## [2026-07-10] acb63ab — Daily Summary Trigger + Label Fix

- "Send Daily Summary Now" button added to Notification Settings page
- Authenticated trigger endpoint `POST /notification-settings/trigger-daily-summary`

---

## [2026-07-09] 99720ec — BOQ Access Control, Extra MR Reasons, WhatsApp Cron, Company-Project Linking

- BOQ write operations gated to OFFICE_AND_ABOVE (site staff can no longer modify BOQ directly)
- Extra "reason" field on MR order amendments
- WhatsApp cron authenticated UI trigger
- Company-project linking via CompaniesPage

## [2026-07-09] 47f9a8e — Rafiq Label + Override Dialog Clarity

- "Office Admin" display label renamed to "Rafiq" in override dialogs for clarity

---

## [2026-07-08] cfbea07 / 3b4e62b / 2d2d8d8 / 1b9c376 — Workshop Module Complete (Phases A–D)

**Phase A — 3-person MR approval:**
- Workshop repair request creates an MR with 3-vote gate; OWNER override

**Phase B — Email suppliers for quotes:**
- After MR approval, system emails configured suppliers requesting parts quotations
- MREmailLog records each send

**Phase C — Quote upload and 3-person approval:**
- Suppliers' quote PDFs uploaded by office; 3-person approval gate before PO creation

**Phase D — PO, Invoice, Delivery Note:**
- Full PO → delivery note → invoice chain for workshop repair jobs
- Parts issuance from project warehouse stock to repair job

---

## [2026-07-07 to 2026-07-08] — Vehicle Fleet Management (Phases 1–5)

- Workshop module Phase 1: backend models (RepairJob, vehicle enhancements)
- Phase 2: Site dashboard Workshop tab for site staff
- Phase 3: Office vehicle management page (assign/unassign to projects, repair workflow)
- Phase 4: Parts issuance log from office
- Phase 5: Parts history tab on vehicle detail panel
- VIN field on vehicles (migration 0045)
- Site vehicle features migration (0057)
- Auto-assign vehicle to project warehouse on assignment
- Site dashboard vehicles tab: bulk fuel, repair, transfer requests

---

## [2026-07-01] — Test: Delivery → BOQ Update + BOQ Fixes

- Integration test `test_delivery_boq_update.py` added
- BOQ deduplication: unit case normalisation
- BOQ specificity matching improved
- PDF table row re-joining for split cells in quote extraction

---

## [2026-06-30] — Procurement Quote Extraction + Document Centre Fixes

- Alphanumeric units in quote line-item parser
- Per-item idempotency on quote extraction
- Email body MR match improvement
- Supplier Document Centre: MR lookup uses MREmailLog (not PO chain)

---

## [2026-06-19] Phase 3M — Procurement Pipeline 7 Bug Fixes + 41-Test E2E Suite

See memory: `project_phase3m_pipeline_fixes.md`
- 7 production bugs fixed in MR→PO→Delivery→Invoice pipeline
- 41-test e2e suite added (`test_e2e_procurement_pipeline.py`)

---

## [2026-05-26] Phase 3V — Security Hardening + Upload Validation

See memory: `project_phase3v_security.md`
- Upload MIME validation
- Admin endpoint hardening
- JWT startup secret-key check
- `check_project_access()` project isolation helper

---

## [2026-05-26] Phase B Security Audit

- 1 CRITICAL + 5 HIGH + 6 MEDIUM fixed
- 2 MEDIUM + 1 LOW accepted as risk
- WhatsApp HMAC verification, cron endpoint hardening, exception leak fixes, input validation
- See `SECURITY_AUDIT_PHASE_B.md` for full detail

---

## [2026-04 to 2026-05] Initial Build (Migrations 0001–0055)

Full system build covering:
- Core schema: projects, sites, lots, BOQ, suppliers, items, users, access control
- Full procurement pipeline: MR → Quote → PO → Delivery → Invoice → Payment
- Stock ledger (append-only) + `stock_balances` materialized view
- WhatsApp notification system: SystemAlert, AlertRecipient, NotificationQueue, background drain loop
- Gmail SMTP/IMAP + Document AI (Claude + Google Vision) OCR pipeline
- Site dashboard portal (restricted tablet view for site staff)
- Subcontractor work-done module, municipality invoices
- Audit log, reconciliation, procurement analytics, proof packs
- BOQ templates, allocation, job cards
- Fuel management module
- Phase 3Q.1: Notification Settings page, recipient management, per-category subscriptions
