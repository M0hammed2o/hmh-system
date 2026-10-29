# Future System Roadmap

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only. No implementation authorized.

This document organizes all identified improvements, missing modules, and future capabilities into a prioritized roadmap. Each item includes reason, business value, technical value, difficulty, risk, dependencies, and estimated implementation size.

---

## Roadmap Phases

| Phase | Timeframe | Focus |
|-------|-----------|-------|
| **Immediate** | Before next user-facing release | Data correctness, broken workflows, safety |
| **Next Phase** | Next major development cycle | Core integration gaps |
| **Medium Term** | 3–6 months | New modules completing the Construction OS |
| **Long Term** | 6–18 months | Enterprise scaling, multi-tenant, advanced features |
| **Future AI** | 12+ months | Predictive analytics, autonomous operations |

---

## IMMEDIATE — Before Next Release

These items represent correctness risks or broken core workflows. They should be fixed before adding any new features.

---

### IMM-001 — Fix Stock Balance Auto-Refresh

**Reason:** Materialized view is stale after every delivery and adjustment.  
**Business value:** Site managers and procurement team see accurate stock data.  
**Technical value:** Eliminates a class of silent data errors.  
**Difficulty:** Low  
**Risk:** Low — additive change only  
**Dependencies:** None  
**Estimated size:** 1–2 days  
**How:** PostgreSQL LISTEN/NOTIFY + background refresher, or convert to a regular view with application-layer caching.

---

### IMM-002 — Fix Invoice Status: Add PAID Transition

**Reason:** Invoices never show as PAID in the system, causing false overdue alerts.  
**Business value:** Correct outstanding balance view; accurate payment status for accounting.  
**Technical value:** Enables proof packs to correctly show closed invoices.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** Verify RecordStatus enum can add PAID without breaking existing client code  
**Estimated size:** Half-day

---

### IMM-003 — Schedule Proactive Alert Scan

**Reason:** All 6 proactive checks (low stock, overdue, stale MR, delivery without PO, etc.) only fire on manual trigger.  
**Business value:** Operations team is notified without manual intervention.  
**Technical value:** Minimal — reuses existing alert infrastructure.  
**Difficulty:** Tiny  
**Risk:** Very low — adds a cron endpoint call  
**Dependencies:** CRON_SECRET must be configured  
**Estimated size:** 2–4 hours

---

### IMM-004 — Fix summary_service.py to Use amount_paid

**Reason:** `summary_service.py:66` queries `Payment.amount` (legacy column) instead of `Payment.amount_paid`. (See Legacy_Field_Analysis.md Group E.)  
**Business value:** Daily summary shows correct payment totals.  
**Technical value:** Eliminates silent data inconsistency.  
**Difficulty:** Tiny  
**Risk:** Very low  
**Dependencies:** None  
**Estimated size:** 15 minutes

---

### IMM-005 — Schedule Gmail Polling

**Reason:** Supplier emails pile up unprocessed until someone manually triggers fetch.  
**Business value:** Procurement response times improve from hours/days to minutes.  
**Technical value:** Minimal — adds a cron endpoint.  
**Difficulty:** Low  
**Risk:** Low — additive  
**Dependencies:** IMAP credentials, CRON_SECRET  
**Estimated size:** Half-day

---

### IMM-006 — Auto-Process High-Confidence Email Attachments

**Reason:** Per-email processing is the highest-frequency manual operation in the system.  
**Business value:** 5–10 daily clicks eliminated in an active procurement period.  
**Technical value:** Exercises the existing OCR pipeline automatically.  
**Difficulty:** Low  
**Risk:** Low — draft results require human confirmation before any record is created  
**Dependencies:** IMM-005 (scheduled Gmail polling)  
**Estimated size:** 2–3 days

---

## NEXT PHASE — Core Integration Gaps

These items complete the integration between existing modules without adding new capabilities.

---

### NXT-001 — Milestone Completion Events

