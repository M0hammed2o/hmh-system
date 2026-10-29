# System Integration Audit

**Date:** 2026-07-15  
**Author:** Architecture Audit  
**Classification:** L0 — Documentation only.

This document audits every module in the HMH Construction OS for integration completeness. For each module, it answers: who creates the data, who consumes it, who updates it, who should receive it automatically, which downstream modules should react, and whether workflows stop prematurely.

---

## Module 1 — Authentication & Users

**Who creates:** OWNER creates users. Users create themselves via login.  
**Who consumes:** Every route. JWT token is the identity carrier.  
**Who updates:** OWNER updates user profiles. Users update own password.  
**Who should auto-receive:** N/A — auth events emit audit entries.  
**Downstream reactions:** Login creates no alert. Failed lockout creates no WhatsApp notification to admin.  

**Integration gaps:**
- User login / logout is audited, but no alert is created for multiple failed login attempts (account lockout)
- No notification when a user is created or deactivated
- Project/site access grants are not audited (`write_event` not confirmed in access grant routes)

**Assessment:** Isolated — auth is a utility layer, not a business process. No integration needed beyond current state, except security alerting for lockouts.

---

## Module 2 — Companies

**Who creates:** OFFICE_ADMIN+  
**Who consumes:** Supplier filtering (`/companies/{id}/suppliers/{sup_id}`). Projects linked via `company_id`.  
**Who updates:** OFFICE_ADMIN+  
**Who should auto-receive:** When a company is linked to a project, all suppliers for that company should automatically become available for that project.  

**Integration gaps:**
- `Verified:` Company-supplier restriction is applied in `get_project_suppliers()` but only enforced in supplier selection for MRs and POs, not in quote requests or email sending
- No audit events for company create/update/link/unlink (check required)
- Companies are not connected to the reporting or financial module in any meaningful way

**Assessment:** Underused module. Companies provide supplier scoping but the feature is not pervasive across all procurement flows.

---

## Module 3 — Projects

**Who creates:** OFFICE_ADMIN+  
**Who consumes:** Every module. Project is the top-level container.  
**Who updates:** OFFICE_ADMIN+  
**Who should auto-receive:** Dashboard should update in real time when project is created or status changes.  

**Downstream reactions that are missing:**
- When project.status changes to COMPLETED, no validation check runs
- No automatic project closure checklist
- No financial summary generated at project completion
- Dashboard is not event-driven — it re-queries on each request

**Assessment:** Central entity but passive container. The project entity should be the hub that aggregates status from all child modules.

---

## Module 4 — Sites

**Who creates:** OFFICE_ADMIN+  
**Who consumes:** Material requests, deliveries, stock, stage statuses, fuel logs, job cards, work done, user access  
**Who updates:** OFFICE_ADMIN+ for site config; site-scoped endpoints consume site_id  
**Who should auto-receive:** When a site is deactivated, all active users with site access should receive a notification  

**Integration gaps:**
- GPS coordinates (`gps_lat`, `gps_lng`) are captured on deliveries and site model but never used for any validation or map display
- Site `address` column is present in bootstrap but absent from production (Schema Reconciliation Report §2.1)
- No automatic notification when site is deactivated

**Assessment:** Well-integrated as a routing entity. No behavioral logic associated with site-level events.

---

## Module 5 — Lots & Lot Types

**Who creates:** OFFICE_ADMIN+ (manual or bulk generate)  
**Who consumes:** BOQ, stage statuses, stock, usage, material requests, deliveries  
**Who updates:** OFFICE_ADMIN+ and lot-type propagation  
**Who should auto-receive:** When all stages complete, lot should auto-transition to COMPLETED  

**Integration gaps:**
- `lots.status` (PENDING/IN_PROGRESS/COMPLETED) is never automatically updated — it must be set manually or remains PENDING
- No lot-level alert when a stage is blocked
- `lot_type_id` FK provides grouping but doesn't drive any automation beyond BOQ template propagation
- `boq_customized_at` is set when BOQ is customized — used for SAFE propagation mode — this is a good integration point but nothing else uses it

