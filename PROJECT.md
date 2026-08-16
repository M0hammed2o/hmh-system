# HMH Construction OS — Project Map
<!-- Hard cap 200 lines. Update this file whenever structure, stack, or commands change. -->

## Purpose
Current scope includes standalone Fuel Management and an installable mobile PWA. Fuel transactions are intentionally separate from BOQ quantities and procurement calculations.
Full-stack construction management platform for HMH Group and Minerat Construction & Civils.
Covers project hierarchy (project → site → lot), full procurement pipeline (MR → Quote → PO → Delivery → Invoice → Payment), warehouse and stock management, workshop/fleet management with repair workflow, municipality progress claims (physical evidence only — no pricing), programme planning (Gantt-style with baseline), weekly work planning with progress propagation, WhatsApp-based alert system, Gmail OCR pipeline for automated invoice ingestion, and reporting. Two portal modes: office (full) and site (restricted tablet view).

## Stack
| Layer | Technology | Version |
|---|---|---|
| Backend | Python / FastAPI | 3.11.9 / 0.115.6 |
| ORM | SQLAlchemy | 2.0.36 |
| Migrations | Alembic | 1.14.0 |
| Validation | Pydantic v2 | 2.10.3 |
| Frontend | React + TypeScript | 18.3.1 / 5.8.3 |
| Build | Vite + SWC | 5.4.19 |
| CSS | Tailwind CSS | 3.4.17 |
| UI primitives | Radix UI | various |
| Database | PostgreSQL | 15+ |
| File storage | Local (dev) / Supabase (prod) | — |
| Notifications | WhatsApp Cloud API (Meta) | v25.0 |
| Email | SMTP/IMAP via Gmail | — |
| AI/OCR | Claude API (Anthropic) + Google Vision | — |
| Deploy | Render (web + static + cron) | — |

## Directory Map
```
hmh-backend/                  ← FastAPI backend (Python 3.11.9)
  main.py                     ← App factory, CORS, routers, cron endpoints, background drain
  requirements.txt            ← Pinned Python dependencies
  .env.example                ← Env var template (copy to .env)
  alembic.ini                 ← Alembic config; DATABASE_URL overridden at runtime
  docker-compose.yml          ← Local PostgreSQL 15 container on port 55432
  app/
    api/v1/                   ← 50+ FastAPI route modules (one file per domain)
    models/                   ← 40 SQLAlchemy ORM models + enums.py
    schemas/                  ← Pydantic v2 request/response schemas
    services/                 ← 45 business-logic service files
    core/                     ← config.py, security.py, exceptions.py, logging_config.py, storage.py
    db/                       ← base.py (DeclarativeBase), session.py (get_db, SessionLocal)
    middleware/               ← RequestContextMiddleware
    utils/                    ← Shared helpers
    dependencies.py           ← JWT auth, role guards, check_project_access()
  alembic/
    versions/                 ← 67 incremental migration scripts (0001–0067)
  tests/                      ← 50+ pytest integration/unit test files
  scripts/                    ← seed_stages.py, seed_owner.py, seed_demo.py
hmh-frontend/                 ← React 18 + TypeScript SPA
  src/
    api/                      ← 40+ typed Axios API client modules
    pages/                    ← 45 page components (lazy-loaded)
    routes/                   ← AppRouter.tsx, ProtectedRoute, SiteRoute
    components/               ← Shared layout and UI components
    context/                  ← Auth context (useAuthContext)
    hooks/                    ← Custom hooks
    lib/                      ← format.ts, constants.ts
hmh-docs/
  hmh_v1_schema.sql           ← Canonical PostgreSQL schema (source of truth for enums + generated cols)
```

## Key Entry Points
| Type | Location |
|---|---|
| Backend app | `hmh-backend/main.py` (Uvicorn: `uvicorn main:app`) |
| Frontend app | `hmh-frontend/src/main.tsx` → `AppRouter.tsx` |
| Background queue drain | `_queue_drain_loop()` in main.py — asyncio, 30s or on enqueue signal |
| Cron: queue drain | `POST /api/v1/internal/process-notifications` (X-Cron-Secret) |
| Cron: daily summary | `POST /api/v1/internal/send-daily-summary` (X-Cron-Secret) |
| Cron: payment due scan | `POST /api/v1/internal/scan-payment-due` (X-Cron-Secret) |
| WhatsApp webhook | `POST /api/v1/whatsapp/webhook` (HMAC-verified) |

## Role Hierarchy
`OWNER` > `OFFICE_ADMIN` > `OFFICE_USER` ≈ `PROCUREMENT_LEAD` > `SITE_MANAGER` > `SITE_STAFF` > `SITE_MANAGER_VIEW` > `READ_ONLY`

Office-level roles (`OWNER` through `PROCUREMENT_LEAD`, `READ_ONLY`) see all projects.
Site-level roles (`SITE_MANAGER`, `SITE_STAFF`, `SITE_MANAGER_VIEW`) require an explicit `UserProjectAccess` row — enforced by `check_project_access()` in `app/dependencies.py`.

## Data Stores & External Services
| Service | Purpose |
|---|---|
| PostgreSQL 15 | Primary data store — all business data |
| Local filesystem / Supabase | File attachments (`UPLOAD_DIR` env var) |
| WhatsApp Cloud API (Meta) | Outbound alerts + inbound webhook |
| Gmail SMTP | Outbound procurement emails (PO/quote sends) |
| Gmail IMAP | Inbound inbox reader — fetches procurement emails |
| Claude API (Anthropic) | AI field extraction from OCR'd documents |
| Google Cloud Vision | OCR for PDF/image invoices |
| Render | Hosting: Python web + static SPA + cron |

## Environments
| Env | DB | WhatsApp | Swagger | Notes |
|---|---|---|---|---|
| `development` | Docker (`localhost:55432`) | Disabled (`MOCK_SENT`) | `/docs` enabled | DEBUG=true, SQL logging |
| `production` | External PostgreSQL | Enabled (if configured) | Hidden | Startup secret checks enforced |

Production URLs: `https://app.hmhgroup.co.za` (frontend) · `https://hmh-backend.onrender.com` (backend)

## Commands
```bash
# ── Backend ────────────────────────────────────────────────────────
cd hmh-backend

# Install
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Start local DB
docker compose up -d db
docker compose ps               # wait for "Up (healthy)"

# Apply initial schema (first time only)
docker exec -i hmh-postgres psql -U hmh -d hmh_system < ../hmh-docs/hmh_v1_schema.sql

# Apply incremental migrations
alembic upgrade head

# Run dev server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest tests/ -v
pytest tests/test_procurement_flow.py -v  # single file

# ── Frontend ───────────────────────────────────────────────────────
cd hmh-frontend

npm ci
npm run dev         # dev server on :5173
npm run build       # production build → dist/
npm run lint        # ESLint

# Browser/PWA checks
npm run test:pwa
```

## Must Not Break
- JWT auth and role-gating on all non-public routes
- `check_project_access()` for site-level role project isolation
- `StockLedger` immutable append-only pattern (no direct balance mutation)
- WhatsApp webhook HMAC verification (when `WHATSAPP_APP_SECRET` is set)
- `ApiSuccess[T]` response wrapper on all API responses
- Alembic migration chain (never drop or re-number existing migrations)
- Fuel ledger is separate from BOQ; completed fuel movements use reversals/adjustments, never hard delete
- Service worker must never cache API/auth/private responses
- Cron secret comparison via `secrets.compare_digest()` (timing-safe)
