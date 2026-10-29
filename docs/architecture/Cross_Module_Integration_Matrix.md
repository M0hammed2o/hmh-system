# Cross-Module Integration Matrix

**Date:** 2026-07-16  
**Author:** Architecture Audit — Level 4  
**Classification:** L0 — Documentation only.  
**Evidence basis:** Direct repository inspection of all service, model, and route handler files.

---

## How to Read This Document

This matrix answers, for every module: **who creates the data, who owns it, who reads it, who should consume it but currently does not, and what is missing.**

Legend:
- ✓ **Connected** — integration exists and is verified in the repository
- ✗ **Missing** — integration does not exist but should
- ~ **Partial** — integration exists but is incomplete or requires manual action
- — **Not applicable** — no natural integration relationship

---

## Module 1 — Auth / Users

**Creates:** User records, JWT tokens, refresh tokens, role assignments, UserProjectAccess, UserSiteAccess  
**Owns:** Identity, role, access scope  
**Canonical truth for:** Who performed any action (actor_id on every audit event and created_by on every entity)

| Consumer | Integration | Gap |
|----------|------------|-----|
| All modules (created_by FK) | ✓ | — |
| Audit log (actor_id) | ✓ | — |
| Notifications (recipient lookup by role) | ✓ | — |
| AlertRecipient subscription management | ✓ | — |
| Access grant/revoke notifications | ✗ | When a user's project access is granted or revoked, no notification is sent to the user or their manager |
| Session activity analytics | ✗ | No login/logout audit events; no session tracking |

**Integration Score: 7/10**

---

## Module 2 — Projects

**Creates:** Project records, company assignment  
**Owns:** The top-level organisational container for all operational data  
**Canonical truth for:** `project_id` FK used by every operational entity

| Consumer | Integration | Gap |
|----------|------------|-----|
| Sites (project_id FK) | ✓ | — |
| Lots (via sites) | ✓ | — |
| BOQ (project_id FK) | ✓ | — |
| Material Requests (project_id FK) | ✓ | — |
| Purchase Orders (project_id FK) | ✓ | — |
| Deliveries (project_id FK) | ✓ | — |
| Stock (project_id FK) | ✓ | — |
| Invoices (project_id FK) | ✓ | — |
| Payments (project_id FK) | ✓ | — |
| Job Cards (project_id FK) | ✓ | — |
| Work Done (project_id FK) | ✓ | — |
| Vehicles (project_id FK) | ✓ | — |
| Fuel Logs (project_id FK) | ✓ | — |
| Cost Summary (aggregates by project_id) | ✓ | — |
| Dashboard (project-level KPIs) | ✓ | — |
| Workshop (project_id FK) | ✗ | Workshop entities have no project_id FK — workshop costs are invisible to project financial reporting |
| Municipality Invoices (project_id FK) | ✓ | Invoice exists per project but income is not included in cost summary |
| Expenses (project_id FK) | ✓ | Expense exists per project but cost is not included in cost summary |
| Timeline (project_id FK) | ✗ | Module does not exist yet |
| Progress (project.progress_pct updated) | ✗ | Project progress not persisted; computed on demand inconsistently |
| Alerts (project-scoped alerts) | ~ | Alerts have project_id but proactive alert scan is manual |

**Integration Score: 7/10** (loses points for Workshop isolation and missing progress persistence)

---

## Module 3 — Sites

**Creates:** Site records (location, address)  
**Owns:** Physical location context for all field operations  
**Canonical truth for:** `site_id` FK used by lots, deliveries, warehouse, fuel, stage statuses

| Consumer | Integration | Gap |
|----------|------------|-----|
| Lots (site_id FK) | ✓ | — |
| Deliveries (site_id FK) | ✓ | — |
| Warehouse / Stock (site_id FK) | ✓ | — |
| Stage Statuses (site_id via lot) | ✓ | — |
| Fuel Logs (project_id only; no site_id) | ~ | Fuel logs track project but not which site vehicle operated at |
| Dashboard (site-level breakdown) | ✗ | Dashboard aggregates at project level; no site-level cost breakdown |
| Sites.address / gps_lat / gps_lng | ✗ | These fields exist in migrations 0067 but are absent from production (B-05 in Schema_Reconciliation_Report.md) |

**Integration Score: 7/10**

---

## Module 4 — Lots

