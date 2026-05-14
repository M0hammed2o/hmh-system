"""
HMH Group Construction Management System — Backend API
Entry point for Uvicorn.

Run locally:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import subprocess
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
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
from app.api.v1.job_cards import project_jc_router, jc_router
from app.api.v1.site_dashboard import router as site_dashboard_router
from app.api.v1.gmail import gmail_router, gmail_docs_router
from app.api.v1.proof_packs import router as proof_packs_router
from app.api.v1.site_capture import router as site_capture_router
from app.api.v1.document_ai import router as document_ai_router
from app.api.v1.expenses import router as expenses_router


app = FastAPI(
    title="HMH Group API",
    description="Construction Management System — V1",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# CORS_ORIGINS env var: comma-separated list of allowed origins.
# Always includes localhost for local dev.
_cors_origins = settings.cors_origins_list
if "http://localhost:5173" not in _cors_origins:
    _cors_origins.append("http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(HMHException)
async def hmh_exception_handler(request: Request, exc: HMHException) -> JSONResponse:
    content: dict = {
        "success": False,
        "message": exc.message,
        "code": exc.error_code,
    }
    if exc.detail:
        content["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=content)

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
app.include_router(project_jc_router, prefix="/api/v1")
app.include_router(jc_router, prefix="/api/v1")
app.include_router(site_dashboard_router, prefix="/api/v1")
app.include_router(gmail_router, prefix="/api/v1")
app.include_router(gmail_docs_router, prefix="/api/v1")
app.include_router(proof_packs_router, prefix="/api/v1")
app.include_router(site_capture_router, prefix="/api/v1")
app.include_router(document_ai_router, prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")

# ── Static file serving for uploaded documents ────────────────────────────────
_uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


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
                print("Default stages seeded on startup.")
        finally:
            db.close()
    except Exception as exc:
        print(f"Stage auto-seed skipped: {exc}")


@app.on_event("startup")
def run_demo_seed_once() -> None:
    """
    Runs optional startup seed scripts when RUN_STARTUP_SEED=true.
    Keep this enabled only long enough to seed production once,
    then switch RUN_STARTUP_SEED=false in Render.
    """
    should_seed = os.getenv("RUN_STARTUP_SEED", "false").lower() == "true"
    if not should_seed:
        print("Startup seed skipped.")
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
            print(f"Seed script not found: {script_path}")
            continue

        try:
            print(f"Running startup seed: {script_name}")
            subprocess.run([sys.executable, script_path], check=True)
            print(f"Seed completed: {script_name}")
        except subprocess.CalledProcessError as exc:
            print(f"Seed script failed: {script_name} -> {exc}")
        except Exception as exc:
            print(f"Unexpected seed error in {script_name}: {exc}")