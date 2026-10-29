# Business Process Flow

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only. No code or schema changes.

This document maps the complete lifecycle of every major business process in the HMH Construction OS. For each process, it identifies the trigger (start), terminus (end), inputs, outputs, dependencies, automatic actions, manual actions, missing actions, and disconnected actions.

---

## Legend

- `AUTO` — automatically executed by the system
- `MANUAL` — requires explicit human action
- `MISSING` — should happen but does not currently exist
- `DISCONNECTED` — data is available but the downstream reaction does not happen

---

## 1. Procurement Lifecycle

### 1.1 Material Request (MR) Lifecycle

**Starts:** Site staff identifies a material need  
**Ends:** PO sent to supplier OR MR rejected  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Create MR with items, linked to project/site/lot/stage | MANUAL | Items linked to BOQ items optionally |
| 2 | Submit MR (`DRAFT → PENDING`) | MANUAL | |
| 3 | Office staff vote (3 votes required) | MANUAL | `PENDING → STAFF_APPROVED` |
| 4 | PROCUREMENT_LEAD approves (`STAFF_APPROVED → APPROVED`) | MANUAL | Final approval gate |
| 5 | System emails suppliers with MR PDF | AUTO | Triggered by approval |
| 6 | Alert created: MR approved, notify procurement | AUTO | |
| 7 | Suppliers respond by email with quotes | EXTERNAL | |
| 8 | Gmail fetch pulls supplier reply | MANUAL | `POST /gmail/fetch` — operator must trigger |
| 9 | OCR pipeline classifies attachment as QUOTE | AUTO | After fetch |
| 10 | MRQuote record created (source = EMAIL) | AUTO | |
| 11 | Procurement team reviews quotes, votes on best | MANUAL | 3 votes auto-approve |
| 12 | POs created (one per supplier) | AUTO | `finalize_pos` endpoint |
| 13 | PO emails sent to suppliers | AUTO | With PDF attachment |
| 14 | MR status → CONVERTED_TO_PO | AUTO | |

**Inputs:** Project, site, lot (optional), stage (optional), item catalog, BOQ (optional)  
**Outputs:** MRQuote records, Purchase Orders, PO email logs, audit events, alerts, notifications  
**Dependencies:** stage_master, items, suppliers, projects, sites, lots  

**Missing actions:**
- MISSING: BOQ is not automatically queried to validate MR quantities against planned budget at creation time
- MISSING: Stale MR alert is only fired by manual `POST /alerts/scan`, not automatically on a schedule
- MISSING: Dashboard does not automatically update "pending MR" count in real time after approval
- MISSING: When MR is approved, there is no automatic linkage back to the BOQ to decrement planned vs actual material budget

**Disconnected actions:**
- DISCONNECTED: MR lot/stage linkage exists on the data model but is not used to update stage progress automatically when materials arrive
- DISCONNECTED: `preferred_supplier_id` on MR items has no effect on which email is sent — it is informational only

---

### 1.2 Quote Approval Lifecycle

**Starts:** Supplier email received with quote attachment  
**Ends:** Quote approved, PO created  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Gmail fetch retrieves emails | MANUAL | Operator must press button |
| 2 | OCR classifies as QUOTE | AUTO | |
| 3 | MRQuote created (linked to MR) | AUTO | |
| 4 | 3 staff members vote on quote | MANUAL | |
| 5 | OR PROCUREMENT_LEAD override-approves | MANUAL | Single actor path |
| 6 | Quote status → APPROVED | AUTO | After 3rd vote |
| 7 | PO created from approved quote | MANUAL | `finalize_pos` endpoint called by user |
| 8 | PO email sent to supplier | AUTO | |
| 9 | Alert sent to procurement team | AUTO | |

**Missing actions:**
- MISSING: No automatic price comparison alerting when quoted price exceeds BOQ rate by more than configured threshold
- MISSING: `boq_unit_price` is stored on MRQuote but is not used to automatically flag over-BOQ quotes
- MISSING: No automatic re-solicitation if all quotes are rejected

