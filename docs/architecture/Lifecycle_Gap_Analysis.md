# Lifecycle Gap Analysis

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only.

This document identifies every place in the HMH Construction OS where a business workflow breaks, information stops prematurely, information duplicates across modules, or manual effort substitutes for logic the system should perform automatically.

---

## Severity Scale

| Severity | Meaning |
|----------|---------|
| **CRITICAL** | Causes incorrect financial data, silent data loss, or blocks core workflows |
| **HIGH** | Requires significant manual duplicate work; creates meaningful risk |
| **MEDIUM** | Creates friction, inconsistency, or reporting blindspots |
| **LOW** | Cosmetic or minor improvement opportunity |

---

## Section 1 — Broken Business Cycles

The following are complete broken lifecycle chains where an event should propagate automatically but does not.

---

### GAP-001 — Milestone Completion Chain (CRITICAL)

```
Stage marked COMPLETED
       ↓
Lot progress_pct NOT updated in DB (computed on-the-fly only)
       ↓
Project progress NOT updated in DB (computed on-the-fly only)
       ↓
Dashboard "lots_completed" count stale until next full reload
       ↓
No notification to project manager or client
       ↓
No audit event for milestone completion (Verified: write_event is NOT called
   in stage complete route — audit is present for stage create/update but
   not for the COMPLETED transition specifically)
       ↓
BOQ stage variance NOT computed at completion
       ↓
Timeline NOT updated (Timeline module does not exist)
       ↓
No automatic trigger for the NEXT stage's material needs
```

**Impact:** A completed milestone is an isolated event with no downstream cascade. Project managers must manually check the dashboard to see progress. Clients receive no notification. The completed stage's financial reconciliation never happens automatically.

**Root cause:** The `project_stage_status` table stores `status` and `progress_pct` but neither `lots` nor `projects` tables have a persisted `progress_pct` field. All progress is derived on-the-fly. No event hook exists on stage status change.

---

### GAP-002 — BOQ Over-Budget Propagation (HIGH)

```
Usage recorded against lot/item
       ↓
Over-BOQ flag set on usage_log row (over_boq = True)
       ↓
Dashboard NOT updated with BOQ variance count
       ↓
No automatic alert created
       ↓
Alert scan (POST /alerts/scan) must be manually triggered
       ↓
When scan DOES run, alert created
       ↓
But no notification to PROCUREMENT_LEAD or project owner
       ↓
No restriction prevents further material from being issued
       ↓
Over-BOQ quantities continue accumulating silently
```

**Impact:** A project can significantly exceed its BOQ budget without anyone being automatically notified. The `BOQ_VARIANCE_ALERT_PCT` setting exists but is only checked during a manual scan.

---

### GAP-003 — Delivery → Stock → Usage Refresh Chain (CRITICAL)

```
Delivery received
       ↓
StockLedger RECEIPT entries created (CORRECT)
       ↓
stock_balances materialized view NOT refreshed
       ↓
GET /stock/balances returns STALE data
       ↓
Site warehouse shows old stock levels
       ↓
Operator transfers too much or too little
       ↓
Usage recorded against wrong stock level
       ↓
Manual POST /stock/refresh-balances required after EVERY delivery
```

**Impact:** Every delivery requires a separate manual API call to keep stock data accurate. If the call is missed, all downstream stock decisions are based on stale data. On a busy site with multiple deliveries per day, this is a high-frequency maintenance burden.

**Root cause:** PostgreSQL materialized views do not auto-refresh. A trigger or post-delivery hook is needed.

---

### GAP-004 — Payment Status Propagation (HIGH)

```
Invoice approved for payment
       ↓
Payment NOT automatically created (user must visit /payments to create)
       ↓
Supplier outstanding balance still shows invoice as unpaid
       ↓
Overdue invoice alert may fire even after approval
       ↓
No automatic payment reminder to accounts team
       ↓
Payment finally recorded (manually)
       ↓
Invoice status NOT automatically updated to PAID
       ↓
Proof pack still shows invoice as outstanding
       ↓
Reconciliation NOT triggered automatically
```

**Impact:** Invoice-approved records remain in a "limbo" state. The system knows an invoice should be paid but takes no action to advance the process.

---

### GAP-005 — Workshop Cost Invisibility (CRITICAL)

```
Workshop MR created and approved
       ↓
Workshop PO created and sent to supplier
       ↓
Workshop invoice received and uploaded
       ↓
Workshop stock updated
       ↓
All of this is INVISIBLE to:
   - GET /projects/{pid}/cost-summary
   - GET /dashboard/stats
   - GET /dashboard/ops-summary
   - GET /summary/daily
   - Procurement analytics
   - Reconciliation system
   - Alert scan
```

