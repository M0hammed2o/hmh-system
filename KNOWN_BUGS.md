# KNOWN BUGS & ACCEPTED RISKS

Source: `SECURITY_AUDIT_PHASE_B.md` (2026-05-26), `PRODUCTION_DEPLOY_CHECKLIST.md` (2026-05-26), session observations.
Status labels: **Open**, **Accepted risk**, **Deferred**, **Production blocker**.

---

## Security — Accepted Risks

### M7 — HMAC verification silently disabled when WHATSAPP_APP_SECRET is empty
**File:** `app/api/v1/whatsapp_webhook.py:38`
**Status:** Accepted risk (mitigation in place)
**Impact:** If `WHATSAPP_APP_SECRET` is not set in production, all webhook POSTs are accepted without HMAC signature verification. A spoofed payload could trigger notification state changes.
**Mitigation:** `main.py` startup warning logs this condition. WhatsApp API POST body is structurally validated before any DB write. Fix: set `WHATSAPP_APP_SECRET` in Render env vars.
**Action required:** Set `WHATSAPP_APP_SECRET` before production launch.

### M8 — Localhost origins in production CORS whitelist
**File:** `main.py:129`
**Status:** Accepted risk
**Impact:** `localhost:3000` and `localhost:5173` are hardcoded in `_required_origins`. A browser on the same machine as the production server could make credentialed requests.
**Mitigation:** Render deployment does not expose localhost; TLS-only in production. No action needed for current deployment model.

### L2 — Error response reveals account role for READ_ONLY users
**File:** `app/dependencies.py:125`
**Status:** Accepted risk
**Impact:** 403 response body says "Owner account is read-only" — reveals the user's role type to an attacker who can observe the response.
**Mitigation:** Internal B2B tool; users know their own roles. No action needed.

### L3 — Admin demo-wipe endpoint has no confirmation step
**File:** `app/api/v1/admin.py:32`
**Status:** Deferred
**Impact:** `POST /admin/clear-demo-data` is behind `OWNER_ONLY` but a single mistaken click wipes all demo data with no confirmation.
**Fix:** Add `?confirm=true` query parameter requirement before production launch.

---

## Code Quality — Deferred

### L1 — Duplicate `_phone_variants()` function
**Files:** `app/services/notification_service.py:361`, `app/api/v1/whatsapp_webhook.py:71`
**Status:** Deferred (low risk)
**Impact:** Two identical implementations. If phone normalisation logic needs changing, both files must be updated.
**Fix:** Extract to `app/utils/phone.py` and import from both locations.

---

## Infrastructure / Operational

### No automated Gmail inbox polling
**File:** `app/api/v1/gmail.py` (fetch is manual only)
**Status:** Open
**Impact:** Inbound procurement emails (supplier quotes, invoices) are not automatically ingested. Office staff must manually click "Fetch" to pull new emails.
**Fix:** Add a Render cron job calling `POST /api/v1/gmail/fetch` every 10 minutes, or add an in-process background polling task in `main.py`. See `PRODUCTION_DEPLOY_CHECKLIST.md §7`.

### Render filesystem is ephemeral — uploaded files lost on redeploy
**Status:** Open (production blocker if Supabase not configured)
**Impact:** Files uploaded to `UPLOAD_DIR` are stored on Render's ephemeral disk and are lost on every deploy or restart.
**Fix:** Set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Render env vars to enable Supabase Storage. `app/core/storage.py` handles the routing automatically once configured.

---

## Integration Gaps — Verified by Code Inspection (2026-07-12)

### Stage transitions do not write AuditEvent — activity feed always empty
**Files:** `app/services/stage_service.py:upsert_stage_status()`, `app/api/v1/stages.py:complete_milestone()`
**Status:** Open
**Impact:** `GET /projects/{id}/stage-statuses/{status_id}/activity` reads AuditEvent rows scoped to the stage status ID, but no stage service or API route calls `audit_service.write_event()` for stage status changes. The activity tab on the Milestones page shows no history for any stage transition, block, unblock, progress update, or completion. Evidence is available only via attached photos (Attachment table). This is a real operational gap — office cannot review who completed what stage and when.
**Fix:** Call `audit_service.write_event(db, AuditAction.UPDATE, "project_stage_status", actor_id, pss.id, before_value=..., after_value=...)` at the end of `upsert_stage_status()` and `complete_milestone()` before the final commit. This is a backend-only change, no migration required.

### Workshop financial pipeline is isolated from project cost summary
**Files:** `app/models/workshop.py` (WorkshopInvoice, WorkshopPurchaseOrder), `app/api/v1/cost_summary.py`
**Status:** Open
**Impact:** WorkshopInvoice and WorkshopPurchaseOrder are separate models with no FK to the main Invoice or Payment tables. Workshop procurement spend does NOT appear in `procurement_spend` in the project cost summary. Only `VehicleCost.amount` (when project_id is set) appears as `vehicle_repair_cost`. If a workshop PO goes through its full lifecycle, the final invoice amount is invisible to financial reporting.
**Fix:** Either: (a) add WorkshopInvoice to cost_summary._build_summary() as a separate line item, or (b) create a Payment record from the final WorkshopInvoice (linking to the project via Vehicle.assigned_project_id). Option (a) is the smallest safe change.

