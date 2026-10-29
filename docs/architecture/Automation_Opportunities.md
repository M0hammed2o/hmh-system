# Automation Opportunities

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only.

This document identifies every manual action in the HMH Construction OS that should eventually become automatic, ranked by business impact.

---

## Priority Scale

| Priority | Criteria |
|----------|---------|
| **P0 — Immediate** | Data correctness or safety risk today; should be automated before production user load |
| **P1 — High** | Daily manual repetition; directly delays procurement, finance, or operations |
| **P2 — Medium** | Weekly or event-driven manual work; reduces efficiency |
| **P3 — Low** | Monthly or infrequent; quality of life improvement |

---

## P0 — Immediate (Data Correctness Risk)

### AUT-001 — Auto-Refresh Stock Balances After Every Mutation

**Current:** `stock_balances` materialized view must be manually refreshed via `POST /stock/refresh-balances` after deliveries or adjustments.  
**Should be:** Automatically refreshed after every stock mutation.  
**How to implement:** PostgreSQL trigger on `stock_ledger` INSERT → NOTIFY channel → background worker calls `REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances`. Alternatively, replace the materialized view with a regular view or a database-computed query and cache at the application layer.  
**Risk if not fixed:** Stock decisions are made on stale data. Transfers, issuances, and ordering decisions could be wrong.  
**Estimated size:** Small (1–2 days)

### AUT-002 — Auto-Update Invoice Status When Fully Paid

**Current:** `invoices.status` does not automatically transition to PAID when a payment is recorded that covers the full invoice amount.  
**Should be:** When `SUM(payments.amount_paid) >= invoice.total_amount`, set `invoice.status = PAID`.  
**How to implement:** In `payment_service.py`, after creating a payment, check if the sum of all payments for the invoice covers the total, and update invoice status.  
**Risk if not fixed:** Invoices appear perpetually unpaid even after payment. Overdue alerts fire unnecessarily. Proof packs are incorrect.  
**Estimated size:** Small (half-day)

---

## P1 — High (Daily Manual Repetition)

### AUT-003 — Scheduled Gmail Inbox Polling

**Current:** An operator must manually call `POST /gmail/fetch` to pull new supplier emails from Gmail.  
**Should be:** Gmail inbox polled automatically every 15 minutes (or via Gmail push notification).  
**How to implement:**  
- Option A: Add `POST /api/v1/internal/poll-gmail` cron endpoint alongside the existing notification cron. Schedule at 15-minute intervals via Render Cron or Windows Task Scheduler.  
- Option B (better): Gmail Push Notifications via Google Pub/Sub. Google pushes a notification to a webhook endpoint when new email arrives. This eliminates polling entirely.  
**Business value:** Reduces supplier quote response time from "hours after someone checks" to "minutes after email arrives."  
**Estimated size:** Small for cron (half-day); Medium for Pub/Sub (2–3 days)

### AUT-004 — Auto-Process High-Confidence Email Attachments

**Current:** After fetch, an operator must click "process" on each email individually.  
**Should be:** When an email is fetched from a known supplier (email domain or name matched), auto-run the OCR pipeline and auto-classify the attachment. Create a draft MRQuote or draft Invoice awaiting human confirmation. Only interrupt the user for low-confidence cases.  
**How to implement:** In the Gmail fetch flow, after storing the IncomingEmail record, for each attachment whose `linked_supplier_id` is not NULL, automatically invoke `process_incoming_email()` in a background task. Surface results as "awaiting review" rather than requiring a button click to trigger OCR.  
**Business value:** Eliminates 2-click-per-email manual overhead. A busy procurement period (5–10 emails/day) is currently 10–20 manual operations.  
**Estimated size:** Medium (2–3 days)

### AUT-005 — Scheduled Proactive Alert Scan

**Current:** `POST /alerts/scan` must be manually triggered. Six checks run: low stock, overdue invoices, payment due, stale MRs, deliveries without PO, missing signatures.  
**Should be:** Run automatically every hour (or on a schedule).  
**How to implement:** Add `POST /api/v1/internal/scan-alerts` internal cron endpoint (similar to the existing `scan-payment-due`). Schedule via cron. The existing `scan_payment_due` already runs on a cron — extend it or add a separate endpoint.  
**Business value:** The difference between a blind system and a proactive system. Alerts about stockouts or overdue invoices must fire without someone remembering to run a scan.  
**Estimated size:** Tiny (2–4 hours — infrastructure already exists)

### AUT-006 — Auto-Create Alert on Milestone Completion

**Current:** Completing a stage milestone creates no notification to any stakeholder.  
**Should be:** When `project_stage_status.status → COMPLETED`, automatically:
1. Create a SystemAlert (type: MILESTONE_COMPLETED)
2. Enqueue WhatsApp notification to SITE_MANAGER and OFFICE_ADMIN recipients
3. Write audit event with action MILESTONE_COMPLETED  
**How to implement:** In the stage complete route (`POST /stage-statuses/{id}/complete`), add a call to `enqueue_direct()` after the DB commit.  
**Business value:** Project managers know in real time when work is progressing. Clients can be informed. Cascaded follow-up actions can begin.  
**Estimated size:** Tiny (2–4 hours)