**What:** When a stage is COMPLETED:
- Create `MILESTONE_COMPLETED` SystemAlert
- Enqueue WhatsApp notification to project-scoped recipients
- Write specific audit event
- Check if all stages complete → auto-set `lots.status = COMPLETED`

**Business value:** Real-time visibility into construction progress. Project managers are notified as work happens.  
**Technical value:** Establishes the event-driven pattern for future automations.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** None  
**Estimated size:** 1 day

---

### NXT-002 — Persist Lot and Project Progress

**What:** Maintain denormalized `progress_pct` on `lots` and `projects` tables, updated whenever `project_stage_status` changes.

**Business value:** Consistent progress reporting across all endpoints. Dashboard accuracy.  
**Technical value:** Eliminates duplicate derivation logic and query inconsistencies.  
**Difficulty:** Low  
**Risk:** Low — additive columns  
**Dependencies:** Migration for new columns  
**Estimated size:** 1 day

---

### NXT-003 — Workshop Cost Integration

**What:** Include workshop PO and invoice totals in:
- `GET /projects/{pid}/cost-summary` as a "workshop" line
- Dashboard financial views
- Analytics

**Business value:** True project cost visibility. No more invisible workshop spend.  
**Technical value:** Eliminates the biggest cost reporting blindspot.  
**Difficulty:** Medium — requires workshop models to have `project_id` FK verified/added  
**Risk:** Medium — schema change if project_id not on workshop tables  
**Dependencies:** Verify or add `project_id` to `workshop_mrs`  
**Estimated size:** 2–3 days

---

### NXT-004 — Expense Integration into Cost Summary

**What:** Include approved expenses in cost summary and dashboard financial totals.

**Business value:** Staff expenses no longer invisible to project financial management.  
**Technical value:** Minor — one additional query in cost_summary_service.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** None  
**Estimated size:** Half-day

---

### NXT-005 — Auto-Update PO Received Quantities from Deliveries

**What:** When a delivery item is recorded with a `purchase_order_item_id`, update `purchase_order_items.quantity_received`.

**Business value:** POs show accurate receipt status. Over-delivery or under-delivery visible immediately.  
**Technical value:** Eliminates manual reconciliation of delivery vs PO quantities.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** None  
**Estimated size:** Half-day

---

### NXT-006 — Automatic Invoice Match Attempt

**What:** When an invoice is created (or a delivery is received), automatically attempt matching if a PO and delivery exist for the same supplier+project.

**Business value:** Accounts team no longer needs to manually match each invoice.  
**Technical value:** Exercises existing matching logic.  
**Difficulty:** Low  
**Risk:** Low — match result is informational; no money moves  
**Dependencies:** None  
**Estimated size:** 1 day

---

### NXT-007 — Subcontractor and Job Card Payment Records

**What:** When a job card or work done record is marked PAID, create a corresponding record in the `payments` table with a payment_method indicating the type.

**Business value:** Complete supplier payment history. Accurate outstanding balances for suppliers who do both procurement and subcontractor work.  
**Technical value:** Eliminates the PAID status vs payment record inconsistency.  
**Difficulty:** Medium — requires determining what invoice or reference to link the payment to  
**Risk:** Medium — could double-count if existing work done records are already accounted for  
**Dependencies:** Business decision: how to link work done payments to supplier invoice records  
**Estimated size:** 1–2 days

---

### NXT-008 — Lot Status Auto-Completion Chain

**What:** When all stage statuses for a lot are COMPLETED, automatically set `lots.status = COMPLETED`. When all lots for a site are COMPLETED, flag the site. When all sites for a project are COMPLETED, prompt project closure.

**Business value:** Project managers see accurate lot/site/project completion state without manual updates.  
**Technical value:** Establishes the cascading status update pattern.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** NXT-001 (milestone completion events)  
**Estimated size:** 1 day

---

### NXT-009 — Unify Reconciliation

