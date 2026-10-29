# State Machine Audit

**Date:** 2026-07-16  
**Author:** Architecture Audit — Level 4  
**Classification:** L0 — Documentation only. No code changes.  
**Evidence basis:** Direct repository inspection of all model files, service files, and route handlers.

---

## Overview

A state machine audit examines every major business entity's lifecycle states, the transitions between them, and the quality of those transitions (guards, audit events, notifications). A well-designed state machine has:

- A clear starting state and at least one terminal state
- Explicit guards that prevent illegal transitions
- Audit events on every state-changing mutation
- Notifications to relevant stakeholders where appropriate
- No dead states (states with no exit)
- No orphan states (states reachable but never set)

This audit covers 17 entities. Each entry records the current implementation as verified from the repository, followed by findings.

---

## Rating Scale

| Rating | Meaning |
|--------|---------|
| **CRITICAL** | Missing guard allows data corruption; or terminal state produces invisible side-effect |
| **HIGH** | Missing transition blocks a real workflow; or state is permanently orphaned |
| **MEDIUM** | Missing audit coverage; or notification gap on important event |
| **LOW** | Minor label inconsistency or cosmetic enum mismatch |

---

## SM-01 — MaterialRequest

**Model file:** `app/models/material_request.py`  
**Service:** `app/services/mr_service.py`  
**Status field:** `RecordStatus` shared enum

### State Diagram

```
                    ┌──────────────────────────┐
                    │           DRAFT           │
                    └──────────────────────────┘
                          │ submit_request()
                          ▼
            ┌─────────────────────────────┐
            │          SUBMITTED          │ ← if not over_boq
            └─────────────────────────────┘
            │                             │
            │ cast_staff_vote()           │ reject_request()
            │ (count >= 3)                ▼
            ▼                         REJECTED [TERMINAL]
     STAFF_APPROVED
            │
            │ approve_request() / procurement_lead_approve()
            ▼
         APPROVED ──────────────────────► CONVERTED_TO_PO [TERMINAL]
                                          (via convert_to_po())

            ┌─────────────────────────────┐
            │      PENDING_APPROVAL       │ ← if over_boq
            └─────────────────────────────┘
            (same transitions as SUBMITTED)

Any non-terminal → CANCELLED (force required if ORDERED+)
```

### Orphan States

| State | Status | Finding |
|-------|--------|---------|
| `ORDERED` | **ORPHAN** | No service method sets MR to ORDERED. The MR goes APPROVED → CONVERTED_TO_PO. This state is on the shared enum but unreachable for MaterialRequest. |
| `PARTIALLY_RECEIVED` | **ORPHAN** | Delivery service updates PO status, not MR status. No code path sets MR to PARTIALLY_RECEIVED. |
| `RECEIVED` | **ORPHAN** | Same issue as PARTIALLY_RECEIVED. |

**Severity: HIGH** — Three orphan states inflate the enum and confuse future developers.

### Missing Transitions

| Gap | Finding | Severity |
|-----|---------|---------|
| No REJECTED → DRAFT re-submission | Once rejected, an MR cannot be revised and resubmitted. A new MR must be created. | MEDIUM |
| No APPROVED → ORDERED | There is no intermediate state between approval and PO conversion. An MR cannot be "sent to supplier" without a PO. | LOW |
| CANCELLED has no notification | `cancel_request()` writes audit=UPDATE but sends no notification to the requester or approvers. | MEDIUM |

### Audit Coverage

| Transition | Audit Written |
|------------|--------------|
| DRAFT creation | Yes — CREATE |
| DRAFT → SUBMITTED | Yes — UPDATE |
| → STAFF_APPROVED | Yes — APPROVE |
| → APPROVED | Yes — APPROVE |
| → REJECTED | Yes — REJECT |
| → CANCELLED | Yes — UPDATE (reason not captured in after_value) |
| → CONVERTED_TO_PO | Yes — CREATE (on new PO) |

### Notification Coverage

| Transition | Notification |
|------------|-------------|
| → SUBMITTED | Yes — enqueue_for_alert(MR_SUBMITTED) |
| → APPROVED | Yes — enqueue_direct(MR_APPROVED) |
| → REJECTED | Partial — in_app SystemAlert only; no WhatsApp |
| → CANCELLED | **MISSING** |
| → STAFF_APPROVED | **MISSING** |

---

## SM-02 — MRQuote

**Model file:** `app/models/mr_quote.py`  
**Route:** `app/api/v1/procurement_pipeline.py`  
**Status field:** `String(20)` — not a typed enum

### State Diagram