**Assessment:** Lot model is data-rich but action-poor. The lot is the correct unit of construction progress tracking but the system does not treat lot events as triggers for anything.

---

## Module 6 — BOQ (Bill of Quantities)

**Who creates:** OFFICE_ADMIN+ (CSV upload or manual)  
**Who consumes:** Stage statuses (seeded from BOQ sections), cost summary (budget calculation), material requests (over_boq flag), lot progress  
**Who updates:** OFFICE_ADMIN+ via items/adjustments  
**Who should auto-receive:** When BOQ is propagated, stage milestones should be created per lot. `Verified:` This DOES happen — `boq_template_service.clone_template_to_lots()` creates `ProjectStageStatus` rows.  

**Integration gaps:**
- BOQ budget is never checked at MR creation time — `over_boq` flag is set by the requesting user, not computed
- No hard stop when MR quantity exceeds BOQ planned quantity
- BOQ rate vs actual quote price is tracked (`boq_unit_price` on MRQuote) but not enforced or alerted
- Multiple BOQ versions can exist per project — the "active version" concept is implemented (`is_active_version` flag) but only one version can be active; no history comparison between versions

**Assessment:** BOQ is well-modeled but weakly enforced. It describes the plan but does not constrain execution.

---

## Module 7 — Stage Tracking (Milestones)

**Who creates:** BOQ template propagation (automatic) or manual upsert  
**Who consumes:** Lot progress, project progress, site dashboard activity feed, work done (linked via `stage_status_id`)  
**Who updates:** Site staff (progress %), office (complete, block, unblock)  
**Who should auto-receive:** Project manager (milestone completed), Timeline module (update schedule), Dashboard (real-time update)  

**Downstream modules that should react but don't:**
- Lot status (should auto-complete when all stages done)
- Project progress (should recompute when stage changes)
- Audit log (COMPLETED transition not specifically audited)
- WhatsApp notification (no MILESTONE_COMPLETED alert type exists)
- Timeline (module does not exist)
- Subcontractor work done (no auto-creation prompt when stage completes)

**Assessment:** The most underconnected core module. Milestone completion is the primary signal of construction progress, but it triggers nothing downstream.

---

## Module 8 — Material Requests

**Who creates:** SITE_STAFF, SITE_MANAGER, OFFICE_USER  
**Who consumes:** MRQuotes (child), POs (linked), email service (sends MR to suppliers), audit log, procurement pipeline  
**Who updates:** Status transitions driven by approval flow  
**Who should auto-receive:** Procurement team (new MR submitted), PROCUREMENT_LEAD (awaiting approval), suppliers (email sent on approval)  

**Downstream that works:**
- `Verified:` MR approval triggers email to suppliers (via `send_mr_approval_email`)
- `Verified:` Audit events written for MR state transitions
- `Verified:` MRQuote created from email OCR pipeline
- `Verified:` PO created from `finalize_pos` when quotes approved

**Downstream that is missing:**
- BOQ budget check at MR creation
- Dashboard "pending MRs" count is static — not event-driven
- No notification to the original requester when their MR is approved/rejected
- `stage_id` FK on MR is informational — does not update stage progress

**Assessment:** Best-integrated module in the system. The MR → Quote → PO pipeline is the platform's strongest workflow chain.

---

## Module 9 — Quotations (Formal)

**Who creates:** OFFICE_AND_ABOVE  
**Who consumes:** POs (`quotation_id` FK on `purchase_orders`)  
**Who updates:** OFFICE_AND_ABOVE  
**Who should auto-receive:** No clear downstream consumer  

**Integration gaps:**
- The `Quotation` model is separate from `MRQuote`. Both can lead to a PO but through different paths
- `quotation_id` on `purchase_orders` is SET NULL — when a quotation is deleted, the PO loses its quotation link silently
- No analytics for formal quotations; `procurement-analytics` uses `MRQuote` data only
- The quotation module has no approval workflow

**Assessment:** Underspecified module. Its relationship to the main MR → Quote → PO pipeline is unclear. Either unify with `MRQuote` or define a clear use case (formal supplier rate cards vs ad-hoc MR quotes).

