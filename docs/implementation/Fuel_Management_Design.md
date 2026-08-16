# Fuel Management Design

## Boundary

Fuel Management is an independent operational ledger. It may reference projects, sites, suppliers, vehicles, users, attachments, alerts and audit infrastructure, but it has no BOQ foreign key and does not write BOQ quantities, material consumption or procurement totals.

Legacy `FuelLog` records remain readable. Their DELETE endpoint returns HTTP 409; corrections use a new reversal or authorised adjustment.

## Data model

| Table/model | Purpose |
|---|---|
| `fuel_types` / `FuelTypeDefinition` | Configurable active fuel catalogue; seeded with diesel, petrol 93, petrol 95 and other |
| `fuel_storage_locations` / `FuelStorageLocation` | Project/site tank or store, fuel type, capacity, threshold and opening stock |
| `fuel_orders` / `FuelOrder` | Numbered request, approval and supplier-order lifecycle |
| `fuel_deliveries` / `FuelDelivery` | Existing table extended with order, storage, meter, variance, verification and excess-override evidence |
| `fuel_issues` / `FuelIssue` | Immutable issue to vehicle, plant, generator, tank or other equipment; optional reversal metadata |
| `fuel_stock_adjustments` / `FuelStockAdjustment` | Append-only authorised opening/correction/loss/gain/reversal movement |
| `fuel_reconciliations` / `FuelReconciliation` | Calculated-versus-physical stock snapshot and approval |

Identifiers are UUIDs. Order, issue and reconciliation numbers are unique. Database checks enforce positive quantities, valid states/destinations, non-zero adjustments and valid physical balances.

## Order workflow

```text
DRAFT -> SUBMITTED -> APPROVED -> ORDERED
                                  |-> PARTIALLY_DELIVERED -> DELIVERED -> CLOSED
SUBMITTED -> REJECTED
DRAFT/SUBMITTED/APPROVED/ORDERED/PARTIALLY_DELIVERED -> CANCELLED
```

- The requester cannot approve their own request.
- Rejection and cancellation require a reason.
- Marking ordered requires a supplier reference.
- Only verified deliveries count toward delivered quantity and stock.
- Multiple partial deliveries are supported.
- A delivery above the outstanding order quantity returns HTTP 409 unless OWNER/OFFICE_ADMIN supplies an explicit excess reason; the override is audited.
- Completed transactions are never hard-deleted.

## Stock and monitoring rules

```text
calculated balance =
  opening stock
  + verified confirmed deliveries
  - non-reversed fuel issues
  + authorised stock adjustments
```

Storage and transaction fuel types must match. Issues cannot exceed calculated stock. Vehicle issues require a vehicle; non-vehicle issues require an equipment reference. A later odometer/hour reading cannot be lower than the preceding reading.

The service derives distance, L/100 km, operating hours and L/hour where readings permit it. Missing readings or usage above the configured vehicle expectation is flagged for review. Low stock is surfaced when calculated balance is at or below the storage threshold.

A reconciliation records an immutable snapshot. Approval is required when absolute variance exceeds the greater of 50 litres or 2% of calculated stock. The reconciler cannot approve their own exceptional variance. Approval does not silently rewrite stock; an authorised adjustment records any accepted correction.

## Permission matrix

| Role | Capabilities |
|---|---|
| OWNER, OFFICE_ADMIN | All `fuel.*` permissions |
| PROCUREMENT_LEAD | view, request, submit, approve, order, receive, export |
| OFFICE_USER | view, request, submit, receive, issue, export |
| SITE_MANAGER | view, request, submit, receive, issue, reconcile |
| SITE_STAFF | view, request, submit, receive, issue |
| SITE_MANAGER_VIEW | view |
| READ_ONLY | view, export |

Every route also applies `check_project_access()`; permissions never bypass project isolation.

## Audit, notifications and UI

Order creation/transitions, delivery recording/verification, issue/reversal, reconciliation/approval, adjustment, excess override and export generate audit activity through the existing audit service. Workflow notifications use the existing queue inside a nested savepoint so a notification failure cannot roll back the fuel transaction.

The frontend exposes dashboard, orders, deliveries, issues, stock/reconciliation and reports at `/fuel-management/*`. Forms use mobile-safe responsive grids. The old page remains at `/fuel-legacy`; `/fuel` redirects to the new module.

Migration: `0069_fuel_management.py`, down-revision `0068`.

## Targeted gap closure (`0070`)

Migration `0070` extends—not replaces—the ledger with site-clerk submitted requests, order history/next approver, destination-specific issue evidence, explicit evidence and feasibility overrides, configurable vehicle/equipment profiles, reading provenance, a provider-neutral tracker adapter, and durable Fuel email logs. Feasibility is advisory unless the selected profile requires an authorised override. Messages use neutral review language.

Fuel remains separate from BOQ. See [the complete requirement matrix](../../docs/fuel-management-gap-closure.md) for field, workflow, security and future Non-BOQ boundaries.