```
         PENDING
            │
            ├── vote_quote() count >= 3 ──────► APPROVED [TERMINAL]
            │
            ├── approve_quote() (override) ──► APPROVED [TERMINAL]
            │
            └── (no reject path found) ───────► ???
```

### Critical Findings

| Finding | Severity |
|---------|---------|
| **No REJECTED state transition**: `reject_quote()` does not exist as a route or service method. A quote cannot be rejected — it stays PENDING indefinitely. | CRITICAL |
| **No audit events**: Zero calls to `audit_service.write_event()` for any MRQuote transition. Quote approvals are completely invisible to the audit log. | HIGH |
| **No notifications**: Neither vote counting nor approval sends any notification to the MR requestor or procurement lead. | MEDIUM |
| **APPROVED is a dead end**: Once approved, the quote status never changes even after a PO is created from it. The link between quote approval and PO creation has no status feedback loop. | MEDIUM |
| **Untyped status string**: Status is `String(20)` rather than a typed enum. A typo would produce a silent invalid state with no database-level rejection. | LOW |

---

## SM-03 — PurchaseOrder

**Model file:** `app/models/purchase_order.py`  
**Service:** `app/services/po_service.py`  
**Status field:** `RecordStatus` shared enum

### State Diagram

```
         DRAFT ──────► APPROVED (via approve_po())
                            │
                            ▼
                          SENT (via send_po_email())
                            │
                            ▼
                   SUPPLIER_CONFIRMED
                            │
                            ▼
                    PARTIALLY_RECEIVED ──► RECEIVED [semi-terminal]
                   (set by delivery_service)
```

### Orphan States

| State | Finding | Severity |
|-------|---------|---------|
| `SUBMITTED` | No service method transitions a PO to SUBMITTED. PO is created at DRAFT and immediately approved. | HIGH |
| `ORDERED` | No service method sets ORDERED on a PO. | HIGH |
| `INVOICED` | No service sets INVOICED on a PO. PO does not react when a linked invoice is created. | MEDIUM |
| `PARTIALLY_PAID` / `PAID` | Invoice payment status does not propagate back to PO. | MEDIUM |

### Missing Transitions

| Gap | Severity |
|-----|---------|
| No audit event on PO creation | MEDIUM |
| No audit event on `update_po()` | MEDIUM |
| No guard on `send_po_email()` — any status can be "sent" | MEDIUM |
| `RECEIVED` has no downstream trigger to create reconciliation | HIGH |

---

## SM-04 — Delivery / DeliveryNote

**Model file:** `app/models/delivery.py`  
**Service:** `app/services/delivery_service.py`  
**Status field:** `delivery_status: String`, default=RECEIVED

### State Diagram

```
         [NEW] ──► RECEIVED (full delivery)
                 ──► PARTIALLY_RECEIVED (shortage)
```

### Critical Findings

| Finding | Severity |
|---------|---------|
| **No creation audit event**: `create_delivery()` does not call `audit_service.write_event()`. | HIGH |
| **No DRAFT or PENDING state**: A delivery is immediately RECEIVED upon creation. There is no pre-receipt verification step. | MEDIUM |
| **No DISPUTED state**: If a delivery is incorrect or damaged, there is no state to mark it as disputed. The only option is to record a short delivery (partial). | MEDIUM |
| **Materialized view not refreshed on partial**: `POST /stock/refresh-balances` must be manually called after `PARTIALLY_RECEIVED`; stock decisions can be made on stale data. | CRITICAL (see AUT-001 in Automation_Opportunities.md) |

---

## SM-05 — Invoice

**Model file:** `app/models/invoice.py`  
**Service:** `app/services/invoice_service.py` + `app/services/payment_service.py`  
**Status field:** `String`, computed by `_recalculate_invoice_status()`

### State Diagram

```
         DRAFT ──────────────────────────────────────────┐
            │                                            │
            │ (payment created)                          │ (no payment)
            ▼                                            │
         MATCHED ──► PARTIALLY_PAID ──► PAID [TERMINAL] │
                                    ──► OVERPAID         │
                                                         │
                    (status computed automatically       │
                     by payment_service, not set         │
                     explicitly by any route)            │
```

### Critical Findings

| Finding | Severity |
|---------|---------|
| **Status is computed, never guarded**: `_recalculate_invoice_status()` silently overwrites the status on every payment mutation. No explicit state machine protects against illegal transitions (e.g., going from PAID back to DRAFT). | HIGH |
| **APPROVED_FOR_PAYMENT state missing**: Referenced in `Automation_Opportunities.md` (AUT-009) as a trigger for reconciliation, but this state does not exist in the model or service. The payment approval step is absent. | HIGH |
| **No audit on status recalculation**: When `_recalculate_invoice_status()` transitions an invoice from MATCHED → PAID, no audit event is written. | HIGH |
| **No audit on `update_invoice()`**: Direct field edits produce no audit trail. | MEDIUM |
| **OVERPAID is a dead-end terminal**: Once OVERPAID, there is no refund, credit note, or recovery workflow. | MEDIUM |

