# Legacy Field Analysis

**Date:** 2026-07-15  
**Scope:** All duplicate, redundant, and legacy columns identified across the HMH schema  
**Method:** Database inspection + ORM model analysis + API endpoint scan + service layer scan  
**Status:** Analysis only. No columns dropped or renamed.

---

## Overview

Five duplicate-purpose column groups have been identified. Each group represents a case where a migration added a replacement column without dropping the original, leaving both in the database. The ORM exclusively uses the newer (canonical) column. The older column is kept nullable for backwards compatibility but is no longer read or written by application code in most cases.

| Group | Table | Old column(s) | New column(s) | ORM uses | Active code risk |
|-------|-------|--------------|--------------|----------|-----------------|
| A | material_request_items | `request_id` | `material_request_id` | NEW | None — old is dead |
| B | material_request_items | `quantity_requested` | `requested_quantity` | NEW | Low — old accepted via AliasChoices |
| C | material_request_items | `quantity_approved` | `approved_quantity` | NEW | None — old is dead |
| D | payments | `reference` | `payment_reference` | NEW | None — old is dead |
| E | payments | `amount` | `amount_paid` | BOTH | **Medium — `summary_service.py` still uses old** |

---

## Group A — `material_request_items.request_id` vs `material_request_items.material_request_id`

### History

| Migration | Action |
|-----------|--------|
| 0001 | Created `request_id UUID NOT NULL FK → material_requests.id` |
| 0003 | Added `material_request_id UUID NULLABLE FK → material_requests.id` (ORM-mapped replacement) |
| 0006 | Backfilled `material_request_id ← request_id` for existing rows; dropped NOT NULL from `request_id` |

### Current state

- **`material_request_id`**: Canonical. Mapped in `app/models/material_request.py`. Used exclusively by all API routes, service functions, schemas, and tests.
- **`request_id`**: Dead. Not mapped by any ORM model. Not referenced in any Python file. Contains data backfilled from `material_request_id` by migration 0006 for rows that pre-date migration 0003.

### Who uses each

| Layer | Uses `request_id` | Uses `material_request_id` |
|-------|------------------|--------------------------|
| ORM model | NO | YES — `app/models/material_request.py` |
| API routes | NO | YES — all procurement, MR, supplier routes |
| Services | NO | YES — `mr_service.py`, `email_service.py`, `po_service.py`, etc. |
| Schemas | NO | YES — `MaterialRequestItemRead`, `MaterialRequestItemCreate` |
| Tests | NO | YES — all test files |

### Is data in both columns?

In the bootstrap DB, `request_id` is populated with the same value as `material_request_id` for all rows created before migration 0003. For rows created after migration 0003, `request_id` is NULL (ORM never sets it).

### Recommendation

`material_request_id` is the canonical column. `request_id` is safe to drop in a future cleanup migration once:
1. All environments are on the clean bootstrap path (i.e., after production is rebuilt from migration 0001+).
2. No external scripts query `request_id` directly.

**Removal risk: LOW.** No application code reads `request_id`.

---

## Group B — `material_request_items.quantity_requested` vs `material_request_items.requested_quantity`

### History

| Migration | Action |
|-----------|--------|
| 0001 | Created `quantity_requested NUMERIC(14,3) NOT NULL` |
| 0003 | Added `requested_quantity NUMERIC(14,3) NULLABLE` (ORM-mapped replacement) |
| 0006 | Backfilled `requested_quantity ← quantity_requested`; dropped NOT NULL from `quantity_requested` |

### Current state

- **`requested_quantity`**: Canonical ORM column. Used by `MaterialRequestItem` model, all service functions, and most tests.
- **`quantity_requested`**: Legacy. Kept nullable. Two places still use it:
  1. `app/schemas/material_request.py:37-39` — `MaterialRequestItemCreate` accepts both `requested_quantity` and `quantity_requested` via `AliasChoices`. This means old API clients sending `quantity_requested` still work.
  2. `app/services/email_service.py:1191, 1430` and `app/services/workshop_service.py:249` — these reference `quantity_requested` on **WorkshopMRLine** objects (a completely different model on a different table), not on MaterialRequestItem. This is NOT a usage of the legacy MaterialRequestItem column.

