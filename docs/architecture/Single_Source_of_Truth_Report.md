# Single Source of Truth Report

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only.

This document identifies the canonical owner of every major business concept in the HMH Construction OS. Where multiple modules own the same concept, it identifies the conflict, recommends one canonical owner, and explains how other modules should reference it.

---

## Confidence Labels

- `Verified:` — confirmed by direct code inspection
- `Likely:` — strong inference from model structure
- `Requires business decision` — no technically correct answer; depends on company policy
- `Unknown` — insufficient evidence to determine

---

## 1. Project Budget

**Current state: CONFLICTED**

The project budget is derived from multiple sources that can disagree:

| Source | Location | What it represents |
|--------|----------|--------------------|
| BOQ planned total | `SUM(boq_items.planned_total)` where `is_active_version=True` | Planned cost at BOQ creation |
| Procurement actual | `SUM(payments.amount_paid)` for project | Money actually paid to suppliers |
| Cost summary | `GET /projects/{pid}/cost-summary` | Aggregate of 6 different cost types |

**Conflict:** The BOQ is the "planned budget" but it does not constrain procurement. An MR can be created as `over_boq=True` and will still flow through to PO/payment. There is no hard budget ceiling.

**Recommendation:** `Canonical source: BOQ (active version)` for planned budget. `Actual spend: cost-summary endpoint` which aggregates all cost types. These are two different concepts (plan vs actual) and should be clearly separated in the UI.

**Missing:** No `budget_ceiling` field on `projects` separate from the BOQ. The BOQ can change (new versions) and the relationship between "approved budget" and "active BOQ" is not explicit.

---

## 2. Actual Project Cost (Spend to Date)

**Current state: FRAGMENTED**

The cost summary endpoint (`GET /projects/{pid}/cost-summary`) attempts to aggregate actual costs but is incomplete:

| Cost type | Included in cost-summary? | Source |
|-----------|--------------------------|--------|
| Procurement (materials) | YES | `payments.amount_paid` |
| Labour (job cards) | YES | `job_cards.total_amount` WHERE status IN (OWNER_APPROVED, PAYMENT_APPROVED, PAID) |
| Subcontractor work done | YES | `subcontractor_work_done.amount` WHERE status IN (SITE_APPROVED, OFFICE_APPROVED, PAID) |
| Fuel | YES | `SUM(fuel_logs.total_cost)` |
| Vehicle repairs | YES | `SUM(vehicle_costs.amount)` |
| Extra/breakage items | YES | MR items with `extra_reason_type` set |
| Workshop spend | **NO** | Not included |
| Expenses | **NO** | Not included |
| Municipality invoices (income) | **NO** | Not included |

**Canonical owner recommendation:** The cost-summary endpoint should be the single source of actual project cost, but it must be extended to include workshop spend and expenses before it can serve that role.

**Risk:** The current cost summary understates true project cost by an unknown amount (workshop + expenses).

---

## 3. Lot Progress Percentage

**Current state: NOT PERSISTED — computed on-the-fly only**

- `Verified:` The `lots` table has no `progress_pct` column
- `Verified:` `GET /lots/{lot_id}/progress` computes progress by counting completed/total stage statuses for that lot
- `Verified:` The dashboard's `lots_completed` count uses a different query (counting lots with all stages COMPLETED vs the progress_pct calculation)

**Conflict:** The dashboard may disagree with the lot-level progress endpoint because they use different counting logic.

**Canonical owner recommendation:** Add a denormalized `progress_pct` column to the `lots` table, updated by a trigger or hook whenever `project_stage_status` changes for a lot. All other sources should read from this column. This eliminates inconsistency and enables efficient filtering.

---

## 4. Project Progress Percentage

**Current state: NOT PERSISTED — derived from lot data**

- `Verified:` The `projects` table has no `progress_pct` column
- `Likely:` Project-level progress is derived from the average (or weighted average) of lot progress percentages
- Dashboard `operations.progress_pct` is the closest thing to a canonical source

**Conflict:** Different endpoints may compute project progress differently.

**Canonical owner recommendation:** Add `progress_pct` to the `projects` table. Update it whenever any child lot's progress changes.

---

## 5. Stock Balance

**Current state: CONFLICTED (materialized view vs live ledger)**

| Source | Location | Freshness |
|--------|----------|-----------|
| Materialized view | `stock_balances` | Stale — only refreshed on delivery or manual call |
| Live ledger | `SELECT SUM(quantity_in) - SUM(quantity_out) FROM stock_ledger` | Always current |