**What:** Consolidate the three parallel reconciliation systems (InvoiceMatchingResult, ProcurementReconciliation, Admin Reconciliation) into one unified workflow.

**Business value:** One place to see if a procurement cycle is closed.  
**Technical value:** Eliminates confusion and duplicate data entry.  
**Difficulty:** High — schema change, data migration  
**Risk:** Medium — existing reconciliation records must be migrated  
**Dependencies:** Business decision on which reconciliation model to keep  
**Estimated size:** 3–5 days

---

## MEDIUM TERM — New Modules Completing the Construction OS

These are new functional capabilities that are currently absent.

---

### MED-001 — Timeline & Gantt Chart Module

**Why this next:** This is the most commonly mentioned missing feature in any construction management platform. Without a timeline, the project has no schedule visibility.

**What it provides:**
- Planned start and end dates per stage per lot
- Gantt chart view (read-only for SITE_STAFF, editable for OFFICE_ADMIN)
- Baseline schedule vs actual progress
- Delay detection when actual progress falls behind plan
- Critical path identification

**Business value:** Project managers can answer "Are we on schedule?" and "Which lots are delayed?"  
**Technical value:** Extends `project_stage_status` with `planned_start`, `planned_end`, `actual_start`, `actual_end`.  
**Difficulty:** High  
**Risk:** Low — new module, no existing data to break  
**Dependencies:** NXT-001 (milestone completion events), NXT-002 (progress persistence)  
**Estimated size:** 2–3 weeks (full module: model + routes + service + frontend)

---

### MED-002 — Weekly Work Planning Module

**What:** A weekly plan per site: "This week we will work on lots X, Y, Z, stages A, B."

**Business value:**
- Foreman can communicate the week's work targets
- Week-end review can compare plan vs actual
- Labour planning enables smarter material requests

**Technical value:** Creates a structured schedule that drives material pre-positioning.  
**Difficulty:** Medium  
**Risk:** Low  
**Dependencies:** MED-001 (Timeline)  
**Estimated size:** 1–2 weeks

---

### MED-003 — Cash Flow Module

**What:** Projected outflows (when invoices are due) vs projected inflows (when municipality invoices are expected to be paid). Cash position over 90 days.

**Business value:** Owner can answer "Will we have enough cash to pay suppliers next month?"  
**Technical value:** Reads from existing `invoices.due_date` and municipality invoice data.  
**Difficulty:** Medium  
**Risk:** Low  
**Dependencies:** IMM-002 (invoice PAID status), municipality invoice payment tracking  
**Estimated size:** 1–2 weeks

---

### MED-004 — Variation Orders Module

**What:** When work scope changes (more lots, different materials, changed specs), a variation order (VO) is raised against the original contract. VOs need approval and must update the BOQ.

**Business value:** Construction projects almost always have scope changes. Without VOs, the BOQ is wrong and costs are unattributed.  
**Technical value:** Extends BOQ module with a VO linkage.  
**Difficulty:** High  
**Risk:** Medium — changes BOQ structure  
**Dependencies:** Stable BOQ module (MED-001 timeline context)  
**Estimated size:** 2–3 weeks

---

### MED-005 — Resource Planning Module

**What:** Track which workers, vehicles, and equipment are assigned to which lots/sites on which days.

**Business value:** Avoids double-booking vehicles and workers. Enables resource utilization reporting.  
**Technical value:** Provides data for labour cost estimation and future AI scheduling.  
**Difficulty:** High  
**Risk:** Low  
**Dependencies:** MED-001 (Timeline), MED-002 (Weekly Work Plan)  
**Estimated size:** 3–4 weeks

---

### MED-006 — Quality Inspections & Snag Lists

**What:** After a stage is completed, a quality inspection is required before it can be CERTIFIED. Snag list items (defects found during inspection) must be resolved.

