# Verification Standards — HMH Construction OS

## Confidence labels (required on financial, security, and milestone claims)

| Label | Meaning |
|---|---|
| `Verified:` | Code was read and traced this session, or command ran and output captured. |
| `Derived:` | Calculated from Verified inputs. Show the calculation. |
| `Likely:` | Strong inference from adjacent code or docs. Not confirmed by direct read. |
| `Assumption:` | Chosen to proceed; state what would falsify it. |
| `Unknown —` | Cannot determine; name what tool call would settle it. |

## L3 acceptance criteria checklist

Run this checklist before reporting any L3 task as complete.

### Code review
- [ ] The change does not weaken any invariant in `Coding.md`.
- [ ] No new raw mutations to `StockLedger` rows (only INSERTs).
- [ ] No unguarded financial calculation (all money values use `Decimal`, not `float`).
- [ ] Every changed route still returns `ApiSuccess[T]`.
- [ ] Every site-scoped route still calls `check_project_access()`.

### Test requirements
- [ ] At least one **regression test** per bug fixed: a test that would have caught the bug before the fix.
- [ ] At least one **boundary test** per financial calculation: zero amount, null project linkage, duplicate record.
- [ ] For audit-trail changes: test that `AuditEvent` rows exist with correct `entity_type`, `entity_id`, `before_value`, `after_value`, and `actor_id`.
- [ ] For stock changes: test that `StockLedger` has the correct `quantity_in`/`quantity_out` sign, `lot_id`, and `movement_type`.
- [ ] For cost-summary changes: test with at least two scenarios — one that should include the amount and one that should not.
- [ ] No test weakened, skipped, or deleted to force a pass. Any blocked test is named with its unblocking command.

### Financial verification
- [ ] Before/after cost_summary figures calculated independently (by hand or SQL) and match the test assertions.
- [ ] No double-counting verified: if two code paths could write the same amount, a test proves only one does.
- [ ] BOQ budget queries tested against a project with two BOQ versions (one active, one inactive).

### Migration verification (when applicable)
- [ ] Migration is reversible (`downgrade()` method implemented and tested via `alembic downgrade -1`).
- [ ] Migration does not DROP or ALTER existing columns without explicit user confirmation.
- [ ] New columns are `nullable=True` or have a server-side default (never bare `NOT NULL` on existing table).
- [ ] Migration chain tested: `alembic upgrade head` from migration N-1 → N → downgrade → N-1.

### Security verification (for any change touching auth, roles, or project isolation)
- [ ] A test with a SITE_STAFF user proves they cannot access a project they are not assigned to.
- [ ] A test with an OFFICE_USER proves they can access all projects.
- [ ] No new route bypasses `require_role()`.

## Self-verification disclosure

All verifications in this project are self-verified unless an independent verifier is available. Every report must state:

> Self-verified; no independent verifier available.

## Evidence rules

- Every claim that "tests pass" requires the exact `pytest` output captured in the same session.
- "TypeScript passes" requires `npx tsc --noEmit` output captured in the same session.
- "Build passes" requires `npm run build` output captured in the same session.
- Historical test evidence (from a prior session) is labelled `HISTORICAL` and is not a substitute for a current-session pass.

## Rollback plan template (required for all L3 changes)

```
Files changed: [list]
Migration: [number or "none"]
Rollback:
  - git revert <commit-sha>
  - If migration: alembic downgrade <N-1>
  - No data loss expected because: [reason]
Validation after rollback:
  - pytest tests/test_X.py -v passes
  - cost_summary returns same values as before
```