- `Verified:` `GET /stock/balances` reads from the materialized view
- `Verified:` Warehouse endpoints (`GET /sites/{id}/warehouse/`) use raw SQL against `stock_ledger` directly
- `Verified:` The site warehouse route uses raw SQL while the global balance route uses the materialized view

**Conflict:** Two different users querying stock at the same time may see different balances if the materialized view is stale.

**Canonical owner recommendation:** The `stock_ledger` table is the canonical source (append-only, immutable entries). The `stock_balances` materialized view is a performance optimization only and must be clearly documented as such. Refresh it automatically after every stock mutation (delivery receipt, usage log, adjustment, transfer).

---

## 6. Supplier Outstanding Balance

**Current state: COMPUTED ON-THE-FLY — no persisted balance**

Supplier outstanding balance is derived at query time by joining `purchase_orders`, `invoices`, and `payments`. It appears in:
- `GET /suppliers/{id}/outstanding` — PO vs invoiced vs paid vs outstanding vs overdue
- `GET /payments/outstanding-summary` — outstanding per supplier
- Payment aging report

**No conflict** — there is only one computation path and it is correct. The risk is **performance at scale**: every outstanding balance query does a full join across all POs, invoices, and payments for the supplier.

**Recommendation:** For up to ~10,000 records, on-the-fly is acceptable. At scale (hundreds of suppliers, thousands of records), introduce a `supplier_balances` materialized view or a periodic balance snapshot.

**Important:** Supplier outstanding balance does NOT include job card payments or work-done payments, because those are not in the `payments` table. The balance understates what HMH owes to suppliers who also do subcontractor work.

---

## 7. Material Usage for a Lot

**Current state: FRAGMENTED**

Material consumed against a lot appears in:

| Source | Table | What it tracks |
|--------|-------|---------------|
| Site dashboard material summary | `stock_ledger` (TRANSFER_IN) | Materials transferred to lot from site warehouse |
| Usage logs | `usage_logs` | Materials explicitly "used" on lot |
| Stock balances | `stock_balances` (materialized) | Net balance at lot level |
| BOQ allocation | `boq_items` | Planned quantity for lot |

**Conflict:** The site dashboard (`/site-dashboard/material-summary`) and the warehouse summary (`/projects/{pid}/warehouse/boq-summary`) compute "delivered to lot" differently. The site dashboard counts `TRANSFER_IN` movements; the warehouse summary queries `stock_ledger` with different conditions.

**Canonical owner recommendation:** `stock_ledger` is the canonical source for all material movement. All "delivered," "used," and "balance" calculations should derive from `stock_ledger` with consistent filters. The materialized view should be enhanced to include pre-computed delivered/used/balance per lot/item.

---

## 8. Invoice Match Status

**Current state: SINGLE SOURCE — good**

`Verified:` `invoice_matching_results` is the canonical store for PO-vs-invoice-vs-delivery match status. Only one record exists per invoice (CASCADE on invoice delete). The `match_status` enum (MATCH/MISMATCH/PARTIAL) is clear.

**No conflict.** The proof pack endpoint reads from this table correctly.

**Gap:** Match results are only created when a user explicitly calls `PATCH /invoices/{id}/match`. There is no automatic match attempt when all three documents (PO + invoice + delivery) exist.

---

## 9. Supplier Performance Score

**Current state: CONFLICTED — column exists, computation does not**

- `Verified:` `suppliers.performance_score` column exists (Float, nullable)
- `Verified:` The procurement analytics endpoint (`GET /procurement-analytics/supplier-performance/{id}`) computes a score from (on-time delivery %, invoice match %, price variance %)
- `Verified:` No code was found that writes the computed score back to `suppliers.performance_score`

**Conflict:** The `performance_score` column is never updated. The analytics endpoint computes a fresh score every request. If any code reads `suppliers.performance_score` expecting a meaningful value, it will get NULL for all suppliers.

**Canonical owner recommendation:** Either (a) remove `suppliers.performance_score` and always use the analytics endpoint, or (b) add a scheduled job that writes the analytics-computed score back to the column nightly.

---

## 10. Payment Status (Has This Invoice Been Paid?)

**Current state: INFERRED — no explicit PAID status on invoice**

The `invoices` table has a `status` field (RecordStatus enum), but "PAID" is determined by checking whether a payment record exists for the invoice:
- `invoice.status` can be APPROVED_FOR_PAYMENT but there is no PAID status in the enum for invoices specifically
- Payment records link to invoices via `payments.invoice_id`
- Partially paid invoices have no explicit tracking — it must be inferred from `SUM(payments.amount_paid) < invoice.total_amount`