### AliasChoices behaviour

```python
# app/schemas/material_request.py
class MaterialRequestItemCreate(BaseModel):
    requested_quantity: Decimal = Field(alias=AliasChoices("requested_quantity", "quantity_requested"))
```

This means:
- API input: accepts both `requested_quantity` and `quantity_requested` 
- API output: always returns `requested_quantity`
- DB write: always writes to `requested_quantity` column
- `quantity_requested` (old column) is never written by the ORM — it remains NULL for all new rows

### Is data in both columns?

- Rows created before migration 0003: data backfilled into `requested_quantity`; `quantity_requested` still has the original value.
- Rows created after migration 0003: `requested_quantity` is populated; `quantity_requested` is NULL.

### Recommendation

`requested_quantity` is canonical. The `AliasChoices` means `quantity_requested` as a JSON key name is still an accepted API alias — this can be retained indefinitely without risk. The `quantity_requested` *database column* can be dropped once no client sends that key name in payloads. Verify with frontend code before dropping.

**Removal risk: LOW–MEDIUM.** The column is safe to drop from DB, but the AliasChoices API alias should be retained to avoid breaking existing clients.

---

## Group C — `material_request_items.quantity_approved` vs `material_request_items.approved_quantity`

### History

| Migration | Action |
|-----------|--------|
| 0001 | Created `quantity_approved NUMERIC(14,3) NULLABLE` on `material_request_items` |
| 0003 | Added `approved_quantity NUMERIC(14,3) NULLABLE` on `material_request_items` |
| — | No backfill migration (both are nullable; no constraint failure occurred) |

### Current state

**Important distinction:** `quantity_approved` appears on TWO different tables:

1. **`material_request_items.quantity_approved`** — the OLD unmapped column on MaterialRequestItem
2. **`workshop_mr_lines.quantity_approved`** — a CURRENT actively-used column on the WorkshopMRLine model (added by migration 0058)

These are entirely separate columns on separate tables. The similarity in name is coincidental.

For `material_request_items`:
- **`approved_quantity`**: Canonical ORM column. Mapped at `app/models/material_request.py:155`. Returned in `MaterialRequestItemRead`.
- **`quantity_approved`**: Dead. Not mapped for MaterialRequestItem. The ORM model does not define this column for this table. No service or API code reads `material_request_items.quantity_approved`.

For `workshop_mr_lines`:
- **`quantity_approved`**: Fully active. Mapped at `app/models/workshop.py:224`. Used in `app/schemas/workshop.py` and `app/services/workshop_service.py`. This is NOT the same as the legacy material_request_items column.

### Is data in both columns?

For `material_request_items`: no backfill migration exists. `quantity_approved` (old) and `approved_quantity` (new) may have diverged in value for rows created before migration 0003. **This is a data quality risk**: if any existing rows have `quantity_approved` populated but `approved_quantity` NULL, the approval status is invisible to the application.

**Action required before production upgrade:** Run a data audit:
```sql
SELECT COUNT(*) FROM material_request_items
WHERE quantity_approved IS NOT NULL AND approved_quantity IS NULL;
```
If this returns non-zero, a data migration is needed before dropping `quantity_approved`.

### Recommendation

`approved_quantity` is canonical for material_request_items. Verify data integrity before dropping `quantity_approved`. Add a migration that backfills `approved_quantity ← quantity_approved` where `approved_quantity` IS NULL, then the column can be scheduled for removal.

**Removal risk: MEDIUM.** Data audit required first.

---

## Group D — `payments.reference` vs `payments.payment_reference`

### History

| Migration | Action |
|-----------|--------|
| 0001 | Created `reference VARCHAR(255) NULLABLE` |
| 0004 | Added `payment_reference VARCHAR(100) NULLABLE` (ORM-mapped replacement) |
| — | No backfill migration |

### Current state

- **`payment_reference`**: Canonical. Mapped in `app/models/payment.py:43`. Used in all payment services, API routes, schemas, and tests. Has a unique partial index: `uq_payments_project_reference (project_id, payment_reference) WHERE payment_reference IS NOT NULL`.
- **`reference`**: Dead. Not mapped by the ORM. No Python code reads or writes `payments.reference`. It is a DB-only column that receives no data from any operation.