### Cost summary BOQ budget query does not filter by active BOQ version
**File:** `app/api/v1/cost_summary.py:32`
**Status:** Open
**Impact:** `boq_budget` sums ALL `BOQItem.rate * BOQItem.quantity` for the project, across all BOQ headers including draft, inactive, and historical versions. If a project has multiple BOQ versions, the budget is double-counted. **The correct query should filter to `BOQItem rows where BOQHeader.is_active_version=True`.**
**Fix:** Join BOQItem → BOQSection → BOQHeader and add `BOQHeader.is_active_version == True` filter.

### WorkshopStock uses mutable quantity_on_hand — no audit trail
**File:** `app/models/workshop.py:WorkshopStock`
**Status:** Open
**Impact:** Workshop stock balance is stored as a mutable `quantity_on_hand` float. Unlike the main project StockLedger (append-only), there is no history of workshop stock movements. It is impossible to audit what was received, issued, or adjusted.
**Fix:** Either: (a) add a workshop stock ledger table, or (b) accept the limitation and document it. This is a significant audit gap but low operational risk for current usage.

### Municipality invoices and expenses excluded from project cost summary
**Files:** `app/models/municipality_invoice.py`, `app/models/audit.py` (expenses), `app/api/v1/cost_summary.py`
**Status:** Open
**Impact:** Municipality invoices and general expenses are not included in the project cost summary's total_actual. If these exist for a project, the cost summary understates actual spend.
**Fix:** Add queries for `MunicipalityInvoice` and `Expense` totals in `_build_summary()`.

---

## Pre-existing Test Failures (as of 2026-07-21, not caused by Phase 6)

The following tests fail in the full suite due to pre-existing model or business-rule drift. They are tracked here to distinguish them from implementation regressions.

| Test file | Count | Root cause |
|-----------|-------|-----------|
| `test_payments.py` | 11 | `Payment.payment_date NOT NULL` model drift — column added to DB but not to model constructor in tests |
| `test_procurement_pipeline.py::TestQuoteApprove` | 5 | Role permission and status assertion mismatch — quote approval requires updated role checks |
| `test_mr_pipeline_close.py` | 3 | Asserts `CLOSED` status but service uses `CONVERTED_TO_PO` |
| `test_e2e_procurement_pipeline.py` | 6 | Test ordering dependency — passes when run in isolation |
| `test_gmail_processing.py` | 1 | Email matching regex mismatch |

**Total pre-existing:** 26 failures. None caused by or related to Phase 6 (municipality claims, programme plan, weekly planning).

### No project-level progress percentage — only manual lot/stage fields
**Files:** `app/models/project.py`, `app/models/lot.py`, `app/models/stage.py`
**Status:** Open (design gap)
**Impact:** `Project` has no `progress_pct` field. `Lot.status` is manually set (AVAILABLE/IN_PROGRESS/COMPLETED/ON_HOLD). `ProjectStageStatus.progress_pct` is manually set per stage. There is no automatic calculation of overall project progress from milestone completions. The owner/dashboard sees lot counts but no meaningful % complete.
**Fix:** Compute dynamically in the project detail response: completed_stages / total_stages. Can be added to project_service as a computed property with no migration.

### Subcontractor work (WorkDone) bypasses the Invoice → Payment chain
**File:** `app/services/work_done_service.py:mark_paid()`
**Status:** Open
**Impact:** `mark_paid()` creates a `Payment` record directly (PaymentType.LABOUR) without creating an Invoice first. This bypasses the standard invoice approval workflow and reconciliation. Subcontractor payments appear in cost_summary.procurement_spend (because Payment table is queried) but are not visible in the invoice list or reconciliation page.
**Fix:** Either: (a) create an Invoice first and link the Payment to it, or (b) add WorkDone payments as a separate line in the reconciliation view.

---

## Test Coverage Gaps

### Warehouse transfer approval flow — no automated tests
**Status:** Open
**Impact:** The 3-vote approval, auto-execution, OWNER override, and rejection paths for warehouse transfers have no integration tests. Changes to `warehouse_transfer_service.py` can silently break these flows.
**Fix:** Add `tests/test_warehouse_transfer_flow.py` covering: submit, vote-to-execute, override, reject, insufficient-stock guard.

### Payment due scan — no automated tests
**Status:** Open
**Impact:** `payment_due_service.scan_payment_due()` has no test coverage. The 7-day window, 23h deduplication, and OVERDUE_PAYMENT trigger are unverified by automated tests.
**Fix:** Add `tests/test_payment_due_scan.py` covering: warning fired within window, overdue fired past due_date, deduplication suppresses second alert within 23h.

---

## Production Launch Blockers (from deploy checklist)

These items from `PRODUCTION_DEPLOY_CHECKLIST.md` are unverified for the current production deployment:
- [ ] `WHATSAPP_APP_SECRET` set in Render env vars
- [ ] `CRON_SECRET` set to a 32+ char random string in Render env vars
- [ ] `WHATSAPP_VERIFY_TOKEN` changed from default `"hmh_verify_token"`
- [ ] `SECRET_KEY` set to a 64+ char random string in Render env vars
- [ ] Supabase Storage configured (or Render Persistent Disk mounted) for file uploads
- [ ] Gmail polling automated (cron job added for `POST /api/v1/gmail/fetch`)