**Recommendation:** Add `PAID` and `PARTIALLY_PAID` statuses to the invoice status enum. Update invoice status automatically when a payment is recorded.

---

## 11. Notification Status

**Current state: DUAL TRACKING — aligned**

Two tables track notification state:
1. `system_alerts.status` (OPEN/ACKNOWLEDGED/RESOLVED) — business-level alert state
2. `notification_queue.status` (PENDING/SENT/FAILED/ACKNOWLEDGED) — delivery-level state

These are aligned: when `notification_queue.status → ACKNOWLEDGED`, the parent `system_alerts.status → ACKNOWLEDGED`. This is the correct design — they track different things (message delivery vs alert resolution).

**No conflict.**

---

## 12. Project Timeline

**Current state: DOES NOT EXIST**

There is no timeline or schedule module. The only time-based data in the system is:
- `projects.start_date`, `projects.end_date` — planned dates only
- `project_stage_status.completed_at` — actual completion timestamp
- No planned completion date per stage
- No Gantt chart data

**Canonical owner recommendation:** The `project_stage_status` table is the natural home for both planned and actual stage dates. Add `planned_start`, `planned_end`, `actual_start`, `actual_end` to `project_stage_status`. A timeline module would read from this table.

---

## 13. Audit History

**Current state: SINGLE SOURCE — good but incomplete**

`Verified:` `audit_events` is append-only and is the authoritative audit trail. The `write_event()` function is called throughout the codebase.

**Gap:** Not all important actions write audit events. Identified gaps:
- Stage completion transition does not write a specific STAGE_COMPLETED audit event (the general `update` event is written but not the business-meaningful transition)
- WhatsApp ACK receipt does not create an audit event
- Notification send failures are not audited (only tracked in `notification_queue.error_message`)
- Workshop module actions may not write to the main audit log (workshop has its own parallel structure)

---

## 14. Cash Flow

**Current state: DOES NOT EXIST**

Cash flow (when money is expected in vs when money must go out) is not tracked anywhere. The system has:
- `invoices.due_date` — when a supplier must be paid
- `payments.payment_date` — when money actually went out
- Municipality invoices (potential income) — not linked to payment system

**Recommendation:** A cash flow module would derive projected outflows from `invoices.due_date` and `invoice.total_amount - SUM(payments)`, and projected inflows from municipality invoices and any client billing module. This is a **Missing Module** (see `Lifecycle_Gap_Analysis.md`).

---

## 15. Milestone Status

**Current state: SINGLE SOURCE — good design, insufficient propagation**

`Verified:` `project_stage_status` is the correct and sole owner of milestone status per lot. The `StageStatus` enum (PENDING, IN_PROGRESS, BLOCKED, COMPLETED, CERTIFIED) is clear and meaningful.

**Gap:** The status is not propagated upward. When a lot's last stage becomes COMPLETED, the lot itself has no `status` that reflects completion (the `LotStatus` enum does exist: PENDING, IN_PROGRESS, COMPLETED — but it is never automatically updated by stage completion).

**Recommendation:** When all stages for a lot are COMPLETED, automatically set `lots.status = COMPLETED`. When all lots for a site are COMPLETED, flag the site. This chain does not currently exist.

---

## Canonical Owner Summary

| Concept | Canonical Owner | Current Status |
|---------|----------------|----------------|
| Project budget (planned) | `boq_headers` (active version) | OK, but no budget ceiling |
| Actual project cost | `cost-summary` endpoint | INCOMPLETE — missing workshop + expenses |
| Lot progress % | `project_stage_status` (derived) | NOT PERSISTED — compute risk |
| Project progress % | Derived from lots | NOT PERSISTED — compute risk |
| Stock balance | `stock_ledger` (live) | CONFLICTED with materialized view |
| Supplier outstanding | Derived from payments | OK — performance risk at scale |
| Material usage per lot | `stock_ledger` (TRANSFER_IN / usage_logs) | FRAGMENTED — two different queries |
| Invoice match status | `invoice_matching_results` | OK |
| Supplier performance score | CONFLICTED — column vs analytics | BUG — column never written |
| Payment status on invoice | INFERRED — no PAID status | INCOMPLETE |
| Notification status | `system_alerts` + `notification_queue` | OK — correctly dual-tracked |
| Timeline / Schedule | DOES NOT EXIST | MISSING MODULE |
| Audit history | `audit_events` | OK — some gaps in coverage |
| Cash flow | DOES NOT EXIST | MISSING MODULE |
| Milestone status | `project_stage_status` | OK — propagation missing |