### AUT-007 — Auto-Update Lot Status When All Stages Complete

**Current:** `lots.status` is never automatically set to COMPLETED, even when all stage milestones for that lot are complete.  
**Should be:** After any stage status update, check if all stages for the lot are COMPLETED; if so, set `lots.status = COMPLETED` and create a LOT_COMPLETED alert.  
**How to implement:** Add a helper function `maybe_complete_lot(db, lot_id)` called after every stage status change. Query `COUNT(*) WHERE status != COMPLETED` for the lot. If 0, update lot status.  
**Estimated size:** Small (half-day)

### AUT-008 — Auto-Attempt Invoice Match When All Documents Exist

**Current:** Invoice matching requires explicit operator action: `PATCH /invoices/{id}/match`.  
**Should be:** When an invoice is created (or a delivery is received), automatically attempt matching if a PO and delivery exist for the same supplier+project. Create a draft match result for human review.  
**How to implement:** In the invoice creation service and delivery creation service, after saving, call a `try_auto_match(db, invoice_id)` function that queries for linked PO and delivery.  
**Estimated size:** Small (1 day)

---

## P2 — Medium (Weekly or Event-Driven)

### AUT-009 — Auto-Reconciliation Creation

**Current:** Procurement reconciliation must be manually created for every invoice.  
**Should be:** When an invoice reaches APPROVED_FOR_PAYMENT and a PO + delivery exists, automatically create a `ProcurementReconciliation` record in PENDING status.  
**Estimated size:** Small (half-day)

### AUT-010 — Auto-Mark PO as Overdue for Delivery

**Current:** No alert exists for POs where `expected_delivery_date` has passed and no delivery has been received.  
**Should be:** Add a check to the scheduled alert scan: POs with `expected_delivery_date < today` and no linked delivery → create a PO_DELIVERY_OVERDUE alert.  
**Estimated size:** Small (half-day)

### AUT-011 — Auto-Calculate and Persist Lot and Project Progress

**Current:** `lots.progress_pct` and project progress are computed on every API request.  
**Should be:** Maintain denormalized `progress_pct` on `lots` and `projects` tables, updated after every stage status change.  
**How to implement:** After any `project_stage_status` update, recalculate `lots.progress_pct = completed_stages / total_stages * 100`. After any lot progress change, recalculate `projects.progress_pct = AVG(lots.progress_pct)`.  
**Estimated size:** Small (1 day)

### AUT-012 — Auto-Write Supplier Performance Score

**Current:** `suppliers.performance_score` column exists but is never written.  
**Should be:** Nightly scheduled job computes performance score from procurement_analytics and writes it to `suppliers.performance_score`.  
**How to implement:** Add an internal cron endpoint that calls `get_supplier_performance(supplier_id)` for all suppliers and updates the column.  
**Estimated size:** Small (half-day)

### AUT-013 — Auto-Create Daily Summary Email (Not Just WhatsApp)

**Current:** Daily summary is sent via WhatsApp only.  
**Should be:** Also send a daily HTML email digest to all OFFICE_ADMIN and OWNER users, summarizing:
- Completed milestones today
- Deliveries received today
- Invoices due this week
- Active alerts by severity
- Spend today vs weekly burn rate  
**Estimated size:** Medium (1–2 days)

### AUT-014 — Auto-Supplier Reminder When PO Is Sent But No Quote Received

**Current:** After MR email is sent to suppliers, there is no follow-up if no quote arrives within the needed-by window.  
**Should be:** If `material_request.needed_by_date - today < PENDING_MR_DAYS` and no MRQuote exists for that supplier, automatically send a reminder email.  
**Estimated size:** Medium (2 days)

### AUT-015 — Auto-Archive Processed Gmail Emails

**Current:** Processed emails remain in the inbox indefinitely.  
**Should be:** After processing, mark as READ (or move to a processed label/folder) in Gmail.  
**How to implement:** After `process_incoming_email()` completes with a PROCESSED status, call Gmail IMAP to mark the message as seen or add a label.  
**Estimated size:** Small (half-day)

### AUT-016 — Fuel Anomaly Detection

**Current:** Fuel logs are recorded manually. No anomaly detection exists.  
**Should be:** After a fuel log is recorded, compare litres vs expected consumption (based on odometer delta × average fuel per km). If variance > threshold (e.g., 20%), create a FUEL_ANOMALY alert.  
**How to implement:** Add check in fuel_log creation: fetch last two odometer readings, compute expected fuel, compare to `fuel_log.litres`.  
**Estimated size:** Small (half-day, once the comparison logic is defined)

### AUT-017 — Vehicle Maintenance Reminder

