# Coding Standards — HMH Construction OS

## Invariants that must never be violated

| Invariant | Rule |
|---|---|
| StockLedger | Append-only. Never mutate an existing row. All stock movements (DELIVERY_RECEIVED, TRANSFER_IN, TRANSFER_OUT, USAGE, ADJUSTMENT) are new rows. |
| ApiSuccess[T] | Every endpoint response must use `ApiSuccess[T]` from `app/schemas/common.py`. No bare `dict` or raw Pydantic model returns. |
| check_project_access() | Site-level roles (SITE_MANAGER, SITE_STAFF, SITE_MANAGER_VIEW) require an explicit `UserProjectAccess` row. Always use `check_project_access(db, user, project_id)` on every site-scoped route. |
| JWT roles | Roles are embedded in the JWT payload at login. No per-request DB role lookup. Role checks use `require_roles(*roles)` from `app/dependencies.py`. Pre-built aliases: `OWNER_ONLY`, `OFFICE_ADMIN_AND_ABOVE`, `OFFICE_AND_ABOVE`, `ALL_ROLES`, `WRITE_ROLES`, `PROCUREMENT_LEAD_ONLY`. Always use aliases in route `dependencies=[…]`. |
| Alembic chain | Never drop, renumber, or alter existing migration files. Only add new migrations. Current head: 0067. |
| native_enum=False | All new Python-only enums use `native_enum=False` (stored as VARCHAR). Existing enums are untouched. |
| TimestampMixin | All new models inherit `TimestampMixin` from `app/models/base.py` (adds `created_at`, `updated_at`). `Base` is imported separately from `app/db/base.py`. |
| GENERATED columns | `planned_total` on BOQItem is `GENERATED ALWAYS AS STORED`. Never write to it. |
| cron secret | All internal cron endpoints compare `X-Cron-Secret` via `secrets.compare_digest()`. Never weaken. |
| Tenant isolation | `project_id` scoping must be preserved on every query that touches project-scoped tables. `company_id` is an optional FK on the `projects` table only (added by migration 0065) — it is NOT a universal tenant key and does not need to be applied globally. |

## Patterns for this project

### New model
```python
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base           # DeclarativeBase — always from here
from app.models.base import TimestampMixin   # created_at / updated_at — from here
from app.models.enums import MyNewEnum  # native_enum=False for new Python-only enums

class MyModel(TimestampMixin, Base):
    __tablename__ = "my_models"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[MyNewEnum] = mapped_column(
        SAEnum(MyNewEnum, native_enum=False, name="mynewenumtype"),
        nullable=False,
    )
```

### New endpoint
```python
import uuid
from app.dependencies import DbSession, CurrentUser, OFFICE_AND_ABOVE, check_project_access
from app.schemas.common import ApiSuccess   # NOT from app.core.exceptions

@router.post(
    "/{project_id}/my-endpoint",
    response_model=ApiSuccess[MyResponseSchema],
    dependencies=[OFFICE_AND_ABOVE],   # role guard goes here, not in params
)
def my_endpoint(
    project_id: uuid.UUID,             # UUID, not int
    body: MyRequestSchema,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    result = my_service.do_thing(db, project_id, body, current_user.id)
    return ApiSuccess(data=result)
```

### Writing an audit event
```python
from app.services.audit_service import write_event
from app.models.enums import AuditAction

# Always call with commit=False (default) — let the surrounding transaction commit both
# the business mutation and this audit row together atomically.
# Do NOT pass project_id — write_event() has no such parameter.
write_event(
    db=db,
    action=AuditAction.UPDATE,
    entity_type="project_stage_status",
    actor_id=current_user.id,
    entity_id=pss.id,
    before_value={"status": old_status.value},
    after_value={"status": new_status.value},
    commit=False,   # default — omit or state explicitly; NEVER commit=True inside a route
)
db.commit()   # single commit covers both the mutation and the audit row
```

### Writing a notification
```python
from app.services.notification_service import enqueue_direct
from app.models.enums import AlertType, AlertSeverity

# severity and title are REQUIRED keyword-only arguments.
# Never raises — uses a savepoint; notification failure never blocks the business transaction.
enqueue_direct(
    db=db,
    alert_type=AlertType.MILESTONE_COMPLETED_ALERT,
    severity=AlertSeverity.LOW,
    title="Milestone completed",
    message=f"Milestone '{stage_name}' completed on Lot {lot_ref} by {actor_name}",
    project_id=project_id,
    entity_type="project_stage_status",
    entity_id=pss.id,
)
```

## Test patterns

- Tests are **integration-level** — they hit the PostgreSQL database pointed to by `TEST_DATABASE_URL`.
- `TEST_DATABASE_URL` must be set to a separate `hmh_test` database. Tests must NOT fall back to `DATABASE_URL`.
- No DB mocking. No mock of `StockLedger`, `audit_service`, or `notification_service`.
- WhatsApp sends intercepted via `WHATSAPP_ENABLED=false` → `MOCK_SENT`.
- SMTP sends intercepted via `SMTP_ENABLED=false`.
- `conftest.py` provides one fixture (`db`) and several **free helper functions** (not fixtures):
  - `make_user(db, email=None, role="OFFICE_USER", password="Test@1234") → dict`
  - `make_project(db, owner_id) → dict`
  - `make_site(db, project_id, name="Test Site") → dict`
  - `make_lot(db, project_id, site_id, lot_number) → dict`
  - `make_item(db, name, unit, item_type) → dict`
  - `make_boq_item(db, project_id, lot_id, item_id, qty, rate) → dict`
  - `make_stock(db, project_id, site_id, item_id, qty, lot_id) → dict`
  - `make_supplier(db, name, email) → dict`
  - `make_user_project_access(db, user_id, project_id, ...) → dict`
  - `login(client, email, password) → str` (returns JWT token)
  - `auth(token) → dict` (returns Authorization header dict)
- All helpers return `dict` (not ORM objects). Access IDs as strings: `user["id"]`, `project["id"]`.

### Test structure
```python
from tests.conftest import make_user, make_project, make_site, make_lot, make_boq_item
from app.models.audit import AuditEvent

def test_my_feature(db, client):
    # 1. ARRANGE — use free helper functions, not fixtures
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    token = login(client, owner["email"], owner["password"])

    # 2. ACT — call service layer or HTTP client
    result = my_service.do_thing(db, uuid.UUID(project["id"]), ...)

    # 3. ASSERT — DB state, not return value alone
    db.expire_all()
    row = db.query(MyModel).filter_by(id=result.id).first()
    assert row.status == ExpectedStatus
    audit = db.query(AuditEvent).filter_by(entity_id=row.id).first()
    assert audit is not None  # always verify audit side-effects
    assert audit.actor_id == uuid.UUID(owner["id"])
```

## Before committing

- [ ] All new models have a corresponding Alembic migration.
- [ ] All new routes use `ApiSuccess[T]`.
- [ ] All site-scoped routes call `check_project_access()`.
- [ ] All status-changing operations write an `AuditEvent`.
- [ ] No secrets, credentials, or personal data in code or tests.
- [ ] `TEST_DATABASE_URL=... pytest tests/ -v` passes against the `hmh_test` database (NOT the main local DB).
- [ ] `npx tsc --noEmit` passes.
