# Duplicate Business Logic Report

**Date:** 2026-07-16  
**Author:** Architecture Audit — Level 4  
**Classification:** L0 — Documentation only. No code changes.  
**Evidence basis:** Direct repository inspection of all service, model, and route handler files.

---

## Purpose

Duplicate business logic is code that implements the same computation, workflow, or rule in more than one location. It is the most common cause of:

- Silent divergence (one implementation is updated, the other is not)
- Inconsistent behaviour for users in different parts of the system
- Increased maintenance burden when rules change
- Test coverage gaps (one copy is tested, the other is not)

This document identifies every confirmed instance of duplicate business logic in the HMH Construction OS, its risk level, and the recommended canonical location.

---

## Category A — Vote-Based Approval Workflows

### Finding DUP-A01 — Five Independent Implementations of the Same Vote Pattern

**Severity: CRITICAL**

The following five business entities all use a "three-staff-vote with optional senior override" approval pattern. Each implementation is independent, in a different file, with different constants and slightly different internal logic.

| Instance | Entity | Vote Table | Threshold Constant | Location |
|----------|--------|------------|-------------------|----------|
| A-1 | MaterialRequest | `MRApproval` | `STAFF_VOTES_REQUIRED = 3` (mr_service.py) | `app/services/mr_service.py:557` |
| A-2 | WarehouseTransfer | `WarehouseTransferVote` | `TRANSFER_VOTES_REQUIRED = 3` (warehouse_transfer.py:24) | `app/services/warehouse_transfer_service.py:157` |
| A-3 | WorkshopMR | `WorkshopMRApproval` | `WORKSHOP_VOTES_REQUIRED = 3` (workshop_service.py:28) | `app/services/workshop_service.py:281` |
| A-4 | WorkshopQuote | `WorkshopQuoteApproval` | `WORKSHOP_VOTES_REQUIRED = 3` (same constant reused) | `app/services/workshop_service.py:476` |
| A-5 | MRQuote | `MRQuoteVote` | `QUOTE_VOTES_REQUIRED = 3` (defined in route handler, not service) | `app/api/v1/procurement_pipeline.py:447` |

**Core logic duplicated in all five:**
```
1. Check entity is in correct pre-approval state
2. Check voter has not already voted
3. Insert vote row with is_override flag
4. Count non-override votes
5. If count >= threshold: auto-approve entity
6. If is_override=True: skip count, approve immediately
```

**Divergence already present:**

| Behaviour | MR | WarehouseTransfer | WorkshopMR | MRQuote |
|-----------|----|--------------------|------------|---------|
| Audit event written | Yes | Yes (on execute) | **No** | **No** |
| Notification sent | Yes (APPROVED) | **No** | **No** | **No** |
| Override path explicit | Yes (procurement_lead_approve) | Yes (override_approve) | Yes (approve_mr) | Partial (is_override=True flag) |
| Threshold constant location | Service file | Model file | Service file | Route handler |

**Risk:** When the vote threshold rule changes (e.g., to 2 or 4), or a new entity needs vote-based approval, a developer must find and update all five locations. If any is missed, the system silently applies different rules to different workflows.

**Recommended canonical location:** `app/services/approval_service.py` — a single `ApprovalService` with a `cast_vote(db, entity_type, entity_id, voter_id, is_override, threshold)` method and an `override_approve(db, entity_type, entity_id, approver_id)` method. Entity-specific business rules (pre-approval state check, post-approval actions) remain in the entity service and are passed as callbacks.

**Migration difficulty:** Medium. Each vote table has a different schema but identical purpose. The service interface can be shared without merging tables.

---

## Category B — Payment Amount Aggregation

### Finding DUP-B01 — Eleven Independent Aggregations of `SUM(Payment.amount_paid)`

**Severity: HIGH**

Every module that needs to know "how much has been paid" independently queries `SUM(Payment.amount_paid)` with its own filter conditions. There is no shared `get_total_paid(invoice_id=None, supplier_id=None, project_id=None)` utility.

| Location | Purpose | File |
|----------|---------|------|
| `payment_service.py:39` | Determine invoice status after new payment | `_recalculate_invoice_status()` |
| `payment_service.py:182` | Recompute total before update | `update_payment()` |
| `payment_service.py:290` | Python sum over list for history view | `get_payment_history()` |
| `po_service.py:304` | Compute payment totals on linked PO docs | `get_po_linked_docs()` |
| `cost_summary.py:38` | Project procurement spend | `_build_summary()` |
| `dashboard_service.py:69` | Dashboard KPI | financial aggregation |
| `dashboard_service.py:188` | Dashboard KPI | financial aggregation |
| `dashboard_service.py:301` | Dashboard KPI | financial aggregation |
| `api/v1/invoices.py:75` | Invoice detail view total | route handler |
| `api/v1/payments.py` | Multiple aggregations | ≥7 locations in route |
| `api/v1/suppliers.py:146,234` | Supplier spend total | route handler |
| `reconciliation_service.py:301` | Reconciliation summary | service |
| `procurement_analytics_service.py:122` | Analytics dashboard | service |

