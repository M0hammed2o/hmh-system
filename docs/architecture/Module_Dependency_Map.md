# Module Dependency Map

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only.

This document maps every module dependency in the HMH Construction OS. Arrows (→) indicate data flow or dependency. Dashed arrows (⇢) indicate a dependency that should exist but is currently missing or broken.

---

## Section 1 — Primary Construction Lifecycle Chain

```
Companies ──────────────────────────────────────────────────────────────────┐
                                                                             ↓
Suppliers ──────────────────────────────────────────────────────────────────┐
                                                                             ↓
Items & Categories ─────────────────────────────────────────────────────────┐
                                                                             ↓
                                              Project ──→ Company (optional)
                                                  ↓
                                              Site(s)
                                                  ↓
                                              Lot(s)
                                                  ↓
                                 ┌────────────────┴───────────────────┐
                                 ↓                                     ↓
                            BOQ (plan)                       Lot Types (template)
                                 ↓ propagate                          ↓ propagate
                         Stage Statuses ←────────────────── BOQ Template
                         (milestones)
                                 ↓ (lot progress)
                                 ↓
                         Material Request ←── Items, Site, Lot, Stage
                                 ↓ (approve)
                         MR Email → Supplier
                                 ↓ (supplier replies)
                         Gmail Inbox → OCR Pipeline
                                 ↓ (auto-create)
                         MR Quote
                                 ↓ (vote/approve)
                         Purchase Order → Supplier Email
                                 ↓
                         Delivery ←── Supplier, Site, PO
                                 ↓ (receipt)
                         Stock Ledger → Stock Balances (materialized)
                                 ↓
                         Site Warehouse
                                 ↓ (transfer)
                         Lot Stock
                                 ↓ (usage)
                         Usage Logs
                                 ↓ (over_boq?)
                                 ⇢ BOQ Variance Check [MISSING]
                                 ↓
                         Invoice ←── PO, Supplier
                                 ↓ (match)
                         Invoice Matching Result ←── Delivery
                                 ↓ (approve for payment)
                         Payment ←── Invoice, Supplier, Project
                                 ↓
                         Supplier Outstanding Balance
                                 ↓
                         Reconciliation [MANUAL, INCOMPLETE]
```

---

## Section 2 — Stage / Milestone Sub-chain

```
Stage Master (seeded defaults: 15 stages)
       ↓ (BOQ propagation)
Project Stage Status (per lot × per stage)
       ↓
       ├── progress_pct (manually set by site staff)
       │       ⇢ lots.progress_pct [MISSING — not persisted]
       │       ⇢ projects.progress_pct [MISSING — not persisted]
       │
       ├── status: COMPLETED
       │       ⇢ lots.status = COMPLETED [MISSING — not auto-set]
       │       ⇢ Alert: MILESTONE_COMPLETED [MISSING — no alert type]
       │       ⇢ WhatsApp notification to project manager [MISSING]
       │       ⇢ Timeline update [MISSING MODULE]
       │       ⇢ Audit event: STAGE_COMPLETED [partially present]
       │
       ├── status: BLOCKED
       │       ⇢ Alert: STAGE_BLOCKED [MISSING]
       │       ⇢ Delay tracking [MISSING MODULE]
       │
       └── activity feed (photos, warehouse events, audit)
```

---

## Section 3 — Financial Chain

```
BOQ Items (planned_total = rate × quantity)
       ↓ (plan)
       ↓
┌──────────────────────────────────────────────────────┐
│                  COST SUMMARY                        │
│  = BOQ budget                                        │
│  + payments (procurement spend)                      │
│  + job card labour                                   │
│  + subcontractor work done                           │
│  + fuel costs                                        │
│  + vehicle repair costs                              │
│  + extra/breakage MR items                           │
│  ⇢ MISSING: workshop invoices                        │
│  ⇢ MISSING: expenses                                 │
│  ⇢ MISSING: municipality invoice income              │
└──────────────────────────────────────────────────────┘
       ↓
Dashboard (financial section)
       ↓
Management reports
       ↓
⇢ Cash Flow Forecast [MISSING MODULE]
```