**Current:** No vehicle service interval tracking exists.  
**Should be:** When a vehicle's odometer reading (tracked in `fuel_logs.odometer_reading` and the new `vehicles.current_hours_reading`) crosses a service interval (e.g., every 5,000 km or 250 hours), create a VEHICLE_MAINTENANCE_DUE alert.  
**How to implement:** Add a `service_interval_km` and `last_service_odometer` field to vehicles. After any fuel log recording odometer, check if `odometer - last_service_odometer >= service_interval_km`.  
**Estimated size:** Small (1 day)

### AUT-018 — Auto-BOQ Variance Alert on Usage

**Current:** BOQ variance alerts only fire during a manual scan.  
**Should be:** When a usage log is created with `over_boq=True`, immediately create a BOQ_VARIANCE alert.  
**How to implement:** In the usage creation endpoint, after the usage is saved, check `over_boq` flag and call `enqueue_direct()` if true.  
**Estimated size:** Tiny (2–4 hours — pattern already exists)

### AUT-019 — Auto-Link Workshop Costs to Cost Summary

**Current:** Workshop spend is invisible to `GET /projects/{pid}/cost-summary`.  
**Should be:** Workshop invoices and PO totals should be included in the cost summary as a new "workshop" cost category.  
**How to implement:** Modify `cost_summary_service.py` to include a query against `workshop_invoices` grouped by project. Requires workshop models to have a `project_id` FK (verify if this exists or needs to be added).  
**Estimated size:** Medium (1–2 days)

### AUT-020 — Auto-Link Expense Records to Cost Summary

**Current:** Approved expenses are invisible to the cost summary.  
**Should be:** Add an "expenses" cost category to the cost summary.  
**How to implement:** Modify `cost_summary_service.py` to include `SUM(expense_records.amount) WHERE status IN (APPROVED, PAID) AND project_id = ?`.  
**Estimated size:** Small (half-day)

---

## P3 — Low (Quality of Life)

### AUT-021 — Auto-Generate Proof Pack When Invoice Is Approved for Payment

**Current:** Proof packs must be manually requested per invoice.  
**Should be:** When `POST /invoices/{id}/approve-payment` is called, automatically generate and store the proof pack as an attachment.  
**Estimated size:** Small (half-day)

### AUT-022 — Auto-Archive Old Alerts

**Current:** Alerts accumulate indefinitely in OPEN or RESOLVED status.  
**Should be:** Alerts older than 90 days with RESOLVED status should be soft-archived (added `is_archived` flag or moved to an archive table).  
**Estimated size:** Small (half-day)

### AUT-023 — Weekly Project Summary to Project Managers

**Current:** Daily summary exists for WhatsApp; no weekly summary exists.  
**Should be:** Every Monday morning, generate a weekly summary for each active project and send to the project-scoped WhatsApp recipients.  
**Estimated size:** Small (1 day)

### AUT-024 — OCR Auto-Classification Improvement with Feedback Loop

**Current:** OCR classifies attachments based on filename and content keywords. No learning from corrections.  
**Should be:** Track when a user overrides the AI classification (e.g., classified as QUOTE but corrected to INVOICE). Store correction data. Use it to improve classification rules or provide feedback to AI model fine-tuning.  
**Estimated size:** Medium (2–3 days for feedback tracking; AI fine-tuning is separate)

### AUT-025 — Auto-Update PO Received Quantities from Deliveries

**Current:** `purchase_order_items.quantity_received` is not automatically updated when a delivery is received.  
**Should be:** When a delivery item is created with a `purchase_order_item_id`, update `PurchaseOrderItem.quantity_received += delivery_item.quantity_accepted`.  
**Estimated size:** Small (half-day)

---

## Automation Architecture Recommendation

As the system grows, individual service-level hooks will become difficult to maintain. The recommended long-term pattern is an **event bus**:

```
Business operation → emit domain event → event bus → async consumers

Example:
stage_service.complete_stage() 
  → emit StageCompleted(stage_id, lot_id, project_id, actor_id)
  → event bus
  → Consumer A: update_lot_progress()
  → Consumer B: create_milestone_alert()
  → Consumer C: write_audit_event()
  → Consumer D: check_project_completion()
  → Consumer E: trigger_timeline_update() (future)
```

**Why this matters for future AI readiness:** An event bus creates a structured stream of business events that can be consumed by:
- A predictive analytics engine
- A chatbot that answers "what's happening on project X?"
- An anomaly detection model
- A reporting engine

The current pattern (imperative calls inside route handlers) makes adding new consumers require touching existing code. An event bus decouples producers from consumers.

**Short-term option (without a full event bus):** Use Python's `asyncio.gather()` to run side-effect tasks (audit write, alert creation, progress update) concurrently after the main DB commit. Each task is wrapped in a try/except so a notification failure cannot roll back the business operation. This is structurally similar to what `notification_service.enqueue_direct()` already does with `db.begin_nested()`.