**Divergence risk:** The `payment_service.py:182` aggregation uses Python list sum; all others use SQL `SUM()`. Under concurrent writes, the Python aggregation can return stale data.

**The critical divergence already confirmed:** `summary_service.py:66` was found in the previous audit session to use `Payment.amount` (legacy column) instead of `Payment.amount_paid` — the canonical column. This is the directly observable consequence of having no shared aggregation function: one call site uses the wrong column.

**Recommended canonical location:** `app/services/payment_service.py` — a `get_payment_total(db, invoice_id=None, supplier_id=None, project_id=None)` function that performs a single SQL `SUM(amount_paid)` with any combination of filters. All other sites import and call this function. No inline `SUM(amount_paid)` outside this function.

**Migration difficulty:** Low. Each call site needs a one-line replacement.

---

## Category C — Notification Creation Patterns

### Finding DUP-C01 — Two Competing Patterns for Creating and Queuing Notifications

**Severity: MEDIUM**

There are two patterns for creating a `SystemAlert` and enqueuing it for delivery. Both are in active use but produce slightly different database outcomes.

**Path A — Two-step explicit pattern:**
```python
alert = SystemAlert(alert_type=..., severity=..., ...)
db.add(alert)
db.flush()
enqueue_for_alert(db, alert)
```
Used in: `mr_service.py:_create_mr_submitted_alert()`, `warehouse_transfer_service.py:create_transfer_request()`, `stage_service.py:upsert_stage_status()`

**Path B — One-step helper pattern:**
```python
enqueue_direct(db, alert_type=..., severity=..., title=..., message=..., ...)
```
Used in: `mr_service.py:approve_request()`, `po_service.py:_notify_po_sent()`, `delivery_service.py`, `invoice_service.py`, `payment_service.py`

**A third anti-pattern also present:**
```python
alert = SystemAlert(...)
db.add(alert)
# enqueue_for_alert() never called — alert exists in DB but no WhatsApp/notification sent
```
Used in: `po_service.py:create_po()` (in-app alert only), `stage_service.py:BLOCKED` case

**Risk:** Path A and Path B have different error semantics. In Path A, if `enqueue_for_alert()` fails, the alert record exists but is never delivered. In Path B, `enqueue_direct()` uses `db.begin_nested()` (a savepoint) to protect the main transaction from notification failure. The Path A callers do not have this protection.

**Recommended canonical location:** Standardise on Path B (`enqueue_direct()`). Remove all Path A usage from service code. Path A (manual alert + flush + enqueue) is a valid lower-level building block that `enqueue_direct()` should wrap internally, but it should not appear in service code.

---

## Category D — Audit Event Coverage Gaps

### Finding DUP-D01 — Inconsistent Audit Coverage Across Architecturally Identical Transitions

**Severity: HIGH**

The `audit_service.write_event()` function is correctly shared, but the decision of *when to call it* is made independently by each module. The result is that structurally identical transitions (e.g., "submit for approval") are audited in some modules and not in others.

| Entity | Submit | Approve | Reject | Create | Update |
|--------|--------|---------|--------|--------|--------|
| MaterialRequest | ✓ | ✓ | ✓ | ✓ | Partial |
| PurchaseOrder | — | ✓ | — | **MISSING** | **MISSING** |
| Invoice | — | — | — | ✓ | **MISSING** |
| Payment | — | **MISSING** | — | ✓ | **MISSING** |
| WorkshopMR | **MISSING** | **MISSING** | **MISSING** | **MISSING** | — |
| WorkshopQuote | **MISSING** | **MISSING** | **MISSING** | **MISSING** | — |
| WorkshopPO | **MISSING** | **MISSING** | **MISSING** | **MISSING** | — |
| WorkshopInvoice | — | — | — | **MISSING** | — |
| MunicipalityInvoice | — | — | — | **MISSING** | **MISSING** |
| ExpenseRecord | — | **MISSING** | **MISSING** | **MISSING** | — |
| Quotation | — | **MISSING** | **MISSING** | **MISSING** | **MISSING** |
| ProjectStageStatus | — | — | — | — | **MISSING** (status change) |