---

### 1.3 Purchase Order Lifecycle

**Starts:** PO created (from MR or manually)  
**Ends:** Invoice paid and reconciled  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | PO created with items | MANUAL or AUTO (from finalize_pos) | |
| 2 | PO email sent to supplier with PDF | MANUAL or AUTO | |
| 3 | Supplier delivers goods | EXTERNAL | |
| 4 | Delivery received (create Delivery record) | MANUAL | |
| 5 | Stock ledger updated | AUTO | On delivery receipt |
| 6 | Stock balances materialized view refreshed | MANUAL | Must call POST /stock/refresh-balances |
| 7 | Invoice received from supplier | MANUAL | Created manually or from Gmail |
| 8 | Invoice matched against PO and delivery | MANUAL | `PATCH /invoices/{id}/match` |
| 9 | Invoice approved for payment | MANUAL | |
| 10 | Payment recorded | MANUAL | |
| 11 | Reconciliation created | MANUAL | Optional — operator must create it |
| 12 | Payment closed | MANUAL | |

**Missing actions:**
- MISSING: Stock balance not automatically refreshed after delivery receipt — requires manual API call
- MISSING: No automatic invoice creation from OCR-processed emails in all cases; only when PO number found in document
- MISSING: No automatic due-date alert on PO delivery date when supplier hasn't delivered
- MISSING: Reconciliation is fully manual — no automatic creation when invoice + payment + delivery all exist

**Disconnected actions:**
- DISCONNECTED: `quantity_received` on PurchaseOrderItem is not automatically updated from DeliveryItem records; the two are linked but no sync service exists
- DISCONNECTED: When PO is fully paid, there is no automatic status transition on the PO
- DISCONNECTED: Proof pack exists (`/proof-packs/{invoice_id}`) but is never automatically generated or sent

---

### 1.4 Delivery Lifecycle

**Starts:** PO delivery expected  
**Ends:** Stock confirmed and usage tracked  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Delivery arrives at site | EXTERNAL | |
| 2 | Site staff photographs delivery note | MANUAL | |
| 3 | `POST /site-capture/delivery-note/upload` — OCR extracts quantities | AUTO | After upload |
| 4 | Staff corrects OCR errors | MANUAL | |
| 5 | Staff verifies quantities vs delivery note | MANUAL | `POST /site-capture/delivery-note/{id}/verify` |
| 6 | Delivery record created | MANUAL or AUTO | `POST /deliveries/receive-with-document` unified endpoint |
| 7 | StockLedger RECEIPT entries created | AUTO | On delivery creation |
| 8 | Delivery note signature captured | MANUAL | `POST /deliveries/{id}/capture` |
| 9 | Alert: delivery received | AUTO (if enabled) | Sends WhatsApp notification |
| 10 | Invoice matched to delivery | MANUAL | |

**Missing actions:**
- MISSING: When delivery quantities are less than ordered, no automatic shortage alert or back-order tracking exists
- MISSING: No automatic PO outstanding quantity update when delivery is received
- MISSING: Rejected delivery items (`quantity_rejected`) have no automatic supplier credit memo or return-to-supplier process

---

### 1.5 Invoice and Payment Lifecycle

**Starts:** Invoice received from supplier  
**Ends:** Invoice reconciled and closed  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Invoice created (manual or from Gmail OCR) | MANUAL | |
| 2 | Invoice matched to PO and delivery | MANUAL | Sets match_status: MATCH/MISMATCH/PARTIAL |
| 3 | Variance alert if mismatch | MANUAL | Only if `POST /alerts/scan` runs |
| 4 | Invoice approved for payment | MANUAL | `POST /invoices/{id}/approve-payment` |
| 5 | Payment recorded | MANUAL | `POST /projects/{pid}/payments/` |
| 6 | Payment due alert | AUTO | Daily cron `scan-payment-due` |
| 7 | Overdue alert | AUTO | Daily cron |
| 8 | Supplier outstanding balance updated | AUTO | Derived from payments query |
| 9 | Cost summary updated | AUTO | Derived query |
| 10 | Reconciliation created | MANUAL | Optional |
| 11 | WhatsApp payment due notification | AUTO | From notification queue |