---

## SM-06 — Payment

**Model file:** `app/models/payment.py`  
**Service:** `app/services/payment_service.py`  
**Status field:** `PaymentStatus` enum — PENDING, APPROVED, PAID, FAILED, CANCELLED

### State Diagram

```
Normal path:  [NEW] ──► PENDING ──► APPROVED ──► PAID [TERMINAL]
                                               ──► FAILED [TERMINAL]
                                               ──► CANCELLED [TERMINAL]

Labour path (JobCard/WorkDone):
              [NEW] ──► PAID (created directly as PAID, skipping PENDING+APPROVED)
```

### Critical Findings

| Finding | Severity |
|---------|---------|
| **Two creation paths with different initial states**: A payment from `payment_service.create_payment()` starts at PENDING; a payment from `job_card_service.mark_paid()` is created directly as PAID. These represent different business semantics (pending payment vs. recorded past payment) but use the same model with different starting states and no guard distinguishing them. | HIGH |
| **No audit on `update_payment()`**: Approvals, cancellations, and failures produce no audit event. | HIGH |
| **APPROVED → PAID transition not enforced**: The `update_payment()` function sets status directly without checking the current state. A FAILED payment could be set to PAID with no guard. | MEDIUM |

---

## SM-07 — WarehouseTransfer

**Model file:** `app/models/warehouse_transfer.py`  
**Service:** `app/services/warehouse_transfer_service.py`  
**Status field:** `WarehouseTransferStatus` (local enum) — PENDING, EXECUTED, REJECTED

### State Diagram

```
         PENDING ──► EXECUTED [TERMINAL] (via vote count >= 3 or override_approve)
                 ──► REJECTED [TERMINAL] (via reject_transfer)
```

### Assessment

**This is the best state machine in the codebase.** Clean terminal states, re-verification of stock at execution time, stock ledger entries on EXECUTED, and audit events on create/reject/execute.

| Finding | Severity |
|---------|---------|
| No notification after EXECUTED — receiving project manager not informed | MEDIUM |
| `WarehouseTransferStatus` is a local enum not in `enums.py` — inconsistent with pattern | LOW |

---

## SM-08 — JobCard

**Model file:** `app/models/job_card.py`  
**Service:** `app/services/job_card_service.py`  
**Status field:** `JobCardStatus` — DRAFT, SUBMITTED, SITE_APPROVED, OFFICE_APPROVED, OWNER_APPROVED, PAYMENT_APPROVED, PAID, REJECTED

### State Diagram

```
DRAFT ──► SUBMITTED ──► SITE_APPROVED ──► OFFICE_APPROVED ──► OWNER_APPROVED ──► PAYMENT_APPROVED ──► PAID [TERMINAL]
  │           │               │                  │                                       │
  │           │               │                  └──► PAYMENT_APPROVED (if !owner_req)   │
  │           └───────────────┴──────────────────────────────────────────────────────────┴──► REJECTED [semi-terminal]
  └───────────────────────────────────────────────────────────────────────────────────────────► REJECTED
```

### Assessment

**Second best state machine after WarehouseTransfer.** Uses a shared `_transition()` helper that enforces the from-state guard and writes an audit event on every transition.

| Finding | Severity |
|---------|---------|
| No notification on any transition — site staff who submitted a job card get no feedback until payment. | HIGH |
| REJECTED is semi-terminal: no re-submission path exists. A rejected job card requires a new one to be created. | MEDIUM |
| `OWNER_APPROVED` is optional (controlled by `owner_approval_required` flag on the record). This bypasses a state, meaning the effective state machine differs per record — not visible from status alone. | MEDIUM |
| PAID creates a Payment record but with no link back to the JobCard id in any foreign key on the Payment model. | HIGH |

---

## SM-09 — SubcontractorWorkDone

**Model file:** `app/models/work_done.py`  
**Service:** `app/services/work_done_service.py`  
**Status field:** `WorkDoneStatus` — DRAFT, SUBMITTED, SITE_APPROVED, OFFICE_APPROVED, PAID, REJECTED

### State Diagram

