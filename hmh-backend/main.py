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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "code": exc.error_code,
        },
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


# ── Temporary startup seeding ────────────────────────────────────────────────
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