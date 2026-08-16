# KNOWN BUGS & ACCEPTED RISKS

Source: `SECURITY_AUDIT_PHASE_B.md` (2026-05-26), `PRODUCTION_DEPLOY_CHECKLIST.md` (2026-05-26), session observations.
Status labels: **Open**, **Accepted risk**, **Deferred**, **Production blocker**.


---

## Unverified — Needs Investigation

### Possible transient re-render on the office dashboard immediately after login
**File:** `hmh-frontend/src/pages/DashboardPage.tsx` (unconfirmed — not touched or diagnosed this session)
**Status:** Unverified — observed once, not chased down
**Impact:** While adding a Playwright test that clicked a link in `AppTopbar` immediately after a fresh OWNER login on `/`, the click intermittently failed with "element was detached from the DOM, retrying" for the full 30s timeout — consistent with the header (and likely its `AppLayout` parent) unmounting/remounting one or more times shortly after the dashboard first renders. Asserting the element's `toBeVisible()` immediately after render was reliable; a second assertion a tick later was not. Root cause not investigated (unrelated to the AppTopbar/routing changes made in this session — no data-fetching code on that page was touched).
**Fix:** Reproduce deliberately (e.g. record a video of a fresh `/` login under Playwright trace) and check `DashboardPage.tsx` / its child widgets for an effect with a missing or unstable dependency causing an extra fetch-driven re-render cycle right after mount.

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
**Status:** Partially mitigated (2026-08-03) for Fuel evidence and generic attachments; still open for other uploads.
**Impact:** Files uploaded to `UPLOAD_DIR` are stored on Render's ephemeral disk and are lost on every deploy or restart.
**Fix:** Set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Render env vars to enable Supabase Storage. `app/core/storage.py` handles the routing automatically once configured. As of 2026-08-03, `Settings.validate_production_storage` makes this a hard **startup failure** outside development/test for the private-bucket path (see next entry) — the app will no longer silently start without it and later lose Fuel evidence.

### Private evidence bucket must be manually created before production deploy
**File:** `app/core/storage.py`, `app/core/config.py` (`SUPABASE_PRIVATE_BUCKET`, default `hmh-evidence-private`)
**Status:** Open — production blocker
**Impact:** Fuel evidence and generic `/attachments/upload` records now route to a **private** Supabase bucket, separate from the existing public `hmh-uploads` bucket, so evidence is never reachable except via a short-lived signed URL through `GET /attachments/{id}/download`. This bucket does not exist by default and must be created in the Supabase Dashboard (Storage → New Bucket → public: **false**, name matching `SUPABASE_PRIVATE_BUCKET`) before `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are set in production — the app will refuse to start in production without those two vars, and evidence uploads will fail closed (503, no fuel issue recorded, no stock reduced) if the bucket itself is missing or misconfigured as public.
**Fix:** Create the bucket, then confirm with `GET /admin/storage-status` (OWNER only) that `private_evidence_bucket.ok` is `true`. No Supabase dashboard access was available in the 2026-08-03 session to do this.

### [FIXED 2026-08-03] Three attachment entity types bypassed project isolation entirely
**File:** `app/api/v1/attachments.py:_entity_project_id()`
**Status:** Fixed — verified
**Impact:** `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, and `WEEKLY_PLAN` (all project-scoped, added in migration 0068) were missing from `_entity_project_id`'s resolution table and fell through to `return None`, which the caller treats as "not project-scoped, skip the check." Every attachment operation (list/upload/delete, and download once the private-storage work landed) against these three entity types was reachable by **any authenticated user, any role, regardless of project membership** — a genuine cross-project data exposure, unlike the STAGE_STATUS item below. Found by auditing every `AttachmentEntity` value against the resolver while investigating a separate, unrelated test failure.
**Fix:** Added resolution branches for all three (`MunicipalityProgressClaim.project_id`, `ProgrammeActivity.project_id`, `WeeklyPlan.project_id`). Also removed `BOQ_HEADER` from the function's stale "not project-scoped" comment — it was already correctly handled above that comment; the comment itself was simply wrong, not a functional bug.
**Verification:** New parametrized test `test_previously_unresolved_entity_types_now_enforce_project_isolation` (list/upload/delete, all three entity types) in `tests/test_attachments.py` — 48/48 passing. `tests/test_progress_claims.py` (38/38) and `tests/test_fuel_management.py` (29/29) re-run clean, no regression.