---

## Section 4 — Workshop Chain (Isolated)

```
Workshop Categories
       ↓
Workshop Items (stock)
       ↓
Workshop Supplier Links → Suppliers [partially]
       ↓
Workshop MR → Workshop MR Votes → Workshop MR Approvals
       ↓ (approved)
Workshop Email to Suppliers [via email_service]
       ↓ (supplier replies — currently MANUAL)
Workshop Quotes → Workshop Quote Votes
       ↓ (approved)
Workshop PO → Workshop PO Email [via email_service]
       ↓
Workshop Invoice
       ↓
Workshop Delivery Note
       ↓
Workshop Issuances (stock consumed)

[ZERO connection to main Cost Summary, Payments, or Stock]
```

---

## Section 5 — Vehicle & Fuel Chain

```
Vehicles (project/site assigned)
       ↓
       ├── Fuel Logs → FuelDeliveries (bulk fill)
       │       ↓
       │   Cost Summary (fuel_cost line)
       │
       ├── Vehicle Costs (general costs)
       │       ↓
       │   Cost Summary (vehicle_repair line)
       │
       └── Repair Jobs (status-driven)
               ↓ (quote submitted)
           Quote Approval (3-stage manual)
               ↓ (approved)
           Invoice Uploaded
               ↓
           ⇢ VehicleCost created [MISSING — not auto-created]
           ⇢ Supplier Invoice linked [MISSING — not linked to invoices table]
           ⇢ Payment created [MISSING]

[Workshop for vehicle parts is SEPARATE — no link to Repair Jobs]
```

---

## Section 6 — Notification & Alert Chain

```
Business Event (any module)
       ↓ (enqueue_direct)
System Alert (type, severity, project scope)
       ↓ (enqueue_for_alert)
Notification Queue (per recipient, per channel)
       ↓ (asyncio drain loop or cron)
WhatsApp Send (template → free-form → FAILED)
       ↓ (Meta webhook callback)
Notification Queue (status: SENT/FAILED/DELIVERED/READ)
       ↓ (recipient replies ACK)
WhatsApp Webhook Handler
       ↓ (acknowledge_by_phone)
Notification Queue (status: ACKNOWLEDGED)
Alert Recipients (last_inbound_at updated for 24h window)
System Alert (status: ACKNOWLEDGED → RESOLVED)

[Proactive checks — all MANUAL currently]:
POST /alerts/scan → 6 checks → System Alerts → Notification Queue
POST /internal/scan-payment-due → Payment Due alerts → Notification Queue
POST /internal/send-daily-summary → Daily summary → Notification Queue
```

---

## Section 7 — Document AI Chain

```
Incoming email arrives in Gmail
       ↓ [MANUAL TRIGGER]
POST /gmail/fetch → IncomingEmail + IncomingEmailAttachment
       ↓ [MANUAL TRIGGER per email]
POST /gmail/incoming/{id}/process
       ↓ (OCR pipeline)
Document Extraction (raw_text, extracted_json)
       ↓ (AI extraction)
Claude Haiku → AI extraction JSON (field confidence scores)
       ↓ (classify)
QUOTE → MRQuote (draft) → human confirms
INVOICE → Draft Invoice → human confirms
DELIVERY_NOTE → Draft DeliveryVerification → human confirms
       ↓ (human confirms)
Actual records created in respective tables
```

---

## Section 8 — Audit Chain

```
Any significant business action
       ↓
audit_service.write_event(action, entity_type, entity_id, before, after)
       ↓
AuditEvent (immutable, append-only)
       ↓
GET /audit (OWNER_ONLY) — filter by actor/entity/action/date

[No downstream reactions from audit events — audit is terminal]
[Audit events are not consumed by analytics or reporting]
```

---

## Section 9 — User Access Chain