**Missing actions:**
- MISSING: No automatic invoice → payment record creation when approved
- MISSING: No partial payment tracking against invoice outstanding balance other than via manual reconciliation
- MISSING: No automatic "invoice overdue" escalation beyond the alert (e.g., email to procurement manager)

---

## 2. Warehouse Lifecycle

### 2.1 Stock Management Lifecycle

**Starts:** Goods delivered to project  
**Ends:** Materials issued to lot and usage recorded  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Delivery receipt → RECEIPT stock entries | AUTO | |
| 2 | Stock in main warehouse (site_id=NULL) | AUTO | If `delivery_destination=WAREHOUSE` |
| 3 | Transfer from main warehouse to site warehouse | MANUAL | `POST /projects/{pid}/warehouse/transfer` |
| 4 | Transfer from site warehouse to lot | MANUAL | `POST /sites/{site_id}/warehouse/transfer` |
| 5 | Stock issued to lot (StockLedger TRANSFER_IN) | AUTO | |
| 6 | Site staff records usage | MANUAL | `POST /stock/usage` |
| 7 | Usage deducted from lot balance | AUTO | |
| 8 | Low stock alert triggered | MANUAL | Only if `POST /alerts/scan` runs |
| 9 | Lot material summary updated | AUTO (on-the-fly) | |