### [FIXED 2026-08-03] `test_stage_status_attachment_requires_project_access` used the wrong role for its "outsider" persona
**File:** `hmh-backend/tests/test_attachments.py`
**Status:** Fixed — was a test defect, not a code defect
**Impact:** The test asserted an `OFFICE_USER` with no explicit `UserProjectAccess` record should get 403/404 on a STAGE_STATUS attachment. `OFFICE_USER` is one of five office-level roles (`OWNER`, `OFFICE_ADMIN`, `OFFICE_USER`, `PROCUREMENT_LEAD`, `READ_ONLY`) that `check_project_access()` intentionally treats as company-wide — `_PROJECT_ACCESS_BYPASS` in `app/dependencies.py`, applied consistently to every project-scoped resource in the app (purchase orders, material requests, deliveries, payments, etc.), not something specific to attachments. Verified empirically: a `SITE_STAFF` outsider (a site-level role, which does require explicit project access) is correctly blocked with 403 against the exact same STAGE_STATUS record — `_entity_project_id`'s STAGE_STATUS resolution and `check_project_access` were both already correct.
**Fix:** Changed the test's outsider to `SITE_STAFF` with access to a *different* project only. No production code was changed for this item — changing `check_project_access` to require explicit access for office roles would have been inconsistent with the rest of the codebase and would have reversed an intentional design decision (office staff have company-wide visibility in this internal B2B tool).

### Five upload flows remain on the legacy public bucket
**Files:** `app/api/v1/deliveries.py` (delivery notes, receiver/driver signatures), `app/api/v1/stock.py` (usage evidence), `app/api/v1/stages.py` (milestone photo upload, two sites), `app/services/email_service.py` (generated MR/PO PDF auto-attach)
**Status:** Open — accepted for this pass, out of scope
**Impact:** These call `save_upload(..., private=False)` (the default) and remain publicly reachable via a permanent URL, same as before 2026-08-03. They write into the shared `attachments` table like Fuel evidence does, but were excluded from the 2026-08-03 privacy hardening because migrating them touches raw model columns (e.g. `Delivery.delivery_note_image_url`, `Delivery.signature_image_url`) and additional frontend rendering paths beyond the `Attachment`/`attachment_service` system that Fuel evidence uses exclusively.
**Fix:** A follow-up pass should either migrate these five call sites to `private=True` (requires updating the raw-column frontend rendering to go through `/attachments/{id}/download` too) or make an explicit, documented decision that these document types may remain public.

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

## Pre-existing Test Failures (register from 2026-07-21; re-audit needed)

The following tests fail in the full suite due to pre-existing model or business-rule drift. They are tracked here to distinguish them from implementation regressions.

| Test file | Count | Root cause |
|-----------|-------|-----------|
| `test_payments.py` | 11 | `Payment.payment_date NOT NULL` model drift — column added to DB but not to model constructor in tests |
| `test_procurement_pipeline.py::TestQuoteApprove` | 5 | Role permission and status assertion mismatch — quote approval requires updated role checks |
| `test_mr_pipeline_close.py` | 3 | Asserts `CLOSED` status but service uses `CONVERTED_TO_PO` |
| `test_e2e_procurement_pipeline.py` | 6 | Test ordering dependency — passes when run in isolation |
| `test_gmail_processing.py` | 1 | Email matching regex mismatch |

**Total pre-existing:** 26 failures. None caused by or related to Phase 6 (municipality claims, programme plan, weekly planning).

**2026-08-02 observation:** a new full run collected 873 tests and timed out after 900 seconds at 86%. It showed failures in the previously recorded procurement/payment groups plus AI/OCR, attachments, document AI, municipality invoice and procurement analytics tests. Because the run did not finish, an exact new baseline is not claimed. The new Fuel tests pass 14/14 and Fuel + progress/programme/weekly pass 51/51 in isolation; the expanded legacy failure list still needs a sharded CI re-audit.

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
- [ ] Apex/www frontend mapping: `hmhgroup.co.za` and `www.hmhgroup.co.za` returned HTTP 404 on 2026-08-02; only `app.hmhgroup.co.za` served the SPA
- [ ] `WHATSAPP_APP_SECRET` set in Render env vars
- [ ] `CRON_SECRET` set to a 32+ char random string in Render env vars
- [ ] `WHATSAPP_VERIFY_TOKEN` changed from default `"hmh_verify_token"`
- [ ] `SECRET_KEY` set to a 64+ char random string in Render env vars
- [ ] Supabase Storage configured (or Render Persistent Disk mounted) for file uploads
- [ ] Gmail polling automated (cron job added for `POST /api/v1/gmail/fetch`)

## Fuel targeted closure — remaining production verification

- [ ] Configure and perform a controlled real Fuel event email delivery; automated tests cover mock, failure logging and retry only.
- [ ] Validate camera capture/upload and installed-PWA behavior on the actual supported Android/iOS devices and constrained site networks.
- [ ] Configure tracker provider adapters only when a real vendor contract and credentials exist; the current adapter intentionally returns no external reading.