**Business value:** Quality control process formalized. Reduces rework disputes with municipalities.  
**Technical value:** Adds INSPECTION stage between COMPLETED and CERTIFIED.  
**Difficulty:** Medium  
**Risk:** Medium — changes stage status flow  
**Dependencies:** NXT-001, NXT-008  
**Estimated size:** 2 weeks

---

### MED-007 — Client Portal (Read-Only)

**What:** A read-only view for project owners/clients (municipality representatives) to see milestone progress, delivery counts, and high-level cost summary.

**Business value:** Client transparency builds trust; reduces "status update" calls.  
**Technical value:** Can reuse existing API endpoints with a new `CLIENT` role.  
**Difficulty:** Medium  
**Risk:** Low  
**Dependencies:** Stable milestone and cost summary modules  
**Estimated size:** 1–2 weeks

---

### MED-008 — Retention Tracking

**What:** Construction contracts typically withhold 5–10% of subcontractor payments as retention until final completion. Track retention amounts and release dates.

**Business value:** Correct subcontractor outstanding balance. No forgotten retention releases.  
**Technical value:** Adds `retention_pct` and `retention_released_at` to work done and job card models.  
**Difficulty:** Medium  
**Risk:** Low  
**Dependencies:** NXT-007 (subcontractor payments in payments table)  
**Estimated size:** 1 week

---

### MED-009 — Safety Incidents Module

**What:** Record site safety incidents (injuries, near-misses, equipment damage). Track corrective actions.

**Business value:** Legal compliance. Pattern identification for prevention.  
**Technical value:** New module; no existing schema conflict.  
**Difficulty:** Low  
**Risk:** Low  
**Dependencies:** None  
**Estimated size:** 1 week

---

### MED-010 — Move Workshop Into Main Procurement Pipeline

**What:** Retire the parallel workshop pipeline. Workshop MRs should use the main `material_requests` table with a `source: WORKSHOP` flag. Workshop items should use the main item catalog.

**Business value:** All costs visible in one place. No duplicate data entry.  
**Technical value:** Eliminates 14 workshop-specific tables and the entire duplicate code path.  
**Difficulty:** Very high — significant migration, data consolidation  
**Risk:** High — must preserve existing workshop data  
**Dependencies:** NXT-003 (workshop cost integration) proves feasibility  
**Estimated size:** 4–6 weeks (with migration)

---

## LONG TERM — Enterprise Scale

### LT-001 — Multi-Tenant Architecture

**What:** Support multiple construction companies on one platform, each with full data isolation.

**Business value:** Transform from single-company tool to a SaaS product serving hundreds of companies.  
**Technical value:** Requires row-level security in PostgreSQL or separate schemas per tenant.  
**Difficulty:** Very high — fundamental architecture change  
**Risk:** Very high — touches every table and query  
**Dependencies:** All current features stable; clean schema  
**Estimated size:** 3–6 months

---

### LT-002 — Event-Driven Architecture (Event Bus)

**What:** Replace imperative service calls with an event bus (Redis Streams or PostgreSQL LISTEN/NOTIFY at first; Kafka at scale).

**Business value:** Reliably connects all modules. New consumers can be added without touching existing code.  
**Technical value:** Foundation for AI analytics and real-time features.  
**Difficulty:** High  
**Risk:** Medium — gradual migration possible  
**Dependencies:** Stable core modules  
**Estimated size:** 1–3 months (incremental)

---

### LT-003 — Mobile Application (PWA or Native)

**What:** A mobile-first interface for site staff to: record deliveries, mark stage progress, upload photos, record fuel, record usage.

**Business value:** Site staff currently use the web app on phones (likely). A native or PWA experience with offline support would be transformative.  
**Technical value:** API is already mobile-friendly; needs offline support layer.  
**Difficulty:** High (native); Medium (PWA)  
**Risk:** Low — additive  
**Dependencies:** Stable API  
**Estimated size:** 2–4 months

---

### LT-004 — Real-Time Dashboard (WebSockets / SSE)