---

## Module 10 — Purchase Orders

**Who creates:** Procurement team (manual) or automated from `finalize_pos`  
**Who consumes:** Deliveries, invoices, invoice matching, email logs, reconciliation  
**Who updates:** Status transitions, `quantity_received` (but not auto-updated from deliveries — see Gap AUT-025)  
**Who should auto-receive:** Supplier (email sent), warehouse team (expected delivery), project manager  

**Downstream that works:**
- `Verified:` PO email sent to supplier with PDF
- `Verified:` Delivery linked to PO via `purchase_order_id`
- `Verified:` Invoice linked to PO
- `Verified:` Proof pack aggregates PO + delivery + invoice

**Downstream that is missing:**
- `purchase_order_items.quantity_received` not auto-updated from deliveries
- No alert when `expected_delivery_date` passes with no delivery
- No automatic partial-delivery tracking (when supplier delivers in multiple batches against one PO)
- PO status does not auto-advance to DELIVERED or CLOSED

**Assessment:** Well-integrated at creation and email stage. Weak on post-send lifecycle tracking.

---

## Module 11 — Deliveries

**Who creates:** SITE_STAFF (via receive-with-document or manual)  
**Who consumes:** Stock ledger (RECEIPT entries), invoice matching, delivery verification  
**Who updates:** Delivery capture (photos, signature, GPS)  
**Who should auto-receive:** Warehouse team (stock updated), invoice processing team (ready to match), PO status updater  

**Downstream that works:**
- `Verified:` StockLedger RECEIPT entries created on delivery receipt
- `Verified:` Delivery note OCR pipeline produces DeliveryVerification

**Downstream that is missing:**
- `stock_balances` materialized view not refreshed
- `purchase_order_items.quantity_received` not updated
- No automatic invoice match attempt
- No automatic alert to office that a delivery was received (can be significant for large orders)

**Assessment:** Correctly integrated for stock entry. Missing downstream propagation for PO tracking and invoice matching.

---

## Module 12 — Stock & Warehouse

**Who creates:** Deliveries (RECEIPT), transfers (TRANSFER_IN/OUT), manual adjustments  
**Who consumes:** Warehouse views, stock balances, usage logs, allocation service, site dashboard  
**Who updates:** SITE_STAFF via issuances, usage logs, adjustments  
**Who should auto-receive:** Procurement team (low stock), site managers (transfer approved)  

**Integration gaps:**
- `Verified:` `stock_balances` view not auto-refreshed
- Low stock alert only fires on manual scan
- `boq_item_id` FK on stock_ledger and usage_logs links to BOQ — but this link is not used to check BOQ budget compliance
- Tool inventory (`workshop_items`) is separate from main stock system

**Assessment:** Core ledger model is correct (append-only, immutable entries). Gaps are in alerting and refresh automation.

---

## Module 13 — Invoices

**Who creates:** Office team (manual) or Gmail OCR auto-create  
**Who consumes:** Payments, invoice matching, proof packs, reconciliation, payment due scan  
**Who updates:** Match status, approval status  
**Who should auto-receive:** Accounts team (new invoice to process), PROCUREMENT_LEAD (invoice for approval)  

**Integration gaps:**
- Invoice status (`invoices.status`) does not include PAID — determining if an invoice is paid requires checking the payments table
- No automatic match attempt
- No automatic reminder to accounts when invoice is due within PAYMENT_DUE_DAYS (scan runs daily but only if scheduled)
- Invoice deletion leaves `InvoiceMatchingResult.delivery_id = NULL` — partial orphan

**Assessment:** Functional but missing automatic status transitions and lifecycle completion.

---

## Module 14 — Payments

**Who creates:** Office team (manual)  
**Who consumes:** Supplier outstanding balance, cost summary, payment report, reconciliation  
**Who updates:** N/A (payment records are immutable conceptually; update is available but should be rare)  
**Who should auto-receive:** Supplier (payment confirmation email?), accounts (payment recorded audit), dashboard (real-time update)  