**Creates:** Lot records (subdivision of a site)  
**Owns:** The primary unit of construction work tracking  
**Canonical truth for:** Progress_pct, stage statuses, BOQ allocation, MR context

| Consumer | Integration | Gap |
|----------|------------|-----|
| BOQ (lot_id FK) | ✓ | — |
| Stage Statuses (lot_id FK) | ✓ | — |
| Material Requests (lot_id FK, optional) | ✓ | — |
| Stock / Usage (lot_id FK) | ✓ | — |
| Job Cards (lot_id FK) | ✓ | — |
| Work Done (lot_id FK) | ✓ | — |
| lots.progress_pct (auto-updated) | ✗ | Not auto-updated when stages complete; computed on demand |
| lots.status (auto-set to COMPLETED) | ✗ | Never auto-set when all stages complete (see AUT-007) |
| Timeline (lot as scheduling unit) | ✗ | Module does not exist |
| Dashboard (lot-level progress cards) | ~ | Partial — lot list shows progress but it is computed on demand |

**Integration Score: 6/10**

---

## Module 5 — BOQ

**Creates:** BOQ items (budget lines), BOQ sections, BOQ templates  
**Owns:** Project budget plan; the planned cost baseline  
**Canonical truth for:** Planned cost per category per project

| Consumer | Integration | Gap |
|----------|------------|-----|
| Cost Summary (BOQ budget vs actual) | ✓ | — |
| Dashboard (budget utilisation) | ✓ | — |
| Stage Statuses (BOQ propagation via templates) | ✓ | — |
| Material Requests (over_boq flag) | ✓ | — |
| Usage Logs (over_boq flag via BOQ check) | ~ | BOQ variance check exists but is manual scan only |
| BOQ Adjustments (revisions) | ✓ | — |
| Allocation (MR items linked to BOQ items) | ✓ | — |
| Timeline (BOQ items as timeline activities) | ✗ | Module does not exist |
| Cash Flow Forecast (BOQ as planned spend) | ✗ | Module does not exist |

**Integration Score: 7/10**

---

## Module 6 — Stage Statuses / Milestones

**Creates:** ProjectStageStatus records (stage progress per lot)  
**Owns:** Physical construction progress  
**Canonical truth for:** What has been built, when, and to what completion percentage

| Consumer | Integration | Gap |
|----------|------------|-----|
| Material Requests (stage_id FK) | ✓ | — |
| Job Cards (stage_id FK) | ✓ | — |
| Work Done (stage_id FK) | ✓ | — |
| Lot progress (lots.progress_pct) | ✗ | Not updated when stage completes |
| Project progress (projects.progress_pct) | ✗ | Not updated when lot completes |
| Notifications (MILESTONE_COMPLETED) | ✗ | Completion triggers no notification |
| Dashboard (project progress displayed) | ~ | Progress shown but computed on demand, not from persisted field |
| Timeline (stages as Gantt bars) | ✗ | Module does not exist |
| Audit log (stage status changes) | ✗ | Zero audit events on any stage transition |
| Alerts (STAGE_BLOCKED) | ~ | SystemAlert created but no WhatsApp notification |
| Weekly Work Plan (stages as planning units) | ✗ | Module does not exist |

**Integration Score: 2/10** — The most under-integrated module relative to its business importance.

---

## Module 7 — Material Requests

**Creates:** MaterialRequest records, MaterialRequestItem records  
**Owns:** Labour and material needs at site level  
**Canonical truth for:** What site staff require; the trigger for the entire procurement pipeline

| Consumer | Integration | Gap |
|----------|------------|-----|
| MR Emails (send to supplier on approval) | ✓ | — |
| MRQuotes (created from supplier responses) | ✓ | — |
| Purchase Orders (created from approved quote) | ✓ | — |
| Deliveries (linked to PO) | ✓ | — |
| Audit log | ✓ | — |
| Notifications (submitted, approved, rejected) | ~ | Approved and submitted have alerts; rejected is in-app only; cancelled has nothing |
| BOQ variance check (over_boq alerts) | ~ | Alert created at submission; scan is manual |
| Analytics (MR volume, cycle time) | ~ | Analytics endpoint exists but MR-specific metrics are limited |
| Cost Summary (MR items as cost projection) | ✗ | MR items are not included in any cost projection before PO creation |
| Timeline (MR as scheduling dependency) | ✗ | Module does not exist |

