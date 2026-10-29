# Architecture Principles

**Date:** 2026-07-16  
**Author:** Architecture Audit — Level 4  
**Classification:** L0 — Documentation only.  
**Status:** MANDATORY — These principles govern all future development on the HMH Construction OS.

---

## Purpose

These principles are derived from patterns observed in the existing codebase, the gaps identified in the architecture audit, and the long-term goal of operating as a complete Construction ERP. They are not aspirational — they are required constraints on every future pull request, migration, and module addition.

Each principle includes its rationale, the code pattern it requires, and the observable violation that signals it is being broken.

---

## AP-01 — One Business Concept, One Canonical Owner

**Statement:** Every business concept (stock balance, project progress, supplier balance, cash position) has exactly one owner: the table or service that holds the definitive value. All other modules read from the canonical owner; none maintain their own copy.

**Rationale:** The current system computes project progress in five places and payment totals in thirteen. When any one of those computations diverges, the system shows different data to different users in different screens with no way to determine which is correct.

**Required pattern:**
```
canonical_owner.field → readers query it directly
                      → no secondary copies maintained
                      → no recomputation at read time after initial persistence
```

**Violation signal:** Any SUM(), AVG(), or COUNT() query outside the designated canonical service for that concept. Any column on two tables storing the same business value.

**Known gaps to resolve:** `lots.progress_pct` (currently computed on-the-fly), `projects.progress_pct` (same), `suppliers.performance_score` (computed but never persisted).

---

## AP-02 — Every Status-Changing Mutation Produces Exactly One Audit Event

**Statement:** Any operation that changes the `status` field of any entity must call `audit_service.write_event()` as part of the same database transaction. This is not optional and not subject to developer judgement.

**Rationale:** The audit log is the system's memory of what happened and when. Incomplete audit coverage makes incident investigation impossible and breaks compliance requirements. Currently, the Workshop module, Municipality Invoices, Quotations, and Expenses have zero audit coverage on status changes.

**Required pattern:**
```python
# ALL of these must be in the same transaction:
entity.status = new_status
entity.updated_at = now()
audit_service.write_event(db, action, entity_type, actor_id, entity.id, after_value={...})
# Notifications are side effects added AFTER commit, not before
```

**Violation signal:** Any route handler or service function that assigns `.status =` without a corresponding `audit_service.write_event()` call in the same transaction.

**Implementation path:** The `_transition()` helper pattern in `job_card_service.py` is the reference implementation. Extract it to `app/services/state_service.py` and require all service code to use it.

---

## AP-03 — Every Workflow Reaches a Terminal State

**Statement:** Every entity's state machine has at least one terminal state. Terminal states are named with a suffix: `PAID`, `CANCELLED`, `COMPLETED`, `REJECTED`, `EXPIRED`, `ARCHIVED`. No entity can exist in a non-terminal state indefinitely without a defined escalation path.

**Rationale:** Open-ended workflows create invisible work queues. A Payment in PENDING status for 90 days and a Payment in PENDING status for 1 hour look identical to the system. Without terminal states, there is no way to identify stale records.

**Required pattern:**
- Every entity has at least one happy-path terminal state and one cancellation terminal state
- Entities stuck in non-terminal states beyond a defined threshold trigger a STALE alert (via the scan-alerts cron)
- `EXPIRED` states are set by the scheduled alert scanner, not by manual action

**Violation signal:** Any entity that can exist in a non-terminal state indefinitely with no alert or escalation path. Any new entity model without a CANCELLED or equivalent terminal state.

---

## AP-04 — Notifications Are Side Effects, Never Blocking Operations

**Statement:** All notification and alert creation happens after the primary database transaction commits. A notification failure must never roll back a business operation.

**Rationale:** The current `enqueue_direct()` function correctly uses `db.begin_nested()` (a savepoint) to protect the main transaction. This pattern must be used everywhere. Notifications are not part of the business operation — they are a side effect of it.

**Required pattern:**
```python
# 1. Complete the primary business operation and commit
db.flush()  # or db.commit() at route level

# 2. Then enqueue notifications as a side effect
try:
    enqueue_direct(db, ...)
except Exception:
    logger.warning("Notification failed — business operation already committed")
    # Never re-raise here
```

**Violation signal:** Any `enqueue_for_alert()` or `db.add(SystemAlert(...))` call that appears BEFORE the entity status is committed to the database. Any notification failure that raises an HTTP 500 to the user.

---

## AP-05 — No Duplicate Business Logic

**Statement:** Every business rule has one canonical implementation. Implementations of the same rule in more than one location are architectural debt requiring immediate resolution. This applies to: approval workflows, status transitions, cost calculations, permission checks, progress calculations, and notification patterns.

