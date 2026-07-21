# CHANGELOG — HMH Construction OS
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
