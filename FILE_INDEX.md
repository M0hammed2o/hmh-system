# HMH System — File Index

This index describes every file in the active workspace. Archived files are excluded.

---

## hmh-docs/

| File | Purpose |
|------|---------|
| `hmh_v1_schema.sql` | **Canonical PostgreSQL schema.** Single source of truth. Includes all enums, tables, indexes, the `stock_balances` materialized view, and `system_config` seed data. |

---

## hmh-backend/

### Root

| File | Purpose |
|------|---------|
| `main.py` | FastAPI application factory. Registers CORS and routers. Entry point for Uvicorn. |
| `requirements.txt` | Python dependencies with pinned versions. |
| `.env.example` | Template for `.env`. Copy and fill in before running. |
| `alembic.ini` | Alembic configuration. URL is overridden at runtime by `alembic/env.py`. |
| `README.md` | Local setup instructions, env var reference, stage list. |

### alembic/

| File | Purpose |
|------|---------|
| `env.py` | Alembic env — loads `DATABASE_URL` from settings, imports all models, supports offline and online mode. |
| `script.py.mako` | Template for generated migration files. |
| `versions/` | Generated migration files live here. Empty at project init. |

### app/core/

| File | Purpose |
|------|---------|
| `config.py` | Pydantic-settings `Settings` class. Reads `.env`. Validates `SECRET_KEY` length. Provides `settings` singleton. |
| `security.py` | `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`, `generate_temp_password`. |
| `exceptions.py` | Domain exception hierarchy: `NotFoundError`, `ConflictError`, `AuthenticationError`, `ForbiddenError`, `AccountLockedError`, `InvalidStateError`, `AlreadyPostedError`. |

### app/db/

| File | Purpose |
|------|---------|
| `base.py` | SQLAlchemy `DeclarativeBase`. All models inherit from `Base`. |
| `session.py` | `engine`, `SessionLocal`, `get_db()` (FastAPI dependency), `db_session()` (context manager for scripts). |

### app/models/

| File | Tables / Types |
|------|---------------|
| `enums.py` | All Python enum classes mirroring PostgreSQL enum types. |
| `base.py` | `TimestampMixin` — adds `created_at` / `updated_at` to any model. |
| `user.py` | `User` |
| `project.py` | `Project` |
| `site.py` | `Site` |
| `lot.py` | `Lot` |
| `stage.py` | `StageMaster`, `ProjectStageStatus` |
| `access.py` | `UserProjectAccess`, `UserSiteAccess` |
| `__init__.py` | Imports all models so Alembic sees them via a single import. |

### app/schemas/

| File | Schemas |
|------|---------|
| `common.py` | `ApiSuccess[T]`, `ApiError`, `PaginatedResult[T]`, `PaginationParams` |
| `user.py` | `UserRead`, `UserSummary`, `UserCreate`, `UserUpdate`, `UserCreatedResponse`, `ProjectAccessGrant`, `SiteAccessGrant`, `LoginRequest`, `TokenResponse`, `RefreshRequest`, `ChangePasswordRequest` |
| `project.py` | `ProjectRead`, `ProjectCreate`, `ProjectUpdate` |
| `site.py` | `SiteRead`, `SiteCreate`, `SiteUpdate` |
| `lot.py` | `LotRead`, `LotCreate`, `LotUpdate` |
| `stage.py` | `StageMasterRead`, `ProjectStageStatusRead`, `StageStatusUpsert` |

### app/api/

| File | Routes |
|------|--------|
| `health.py` | `GET /health` — DB connectivity + env info |

### app/

| File | Purpose |
|------|---------|
| `dependencies.py` | `get_current_user_payload`, `CurrentUserPayload`, `require_roles()`, `OWNER_ONLY`, `OFFICE_ADMIN_AND_ABOVE`, `OFFICE_AND_ABOVE`, `ALL_ROLES` |

### scripts/

| File | Purpose |
|------|---------|
| `seed_stages.py` | Inserts the 11 locked V1 stages into `stage_master`. Idempotent. |

---

## hmh-backend-archive-node/ (archived — do not use)

Contains the original Node/Express/TypeScript backend. Archived for reference only.
The Python backend supersedes it in all respects.