**Missing actions:**
- MISSING: No automatic low-stock alert on delivery/usage — scan is always manual
- MISSING: No stock reservation system (BOQ quantities don't automatically reserve stock)
- MISSING: Materialized view `stock_balances` is not auto-refreshed after warehouse adjustments
- MISSING: No FIFO/LIFO valuation — all stock is valued at last unit_cost

**Disconnected actions:**
- DISCONNECTED: BOQ quantities define planned material needs but don't affect stock allocation or reservation
- DISCONNECTED: Stage progress is not updated when material usage is recorded against a stage

---

### 2.2 Cross-Project Transfer Lifecycle

**Starts:** Project needs materials held in another project  
**Ends:** Materials transferred and both projects' stock updated  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Transfer request submitted | MANUAL | |
| 2 | 3 office votes required (or OWNER override) | MANUAL | |
| 3 | Transfer executed on approval | AUTO | TRANSFER_OUT + TRANSFER_IN ledger entries |
| 4 | Both project stock balances updated | AUTO (on next query) | |
| 5 | Materialized view refreshed | MANUAL | |

**Missing actions:**
- MISSING: No notification to the receiving project manager when transfer is approved
- MISSING: No cost allocation — the transferred materials' cost remains on the source project's ledger

---

## 3. Project Lifecycle

### 3.1 Project Setup Lifecycle

**Starts:** Contract won  
**Ends:** Project active with all structure in place  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Create project (code, name, start/end date) | MANUAL | |
| 2 | Link to company | MANUAL | Optional |
| 3 | Create sites within project | MANUAL | Can bulk-create |
| 4 | Generate lots within project | MANUAL | Can bulk-generate up to 500 |
| 5 | Assign lots to sites | MANUAL | Bulk assign |
| 6 | Create lot types | MANUAL | |
| 7 | Assign lots to lot types | MANUAL | |
| 8 | Upload BOQ template (CSV or manual) | MANUAL | |
| 9 | Propagate BOQ to all lots | MANUAL | SAFE/FORCE mode |
| 10 | Seed construction stages (if not seeded) | MANUAL | Or AUTO on startup |
| 11 | Create ProjectStageStatus milestones per lot | AUTO | On BOQ propagation |
| 12 | Grant user access to project/sites | MANUAL | |

**Missing actions:**
- MISSING: No project timeline or Gantt chart — no planned vs actual schedule
- MISSING: No project kick-off checklist or completeness validation (e.g., "you haven't assigned BOQ yet")
- MISSING: No automatic budget calculation from BOQ propagation
- MISSING: No client contact or client portal setup step

---

### 3.2 Milestone (Stage) Tracking Lifecycle

**Starts:** Lot created with stage statuses  
**Ends:** Lot fully completed (all stages CERTIFIED)  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | ProjectStageStatus rows created per lot | AUTO | On BOQ propagation |
| 2 | Stage progressed (PENDING → IN_PROGRESS) | MANUAL | Set progress_pct |
| 3 | Stage blocked (IN_PROGRESS → BLOCKED) | MANUAL | Reason required |
| 4 | Stage unblocked (BLOCKED → IN_PROGRESS) | MANUAL | |
| 5 | Stage completed (`COMPLETED` status) | MANUAL | `POST /stage-statuses/{id}/complete` |
| 6 | Evidence photo uploaded | MANUAL | |
| 7 | Stage certified | MANUAL | |
| 8 | Lot progress % calculated | AUTO | On-the-fly: `GET /lots/{id}/progress` |
| 9 | Project progress % calculated | AUTO | On-the-fly: derived from stage data |

**Missing actions:**
- MISSING: When a stage completes, there is no automatic alert to the project manager or client
- MISSING: No automatic creation of the next stage's materials/labor needs based on completion
- MISSING: Stage completion does not automatically trigger BOQ reconciliation for that stage
- MISSING: No automatic timeline update when stage is delayed
- MISSING: Lot/project progress percentage is computed on-the-fly; the database has no `progress_pct` column on `lots` or `projects` — this is a performance and staleness risk
- MISSING: No subcontractor work done record automatically linked when a stage is completed by a subcontractor

**Disconnected actions:**
- DISCONNECTED: Stage completion exists in the data model but the Dashboard's `lots_completed` count is computed differently
- DISCONNECTED: Stage has `stage_id` FK on material_requests, but MR completion does not update stage progress

---

## 4. Vehicle and Fuel Lifecycle

### 4.1 Vehicle Lifecycle

**Starts:** Vehicle assigned to project  
**Ends:** Vehicle decommissioned or transferred  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Vehicle created | MANUAL | |
| 2 | Vehicle assigned to project/site | MANUAL | |
| 3 | Fuel fills recorded per vehicle | MANUAL | With evidence photos |
| 4 | Fuel costs allocated to project | AUTO | `total_cost` on FuelLog |
| 5 | Vehicle repair needed → repair job created | MANUAL | |
| 6 | Quote submitted for repair | MANUAL | |
| 7 | 3-stage approval process | MANUAL | QUOTE_APPROVED_1 → _2 → APPROVED |
| 8 | Repair invoice uploaded | MANUAL | |
| 9 | Repair cost tracked | MANUAL | VehicleCost records |
| 10 | Repair linked to RepairJob | MANUAL | |
| 11 | Total vehicle cost reported in cost summary | AUTO | Derived query |

**Missing actions:**
- MISSING: No fuel anomaly detection (spikes in consumption automatically flagged)
- MISSING: No vehicle maintenance reminder (service intervals)
- MISSING: VehicleCost records are separate from the main payment system; no link to supplier invoices
- MISSING: Repair jobs with INVOICE_UPLOADED status have no automatic payment record creation
- MISSING: No vehicle utilization tracking (hours billed vs hours available)

---

## 5. Workshop Lifecycle

**Starts:** Workshop item needed for a vehicle repair  
**Ends:** Workshop item issued from workshop stock  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Workshop item identified as needed | MANUAL | |
| 2 | Workshop MR created | MANUAL | |
| 3 | Workshop MR voted (staff) | MANUAL | |
| 4 | Workshop MR approved | MANUAL | |
| 5 | Email sent to suppliers requesting quotes | MANUAL | `send-to-suppliers` |
| 6 | Quotes received and uploaded | MANUAL | |
| 7 | Quotes voted on | MANUAL | |
| 8 | Quote approved | MANUAL | |
| 9 | Workshop PO created and sent | MANUAL | |
| 10 | Workshop invoice received and uploaded | MANUAL | |
| 11 | Workshop delivery note uploaded | MANUAL | |
| 12 | Workshop stock updated | MANUAL | Issuance records |
| 13 | Item issued to vehicle/job | MANUAL | |

**Missing actions:**
- MISSING: Workshop costs are COMPLETELY disconnected from the main cost summary. `GET /projects/{pid}/cost-summary` does not include workshop spend
- MISSING: Workshop invoices are not linked to the main invoice/payment system
- MISSING: Workshop stock is separate from the main warehouse stock — no unified view
- MISSING: Workshop repair work is not linked to vehicle RepairJob records

**Disconnected actions:**
- DISCONNECTED: Workshop module has its own complete MR → Quote → PO → Invoice pipeline that duplicates the main procurement pipeline
- DISCONNECTED: Workshop items do not appear in the main Item catalog
- DISCONNECTED: Workshop supplier links are separate from company-level supplier restrictions

---

## 6. Subcontractor Lifecycle

### 6.1 Job Card Lifecycle

**Starts:** Labour work completed on site  
**Ends:** Labour paid  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Job card created (linked to project/site/lot/stage) | MANUAL | |
| 2 | Job card submitted | MANUAL | DRAFT → SUBMITTED |
| 3 | Site approved | MANUAL | → SITE_APPROVED |
| 4 | Office approved | MANUAL | → OFFICE_APPROVED |
| 5 | Owner approved (if required) | MANUAL | → OWNER_APPROVED |
| 6 | Payment approved | MANUAL | → PAYMENT_APPROVED |
| 7 | Marked paid | MANUAL | → PAID |
| 8 | Amount captured in cost summary | AUTO | Sum of OWNER_APPROVED+/PAID job cards |

**Missing actions:**
- MISSING: Job card payment is not linked to the payments table — it is a status field, not an actual payment record
- MISSING: No supplier invoice required for job card — no 3-way match
- MISSING: No cash flow impact when job card is approved

### 6.2 Subcontractor Work Done Lifecycle

**Starts:** Subcontractor submits monthly claim  
**Ends:** Claim paid  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Work done record created (monthly claim) | MANUAL | Linked to project/site/lot/stage_status |
| 2 | Submitted | MANUAL | DRAFT → SUBMITTED |
| 3 | Site approved | MANUAL | → SITE_APPROVED |
| 4 | Office approved | MANUAL | → OFFICE_APPROVED |
| 5 | Marked paid | MANUAL | → PAID |
| 6 | Amount appears in cost summary | AUTO | Sum of SITE_APPROVED+ records |

**Missing actions:**
- MISSING: Work done payment is not linked to the payments table
- MISSING: No retention tracking (common in construction: withhold 5% until completion)
- MISSING: No variation order linkage when work changes scope

---

## 7. Document and Email Lifecycle

### 7.1 Incoming Email Processing Lifecycle

**Starts:** Supplier sends email with attachment  
**Ends:** Quote or Invoice created in the system  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Email arrives in Gmail inbox | EXTERNAL | |
| 2 | Operator triggers Gmail fetch | MANUAL | `POST /gmail/fetch` |
| 3 | IncomingEmail + attachments stored | AUTO | |
| 4 | Operator clicks "process" on an email | MANUAL | `POST /gmail/incoming/{id}/process` |
| 5 | OCR pipeline runs on attachment | AUTO | |
| 6 | Document classified (QUOTE/INVOICE/DELIVERY_NOTE) | AUTO | |
| 7 | Supplier matched by name | AUTO | |
| 8 | MR matched by item descriptions | AUTO | |
| 9 | MRQuote or Invoice draft created | AUTO | Requires human confirmation |
| 10 | Human confirms/corrects draft | MANUAL | |
| 11 | Record officially created | AUTO | After human confirmation |

**Missing actions:**
- MISSING: Gmail fetch is never automatic — an operator must trigger it; emails could pile up unprocessed
- MISSING: No automatic classification of email as "from known supplier" to prioritize it for processing
- MISSING: Incoming emails are never automatically acknowledged (no auto-reply to supplier confirming receipt)

---

## 8. Expense Lifecycle

**Starts:** Staff incurs a business expense  
**Ends:** Expense approved and tracked  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Staff uploads expense receipt | MANUAL | `POST /expenses/upload` |
| 2 | OCR extracts amount, date, description | AUTO | |
| 3 | ExpenseRecord created with NEEDS_REVIEW status | AUTO | |
| 4 | Office reviews and corrects OCR | MANUAL | |
| 5 | Office approves | MANUAL | `POST /expenses/{id}/approve` |
| 6 | Expense tracked | AUTO | |

**Missing actions:**
- MISSING: Expenses are COMPLETELY absent from the cost summary. `GET /projects/{pid}/cost-summary` does not include expenses
- MISSING: No expense categories (fuel? materials? accommodation?)
- MISSING: No payment record for expenses
- MISSING: No monthly expense report

---

## 9. Municipality Invoice Lifecycle

**Starts:** Construction milestone reached for billing to municipality  
**Ends:** Certificate submitted and tracked  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Municipality invoice created from template (15 Ethekweni line items) | MANUAL | |
| 2 | Line items customized | MANUAL | |
| 3 | Invoice exported to Excel | MANUAL | Ethekweni Cert 26 format |
| 4 | Excel submitted to municipality (externally) | EXTERNAL | |
| 5 | Payment received from municipality | EXTERNAL | |

**Missing actions:**
- MISSING: Municipality invoices have their own data model completely isolated from the main invoice/payment system
- MISSING: No tracking of whether municipality has paid
- MISSING: No link between municipality invoice and project milestone progress
- MISSING: No connection to the main financial reporting (cost summary, dashboard)
- MISSING: Only Ethekweni template is supported — no other municipalities

---

## 10. Notification and Alert Lifecycle

**Starts:** Business event occurs  
**Ends:** Recipient acknowledges or resolves  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | Business operation creates SystemAlert | AUTO | Via enqueue_direct() |
| 2 | NotificationQueue rows created for matching recipients | AUTO | Respects subscriptions, quiet hours |
| 3 | asyncio drain loop wakes within 30s | AUTO | Or immediately via event |
| 4 | WhatsApp message sent (template or free-form) | AUTO | 3-tier strategy |
| 5 | Delivery receipt from Meta | AUTO | |
| 6 | Recipient replies ACK | MANUAL (recipient) | |
| 7 | Webhook handler marks all ACKNOWLEDGED | AUTO | |
| 8 | Parent alert resolved | AUTO | |

**Disconnected actions:**
- DISCONNECTED: Many important events do NOT create alerts — milestone completion, BOQ over-budget, stage blocking, subcontractor payment
- DISCONNECTED: Proactive scan (`POST /alerts/scan`) must be manually triggered — not on a schedule

---

## 11. Reporting and Dashboard Lifecycle

**Starts:** User opens dashboard  
**Ends:** Data displayed  

| Step | Action | Type | Notes |
|------|--------|------|-------|
| 1 | User requests dashboard stats | MANUAL | |
| 2 | 8+ SQL aggregate queries execute synchronously | AUTO | |
| 3 | Results returned | AUTO | |
| 4 | User requests cost summary | MANUAL | |
| 5 | 7 separate SQL aggregates execute | AUTO | |
| 6 | Results returned | AUTO | |

**Missing actions:**
- MISSING: No caching — every dashboard request re-runs all SQL queries regardless of data freshness
- MISSING: No real-time dashboard updates (WebSockets or polling)
- MISSING: No project completion forecast based on progress vs timeline
- MISSING: No cash flow projection
- MISSING: Expenses, workshop costs, and municipality invoice income are excluded from all financial views