**Impact:** If a construction project spends R50,000 per month on workshop supplies (workshop parts for vehicles, equipment maintenance), 100% of that cost is invisible to financial reporting. A project could appear under budget when it is actually over budget.

**Root cause:** Workshop module is completely self-contained with no cross-module reporting integration.

---

### GAP-006 — Expense Cost Invisibility (HIGH)

```
Staff uploads expense (fuel receipt, accommodation, tools)
       ↓
OCR extracts amount
       ↓
Expense approved
       ↓
Amount is INVISIBLE to:
   - GET /projects/{pid}/cost-summary (only includes labour, subcontractor, fuel logs, vehicle repair, BOQ spend)
   - Dashboard
   - Procurement analytics
```

**Impact:** Staff expenses — potentially thousands of rand per month — are tracked in the `expense_records` table but have no pathway into financial reporting.

---

### GAP-007 — Gmail Auto-Processing Gap (HIGH)

```
Supplier sends quote by email (EXPECTED within 24h)
       ↓
Email arrives in Gmail
       ↓
System does NOT know email arrived
       ↓
Operator must manually trigger POST /gmail/fetch
       ↓
Operator must manually click "process" on each email
       ↓
Hours or days may pass before quote is seen by procurement team
       ↓
Supplier follows up wondering if quote was received
       ↓
procurement timeline delayed
```

**Impact:** Every supplier email reply requires two manual interventions (fetch + process). In a 3-supplier quote round, that is 6 manual operations that should be 0.

---

### GAP-008 — Subcontractor Payment Disconnection (HIGH)

```
Subcontractor work done approved (OFFICE_APPROVED)
       ↓
Marked PAID (→ PAID status)
       ↓
No Payment record created in payments table
       ↓
No entry in supplier outstanding balance
       ↓
No audit trail in payment history
       ↓
Job card → PAID
       ↓
Same problem — no payment record
```

**Impact:** Subcontractor payments and job card payments are invisible to the payment system. Supplier balances do not reflect these payments. A supplier's "outstanding" view would be wrong if they do both supply procurement and subcontractor work.

---

### GAP-009 — Stale Alert Scan (HIGH)

```
Low stock event occurs (usage pushes balance below threshold)
       ↓
No alert created
       ↓
No notification sent
       ↓
Site manager is unaware
       ↓
...3-5 days later, operator thinks to run POST /alerts/scan
       ↓
Alert created (possibly too late)
       ↓
Or: operator never runs scan
       ↓
Stockout occurs on site
```

**Impact:** All proactive alerts depend on a scan that is not scheduled. The system has 6 different proactive checks (`low/negative stock`, `overdue invoices`, `payment due`, `stale MRs`, `deliveries without PO`, `missing signatures`) but none fire automatically.

---

### GAP-010 — Vehicle Cost Disconnection (MEDIUM)

```
Repair job INVOICE_UPLOADED
       ↓
No automatic VehicleCost record created
       ↓
No link to supplier invoice payment system
       ↓
Repair cost tracked separately from all other supplier payments
       ↓
Supplier's outstanding balance does not include repair invoices
       ↓
True cost of vehicle fleet is split across two systems
```

---

## Section 2 — Information Duplication

### DUP-001 — Two Quote Systems

The system has two parallel, non-integrated quote tracking mechanisms:

| System | Model | Used for | Pipeline |
|--------|-------|----------|----------|
| MRQuote | `mr_quotes` | Quotes from suppliers for MR items | MR → MRQuote → PO |
| Quotation | `quotations` | Formal supplier quotation records | Standalone + linked via `PurchaseOrder.quotation_id` |

Both can be linked to a PO. Both have supplier relationships. The integration between them is partial (`quotation_id` FK on PO exists but the MR → quote → PO pipeline uses `MRQuote`, not `Quotation`). This creates confusion about which quote source is authoritative and means supplier quotation history is fragmented.

### DUP-002 — Workshop Module Duplicates Main Procurement

The workshop module is a complete second implementation of the MR → Quote → PO → Invoice pipeline. Every capability exists twice:

| Feature | Main Pipeline | Workshop Pipeline |
|---------|--------------|------------------|
| Material requests | `material_requests` | `workshop_mrs` |
| MR approvals | `mr_approvals` | `workshop_mr_approvals` |
| Email sending | `mr_email_logs` | `workshop_mr_email_logs` |
| Quotes | `mr_quotes` | `workshop_quotes` |
| Quote voting | `mr_quote_votes` | `workshop_quote_votes` |
| Purchase orders | `purchase_orders` | `workshop_pos` |
| Invoices | `invoices` | `workshop_invoices` |
| Delivery notes | `deliveries` | `workshop_delivery_notes` |

