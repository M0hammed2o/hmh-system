# WORKLOG — append-only, newest first
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