**Integration Score: 8/10**

---

## Module 8 — Purchase Orders

**Creates:** PurchaseOrder records, PurchaseOrderItem records  
**Owns:** Formal commitment to a supplier; the trigger for delivery  
**Canonical truth for:** What was ordered, at what price, from whom

| Consumer | Integration | Gap |
|----------|------------|-----|
| Deliveries (po_id FK) | ✓ | — |
| Invoices (po_id FK) | ✓ | — |
| Invoice Matching (PO as the reference doc) | ✓ | — |
| Payments (linked via invoice) | ✓ | — |
| Supplier emails (PO email on approval) | ✓ | — |
| Audit log | ~ | Partial — approve and send audited; create and update not |
| PO status (RECEIVED when delivery complete) | ~ | Delivery service updates PO status; but INVOICED and PAID states are orphaned |
| Reconciliation (PO as anchor document) | ~ | ProcurementReconciliation exists but is not auto-created when PO delivered |
| Price history (PO items build price history) | ✓ | — |
| Analytics (PO volume, supplier spend) | ✓ | — |
| BOQ allocation (PO items linked to BOQ) | ~ | Allocation exists for MR items; PO items have no direct BOQ allocation |

**Integration Score: 7/10**

---

## Module 9 — Deliveries

**Creates:** Delivery records, DeliveryItem records  
**Owns:** Physical receipt of goods; updates stock  
**Canonical truth for:** What was received, when, and in what quantity

| Consumer | Integration | Gap |
|----------|------------|-----|
| Stock Ledger (DELIVERY_IN entries) | ✓ | — |
| Stock Balances (materialized view) | ~ | View is not auto-refreshed after delivery |
| PO status (PARTIALLY_RECEIVED / RECEIVED) | ✓ | — |
| Invoice Matching (delivery as reference) | ✓ | — |
| Notifications (DELIVERY_RECEIVED_ALERT) | ✓ | — |
| Audit log | ~ | `receive_stock()` has audit; `create_delivery()` does not |
| Reconciliation (auto-trigger) | ✗ | Delivery receipt does not auto-create a ProcurementReconciliation |
| BOQ variance update | ✗ | No check of BOQ vs cumulative delivered quantity |
| PurchaseOrderItem.quantity_received | ✗ | Not auto-updated from delivery items (AUT-025) |

**Integration Score: 7/10**

---

## Module 10 — Stock / Warehouse

**Creates:** StockLedger entries, WarehouseTransferRequest records, UsageLog records  
**Owns:** Current stock position per site; physical inventory  
**Canonical truth for:** What is available at each site

| Consumer | Integration | Gap |
|----------|------------|-----|
| Stock Balances materialized view | ~ | Exists; not auto-refreshed |
| Dashboard (stock cards) | ~ | Shows stock but may be stale |
| BOQ (usage against BOQ item) | ~ | `over_boq` flag set but check is not automatic |
| Material Requests (stock availability check) | ✗ | MR creation does not check whether item is already in stock at the site |
| Audit log | ✓ | — |
| Alerts (low stock) | ~ | Low stock check exists in alert scanner but scanner is manual |
| Workshop stock (workshop_items) | ✗ | Workshop has its own stock system with no connection to main stock |
| Cost Summary (stock value at site) | ✗ | Stock on-hand value is not included in any financial summary |

**Integration Score: 5/10**

---

## Module 11 — Invoices

**Creates:** Invoice records, InvoiceLineItem records  
**Owns:** The supplier's payment demand  
**Canonical truth for:** Amount owed to a supplier for goods/services delivered

| Consumer | Integration | Gap |
|----------|------------|-----|
| Invoice Matching (3-way: PO + Invoice + Delivery) | ✓ | — |
| Payments (payment linked to invoice_id) | ✓ | — |
| Invoice status recalculation | ✓ | — |
| Audit log (create only) | ~ | Update and status recalculation have no audit events |
| Notifications (INVOICE_CAPTURED, overdue alerts) | ~ | Capture notified; overdue scan is manual |
| Dashboard (outstanding invoices KPI) | ✓ | — |
| Analytics (invoice accuracy per supplier) | ✓ | — |
| Proof Pack (PDF generation) | ✓ | — |
| Auto invoice matching on create | ✗ | When invoice is created, matching is not attempted automatically |
| APPROVED_FOR_PAYMENT state | ✗ | No explicit payment approval step before payment is created |
| Cost Summary (invoice amounts vs payments) | ~ | Cost summary uses payments, not invoice amounts |

