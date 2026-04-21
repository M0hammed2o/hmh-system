# HMH Group Construction Management System — Backend

**Stack:** Python 3.12 · FastAPI · PostgreSQL 15+ · SQLAlchemy 2.0 · Alembic · Pydantic v2

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| PostgreSQL | 15+ |
| pip | latest |

---

## First-time setup

### 1. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, etc.
```

Minimum required changes in `.env`:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/hmh_system
SECRET_KEY=your_random_64_char_secret_here
```

### 4. Start the database (Docker)

The project uses Docker for local PostgreSQL. The backend runs on your machine directly; only the DB runs in a container.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

```bash
# Start the container in the background (first run pulls the image)
docker compose up -d db

# Confirm the container is healthy before proceeding
docker compose ps
```

Expected output once healthy:

```
NAME           STATUS
hmh-postgres   Up (healthy)
```

**Stop the container (data is preserved in the Docker volume):**

```bash
docker compose stop db
```

**Destroy the container and all data (full reset):**

```bash
docker compose down -v
```

---

### 5. Apply the schema

Run from the `hmh-backend/` directory. Wait until the container reports `healthy` before running this.

```bash
docker exec -i hmh-postgres psql -U hmh -d hmh_system < ../hmh-docs/hmh_v1_schema.sql
```

> **Note:** This is the only correct way to apply the initial schema. Alembic autogenerate does not recreate PostgreSQL-native types (enums, `GENERATED ALWAYS AS`, `UNIQUE NULLS NOT DISTINCT`). Use Alembic only for incremental migrations after the first deploy.

---

### 6. Test the DB connection

```bash
docker exec -it hmh-postgres psql -U hmh -d hmh_system -c "\dt"
```

You should see all tables listed (`users`, `projects`, `sites`, `lots`, etc.).

---

### 7. Seed reference data

```bash
python scripts/seed_stages.py
```

Inserts the 11 locked V1 stages into `stage_master`. Safe to re-run.

---

### 8. Start the development server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)

Health check: [http://localhost:8000/health](http://localhost:8000/health)

---

## Project structure

```
hmh-backend/
├── app/
│   ├── api/            ← FastAPI routers (health + future route modules)
│   ├── core/           ← config, security helpers, exceptions
│   ├── db/             ← SQLAlchemy base + session factory
│   ├── models/         ← ORM models (enums, user, project, site, lot, stage, access)
│   ├── schemas/        ← Pydantic v2 request/response schemas
│   ├── services/       ← Business logic layer (populated per module)
│   ├── utils/          ← Shared helpers
│   └── dependencies.py ← FastAPI Depends() building blocks (auth, roles)
├── alembic/            ← Migration scripts
├── scripts/            ← Admin and seed scripts
├── main.py             ← Application entry point
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md
```

---

## V1 Stage list (locked)

| Order | Name |
|-------|------|
| 1 | Platform |
| 2 | Slab |
| 3 | Wallplate |
| 4 | Roof |
| 5 | Completion |
| 6 | Plumbing |
| 7 | Paint |
| 8 | Tank |
| 9 | Apron |
| 10 | Screed |
| 11 | Beam Filling |

---

## Environment variables reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `SECRET_KEY` | ✅ | — | JWT signing key (min 32 chars) |
| `APP_ENV` | — | `development` | `development` / `production` |
| `DEBUG` | — | `false` | Enables SQL logging and /docs |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | `480` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | — | `7` | JWT refresh token lifetime |
| `UPLOAD_DIR` | — | `./uploads` | File upload directory |
| `MAX_UPLOAD_SIZE_MB` | — | `5` | Max file upload size |
| `CORS_ORIGINS` | — | `localhost:3000,...` | Comma-separated allowed origins |

---

## Schema source of truth

The canonical schema is at:

```
hmh-docs/hmh_v1_schema.sql
```

Do not make direct schema changes without updating that file and creating a corresponding Alembic migration.