None of these tables share data. The workshop module could have reused the main pipeline with a `source: WORKSHOP` flag, but instead duplicated the entire structure.

### DUP-003 — Payment Status vs Payment Record

Subcontractor work done has a `status: PAID` flag on the `subcontractor_work_done` table. Job cards have a `PAID` status. These are conceptually payments but are not represented as payment records in the `payments` table. This means "how much has been paid to Supplier X" gives different answers depending on which table you query.

### DUP-004 — Stock Cost Tracking

Material costs are tracked in three places:
1. `stock_ledger.unit_cost` — per-unit cost at ledger entry time
2. `delivery_items.unit_cost` — cost at delivery time
3. `boq_items.rate` — planned BOQ rate

These three can differ for the same item. There is no reconciliation mechanism between them and no clear definition of which is the "actual cost" for project financials.

---

## Section 3 — Information Stops Prematurely

### STOP-001 — Project Completion Has No Definition

There is no definition of "project complete" in the system. A project has a `status` enum (ProjectStatus) with values that include ACTIVE, but there is no workflow for:
- Checking all lots are in COMPLETED state
- Verifying all invoices are paid
- Verifying all subcontractor claims are paid
- Generating a final project report
- Archiving the project

Projects can remain ACTIVE indefinitely even when all work is done.

### STOP-002 — Site Capture Stops at OCR

The site capture pipeline (`/site-capture/delivery-note/upload`) extracts quantities via OCR and creates a `DeliveryVerification` record. The pipeline stops there. It does not automatically:
- Create a Delivery record
- Update stock balances
- Match against a PO

All of these must be done separately. The OCR result and the actual delivery record are only loosely connected.

### STOP-003 — Expense Stops at Approval

Approved expenses have `status = APPROVED`. There is no:
- Payment record
- Claim against an expense account
- Report to management
- Monthly summary

### STOP-004 — Municipality Invoice Stops at Excel Export

After Excel export, the system has no further visibility into:
- Whether the municipality received the invoice
- Whether a payment was received
- Whether the payment is linked to a project financial record

### STOP-005 — Fuel Delivery Stops at Tank Fill

`POST /vehicles/{id}/fill-from-delivery` updates the bulk delivery record but does not:
- Automatically create a FuelLog record
- Attribute the cost to a vehicle/project
- Create a vehicle cost record

---

## Section 4 — Manual Work That Should Be Automatic

See `Automation_Opportunities.md` for the full list. Summary of the highest-impact manual actions:

| Action | Frequency | Impact |
|--------|-----------|--------|
| Trigger Gmail fetch | Multiple times per day | HIGH — delays procurement |
| Process each email individually | Multiple times per day | HIGH — delays procurement |
| Refresh stock balances | After every delivery | HIGH — data staleness |
| Run alert scan | Should be daily | HIGH — blind spots |
| Create reconciliation | Per invoice | MEDIUM — skipped often |
| Request proof pack | Per payment | MEDIUM — skipped often |
| Update stage progress % | Per stage change | MEDIUM — manual estimation |

---

## Section 5 — Missing Cross-Module Reactions

| Event | Module where event happens | Modules that should react but don't |
|-------|--------------------------|-------------------------------------|
| MR approved | MR module | BOQ module (decrement available budget), Timeline module (MISSING), Dashboard (not real-time) |
| Stage completed | Stage module | Dashboard, Timeline (MISSING), Notification (missing alert), Project completion check (MISSING) |
| Delivery received | Delivery module | Stock balances (needs manual refresh), Invoice module (no auto-match attempt), Dashboard (not real-time) |
| Invoice overdue | Payment due service | Procurement lead notification (only if scan runs), Supplier communication (MISSING) |
| Low stock | Stock module | Procurement trigger (no auto-MR suggestion), Site manager notification (only if scan runs) |
| BOQ exceeded | Usage module | Alert (only if scan runs), Procurement lead notification (MISSING), Approval gate (no hard stop) |
| Quote approved | Quote module | Dashboard (not real-time), Timeline (MISSING) |
| PO sent | PO module | Expected delivery tracking (no auto-overdue check), Calendar integration (MISSING) |
| Payment recorded | Payment module | Invoice status (not auto-updated to PAID), Supplier outstanding (derived, not triggered), Reconciliation (not auto-created) |
| Workshop invoice uploaded | Workshop module | Cost summary (no update), Dashboard (no update), Payment system (no link) |