**Integration Score: 7/10**

---

## Module 12 — Payments

**Creates:** Payment records  
**Owns:** Actual money movement; the terminal financial event  
**Canonical truth for:** What was actually paid, when, to whom

| Consumer | Integration | Gap |
|----------|------------|-----|
| Invoice status update | ✓ | `_recalculate_invoice_status()` called on every payment mutation |
| Supplier outstanding balance | ✓ | — |
| Cost Summary (procurement spend) | ✓ | — |
| Dashboard (payment KPIs) | ✓ | — |
| Analytics (supplier spend analysis) | ✓ | — |
| Audit log (create only) | ~ | Update, approve, cancel, fail have no audit events |
| Notifications (PAYMENT_COMPLETED) | ✓ | — |
| JobCard → Payment link | ✗ | Payment created from JobCard has no `source_id` FK back to JobCard |
| WorkDone → Payment link | ✗ | Same issue as JobCard |
| ExpenseRecord → Payment | ✗ | Expense PAID status creates no Payment record |
| Workshop Invoice → Payment | ✗ | Workshop has no payment entity |
| Reconciliation | ~ | ProcurementReconciliation links to Payment but is manually created |
| Bank integration | ✗ | No module |

**Integration Score: 6/10**

---

## Module 13 — Workshop

**Creates:** WorkshopMR, WorkshopQuote, WorkshopPO, WorkshopInvoice, WorkshopDeliveryNote, WorkshopIssuance, WorkshopStock records  
**Owns:** Internal vehicle/equipment repair and parts procurement  
**Canonical truth for:** Workshop operational spend (currently invisible to the rest of the system)

| Consumer | Integration | Gap |
|----------|------------|-----|
| Suppliers (email send on PO) | ~ | Email is sent but supplier is not linked via FK in all workshop models |
| Cost Summary | ✗ | Workshop spend is INVISIBLE to project financial reporting |
| Main Payments | ✗ | No Payment records created from Workshop invoices |
| Main Stock | ✗ | Workshop stock is completely separate from site warehouse stock |
| Audit log | ✗ | Zero audit events for any Workshop transition |
| Notifications | ✗ | Zero notifications for any Workshop event |
| Repair Jobs (vehicle repairs) | ✗ | Workshop is not linked to vehicle repair jobs |
| Project (project_id FK) | ✗ | Workshop entities have no project_id FK |

**Integration Score: 2/10** — Confirmed most isolated module.

---

## Module 14 — Expenses

**Creates:** ExpenseRecord records  
**Owns:** Staff reimbursable expenses  
**Canonical truth for:** Ad-hoc project expenditure

| Consumer | Integration | Gap |
|----------|------------|-----|
| Projects (project_id FK) | ✓ | — |
| Cost Summary | ✗ | Approved expenses are invisible to project cost reporting |
| Payments | ✗ | PAID status creates no Payment record |
| Audit log | ✗ | No audit events |
| Notifications | ✗ | No notifications |
| Dashboard | ✗ | Expenses not visible in any dashboard card |

**Integration Score: 2/10**

---

## Module 15 — Municipality Invoices

**Creates:** MunicipalityInvoice records  
**Owns:** Revenue from municipality billing  
**Canonical truth for:** Project income (currently orphaned from financial reporting)

| Consumer | Integration | Gap |
|----------|------------|-----|
| Projects (project_id FK) | ✓ | — |
| Payments (income side) | ✗ | No income payment tracking |
| Cost Summary (income contra) | ✗ | Municipality income is invisible to cost summary |
| Audit log | ✗ | No audit events |
| Notifications | ✗ | No notifications |
| Dashboard | ✗ | Not visible in dashboard financial figures |

**Integration Score: 2/10**

---

## Module 16 — Job Cards

**Creates:** JobCard records (labour payments to subcontractors)  
**Owns:** Subcontractor labour cost records  
**Canonical truth for:** Labour cost at stage/site level