```
DRAFT ──► SUBMITTED ──► SITE_APPROVED ──► OFFICE_APPROVED ──► PAID [TERMINAL]
  │           │               │                  │
  └───────────┴───────────────┴──────────────────┴──► REJECTED
                                                           │
                                                           └──► SUBMITTED (re-submission allowed)
```

### Assessment

Clean state machine with re-submission from REJECTED (better than JobCard). Uses the same `_transition()` helper pattern.

| Finding | Severity |
|---------|---------|
| PAID creates a Payment record but the payment is recorded as type LABOUR with no reference to the WorkDone entity id. Payment is orphaned from its source. | HIGH |
| No notifications on any transition. | HIGH |
| `_update_milestone_progress()` is called on PAID if `stage_status_id` is set, but this is optional and most records may not have it set. Progress update is not guaranteed. | MEDIUM |

---

## SM-10 — ProjectStageStatus (Milestone)

**Model file:** `app/models/stage.py`  
**Service:** `app/services/stage_service.py`  
**Status field:** `StageStatus` — NOT_STARTED, IN_PROGRESS, BLOCKED, AWAITING_INSPECTION, COMPLETED, CERTIFIED

### State Diagram

```
NOT_STARTED ──► IN_PROGRESS ──► AWAITING_INSPECTION ──► COMPLETED ──► CERTIFIED [TERMINAL]
                   │                                          │
                   └──► BLOCKED                              (no exit from CERTIFIED)
```

*Note: The upsert pattern allows any transition to any state; the diagram above shows intended flow, not enforced flow.*

### Critical Findings

| Finding | Severity |
|---------|---------|
| **No guard on status transitions**: `upsert_stage_status()` allows any state to go to any state (COMPLETED → NOT_STARTED is permitted for non-SITE_STAFF roles). | CRITICAL |
| **COMPLETED triggers nothing downstream**: No lot update, no project update, no WhatsApp notification, no audit event. This is the highest-impact missing automation in the system. | CRITICAL |
| **CERTIFIED has no inspection workflow**: CERTIFIED is meant to follow inspection/sign-off, but there is no inspector role, no inspection entity, and no inspection workflow. CERTIFIED is a dead-end label. | HIGH |
| **No audit events on any transition**: Stage status changes are completely invisible to the audit log. | HIGH |
| **BLOCKED creates an inline SystemAlert but no WhatsApp notification**: BLOCKED is a critical site-level event requiring management attention. | MEDIUM |
| **progress_pct is not persisted to lot**: Stage progress updates do not propagate to `lots.progress_pct`. | HIGH (see AUT-011 in Automation_Opportunities.md) |

---

## SM-11 — WorkshopMR

**Model file:** `app/models/workshop.py`  
**Service:** `app/services/workshop_service.py`  
**Status field:** `RecordStatus` — DRAFT, SUBMITTED, APPROVED, REJECTED

### Assessment

Structurally identical to MaterialRequest's core flow but with **zero audit coverage and zero notifications**. Every transition in the Workshop module is invisible to the audit log and produces no stakeholder communication.

| Finding | Severity |
|---------|---------|
| No audit events on any Workshop entity transition | CRITICAL |
| No notifications on any Workshop entity transition | HIGH |
| No email to suppliers on WorkshopMR approval (unlike main MR) | HIGH |
| Workshop module is architecturally isolated — see GAP-005 in Lifecycle_Gap_Analysis.md | CRITICAL |

---

## SM-12 — WorkshopQuote

**Status:** String(50) — "PENDING", "APPROVED", "REJECTED"  
**Same issues as SM-11.** Additionally: no re-quote workflow if REJECTED.

---

## SM-13 — WorkshopPurchaseOrder

**Status:** String(50) — "DRAFT", "SENT"  
**Same issues as SM-11.** Additionally: no SUPPLIER_CONFIRMED state (unlike main PO).

---

## SM-14 — WorkshopInvoice

**Status:** None  
WorkshopInvoice has no status field whatsoever. An invoice either exists or doesn't — there is no lifecycle at all. No PAID status, no DRAFT state, no approval step.

| Finding | Severity |
|---------|---------|
| No status field means no lifecycle, no auditability, no searchability by payment state | CRITICAL |

---

## SM-15 — MunicipalityInvoice

**Status field:** String(20) — "DRAFT", "FINALISED" (untyped string)

### Critical Findings

| Finding | Severity |
|---------|---------|
| FINALISED blocks edits but produces no downstream event — no payment created, no alert, no audit | HIGH |
| No audit events | HIGH |
| No notifications | HIGH |
| No PAID state — municipality invoices have no payment tracking | CRITICAL |
| Untyped string status | LOW |

---

## SM-16 — ExpenseRecord