**What:** Push dashboard updates to connected browsers when business events occur.

**Business value:** Dashboard always reflects current state without page refresh.  
**Technical value:** Requires WebSocket or SSE support in FastAPI (already supported).  
**Difficulty:** Medium  
**Risk:** Low — additive  
**Dependencies:** LT-002 (event bus) or direct asyncio publish  
**Estimated size:** 2–4 weeks

---

### LT-005 — Payroll Integration (API Bridge)

**What:** While payroll remains external, build an export bridge: export approved job cards and work done as a payroll input file in the external system's required format.

**Business value:** Eliminates manual payroll data entry from HMH System records.  
**Technical value:** API bridge pattern — no deep integration needed.  
**Difficulty:** Low–Medium (depends on external system format)  
**Risk:** Low  
**Dependencies:** Stable job card and work done approvals  
**Estimated size:** 1–2 weeks

---

## FUTURE AI — Predictive and Autonomous

### AI-001 — Predictive Project Delay Detection

**What:** ML model trained on historical stage completion times, lot types, material request lead times, and seasonal patterns. Predicts which lots are likely to fall behind schedule before they actually do.

**Business value:** Proactive intervention opportunity. Prevents cascading delays.  
**Prerequisites:** MED-001 (Timeline module with actual vs planned dates), 6+ months of historical data  
**Estimated size:** 1–2 months (model development)

---

### AI-002 — Intelligent Invoice Processing (Zero-Touch)

**What:** Fully automatic invoice creation from incoming emails — no human confirmation required for high-confidence matches (>95% confidence from AI extraction).

**Business value:** Accounts team handles exceptions only, not every invoice.  
**Prerequisites:** IMM-006 (auto-process emails), 3+ months OCR feedback data  
**Estimated size:** 1 month (incremental improvement on IMM-006)

---

### AI-003 — Smart Material Request Generation

**What:** Based on upcoming scheduled stages (from Timeline), automatically suggest a Material Request with quantities derived from the BOQ for that stage.

**Business value:** Site staff don't need to manually look up what materials are needed — the system suggests it.  
**Prerequisites:** MED-001 (Timeline), stable BOQ module  
**Estimated size:** 2–3 weeks (prompt engineering + suggestion API)

---

### AI-004 — Supplier Price Intelligence

**What:** Analyze historical quote data to detect when a supplier's price has increased significantly versus market. Alert procurement when a quoted price is above the 90th percentile for that item.

**Business value:** Automatic negotiation leverage. Prevents overpaying for materials.  
**Prerequisites:** Sufficient quote history (6+ months), AI price comparison model  
**Estimated size:** 2–4 weeks

---

### AI-005 — Conversational Project Assistant (WhatsApp / Chat)

**What:** A natural language interface: "What's the progress on Project X?" → AI queries the database and responds. "What materials are we waiting for?" → AI queries open POs and responds.

**Business value:** Management can query the system without opening the web app.  
**Prerequisites:** LT-002 (event-driven architecture for context), Claude API integration  
**Estimated size:** 1–2 months

---

### AI-006 — Anomaly Detection Across All Operations

**What:** ML-based anomaly detection across fuel logs, delivery quantities, payment amounts, and usage rates. Flags unusual patterns that may indicate errors or fraud.

**Business value:** Governance and fraud prevention at scale.  
**Prerequisites:** 1+ year of data, LT-001 (multi-tenant data for training scale)  
**Estimated size:** 2–3 months

---

## Roadmap Summary

| Phase | Items | Est. Total |
|-------|-------|-----------|
| Immediate | IMM-001 through IMM-006 | 1–2 weeks |
| Next Phase | NXT-001 through NXT-009 | 4–6 weeks |
| Medium Term | MED-001 through MED-010 | 4–6 months |
| Long Term | LT-001 through LT-005 | 6–12 months |
| Future AI | AI-001 through AI-006 | 6–12 months (after prerequisites) |