**Integration gaps:**
- `Verified:` `summary_service.py:66` uses `Payment.amount` (legacy column) instead of `Payment.amount_paid` — data quality risk
- No automatic invoice status update when payment covers full amount
- Subcontractor and job card "payments" are not in the `payments` table
- No payment confirmation sent to supplier

**Assessment:** The actual payment module is simple (record payment → done) but the surrounding processes (auto-match, auto-close invoice, supplier notification) are missing.

---

## Module 15 — Reconciliation

**Who creates:** OFFICE_AND_ABOVE (manual)  
**Who consumes:** Management reporting, `GET /reconciliations/dashboard`  
**Who updates:** Office team  
**Who should auto-receive:** N/A — reconciliation is a review step  

**Integration gaps:**
- No automatic reconciliation creation
- Procurement reconciliation is separate from payment reconciliation — two different systems for the same concept
- `GET /admin/reconciliation` (integrity check) is a separate system again

**Assessment:** Three different reconciliation systems: ProcurementReconciliation, InvoiceMatchingResult (proof packs), and admin reconciliation check. These should be unified into one reconciliation workflow.

---

## Module 16 — Alerts & Notifications

**Who creates:** Business operations (via `enqueue_direct`), manual scan  
**Who consumes:** WhatsApp recipients, notification queue drain loop, webhook handler  
**Who updates:** WhatsApp ACK, user acknowledgement  
**Who should auto-receive:** All relevant role-holders in the project scope  

**Downstream that works:**
- `Verified:` asyncio drain loop sends notifications within 30 seconds
- `Verified:` 9-category subscription filtering works
- `Verified:` WhatsApp APPROVE/REJECT/ACK intent parsing works
- `Verified:` CRITICAL escalation: [0, 5, 15, 30, 60 min] retry schedule

**Integration gaps:**
- Many important events don't create alerts (see Lifecycle_Gap_Analysis.md §5)
- Alert scan must be manually triggered
- `SUPPLIER_MISMATCH` alert type defined in enum but scan logic not found

**Assessment:** Notification infrastructure is excellent. The gap is event coverage — the queue can deliver anything, but not enough business events create entries.

---

## Module 17 — Dashboard & Reporting

**Who creates:** N/A — computed  
**Who consumes:** Frontend (management UI)  
**Who updates:** N/A — re-queried on each request  

**Integration gaps:**
- All queries run on-the-fly — no caching; performance risk at scale
- Workshop costs, expenses, municipality invoice income are absent from all financial views
- Progress percentages are computed differently across different endpoints
- No real-time updates (WebSockets or SSE)
- Cost summary does not show actual vs forecast (only actual vs BOQ plan)

**Assessment:** Correct data sources, incomplete coverage, performance risk for scale.

---

## Module 18 — Fuel & Vehicles

**Who creates:** Site staff (fuel logs), office (vehicles, costs, repairs)  
**Who consumes:** Cost summary (fuel total, repair total), dashboard  
**Who updates:** Workshop team (repair workflow)  

**Integration gaps:**
- Vehicle costs (VehicleCost table) are separate from the payment system
- Repair jobs do not connect to supplier invoices or payments
- Fuel anomaly detection does not exist
- Workshop module and vehicle repair module are parallel but not integrated (a workshop MR for vehicle parts does not link to a repair job)

**Assessment:** Functional but isolated. Vehicle cost is tracked in its own silo with no connection to procurement, payments, or supplier management.

---

## Module 19 — Workshop

**Who creates:** Workshop team  
**Who consumes:** Workshop stock, workshop cost tracking  
**Who updates:** Workshop team  

**Integration gaps (critical):**
- Workshop costs invisible to cost summary
- Workshop invoices not in main invoice/payment system
- Workshop stock not in main stock system
- Workshop module has no `project_id` FK on its main tables — costs cannot be attributed to projects
- Workshop MRs not searchable from the main MR list
- `Verified (Likely):` Workshop items have their own categories, not shared with main item catalog

**Assessment:** Workshop module is an island. It duplicates the procurement pipeline without connecting to it. This is the biggest integration gap in the platform.

---

## Module 20 — Job Cards & Subcontractor Work Done