**Status field:** String — "UPLOADED", "NEEDS_REVIEW", "APPROVED", "REJECTED", "PAID"

### Critical Findings

| Finding | Severity |
|---------|---------|
| No audit events on any transition | HIGH |
| No notifications on any transition | HIGH |
| PAID transition does not create a Payment record — expense payments are invisible to the financial ledger | CRITICAL |
| No link between an ExpenseRecord and a Payment entity | CRITICAL |

---

## SM-17 — Quotation (Formal Supplier Quotation)

**Model file:** `app/models/quotation.py`  
**Status field:** `QuotationStatus` — DRAFT, SENT, RECEIVED, APPROVED, REJECTED, EXPIRED

### Critical Findings

| Finding | Severity |
|---------|---------|
| Status is set directly by the caller with no guard — any state can jump to any state | CRITICAL |
| EXPIRED state is never auto-set — no scheduled job transitions SENT quotations past their expiry date | HIGH |
| No audit events | HIGH |
| No notifications | HIGH |
| This module has zero integration with the main MR procurement pipeline (see System_Integration_Audit.md) | HIGH |

---

## Summary: State Machine Health by Entity

| Entity | Guards | Audit | Notify | Dead States | Score |
|--------|--------|-------|--------|-------------|-------|
| MaterialRequest | ✓ Good | ✓ Good | Partial | 3 orphan | 7/10 |
| MRQuote | Partial | **NONE** | **NONE** | APPROVED dead-end | 3/10 |
| PurchaseOrder | Partial | Partial | Partial | 4 orphan | 5/10 |
| Delivery | Minimal | **NONE** on create | Partial | — | 4/10 |
| Invoice | **Computed** | **NONE** on recalc | Partial | — | 4/10 |
| Payment | Partial | **NONE** on update | Partial | — | 5/10 |
| WarehouseTransfer | ✓ Best | ✓ Good | Partial | — | **8/10** |
| JobCard | ✓ Good | ✓ Good | **NONE** | — | 7/10 |
| WorkDone | ✓ Good | ✓ Good | **NONE** | — | 7/10 |
| ProjectStageStatus | **NONE** | **NONE** | Partial | CERTIFIED dead | 2/10 |
| WorkshopMR | Partial | **NONE** | **NONE** | — | 2/10 |
| WorkshopQuote | Partial | **NONE** | **NONE** | — | 2/10 |
| WorkshopPO | **NONE** | **NONE** | **NONE** | — | 1/10 |
| WorkshopInvoice | N/A | N/A | N/A | No status field | 0/10 |
| MunicipalityInvoice | Partial | **NONE** | **NONE** | No PAID state | 2/10 |
| ExpenseRecord | Partial | **NONE** | **NONE** | PAID ≠ Payment | 2/10 |
| Quotation | **NONE** | **NONE** | **NONE** | EXPIRED never set | 1/10 |

**System average: 3.9/10**

---

## Structural Defects Across All State Machines

### D-01 — Shared Enum Pollution

`RecordStatus` is a shared enum used by MaterialRequest, PurchaseOrder, Delivery, Invoice, and Workshop entities. Each entity uses a different subset of states. This makes it impossible to reason about which states are valid for which entity from the enum definition alone.

**Recommendation:** Entity-specific enums (like `JobCardStatus`, `WorkDoneStatus`) are the correct pattern. Migrate all entities to their own typed enums.

### D-02 — Missing Canonical State Machine Guard

Neither `RecordStatus` nor any entity model enforces state machine transitions at the database or service layer. The only entities with enforced transitions are JobCard, WorkDone, and WarehouseTransfer, all of which use private `_transition()` helpers that check the current state before mutating.

**Recommendation:** Introduce a shared `transition(entity, from_states, to_state, actor_id, db)` utility that all services use. It handles: state guard, audit write, and timestamp stamping.

### D-03 — Audit Coverage is Entity-Dependent, Not Transition-Dependent

Whether an audit event is written depends on which module implements the transition, not on the architectural principle that "every state change produces an audit event." Workshop, Municipality Invoice, Quotation, and Expense entities have zero audit coverage.

**Recommendation:** Adopt Architecture Principle AP-02 (see `Architecture_Principles.md`): every status-changing mutation produces exactly one audit event. Make this a code review gate.

### D-04 — Notification Coverage is Inconsistent

Some entities notify on every important transition (MR, Payment), some notify on none (JobCard, WorkDone, Workshop). There is no architectural rule governing when a notification must be created.

**Recommendation:** Define a notification matrix (which role receives what event) and encode it in the architecture principles. Every terminal-state transition and every user-blocking event must produce a notification.