### Is data in both columns?

No backfill migration exists. `reference` likely contains data only from before migration 0004 (if the application was used in that period). `payment_reference` contains all data from after migration 0004.

### Recommendation

`payment_reference` is canonical. `reference` is safe to drop. Verify no data exists in `reference` that was not copied to `payment_reference`:
```sql
SELECT COUNT(*) FROM payments WHERE reference IS NOT NULL AND payment_reference IS NULL;
```

**Removal risk: LOW.** No application code reads `payments.reference`.

---

## Group E — `payments.amount` vs `payments.amount_paid`

### History

| Migration | Action |
|-----------|--------|
| 0001 | Created `amount NUMERIC(14,2) NOT NULL` |
| 0004 | Added `amount_paid NUMERIC(14,2) NOT NULL` |
| 0009 | Made `amount` NULLABLE (via backfill: `amount ← amount_paid` where NULL) |

### Current state (most complex group)

Unlike the other groups, **BOTH columns are mapped by the ORM** (`app/models/payment.py:45-48`) with an explicit comment explaining the legacy. The service layer actively double-writes:

```python
# app/services/payment_service.py
payment = Payment(
    amount_paid=data.amount_paid,   # canonical column
    amount=data.amount_paid,        # legacy copy for backwards compat
    ...
)
```

The ORM therefore keeps both columns in sync for new writes. However, one inconsistency exists:

**`app/services/summary_service.py:66`** queries `func.sum(Payment.amount)` instead of `func.sum(Payment.amount_paid)`. All other locations (`cost_summary.py`, `invoices.py`, `payments.py`, `suppliers.py`, `dashboard_service.py`, `payment_service.py`, `procurement_analytics_service.py`, `reconciliation_service.py`) use `amount_paid`.

Because the payment service double-writes, in practice `amount == amount_paid` for all records created since migration 0009. However, this is an undocumented invariant. If any code path ever creates a payment without setting `amount`, `summary_service.py` would return incorrect totals.

### Recommendation

1. **Immediate (P1 fix):** Change `summary_service.py:66` to use `Payment.amount_paid` for consistency.
2. **Medium term:** Remove the `amount` column and its double-write. Before removal:
   - Verify `amount == amount_paid` for all existing rows
   - Remove `amount` from the ORM model
   - Remove double-write from payment_service.py
   - Remove `amount` from migration downgrade paths

**Removal risk: MEDIUM.** Requires verifying data consistency and coordinating with any external integrations that might query `payments.amount` directly.

---

## Additional Fields Investigated (No Duplicates Found)

During this investigation, the following field pairs were examined and confirmed as **non-redundant** (different concepts, not duplicates):

| Field A | Field B | Verdict |
|---------|---------|---------|
| `workshop_mr_lines.quantity_approved` | `material_request_items.quantity_approved` | Different tables, same column name — coincidental naming |
| `workshop_mr_lines.quantity_requested` | `material_request_items.quantity_requested` | Different tables — WorkshopMRLine is a separate feature |
| `invoices.amount` | `payments.amount` | Different entities entirely |
| `delivery_items.quantity_ordered` | `delivery_items.quantity_received` | Different business concepts |
| `boq_items.quantity` | `material_request_items.requested_quantity` | Different entities |

---

## Removal Roadmap

| Priority | Action | Pre-requisite | Risk |
|----------|--------|--------------|------|
| P-immediate | Fix `summary_service.py` to use `amount_paid` | None | Very low |
| P3 | Backfill `material_request_items.approved_quantity ← quantity_approved` | Data audit | Low |
| P4 | Drop `material_request_items.request_id` | Rebuild production from Alembic | Low |
| P4 | Drop `material_request_items.quantity_requested` | Verify no external clients send the old key | Low-medium |
| P4 | Drop `material_request_items.quantity_approved` | After backfill migration | Medium |
| P4 | Drop `payments.reference` | Verify no data loss | Low |
| P4 | Drop `payments.amount` and remove double-write | Verify data equality | Medium |

All P4 items are safe to defer until after production is migrated to Alembic head. Do not drop columns from production while it is on the SQL-schema-bootstrapped path.