```
User (role: OWNER/OFFICE_ADMIN/OFFICE_USER/PROCUREMENT_LEAD/SITE_MANAGER/SITE_STAFF/...)
       ↓
UserProjectAccess (user → project mapping for SITE_* roles)
       ↓
UserSiteAccess (user → site mapping for SITE_* roles)
       ↓
check_project_access() in each route handler
       ↓
Project/Site scoped data access

[Access grants are not event-driven — no notification on grant/revoke]
[PROCUREMENT_LEAD role has no project-level scoping — sees all projects]
```

---

## Section 10 — Cross-Module Dependency Matrix

An **X** indicates that module A (row) directly depends on module B (column).  
A **→** indicates that A should trigger/update B but currently does not (gap).

| From ↓ / To → | Auth | Projects | Sites | Lots | BOQ | Stages | MR | PO | Delivery | Stock | Invoice | Payment | Alerts | Audit | Dashboard |
|--------------|------|----------|-------|------|-----|--------|----|----|----------|-------|---------|---------|--------|-------|-----------|
| Auth | — | — | — | — | — | — | — | — | — | — | — | — | — | X | — |
| Projects | X | — | X | X | X | — | X | X | X | X | X | X | → | X | X |
| Sites | X | X | — | X | — | X | X | X | X | X | — | — | — | X | → |
| Lots | X | X | X | — | X | X | X | X | X | X | — | — | — | X | → |
| BOQ | X | X | X | X | — | X | → | — | — | — | — | — | — | X | → |
| Stages | X | → | → | → | X | — | → | — | — | — | — | — | → | X | → |
| MR | X | X | X | X | → | X | — | X | — | — | — | — | X | X | → |
| PO | X | X | X | X | — | — | X | — | X | — | X | — | X | X | — |
| Delivery | X | X | X | X | — | — | — | X | — | X | → | — | X | X | — |
| Stock | X | X | X | X | → | — | — | — | X | — | — | — | → | X | → |
| Invoice | X | X | X | — | — | — | — | X | X | — | — | X | X | X | → |
| Payment | X | X | — | — | — | — | — | — | — | — | X | — | — | X | → |
| Workshop | X | → | — | — | — | — | — | — | — | — | — | — | — | — | → |
| Expenses | X | X | — | — | — | — | — | — | — | — | — | → | — | — | → |
| Muni Invoice | X | X | — | — | — | — | — | — | — | — | — | → | — | — | → |

**→ = should depend on but currently does not**

---

## Section 11 — Circular Dependencies

None found. The dependency graph is a DAG (directed acyclic graph) at the module level. All dependencies flow downward from the project/organizational entities through operational entities to financial records.

---

## Section 12 — Highest-Coupling Modules

These modules are depended upon by the most other modules. Any schema changes here have the widest blast radius.

| Module | Depended upon by | Risk level |
|--------|-----------------|-----------|
| `projects` | Every operational module | Very high |
| `suppliers` | MR, PO, Invoice, Payment, Delivery, Quotations, Analytics | Very high |
| `items` | BOQ, MR, MRQuote, PO, Delivery, Stock, UsageLogs | High |
| `users` | Every module (created_by, approved_by, recorded_by FKs) | Very high |
| `sites` | Lots, MR, PO, Delivery, Stock, Stage, Fuel, Job Cards, Work Done | High |
| `lots` | BOQ, Stage, Stock, Usage, MR (optional), Delivery, Job Cards, Work Done | High |
| `stage_master` | Stage Status, MR (stage_id), BOQ Sections, Job Cards, Work Done | Medium |

---

## Section 13 — Island Modules (Zero or Near-Zero Integration)

These modules exist but are not consumed by any core workflow:

| Module | What it connects to | What it doesn't connect to |
|--------|--------------------|-----------------------------|
| Workshop | Suppliers (email), Email service | Cost summary, Payments, Stock, Project, Repair Jobs |
| Expenses | Projects, Users | Payments, Cost summary, Suppliers |
| Municipality Invoices | Projects, Users | Payments, Financial reporting, Milestone tracking |
| Quotations (formal) | Suppliers, POs (weakly) | MR pipeline, Analytics |
| Procurement Reconciliation | PO, Invoice, Delivery | Is not created automatically |
| Admin Reconciliation | All tables (read-only check) | No triggered action from findings |
