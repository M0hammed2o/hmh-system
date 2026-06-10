"""Procurement Analytics API — Phase 5."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.dependencies import ALL_ROLES, DbSession
from app.services import export_service, procurement_analytics_service as svc
from app.services.procurement_reconciliation_service import build_detail, list_reconciliations

router = APIRouter(prefix="/procurement-analytics", tags=["Procurement Analytics"])


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", dependencies=[ALL_ROLES])
def dashboard(
    db: DbSession,
    project_id:  Optional[uuid.UUID] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    date_from:   Optional[date]       = Query(None),
    date_to:     Optional[date]       = Query(None),
):
    data = svc.get_dashboard_stats(db, project_id, supplier_id, date_from, date_to)
    return {"data": data}


# ── Supplier Performance ──────────────────────────────────────────────────────

@router.get("/supplier-performance", dependencies=[ALL_ROLES])
def all_supplier_scores(db: DbSession):
    data = svc.get_all_supplier_scores(db)
    return {"data": data}


@router.get("/supplier-performance/{supplier_id}", dependencies=[ALL_ROLES])
def supplier_score(supplier_id: uuid.UUID, db: DbSession):
    from app.models.supplier import Supplier
    from fastapi import HTTPException
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")
    data = svc.compute_supplier_score(db, supplier_id)
    data["supplier_name"] = s.name
    data["supplier_code"] = s.code or ""
    return {"data": data}


# ── Supplier Spend Analysis ───────────────────────────────────────────────────

@router.get("/supplier-spend", dependencies=[ALL_ROLES])
def supplier_spend(db: DbSession, limit: int = Query(10, ge=1, le=50)):
    data = svc.get_supplier_spend_analysis(db, limit=limit)
    return {"data": data}


# ── Project Analytics ─────────────────────────────────────────────────────────

@router.get("/project-analytics", dependencies=[ALL_ROLES])
def project_analytics(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    data = svc.get_project_analytics(db, project_id)
    return {"data": data}


# ── Price History ─────────────────────────────────────────────────────────────

@router.get("/price-history", dependencies=[ALL_ROLES])
def price_history(
    db: DbSession,
    item_id:     Optional[uuid.UUID] = Query(None),
    search:      Optional[str]       = Query(None),
    project_id:  Optional[uuid.UUID] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    limit:       int                  = Query(200, ge=1, le=500),
):
    data = svc.get_price_history(db, item_id, search, project_id, supplier_id, limit)
    return {"data": data}


# ── Quotation Comparison ──────────────────────────────────────────────────────

@router.get("/quotation-comparison/mrs", dependencies=[ALL_ROLES])
def mrs_with_multiple_quotes(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    data = svc.list_mrs_with_multiple_quotes(db, project_id)
    return {"data": data}


@router.get("/quotation-comparison/{mr_id}", dependencies=[ALL_ROLES])
def quotation_comparison(mr_id: uuid.UUID, db: DbSession):
    data = svc.get_quotation_comparison(db, mr_id)
    return {"data": data}


# ── Procurement Savings ───────────────────────────────────────────────────────

@router.get("/savings-report", dependencies=[ALL_ROLES])
def savings_report(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    data = svc.get_savings_report(db, project_id)
    return {"data": data}


# ── Management Reports — Excel ────────────────────────────────────────────────

@router.get("/reports/supplier-spend/excel", dependencies=[ALL_ROLES])
def report_supplier_spend_excel(db: DbSession, limit: int = Query(10, ge=1, le=50)):
    data = svc.get_supplier_spend_analysis(db, limit=limit)
    buf = export_service.export_supplier_spend_excel(data)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=supplier_spend.xlsx"},
    )


@router.get("/reports/outstanding-orders/excel", dependencies=[ALL_ROLES])
def report_outstanding_orders_excel(db: DbSession):
    data = svc.get_project_analytics(db)
    buf = export_service.export_outstanding_orders_excel(data)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=outstanding_orders.xlsx"},
    )


@router.get("/reports/savings/excel", dependencies=[ALL_ROLES])
def report_savings_excel(db: DbSession):
    data = svc.get_savings_report(db)
    buf = export_service.export_savings_excel(data)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=procurement_savings.xlsx"},
    )


@router.get("/reports/reconciliation/excel", dependencies=[ALL_ROLES])
def report_reconciliation_excel(db: DbSession):
    recons = list_reconciliations(db, limit=1000)
    data = [build_detail(db, r) for r in recons]
    buf = export_service.export_reconciliation_excel(data)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reconciliation_report.xlsx"},
    )


# ── Management Reports — PDF ──────────────────────────────────────────────────

@router.get("/reports/supplier-spend/pdf", dependencies=[ALL_ROLES])
def report_supplier_spend_pdf(db: DbSession, limit: int = Query(10, ge=1, le=50)):
    data = svc.get_supplier_spend_analysis(db, limit=limit)
    buf = export_service.export_supplier_spend_pdf(data)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=supplier_spend.pdf"},
    )


@router.get("/reports/outstanding-orders/pdf", dependencies=[ALL_ROLES])
def report_outstanding_orders_pdf(db: DbSession):
    data = svc.get_project_analytics(db)
    buf = export_service.export_outstanding_orders_pdf(data)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=outstanding_orders.pdf"},
    )


@router.get("/reports/savings/pdf", dependencies=[ALL_ROLES])
def report_savings_pdf(db: DbSession):
    data = svc.get_savings_report(db)
    buf = export_service.export_savings_pdf(data)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=procurement_savings.pdf"},
    )


@router.get("/reports/reconciliation/pdf", dependencies=[ALL_ROLES])
def report_reconciliation_pdf(db: DbSession):
    recons = list_reconciliations(db, limit=1000)
    data = [build_detail(db, r) for r in recons]
    buf = export_service.export_reconciliation_pdf(data)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=reconciliation_report.pdf"},
    )