**Who creates:** Site staff (work done records), office (job cards)  
**Who consumes:** Cost summary (labour and subcontractor totals)  
**Who updates:** Approval workflow actors  

**Integration gaps:**
- Payment records for job cards and work done are not in the payments table
- Supplier balances don't include subcontractor payments
- Job cards linked to stages (`stage_id` FK) but stage progress not updated when job card completed
- No retention tracking

**Assessment:** Approval workflow is solid. Financial integration is absent.

---

## Module 21 — Gmail / Document AI

**Who creates:** Gmail IMAP pull (incoming emails), user uploads (vision endpoint)  
**Who consumes:** MR quote creation, draft invoice creation, document extractions  
**Who updates:** Human corrections to OCR output  

**Integration gaps:**
- Gmail fetch is manual (not scheduled)
- Per-email processing is manual
- Auto-created records are drafts requiring human confirmation — good design for accuracy
- No Gmail inbox cleanup after processing

**Assessment:** The OCR and document AI infrastructure is the most forward-thinking part of the system. The gap is automation of the triggering steps.

---

## Module 22 — WhatsApp

**Who creates:** Notification service (outbound), webhook (inbound)  
**Who consumes:** Alert recipients, notification queue  
**Who updates:** Recipient inbound timestamps (24h window)  

**Integration gaps:**
- WhatsApp can APPROVE/REJECT an MR but cannot: approve a payment, approve a transfer, query a stock balance, request a report
- No WhatsApp-to-email capability (recipient replies via WhatsApp, message is forwarded to supplier email)
- No WhatsApp group notifications (only individual messages)

**Assessment:** Excellent for inbound approval intent parsing. Expandable as a conversational interface.

---

## Module 23 — Expenses

**Who creates:** Staff (upload + OCR)  
**Who consumes:** Nothing currently  
**Who updates:** Office (approve/reject)  

**Integration gaps:**
- No connection to cost summary
- No connection to payments
- No supplier tracking on expenses (though construction expenses often have a payee)
- Expense categories don't exist

**Assessment:** Expenses are an orphaned module — collected but never reported.

---

## Module 24 — Municipality Invoices

**Who creates:** Office team  
**Who consumes:** Excel export only  
**Who updates:** Office team  

**Integration gaps:**
- No connection to payment received tracking
- No connection to project financial reporting
- Only Ethekweni template is hardcoded
- No integration with the main invoice/payment system

**Assessment:** A specialized data entry tool with no integration. Useful for Ethekweni billing workflow but isolated from everything else.

---

## Integration Score Per Module

| Module | Integration Score | Biggest Gap |
|--------|------------------|-------------|
| Authentication | 8/10 | No lockout alerts |
| Material Requests | 8/10 | No BOQ budget check |
| Purchase Orders | 7/10 | PO quantity_received not auto-updated |
| Deliveries | 7/10 | Stock view not auto-refreshed |
| Alerts/Notifications | 8/10 | Manual scan for proactive alerts |
| Invoices | 6/10 | No PAID status, no auto-match |
| Payments | 5/10 | Sub/job card payments not in payments table |
| Stock/Warehouse | 6/10 | Stale materialized view |
| BOQ | 6/10 | BOQ not enforced on procurement |
| Stage Tracking | 4/10 | Completion triggers nothing |
| Projects/Sites/Lots | 5/10 | Lot status never auto-updated |
| Dashboard | 5/10 | Missing workshop/expense costs |
| Fuel/Vehicles | 5/10 | Isolated from procurement |
| Workshop | 2/10 | Complete island — no integration |
| Expenses | 2/10 | Orphaned module |
| Municipality Invoices | 2/10 | No financial integration |
| Gmail/Document AI | 7/10 | Manual triggering |
| WhatsApp | 8/10 | Limited interaction patterns |
| Job Cards/Work Done | 5/10 | Payments not in payments table |
| Companies | 4/10 | Supplier restriction incomplete |
| Reconciliation | 4/10 | Three parallel systems |
| Quotations (formal) | 3/10 | Unclear purpose vs MRQuote |

**System average: 5.4/10**