**Entities with correct audit patterns:** `JobCard`, `SubcontractorWorkDone`, `WarehouseTransfer`, `MaterialRequest`. These use a `_transition()` helper that always writes an audit event.

**Root cause:** The `_transition()` helper pattern (implemented in `job_card_service.py` and `work_done_service.py`) is the correct solution. It has not been adopted in other services.

**Recommended canonical location:** Extract `_transition()` into a shared `app/services/state_service.py` utility. All service files that change entity status import and use this shared helper. This guarantees audit coverage by construction — the helper cannot be called without writing an audit event.

---

## Category E — Progress Calculation

### Finding DUP-E01 — Project and Lot Progress Computed in Multiple Places Without Persistence

**Severity: HIGH**

Project and lot progress are computed on-the-fly in multiple locations without being persisted to the database. Each computation may return a different result depending on when it is called and what data has been committed.

| Location | What is computed | Persisted |
|----------|-----------------|-----------|
| Stage status update in `stage_service.py` | Sets `progress_pct` on the stage status record | Stage only (not lot) |
| `GET /lots/{id}` | Computes lot progress from stage statuses | **No** |
| `GET /projects/{id}` | Computes project progress from lots | **No** |
| `_update_milestone_progress()` in `work_done_service.py` | Updates a single stage status progress | Stage only (not lot) |
| `GET /dashboard` | Computes project progress for dashboard cards | **No** |

**Risk:** A dashboard showing project progress and a lot detail screen may show different progress percentages for the same lot, depending on timing and whether the materialized view (for stock) or the live calculation (for progress) is used.

**Recommended canonical location:** A single `calculate_and_persist_lot_progress(db, lot_id)` function called after every stage status change. This function:
1. Queries all stage statuses for the lot
2. Computes `completed / total * 100`
3. Writes the result to `lots.progress_pct`
4. If all lots for the project are complete, computes `projects.progress_pct`

All other progress reads use the persisted column, not a live computation.

---

## Category F — Role-Based Access Enforcement

### Finding DUP-F01 — Role Bypass Logic Repeated at Every Call Site

**Severity: LOW**

`check_project_access(db, current_user, project_id)` is correctly implemented as a shared utility in `app/api/dependencies.py`. However, the decision of which roles bypass this check (OWNER, OFFICE_ADMIN, OFFICE_USER, PROCUREMENT_LEAD, READ_ONLY) is encoded inside the function, not externally configurable.

There are 20+ call sites of `check_project_access()`, each trusting that the bypass logic is correct inside the shared function. This is the correct pattern.

**Residual issue:** Some route handlers perform additional inline role checks after calling `check_project_access()`:
```python
if current_user.role not in [UserRole.OWNER, UserRole.OFFICE_ADMIN]:
    raise HTTPException(403, ...)
```
These inline additions duplicate role logic that should be in the shared `require_roles()` dependency factory.

**Recommended action:** Audit all inline role checks and convert them to `require_roles([...])` Depends entries at the route level. No inline role checks in service code.

---

## Summary Table

| ID | Category | Severity | Instances | Recommended Fix |
|----|----------|----------|-----------|----------------|
| DUP-A01 | Vote-based approval | CRITICAL | 5 | Shared `ApprovalService` |
| DUP-B01 | Payment aggregation | HIGH | 13 | Shared `get_payment_total()` |
| DUP-C01 | Notification patterns | MEDIUM | 3 paths | Standardise on `enqueue_direct()` |
| DUP-D01 | Audit coverage gaps | HIGH | 11 entities with gaps | Shared `_transition()` utility |
| DUP-E01 | Progress calculation | HIGH | 5 locations | `calculate_and_persist_lot_progress()` |
| DUP-F01 | Inline role checks | LOW | ~5 instances | Convert to `require_roles()` |

---

## Implementation Priority

The order below is determined by risk of silent divergence, not implementation effort.

1. **DUP-A01** — Shared ApprovalService: the vote threshold could silently diverge between modules on the next feature change. 
2. **DUP-D01** — Shared transition utility: Workshop module is expanding; adding audit coverage to it via a shared utility is cheaper now than retrofitting later.
3. **DUP-B01** — Shared payment total: the `summary_service.py:66` bug (wrong column) is the direct consequence of this duplication; the fix is a single function and 13 call-site replacements.
4. **DUP-E01** — Persisted progress: required prerequisite before a Timeline/Gantt module can be built.
5. **DUP-C01** — Notification patterns: low risk of incorrect behaviour; standardisation is a cleanup.
6. **DUP-F01** — Inline role checks: no functional risk; cleanup only.