**Rationale:** See `Duplicate_Business_Logic_Report.md` for the current inventory. The five independent vote-based approval implementations are the most dangerous example: they diverge silently when the vote threshold rule changes.

**Required pattern:**
- Vote-based approval: `approval_service.cast_vote()`
- Status transitions: `state_service.transition()`
- Payment totals: `payment_service.get_payment_total()`
- Progress calculation: `progress_service.calculate_and_persist()`
- Role checks: `require_roles()` Depends, no inline `if current_user.role not in [...]` in service code

**Violation signal:** Any new service function that implements a vote-counting loop, any inline SUM(amount_paid), any inline role check in service code, any inline SystemAlert creation without going through `enqueue_direct()`.

---

## AP-06 — One Transaction Per Business Operation

**Statement:** A single user action produces a single database transaction. Multiple entities updated as part of one logical operation (e.g., approving an MR and sending an email) must all commit or all roll back together. The exception is side effects (notifications, emails), which are outside the transaction per AP-04.

**Rationale:** Partial updates corrupt business state. If a PO creation fails halfway through, the MR must not be marked as CONVERTED_TO_PO.

**Required pattern:**
```python
with db.begin():
    # All business state changes here
    entity.status = new_status
    audit_service.write_event(...)
    
# After transaction commits:
send_email(...)
enqueue_direct(...)
```

**Violation signal:** Any service function that commits (`db.commit()`) mid-operation and then performs additional state changes. Any email send that happens before the database transaction for the same operation.

---

## AP-07 — Every Financial Mutation Is Traceable

**Statement:** Every payment, invoice change, stock movement, and cost allocation must be traceable through an unbroken chain of database records back to the original business event that triggered it. No financial record can exist without a linked source document.

**Rationale:** The current system creates Payment records from JobCard and WorkDone approvals without foreign keys back to the source entity. A payment in the payment table cannot be traced back to the job card that generated it.

**Required pattern:**
- `payments.source_type` + `payments.source_id` (nullable, polymorphic): links every payment to its source entity
- No `db.add(Payment(...))` without populating the source link
- `stock_ledger` entries always carry `movement_type` and `reference_id`

**Known gaps:** JobCard → Payment link missing. WorkDone → Payment link missing. ExpenseRecord has no payment link. WorkshopInvoice has no payment link.

---

## AP-08 — Every Module Contributes to the Financial Summary

**Statement:** Any module that generates a business cost or revenue must contribute its figures to `GET /projects/{id}/cost-summary`. No cost category is invisible to project financial reporting.

**Rationale:** Workshop costs, expense records, and municipality invoice income are currently invisible to the cost summary. Project managers make decisions on incomplete financial data.

**Required pattern:**
```
cost_summary = BOQ budget
             + procurement payments
             + labour (job cards)
             + subcontractor work done
             + fuel
             + vehicle costs
             + workshop spend          ← currently MISSING
             + expense records         ← currently MISSING
             - municipality income     ← currently MISSING
```

**Violation signal:** Any new module that records expenditure or income without adding a corresponding line to `cost_summary_service.py`.

---

## AP-09 — All Schema Changes Go Through Alembic Migrations

**Statement:** No production schema change may occur except through a numbered Alembic migration. No manual `ALTER TABLE`, `CREATE TABLE`, or `DROP COLUMN` against any environment. The migration must include both upgrade and downgrade.

**Rationale:** The `hmh_v1_schema.sql` file was not generated by migrations and cannot be re-applied against a clean database without producing a hybrid schema. This has already caused a contamination incident during test bootstrap. See `docs/database/Bootstrap_Strategy.md`.

**Required pattern:**
```
alembic revision --autogenerate -m "description"
# Review generated migration for IF NOT EXISTS guards
# Ensure downgrade() is implemented
# Test against hmh_bootstrap_check (clean DB) before merging
```

**Violation signal:** Any `op.create_table()` in a migration without an `inspect().has_table()` guard. Any schema change committed without a migration file.

---

## AP-10 — APIs Are Idempotent at the Operation Level

**Statement:** Calling the same API endpoint twice with the same payload should produce the same final state, not duplicate records. Create operations must use uniqueness constraints at the database level to enforce this.

**Rationale:** Duplicate invoices, duplicate payments, and duplicate delivery records are currently the most common source of reconciliation failures. The `create_invoice()` service has a uniqueness check on `(supplier_id, invoice_number)` — this pattern must be universal.

**Required pattern:**
- Every entity with a natural business key has a `UniqueConstraint` on that key
- Create operations return the existing record (with 200) if the key already exists, rather than failing with 409 or creating a duplicate
- Vote operations are idempotent: casting the same vote twice produces the same outcome as casting it once

**Violation signal:** Any `db.add(Entity(...))` without a unique constraint on the underlying table for the natural key. Any duplicate vote creating a second vote row.

---

## AP-11 — Backward Compatibility Before Removal

