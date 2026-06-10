"""
HMH Group Construction Management System — Backend API
Entry point for Uvicorn.

Run locally:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
import os
import subprocess
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.logging_config import configure_logging, get_logger
from app.core.config import settings

# Configure root logger before any other imports emit log records
configure_logging("DEBUG" if settings.DEBUG else "INFO")
_log = get_logger("hmh.startup")

# ── Fail fast if deployed to production with the default dev secret ────────────
_DEFAULT_SECRET = "dev_secret_change_before_production_minimum_64_chars_long!!"
if settings.is_production and settings.SECRET_KEY == _DEFAULT_SECRET:
    _log.critical(
        "SECURITY ERROR: SECRET_KEY is the default development value. "
        "Set a strong SECRET_KEY environment variable before deploying to production."
    )
    raise RuntimeError(
        "SECRET_KEY must be overridden in production. "
        "Set SECRET_KEY in your environment or .env file."
    )
elif settings.SECRET_KEY == _DEFAULT_SECRET:
    _log.warning(
        "SECRET_KEY is the default dev value. "
        "Override it with a strong random string before deploying."
    )

# ── Fail fast if WhatsApp is enabled in production with the default verify token
_DEFAULT_WA_TOKEN = "hmh_verify_token"
if settings.is_production and settings.WHATSAPP_ENABLED:
    if settings.WHATSAPP_VERIFY_TOKEN == _DEFAULT_WA_TOKEN:
        _log.critical(
            "SECURITY ERROR: WHATSAPP_VERIFY_TOKEN is the default value 'hmh_verify_token'. "
            "Anyone who knows this value can complete the Meta webhook verification against "
            "your endpoint. Set a strong random WHATSAPP_VERIFY_TOKEN in your environment."
        )
        raise RuntimeError(
            "WHATSAPP_VERIFY_TOKEN must be changed from the default before enabling WhatsApp "
            "in production. Set WHATSAPP_VERIFY_TOKEN in your environment."
        )
    if not settings.WHATSAPP_APP_SECRET:
        _log.warning(
            "WHATSAPP_APP_SECRET is not set. Webhook HMAC signature verification is disabled. "
            "Set WHATSAPP_APP_SECRET to your Meta App Secret to secure the webhook endpoint."
        )

from app.core.exceptions import HMHException
from app.api.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.projects import router as projects_router
from app.api.v1.sites import project_sites_router, sites_router
from app.api.v1.lots import project_lots_router, lots_router
from app.api.v1.stages import stages_router, project_stages_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.items import router as items_router, categories_router
from app.api.v1.boq import (
    project_boq_router,
    boq_sections_router,
    boq_items_router,
    boq_item_router,
)
from app.api.v1.material_requests import project_mr_router, mr_router
from app.api.v1.purchase_orders import project_po_router, po_router
from app.api.v1.deliveries import project_delivery_router, delivery_router
from app.api.v1.stock import router as stock_router
from app.api.v1.invoices import project_invoice_router, invoice_router
from app.api.v1.payments import project_payment_router, payment_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.fuel import project_fuel_router, fuel_router
from app.api.v1.attachments import router as attachments_router
from app.api.v1.vehicles import router as vehicles_router
from app.api.v1.allocation import router as allocation_router
from app.api.v1.boq_templates import router as boq_templates_router
from app.api.v1.delivery_capture import router as delivery_capture_router
from app.api.v1.summary import router as summary_router
from app.api.v1.whatsapp_webhook import router as whatsapp_router
from app.api.v1.notification_settings import router as notification_settings_router
from app.api.v1.job_cards import project_jc_router, jc_router
from app.api.v1.site_dashboard import router as site_dashboard_router, project_lot_router as site_dashboard_lot_router
from app.api.v1.gmail import gmail_router, gmail_docs_router
from app.api.v1.proof_packs import router as proof_packs_router
from app.api.v1.site_capture import router as site_capture_router
from app.api.v1.document_ai import router as document_ai_router
from app.api.v1.vision import router as vision_router
from app.api.v1.expenses import router as expenses_router
from app.dependencies import OWNER_ONLY


app = FastAPI(
    title="HMH Group API",
    description="Construction Management System — V1",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Build allowed origins from the env var, then hard-code production origins so
# they can never be accidentally omitted by a Render env-var override.
_cors_origins: list[str] = settings.cors_origins_list

_required_origins = [
    # Production frontend
    "https://app.hmhgroup.co.za",
    "https://www.app.hmhgroup.co.za",
    # Local dev
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
for _o in _required_origins:
    if _o not in _cors_origins:
        _cors_origins.append(_o)

# Explicit methods and headers — do NOT use ["*"] when allow_credentials=True.
# The CORS spec forbids wildcard methods/headers with credentialed requests, and
# some browsers enforce this strictly causing preflight failures for POST/PATCH/DELETE.
_cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
_cors_headers = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Origin",
    "X-Requested-With",
    "Access-Control-Request-Method",
    "Access-Control-Request-Headers",
    "Cache-Control",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
    expose_headers=["Content-Length", "X-Total-Count", "X-Request-ID"],
    max_age=600,
)

from app.middleware.request_context import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

# ── Exception handlers ────────────────────────────────────────────────────────
def _cors_headers_for(request: Request) -> dict[str, str]:
    """
    Return CORS headers matching the request's Origin (if allowed).
    Used to ensure ALL error responses include CORS headers — otherwise browsers
    report any backend error as a CORS failure and hide the real error message.
    """
    origin = request.headers.get("origin", "")
    if origin and origin in _cors_origins:
        return {
            "Access-Control-Allow-Origin":      origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary":                             "Origin",
        }
    return {}


@app.exception_handler(HMHException)
async def hmh_exception_handler(request: Request, exc: HMHException) -> JSONResponse:
    content: dict = {
        "success": False,
        "message": exc.message,
        "code": exc.error_code,
    }
    if exc.detail:
        content["detail"] = exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=_cors_headers_for(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for any unhandled Python exception.

    Gives specific, actionable messages for known database schema errors so the
    browser (and Render logs) show the real cause instead of a generic 500 / fake
    CORS error.  Always adds CORS headers.
    """
    import logging
    log = logging.getLogger(__name__)

    exc_str = str(exc)

    # ── Detect generated-column write attempts ─────────────────────────────────
    # PostgreSQL raises ProgrammingError with "cannot insert into column" when
    # application code tries to write to a GENERATED ALWAYS AS STORED column.
    if "cannot insert into column" in exc_str or "cannot update column" in exc_str:
        # Extract the column name from the error message when possible
        import re
        m = re.search(r'column "([^"]+)"', exc_str)
        col_name = m.group(1) if m else "unknown"
        log.error("Generated column write attempt: %s", exc_str)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": (
                    f"Database schema error: '{col_name}' is a GENERATED ALWAYS column "
                    f"and cannot be written by the application. "
                    f"Fix: use SQLAlchemy Core INSERT (not ORM add) and omit the column."
                ),
                "code": "GENERATED_COLUMN_WRITE",
                "column": col_name,
            },
            headers=_cors_headers_for(request),
        )

    # ── Detect missing column (migration not applied) ──────────────────────────
    if "column" in exc_str and "does not exist" in exc_str:
        m = re.search(r'column "?([^"]+)"? of relation "?([^"]+)"?', exc_str)
        if not m:
            m = re.search(r'"([^"]+)" does not exist', exc_str)
        detail = m.group(0) if m else exc_str[:120]
        log.error("Missing DB column: %s", exc_str)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": (
                    f"Database schema mismatch: {detail}. "
                    f"Run 'alembic upgrade head' to apply pending migrations."
                ),
                "code": "SCHEMA_MIGRATION_REQUIRED",
            },
            headers=_cors_headers_for(request),
        )

    # ── Detect missing table ───────────────────────────────────────────────────
    if "relation" in exc_str and "does not exist" in exc_str:
        log.error("Missing DB table: %s", exc_str)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": (
                    f"Database schema mismatch: {exc_str[:150]}. "
                    f"Run 'alembic upgrade head'."
                ),
                "code": "TABLE_MISSING",
            },
            headers=_cors_headers_for(request),
        )

    # ── Generic catch-all ──────────────────────────────────────────────────────
    log.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error.", "code": "INTERNAL_ERROR"},
        headers=_cors_headers_for(request),
    )

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(project_sites_router, prefix="/api/v1")
app.include_router(sites_router, prefix="/api/v1")
app.include_router(project_lots_router, prefix="/api/v1")
app.include_router(lots_router, prefix="/api/v1")
app.include_router(stages_router, prefix="/api/v1")
app.include_router(project_stages_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(items_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(project_boq_router, prefix="/api/v1")
app.include_router(boq_sections_router, prefix="/api/v1")
app.include_router(boq_items_router, prefix="/api/v1")
app.include_router(boq_item_router, prefix="/api/v1")
app.include_router(project_mr_router, prefix="/api/v1")
app.include_router(mr_router, prefix="/api/v1")
app.include_router(project_po_router, prefix="/api/v1")
app.include_router(po_router, prefix="/api/v1")
app.include_router(project_delivery_router, prefix="/api/v1")
app.include_router(delivery_router, prefix="/api/v1")
app.include_router(stock_router, prefix="/api/v1")
app.include_router(project_invoice_router, prefix="/api/v1")
app.include_router(invoice_router, prefix="/api/v1")
app.include_router(project_payment_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(project_fuel_router, prefix="/api/v1")
app.include_router(fuel_router, prefix="/api/v1")
app.include_router(attachments_router, prefix="/api/v1")
app.include_router(vehicles_router, prefix="/api/v1")
app.include_router(allocation_router, prefix="/api/v1")
app.include_router(boq_templates_router, prefix="/api/v1")
app.include_router(delivery_capture_router, prefix="/api/v1")
app.include_router(summary_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")
app.include_router(notification_settings_router, prefix="/api/v1")
app.include_router(project_jc_router, prefix="/api/v1")
app.include_router(jc_router, prefix="/api/v1")
app.include_router(site_dashboard_router, prefix="/api/v1")
app.include_router(site_dashboard_lot_router, prefix="/api/v1")
app.include_router(gmail_router, prefix="/api/v1")
app.include_router(gmail_docs_router, prefix="/api/v1")
app.include_router(proof_packs_router, prefix="/api/v1")
app.include_router(site_capture_router, prefix="/api/v1")
app.include_router(document_ai_router, prefix="/api/v1")
app.include_router(vision_router,     prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")

from app.api.v1.audit_log import router as audit_router
app.include_router(audit_router, prefix="/api/v1")

from app.api.v1.admin import router as admin_router
app.include_router(admin_router, prefix="/api/v1")

from app.api.v1.reconciliation import router as reconciliation_router
app.include_router(reconciliation_router, prefix="/api/v1")

from app.api.v1.quotations import router as quotations_router
app.include_router(quotations_router, prefix="/api/v1")

from app.api.v1.ops import router as ops_router
app.include_router(ops_router, prefix="/api/v1")

from app.api.v1.warehouse import router as warehouse_router, project_warehouse_router, global_warehouse_router
app.include_router(warehouse_router, prefix="/api/v1")
app.include_router(project_warehouse_router, prefix="/api/v1")
app.include_router(global_warehouse_router, prefix="/api/v1")

from app.api.v1.lot_types import project_lot_types_router, lot_types_router
app.include_router(project_lot_types_router, prefix="/api/v1")
app.include_router(lot_types_router, prefix="/api/v1")

# ── Static file serving for uploaded documents ────────────────────────────────
# Use settings.UPLOAD_DIR (absolute path from env) so the static mount and all
# file-save calls (stages, deliveries, usage, gmail) reference the SAME directory.
# Previously this used os.path.dirname(__file__) + "/uploads" which resolved to
# hmh-backend/uploads, while files were saved to UPLOAD_DIR one level higher.
_uploads_dir = os.path.abspath(settings.UPLOAD_DIR)
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


# ── Internal cron endpoint ───────────────────────────────────────────────────

@app.post("/api/v1/internal/process-notifications", include_in_schema=False)
async def internal_process_notifications(request: Request):
    """
    Lightweight endpoint for Render Cron Job / external scheduler.

    Validates X-Cron-Secret header against CRON_SECRET env var.
    Returns 404 if CRON_SECRET is not set (endpoint disabled), 403 if wrong secret.
    This is a secondary safety net — the primary drain runs in-process every 5 min.
    """
    if not settings.CRON_SECRET:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    import secrets as _secrets
    header_secret = request.headers.get("X-Cron-Secret", "")
    if not _secrets.compare_digest(settings.CRON_SECRET, header_secret):
        _log.warning("internal_cron rejected invalid_secret ip=%s",
                     request.client.host if request.client else "unknown")
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    from app.db.session import SessionLocal
    from app.services.notification_service import process_queue
    _db = SessionLocal()
    try:
        result = process_queue(_db)
        _log.info("internal_cron queue_drain sent=%d mock=%d failed=%d skipped=%d",
                  result.get("sent", 0), result.get("mock_sent", 0),
                  result.get("failed", 0), result.get("skipped", 0))
        return JSONResponse(result)
    except Exception:
        _db.rollback()
        raise
    finally:
        _db.close()


# ── Debug routes ─────────────────────────────────────────────────────────────

@app.get("/api/v1/debug/db-schema", tags=["debug"], dependencies=[OWNER_ONLY])
def db_schema_check():
    """
    Admin-safe DB schema diagnostic: alembic revision, tables, generated columns, warnings.
    No secrets or row data are exposed.
    """
    import sqlalchemy as _sa
    from app.db.base import Base
    import app.models  # noqa

    engine      = _sa.create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    inspector   = _sa.inspect(engine)
    live_tables = inspector.get_table_names()
    orm_tables  = list(Base.metadata.tables.keys())

    revision = None
    try:
        with engine.connect() as conn:
            row = conn.execute(_sa.text("SELECT version_num FROM alembic_version")).fetchone()
            revision = str(row[0]) if row else None
    except Exception:
        revision = "ERROR — alembic_version table not found"

    generated: dict = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(_sa.text("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND is_generated = 'ALWAYS'
                ORDER BY table_name, column_name
            """)).fetchall()
            for tbl, col in rows:
                generated.setdefault(tbl, []).append(col)
    except Exception as exc:
        generated = {"error": [str(exc)]}

    from app.models.boq import BOQItem
    boq_pt = BOQItem.__table__.columns.get("planned_total")
    has_computed = (
        boq_pt is not None
        and hasattr(boq_pt, "computed")
        and boq_pt.computed is not None
    )

    warnings_list = []
    if not has_computed:
        warnings_list.append(
            "boq_items.planned_total: ORM column lacks Computed() — "
            "ORM inserts will include planned_total=NULL and fail on "
            "PostgreSQL GENERATED ALWAYS columns"
        )
    missing = sorted(set(orm_tables) - set(live_tables))
    if missing:
        warnings_list.append(f"Tables in ORM but missing from DB: {missing} — run alembic upgrade head")

    return {
        "database_dialect":  engine.dialect.name,
        "alembic_revision":  revision,
        "live_tables_count": len(live_tables),
        "orm_tables_count":  len(orm_tables),
        "missing_tables":    missing,
        "generated_columns": generated,
        "boq_planned_total_has_computed_declaration": has_computed,
        "warnings":          warnings_list,
        "status":            "OK" if not warnings_list else "SCHEMA_WARNINGS",
    }


@app.get("/api/v1/debug/routes", tags=["debug"], dependencies=[OWNER_ONLY])
def list_routes():
    """
    Returns all registered route paths and their HTTP methods.
    Useful for production diagnostics without exposing secrets.
    """
    from fastapi.routing import APIRoute
    routes = [
        {
            "path":    r.path,
            "methods": sorted(list(r.methods or [])),
            "name":    r.name,
        }
        for r in app.routes
        if isinstance(r, APIRoute)
    ]
    return {
        "total_routes": len(routes),
        "app_env":       settings.APP_ENV,
        "cors_origins":  _cors_origins,
        "routes":        sorted(routes, key=lambda r: r["path"]),
    }


# ── Background notification queue drain ──────────────────────────────────────
import asyncio as _asyncio


async def _queue_drain_loop() -> None:
    """
    Drain the notification queue every 5 minutes.

    Runs as a background asyncio task for the lifetime of the process.
    Equivalent to a Render Cron Job calling POST /api/v1/alerts/queue/process,
    but runs in-process so it works out of the box without external configuration.

    Set WHATSAPP_ENABLED=false to suppress all real sends; the loop still runs
    so queue rows are processed (marked MOCK_SENT / FAILED) and the system
    remains testable without real WhatsApp credentials.
    """
    # Short startup delay so DB connections are established before first drain.
    await _asyncio.sleep(30)
    while True:
        try:
            from app.db.session import SessionLocal
            from app.services.notification_service import process_queue
            _db = SessionLocal()
            try:
                result = process_queue(_db)
                total = result.get("sent", 0) + result.get("mock_sent", 0) + result.get("failed", 0)
                if total > 0:
                    _log.info(
                        "queue_drain sent=%d mock_sent=%d failed=%d skipped=%d",
                        result.get("sent", 0), result.get("mock_sent", 0),
                        result.get("failed", 0), result.get("skipped", 0),
                    )
            finally:
                _db.close()
        except Exception:
            _log.exception("queue_drain background task error — will retry in 5 min")
        await _asyncio.sleep(300)  # 5 minutes


@app.on_event("startup")
async def _start_background_queue_drain() -> None:
    """Launch the background queue drain loop as a fire-and-forget asyncio task."""
    _asyncio.create_task(_queue_drain_loop())
    _log.info("startup queue_drain_task=started interval=300s")


# ── Startup logging ────────────────────────────────────────────────────────────
@app.on_event("startup")
def _log_startup_config() -> None:
    """Log non-secret configuration at startup for production diagnostics."""
    from fastapi.routing import APIRoute
    api_routes = [r for r in app.routes if isinstance(r, APIRoute)]
    import os as _os
    _upload_exists = _os.path.isdir(settings.UPLOAD_DIR)
    _upload_abs    = _os.path.abspath(settings.UPLOAD_DIR)
    from app.core.storage import storage_mode, verify_supabase_connection
    _mode  = storage_mode()
    _check = verify_supabase_connection()

    _log.info("HMH_BACKEND_BUILD_MARKER=observability-v1")
    _log.info("startup app_env=%s debug=%s routes=%d", settings.APP_ENV, settings.DEBUG, len(api_routes))
    _log.info("startup cors_origins=%s", _cors_origins)
    _log.info("startup upload_dir=%s abs=%s exists=%s", settings.UPLOAD_DIR, _upload_abs, _upload_exists)
    if not _upload_exists:
        _log.warning("startup UPLOAD_DIR missing — check for path typo")
    _log.info("startup storage_mode=%s", _mode.upper())
    if _mode == "supabase":
        if _check["ok"]:
            _log.info("startup supabase=OK photos stored permanently")
        else:
            _log.error("startup supabase=ERROR %s", _check.get("error", "unknown"))
    else:
        _log.warning("startup supabase=NOT_CONFIGURED photos will be lost on Render restart")
    _log.info("startup smtp_enabled=%s whatsapp_enabled=%s", settings.SMTP_ENABLED, settings.WHATSAPP_ENABLED)

    # OCR / Vision
    from app.services.document_ai_service import validate_ocr_setup
    _ocr = validate_ocr_setup()
    if _ocr["ready"]:
        _log.info("startup ocr_provider=%s %s", _ocr["provider"], _ocr["message"])
    else:
        _log.warning("startup ocr_not_ready provider=%s — %s", _ocr["provider"], _ocr["message"])


# ── Temporary startup seeding ────────────────────────────────────────────────
@app.on_event("startup")
def ensure_default_stages() -> None:
    """Auto-seed construction stages if the stage_master table is empty."""
    try:
        from app.db.session import SessionLocal
        from app.services.stage_service import seed_default_stages, list_stage_masters
        db = SessionLocal()
        try:
            if not list_stage_masters(db):
                seed_default_stages(db)
                _log.info("Default stages seeded on startup.")
        finally:
            db.close()
    except Exception as exc:
        _log.warning("Stage auto-seed skipped: %s", exc)


@app.on_event("startup")
def run_demo_seed_once() -> None:
    """
    Runs optional startup seed scripts when RUN_STARTUP_SEED=true.
    Keep this enabled only long enough to seed production once,
    then switch RUN_STARTUP_SEED=false in Render.
    """
    should_seed = os.getenv("RUN_STARTUP_SEED", "false").lower() == "true"
    if not should_seed:
        _log.debug("Startup seed skipped (RUN_STARTUP_SEED not set).")
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    scripts_dir = os.path.join(base_dir, "scripts")

    seed_scripts = [
        "seed_stages.py",
        "seed_owner.py",
    ]

    for script_name in seed_scripts:
        script_path = os.path.join(scripts_dir, script_name)

        if not os.path.exists(script_path):
            _log.warning("Seed script not found: %s", script_path)
            continue

        try:
            _log.info("Running startup seed: %s", script_name)
            subprocess.run([sys.executable, script_path], check=True)
            _log.info("Seed completed: %s", script_name)
        except subprocess.CalledProcessError as exc:
            _log.error("Seed script failed: %s -> %s", script_name, exc)
        except Exception as exc:
            _log.error("Unexpected seed error in %s: %s", script_name, exc)