| Consumer | Integration | Gap |
|----------|------------|-----|
| Payments (creates Payment on mark_paid) | ✓ | — |
| Cost Summary (labour_cost line) | ✓ | — |
| Audit log (all transitions) | ✓ | — |
| Notifications | ✗ | No notifications on any Job Card transition |
| JobCard → Payment FK | ✗ | Payment created has no `source_id` back to JobCard |
| Dashboard | ~ | Included in cost summary used by dashboard |

**Integration Score: 6/10**

---

## Module 17 — Work Done / Subcontractor Payments

**Creates:** SubcontractorWorkDone records  
**Owns:** Monthly subcontractor billing records  
**Canonical truth for:** Subcontractor cost per stage per month

| Consumer | Integration | Gap |
|----------|------------|-----|
| Payments (creates Payment on mark_paid) | ✓ | — |
| Cost Summary (subcontractor_cost line) | ✓ | — |
| Audit log (all transitions) | ✓ | — |
| Stage progress (optional update on paid) | ~ | Only updates if `stage_status_id` is set on the record |
| Notifications | ✗ | No notifications on any WorkDone transition |
| WorkDone → Payment FK | ✗ | Same issue as JobCard |

**Integration Score: 6/10**

---

## Module 18 — Vehicles

**Creates:** Vehicle records, FuelLog records, VehicleCost records, RepairJob records  
**Owns:** Vehicle operational records and costs  
**Canonical truth for:** Vehicle fuel and repair expenditure

| Consumer | Integration | Gap |
|----------|------------|-----|
| Cost Summary (fuel_cost, vehicle_repair lines) | ✓ | — |
| Projects (project_id FK on vehicles) | ✓ | — |
| Fuel anomaly alerts | ✗ | No automatic anomaly detection on fuel records |
| RepairJob → Payment | ✗ | Approved repair job invoices do not create Payment records |
| RepairJob → VehicleCost | ✗ | Approved repair job does not auto-create a VehicleCost entry |
| Workshop (vehicle parts) | ✗ | No link between RepairJob and Workshop parts procurement |
| Audit log | ✗ | No audit events for vehicle or fuel operations |

**Integration Score: 5/10**

---

## Module 19 — Document AI / Gmail / OCR

**Creates:** IncomingEmail, IncomingEmailAttachment, DocumentExtraction records  
**Owns:** AI-extracted document data  
**Canonical truth for:** What was extracted from supplier documents; the source for draft MRQuotes, Invoices, and Delivery records

| Consumer | Integration | Gap |
|----------|------------|-----|
| MRQuotes (draft created from QUOTE extraction) | ✓ | — |
| Invoices (draft created from INVOICE extraction) | ✓ | — |
| Delivery (draft created from DELIVERY_NOTE extraction) | ✓ | — |
| Supplier auto-matching (fuzzy match) | ✓ | — |
| Duplicate detection alerts | ✓ | — |
| Gmail fetch (auto-polling) | ✗ | Manual trigger only; no scheduled polling |
| Auto-process high-confidence extractions | ✗ | Every email requires manual "process" click |
| Document Centre (centralised attachment view) | ~ | Attachments stored; no unified document centre UI |

**Integration Score: 7/10**

---

## Module 20 — Notifications / Alerts

**Creates:** SystemAlert records, NotificationQueue records  
**Owns:** Stakeholder communication; event delivery  
**Canonical truth for:** What alerts exist, their status, and delivery history

| Consumer | Integration | Gap |
|----------|------------|-----|
| WhatsApp (outbound via Meta API) | ✓ | — |
| WhatsApp (inbound ACK/APPROVE/REJECT parsing) | ✓ | — |
| Alert scan (6 proactive checks) | ~ | Scan exists but must be manually triggered |
| Payment due scan (scheduled) | ~ | Scheduled via cron but separate from main alert scan |
| Daily summary (scheduled) | ~ | Scheduled but WhatsApp only; no email digest |
| Milestone completion alerts | ✗ | Stage COMPLETED triggers no notification |
| Workshop events | ✗ | Workshop module sends zero notifications |
| Expense events | ✗ | Expense module sends zero notifications |
| Municipality invoice events | ✗ | No notifications |
| User access change alerts | ✗ | No notification when project access granted/revoked |

**Integration Score: 6/10**

---

## Module 21 — Audit Log

**Creates:** AuditEvent records (immutable, append-only)  
**Owns:** Immutable historical record of all business actions  
**Canonical truth for:** Who did what to which record, when, and what changed