**Statement:** No column, field, or API response property may be removed until: (a) it has been deprecated with a successor in place for at least one release, and (b) all callers in the codebase and any known external clients have been migrated.

**Rationale:** `material_request_items.request_id` (legacy) and `.quantity_approved` (legacy) are currently live columns that cannot be safely dropped without first verifying no caller depends on them. See `docs/database/Legacy_Field_Analysis.md`.

**Required pattern:**
1. Add the new canonical field
2. Write a backfill migration to populate existing rows
3. Update all internal callers to the new field
4. Add a deprecation notice to the API response for the old field
5. Remove the old field in a separate migration after the grace period

---

## AP-12 — Workshop Is a Temporary Parallel System

**Statement:** The Workshop module currently duplicates the entire procurement pipeline (MR → Quote → PO → Invoice → Delivery → Stock). This duplication is an acknowledged architectural debt item. No new duplicate module should be created. The Workshop module must eventually be consolidated into the main procurement pipeline.

**Rationale:** At integration score 2/10, the Workshop module is the most isolated part of the system. Its costs are invisible to financial reporting, its stock is not connected to main warehouse stock, and its audit coverage is zero. Building more onto this foundation increases the cost of eventual consolidation.

**Constraint:** Until consolidation occurs, Workshop routes must begin adding `project_id` foreign keys to all Workshop entities so that cost summary integration (AUT-019) can be implemented without a breaking schema change.

---

## AP-13 — Event-Driven Propagation for Cross-Module Side Effects

**Statement:** When one module's state change requires a reaction from another module, that reaction must be registered as a side effect handler, not embedded as an imperative call inside the originating service.

**Rationale:** The current pattern embeds all downstream reactions inside route handlers. `approve_request()` in `mr_service.py` directly calls `send_email()`, `enqueue_direct()`, and updates the MR status — all in one function. As the platform grows and more modules need to react to MR approval (timeline update, cost forecast update, AI email trigger), every reaction requires a modification to `mr_service.py`. This couples unrelated modules together.

**Required pattern (short term):**
```python
# After mr_service.approve_request() commits:
event = MRApprovedEvent(mr_id=..., project_id=..., supplier_id=...)
asyncio.create_task(event_dispatcher.dispatch(event))
# event_dispatcher calls all registered handlers without mr_service knowing about them
```

**Required pattern (long term):** A proper event bus (see `Future_System_Roadmap.md` LT-002).

**Violation signal:** Any service function that directly imports and calls a function from an unrelated module (e.g., `stage_service.py` importing `notification_service`). Cross-module calls should go through an event dispatcher, not direct imports.

---

## AP-14 — AI Is an Enhancement Layer, Never the Source of Truth

**Statement:** AI-extracted values (invoice amounts, supplier names, document classifications) are always treated as suggestions requiring human confirmation. The canonical record is the human-confirmed value, not the AI-extracted value. AI confidence scores are stored but do not automatically override human decisions.

**Rationale:** The current Document AI pipeline stores both `extracted_json` (raw AI output) and `manually_corrected_json` (human-confirmed values). The `manually_corrected_json` is the source of truth. This separation must be maintained as AI capabilities expand.

**Required pattern:**
- All AI-extracted values are stored in a `_draft` or `_ai_suggested` column or record state
- Human confirmation transitions the record from AI-suggested to canonical
- AI confidence score is stored alongside the extracted value, never hidden
- When confidence >= threshold, auto-confirm is permitted, but the human confirmation action must still be a distinct trackable event

---

## AP-15 — Test Coverage Must Match Risk Level

**Statement:** Every mutation route and every state transition must have at least one test that confirms the happy path. Any route that touches financial data, auth decisions, or multi-entity state must have adversarial tests covering rejection cases and permission checks.

**Rationale:** The current test suite has 835 planned tests but multiple failures in payment, approval, and stage tests that were identified in the Migration Remediation Plan. Financial routes with no test coverage represent an unacceptable production risk.

**Required pattern:**
- New routes: at least 1 happy-path test + 1 auth failure test before merging
- State-changing routes: at least 1 test per illegal transition (attempting an invalid state change must return 4xx, not silently succeed)
- Financial routes: at least 1 test that confirms the exact amount written to the database

**Violation signal:** Any PR that adds a state-changing or financial mutation endpoint without a corresponding test.

---

## Applying These Principles

These principles take effect immediately for all new development. Existing code that violates them is tracked in `Duplicate_Business_Logic_Report.md`, `State_Machine_Audit.md`, and `Lifecycle_Gap_Analysis.md`. Remediation follows the priority order in `Future_System_Roadmap.md`.

No principle in this document requires approval. They are the architectural baseline. Any deviation requires an explicit documented exception in the PR description explaining why the principle cannot be followed in that specific case.
