# Fuel API and Test Coverage

All responses use `ApiSuccess[T]`; all project resources require JWT authentication, a `fuel.*` permission and project access.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/fuel-management/fuel-types` | Active fuel catalogue |
| GET | `/api/v1/projects/{project_id}/fuel-management/dashboard` | Project totals, outstanding/overdue and anomaly counts |
| GET/POST | `.../fuel-management/storage` | List/create storage |
| GET/POST | `.../fuel-management/orders` | List/create orders |
| GET/PATCH | `/api/v1/fuel-management/orders/{id}` | Read/update draft |
| POST | `.../orders/{id}/submit` | Submit request |
| POST | `.../orders/{id}/approve` | Approve with self-approval guard |
| POST | `.../orders/{id}/reject` | Reject with reason |
| POST | `.../orders/{id}/mark-ordered` | Record supplier order |
| POST | `.../orders/{id}/cancel` | Cancel with reason |
| POST | `.../orders/{id}/close` | Close delivered order |
| POST | `.../orders/{id}/deliveries` | Record pending delivery |
| GET | `.../fuel-management/deliveries` | Project delivery register |
| POST | `.../deliveries/{id}/verify` | Verify delivery and post it to stock |
| POST | `.../deliveries/{id}/reject` | Reject pending delivery |
| GET/POST | `.../fuel-management/issues` | List/create fuel issues |
| POST | `.../issues/{id}/reverse` | Append reversal metadata; restore calculated stock |
| POST | `.../fuel-management/adjustments` | Authorised append-only adjustment |
| GET/POST | `.../fuel-management/reconciliations` | List/create reconciliation |
| POST | `.../reconciliations/{id}/approve` | Approve exceptional variance |
| GET | `.../fuel-management/reports/orders.csv` | Order register CSV |
| GET | `.../fuel-management/reports/usage.csv` | Usage/monitoring CSV |

## Automated coverage

`hmh-backend/tests/test_fuel_management.py` contains 14 integration tests:

- order state machine, rejection/cancellation reasons and self-approval prevention;
- unique order-number constraint and unauthorised project access;
- partial/multiple delivery status updates;
- excess delivery rejection and audited admin override;
- storage/delivery/issue fuel-type mismatch;
- vehicle issue stock reduction, reversal restoration and insufficient-stock guard;
- destination references, decreasing hour-meter rejection and monitoring fields;
- reconciliation threshold and separated approval;
- adjustment permission and immutable history;
- both CSV exports and export permission;
- legacy fuel hard-delete protection;
- schema-level proof that fuel tables have no BOQ dependency.

Verification uses an isolated PostgreSQL database:

```powershell
$env:TEST_DATABASE_URL='postgresql://hmh:hmhdev@127.0.0.1:55432/hmh_migration_0069_codex'
python -m pytest tests/test_fuel_management.py -q
```

Latest result: 14 passed. A combined run with `test_progress_claims.py` collected 51 tests and passed all 51; that file includes programme and weekly-plan coverage.

Migration `0069` was verified by full upgrade, downgrade `0069 -> 0068`, then re-upgrade `0068 -> 0069` on the same isolated database.

## `0070` coverage update

Additive endpoints include `POST /projects/{id}/fuel-management/requests`, multipart `issues-with-evidence`, equipment profile read/upsert, per-order email history and admin email retry. Order reads now include requester, history and next approver. Alert open/read endpoints provide access-checked canonical action URLs.

Latest focused result: **28 passed**. This includes all five request destinations and ownership, enriched transition history, staged evidence rollback/retry, controlled multipart failures, audit-row assertions, real Fuel-order notification references and frontend-origin validation. Playwright adds **5/5 notification-link** and **6/6 PWA/login/cache/mobile** checks. A clean UTF-8 Alembic run upgraded `0001 -> 0070` and reported `0070 (head)`. Production SMTP and device-install UAT remain deployment checks, not automated-test claims.