| Consumer | Integration | Gap |
|----------|------------|-----|
| GET /audit (OWNER_ONLY filter endpoint) | ✓ | — |
| Analytics (audit as event source) | ✗ | Audit events are not consumed by any analytics or reporting |
| Stage status changes | ✗ | Zero audit events for stage transitions |
| Workshop module | ✗ | Zero audit events for workshop transitions |
| Expense module | ✗ | Zero audit events |
| Municipality Invoice | ✗ | Zero audit events |
| Quotation module | ✗ | Zero audit events |
| AI training (audit as event stream) | ✗ | Audit data is not exported or streamed |

**Integration Score: 4/10** (the data is correct where written; the coverage gap is in other modules not calling it)

---

## Module 22 — Analytics / Reporting

**Creates:** No new records — read-only aggregation layer  
**Owns:** Business intelligence outputs  
**Reads from:** Payments, Deliveries, POs, Invoices, Suppliers, Projects

| Source | Connected | Gap |
|--------|-----------|-----|
| Procurement data (payments, POs, deliveries) | ✓ | — |
| Supplier performance scores | ~ | Computed but not persisted to suppliers table |
| Project cost summary | ✓ | — |
| Workshop spend | ✗ | Invisible |
| Expense records | ✗ | Invisible |
| Municipality income | ✗ | Invisible |
| Stage progress / milestone data | ✗ | Not in analytics |
| Labour costs (job cards, work done) | ~ | In cost summary but not in analytics dashboard |

**Integration Score: 5/10**

---

## Integration Summary Table

| Module | Score | Key Gap |
|--------|-------|---------|
| Auth / Users | 7/10 | No access change notifications |
| Projects | 7/10 | Workshop isolation, missing progress persistence |
| Sites | 7/10 | No site-level cost breakdown |
| Lots | 6/10 | No auto-progress update, no auto-completion |
| BOQ | 7/10 | No cash flow integration |
| Stage / Milestones | **2/10** | Completion triggers nothing; zero audit |
| Material Requests | 8/10 | Partial notifications, no cost projection |
| Purchase Orders | 7/10 | Orphan statuses, manual reconciliation |
| Deliveries | 7/10 | No auto-reconciliation, stale stock view |
| Stock / Warehouse | 5/10 | Stale balances, no MR availability check |
| Invoices | 7/10 | No auto-matching, no payment approval state |
| Payments | 6/10 | No source FKs, no expense/workshop payments |
| Workshop | **2/10** | Completely isolated from cost, stock, audit |
| Expenses | **2/10** | Invisible to costs; no payment link |
| Municipality Invoices | **2/10** | Invisible income; no payment tracking |
| Job Cards | 6/10 | No notifications; no payment source FK |
| Work Done | 6/10 | No notifications; no payment source FK |
| Vehicles | 5/10 | No repair → payment chain |
| Document AI | 7/10 | Manual triggers; no auto-processing |
| Notifications | 6/10 | Manual scan; workshop/expense blind spots |
| Audit Log | 4/10 | Coverage gaps in 6 modules |
| Analytics | 5/10 | Workshop/expense invisible |

**System average integration score: 5.4/10**

---

## Priority Integration Gaps

Ranked by business impact × implementation feasibility:

| Rank | Gap | Impact | Effort | Blocks |
|------|-----|--------|--------|--------|
| 1 | Stage completion → lot/project progress update | CRITICAL | Small | Dashboard accuracy, Timeline module |
| 2 | Workshop → cost summary (project_id FK first) | CRITICAL | Medium | Financial reporting completeness |
| 3 | Expense → cost summary + payment record | HIGH | Small | Financial reporting completeness |
| 4 | Stock balance auto-refresh | CRITICAL | Small | All stock decisions |
| 5 | Invoice auto-paid status | HIGH | Small | Invoice lifecycle correctness |
| 6 | Municipality income → cost summary | HIGH | Small | Revenue visibility |
| 7 | Audit coverage for Workshop/Expense/Muni | HIGH | Medium | Compliance, audit trail |
| 8 | Payment source FK (JobCard/WorkDone) | HIGH | Medium | Financial traceability |
| 9 | Repair job → VehicleCost + Payment | MEDIUM | Medium | Vehicle financial completeness |
| 10 | Alert scan scheduled (not manual) | HIGH | Small | Proactive monitoring |
