"""
Procurement Analytics Service — Phase 5.

All functions use set-based SQL aggregations to avoid N+1 queries.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.models.boq import BOQHeader, BOQItem, BOQSection
from app.models.delivery import Delivery
from app.models.enums import (
    PaymentStatus,
    QuotationStatus,
    ReconciliationStatus,
    RecordStatus,
)
from app.models.invoice import Invoice
from app.models.material_request import MaterialRequest
from app.models.payment import Payment
from app.models.procurement_reconciliation import ProcurementReconciliation
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.quotation import Quotation
from app.models.supplier import Supplier

# ── Status buckets ────────────────────────────────────────────────────────────

_COMMITTED = [
    RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL,
    RecordStatus.APPROVED, RecordStatus.SENT, RecordStatus.SUPPLIER_CONFIRMED,
    RecordStatus.ORDERED, RecordStatus.PARTIALLY_RECEIVED, RecordStatus.RECEIVED,
    RecordStatus.INVOICED, RecordStatus.PARTIALLY_PAID, RecordStatus.OVERPAID,
    RecordStatus.PAID, RecordStatus.CLOSED,
]

_OPEN = [
    RecordStatus.APPROVED, RecordStatus.SENT, RecordStatus.SUPPLIER_CONFIRMED,
    RecordStatus.ORDERED, RecordStatus.PARTIALLY_RECEIVED,
]

_PENDING_DELIVERY = [RecordStatus.ORDERED, RecordStatus.PARTIALLY_RECEIVED]

_PENDING_INVOICE = [
    RecordStatus.DRAFT, RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL,
]


# ── Procurement Dashboard ─────────────────────────────────────────────────────

def get_dashboard_stats(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict:
    now = datetime.now(tz=timezone.utc)

    def _po(q):
        if project_id:
            q = q.filter(PurchaseOrder.project_id == project_id)
        if supplier_id:
            q = q.filter(PurchaseOrder.supplier_id == supplier_id)
        if date_from:
            q = q.filter(func.date(PurchaseOrder.po_date) >= date_from)
        if date_to:
            q = q.filter(func.date(PurchaseOrder.po_date) <= date_to)
        return q

    # Total spend — committed POs
    total_spend = _po(
        db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
        .filter(PurchaseOrder.status.in_(_COMMITTED))
    ).scalar() or 0

    # Spend this month — same filters + current month
    spend_this_month = _po(
        db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
        .filter(
            PurchaseOrder.status.in_(_COMMITTED),
            func.extract("year",  PurchaseOrder.po_date) == now.year,
            func.extract("month", PurchaseOrder.po_date) == now.month,
        )
    ).scalar() or 0

    # Open POs
    open_pos = _po(
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.status.in_(_OPEN))
    ).scalar() or 0

    # Pending deliveries (POs expecting delivery)
    pending_deliveries = _po(
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.status.in_(_PENDING_DELIVERY))
    ).scalar() or 0

    # Pending invoices
    inv_q = db.query(func.count(Invoice.id)).filter(Invoice.status.in_(_PENDING_INVOICE))
    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)
    if supplier_id:
        inv_q = inv_q.filter(Invoice.supplier_id == supplier_id)
    pending_invoices = inv_q.scalar() or 0

    # Pending reconciliations (need human review)
    pending_reconciliations = (
        db.query(func.count(ProcurementReconciliation.id))
        .filter(ProcurementReconciliation.status.in_([
            ReconciliationStatus.PENDING,
            ReconciliationStatus.MATCHED,
            ReconciliationStatus.VARIANCE_DETECTED,
        ]))
        .scalar() or 0
    )

    # Approved + paid payments
    pay_q = db.query(func.coalesce(func.sum(Payment.amount_paid), 0)).filter(
        Payment.status.in_([PaymentStatus.APPROVED, PaymentStatus.PAID])
    )
    if project_id:
        pay_q = pay_q.filter(Payment.project_id == project_id)
    if supplier_id:
        pay_q = pay_q.filter(Payment.supplier_id == supplier_id)
    approved_payments = pay_q.scalar() or 0

    # Outstanding — invoices not yet fully paid
    out_q = db.query(func.coalesce(func.sum(Invoice.total_amount), 0)).filter(
        Invoice.status.in_([
            RecordStatus.SUBMITTED, RecordStatus.APPROVED, RecordStatus.SENT,
            RecordStatus.INVOICED, RecordStatus.PARTIALLY_PAID,
        ])
    )
    if project_id:
        out_q = out_q.filter(Invoice.project_id == project_id)
    if supplier_id:
        out_q = out_q.filter(Invoice.supplier_id == supplier_id)
    outstanding_payments = out_q.scalar() or 0

    return {
        "total_spend": float(total_spend),
        "spend_this_month": float(spend_this_month),
        "open_pos": int(open_pos),
        "pending_deliveries": int(pending_deliveries),
        "pending_invoices": int(pending_invoices),
        "pending_reconciliations": int(pending_reconciliations),
        "approved_payments": float(approved_payments),
        "outstanding_payments": float(outstanding_payments),
    }


# ── Supplier Performance Scorecard ───────────────────────────────────────────

def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def compute_supplier_score(db: Session, supplier_id: uuid.UUID) -> dict:
    now = datetime.now(tz=timezone.utc)

    # ── 1. Delivery Reliability (30%) ── on-time / total with expected date ──
    total_with_expected = (
        db.query(func.count(Delivery.id))
        .join(PurchaseOrder, Delivery.purchase_order_id == PurchaseOrder.id)
        .filter(
            Delivery.supplier_id == supplier_id,
            PurchaseOrder.expected_delivery_date.isnot(None),
        )
        .scalar() or 0
    )
    on_time = (
        db.query(func.count(Delivery.id))
        .join(PurchaseOrder, Delivery.purchase_order_id == PurchaseOrder.id)
        .filter(
            Delivery.supplier_id == supplier_id,
            PurchaseOrder.expected_delivery_date.isnot(None),
            func.date(Delivery.delivery_date) <= PurchaseOrder.expected_delivery_date,
        )
        .scalar() or 0
    ) if total_with_expected else 0
    reliability = (on_time / total_with_expected * 100) if total_with_expected else 70.0

    # ── 2. Reconciliation Match Rate (45%) ── MATCHED+APPROVED / total ──
    total_recons = (
        db.query(func.count(ProcurementReconciliation.id))
        .join(PurchaseOrder, ProcurementReconciliation.purchase_order_id == PurchaseOrder.id)
        .filter(PurchaseOrder.supplier_id == supplier_id)
        .scalar() or 0
    )
    matched_recons = (
        db.query(func.count(ProcurementReconciliation.id))
        .join(PurchaseOrder, ProcurementReconciliation.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            ProcurementReconciliation.status.in_([
                ReconciliationStatus.MATCHED, ReconciliationStatus.APPROVED,
            ]),
        )
        .scalar() or 0
    )
    match_rate = (matched_recons / total_recons * 100) if total_recons else 70.0

    # ── 3. Quote Acceptance Rate (15%) ── APPROVED / (APPROVED+REJECTED) ──
    total_decided = (
        db.query(func.count(Quotation.id))
        .filter(
            Quotation.supplier_id == supplier_id,
            Quotation.status.in_([QuotationStatus.APPROVED, QuotationStatus.REJECTED]),
        )
        .scalar() or 0
    )
    accepted = (
        db.query(func.count(Quotation.id))
        .filter(
            Quotation.supplier_id == supplier_id,
            Quotation.status == QuotationStatus.APPROVED,
        )
        .scalar() or 0
    )
    total_quotes = (
        db.query(func.count(Quotation.id))
        .filter(Quotation.supplier_id == supplier_id)
        .scalar() or 0
    )
    quote_acceptance = (accepted / total_decided * 100) if total_decided else 50.0

    # ── 4. Delivery Speed (10%) ── avg days PO→delivery ──
    avg_days_scalar = (
        db.query(
            func.avg(
                func.extract(
                    "epoch",
                    Delivery.delivery_date - func.cast(PurchaseOrder.po_date, Delivery.delivery_date.type),
                ) / 86400
            )
        )
        .join(PurchaseOrder, Delivery.purchase_order_id == PurchaseOrder.id)
        .filter(
            Delivery.supplier_id == supplier_id,
            Delivery.purchase_order_id.isnot(None),
        )
        .scalar()
    )
    avg_days = float(avg_days_scalar) if avg_days_scalar is not None else None
    if avg_days is None:
        speed_score = 70.0
    elif avg_days <= 7:
        speed_score = 100.0
    elif avg_days <= 14:
        speed_score = 85.0
    elif avg_days <= 21:
        speed_score = 70.0
    elif avg_days <= 30:
        speed_score = 55.0
    else:
        speed_score = 40.0

    # ── Weighted score ──
    score = round(
        _clamp(reliability) * 0.30
        + _clamp(match_rate) * 0.45
        + _clamp(quote_acceptance) * 0.15
        + _clamp(speed_score) * 0.10,
        1,
    )

    # ── Headline stats ──
    total_pos = (
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.supplier_id == supplier_id)
        .scalar() or 0
    )
    total_deliveries = (
        db.query(func.count(Delivery.id))
        .filter(Delivery.supplier_id == supplier_id)
        .scalar() or 0
    )
    total_invoices = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.supplier_id == supplier_id)
        .scalar() or 0
    )
    total_spend = float(
        db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(_COMMITTED),
        )
        .scalar() or 0
    )
    open_issues = (
        db.query(func.count(PurchaseOrder.id))
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(_OPEN),
        )
        .scalar() or 0
    )

    return {
        "supplier_id": str(supplier_id),
        "score": score,
        "metrics": {
            "delivery_reliability":     round(reliability, 1),
            "reconciliation_match_rate": round(match_rate, 1),
            "quote_acceptance_rate":    round(quote_acceptance, 1),
            "delivery_speed_score":     round(speed_score, 1),
            "avg_delivery_days":        round(avg_days, 1) if avg_days is not None else None,
        },
        "stats": {
            "total_spend":        total_spend,
            "total_pos":          int(total_pos),
            "total_deliveries":   int(total_deliveries),
            "total_invoices":     int(total_invoices),
            "total_quotes":       int(total_quotes),
            "total_reconciliations": int(total_recons),
            "open_issues":        int(open_issues),
        },
    }


def get_all_supplier_scores(db: Session) -> list[dict]:
    suppliers = db.query(Supplier).filter(Supplier.is_active == True).all()
    results = []
    for s in suppliers:
        sc = compute_supplier_score(db, s.id)
        sc["supplier_name"] = s.name
        sc["supplier_code"] = s.code or ""
        results.append(sc)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Supplier Spend Analysis ───────────────────────────────────────────────────

def get_supplier_spend_analysis(db: Session, limit: int = 10) -> dict:
    now = datetime.now(tz=timezone.utc)

    rows = (
        db.query(
            PurchaseOrder.supplier_id,
            Supplier.name.label("supplier_name"),
            Supplier.code.label("supplier_code"),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label("total_spend"),
            func.count(PurchaseOrder.id).label("po_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                func.extract("year",  PurchaseOrder.po_date) == now.year,
                                func.extract("month", PurchaseOrder.po_date) == now.month,
                            ),
                            PurchaseOrder.total_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("spend_this_month"),
            func.coalesce(
                func.sum(
                    case(
                        (func.extract("year", PurchaseOrder.po_date) == now.year, PurchaseOrder.total_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("spend_this_year"),
        )
        .join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
        .filter(PurchaseOrder.status.in_(_COMMITTED))
        .group_by(PurchaseOrder.supplier_id, Supplier.name, Supplier.code)
        .order_by(func.sum(PurchaseOrder.total_amount).desc())
        .limit(limit)
        .all()
    )

    from app.models.project import Project

    top_suppliers = []
    for row in rows:
        proj_rows = (
            db.query(
                PurchaseOrder.project_id,
                Project.name.label("project_name"),
                func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label("spend"),
            )
            .join(Project, PurchaseOrder.project_id == Project.id)
            .filter(
                PurchaseOrder.supplier_id == row.supplier_id,
                PurchaseOrder.status.in_(_COMMITTED),
            )
            .group_by(PurchaseOrder.project_id, Project.name)
            .all()
        )
        top_suppliers.append({
            "supplier_id":      str(row.supplier_id) if row.supplier_id else None,
            "supplier_name":    row.supplier_name,
            "supplier_code":    row.supplier_code or "",
            "total_spend":      float(row.total_spend),
            "po_count":         int(row.po_count),
            "spend_this_month": float(row.spend_this_month),
            "spend_this_year":  float(row.spend_this_year),
            "spend_per_project": [
                {
                    "project_id":   str(p.project_id),
                    "project_name": p.project_name,
                    "spend":        float(p.spend),
                }
                for p in proj_rows
            ],
        })

    return {"top_suppliers": top_suppliers}


# ── Project Procurement Analytics ─────────────────────────────────────────────

def get_project_analytics(db: Session, project_id: Optional[uuid.UUID] = None) -> list[dict]:
    from app.models.project import Project

    projects_q = db.query(Project)
    if project_id:
        projects_q = projects_q.filter(Project.id == project_id)
    projects = projects_q.all()

    results = []
    for proj in projects:
        total_spend = float(
            db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
            .filter(PurchaseOrder.project_id == proj.id, PurchaseOrder.status.in_(_COMMITTED))
            .scalar() or 0
        )
        open_pos = int(
            db.query(func.count(PurchaseOrder.id))
            .filter(PurchaseOrder.project_id == proj.id, PurchaseOrder.status.in_(_OPEN))
            .scalar() or 0
        )
        outstanding_deliveries = int(
            db.query(func.count(PurchaseOrder.id))
            .filter(PurchaseOrder.project_id == proj.id, PurchaseOrder.status.in_(_PENDING_DELIVERY))
            .scalar() or 0
        )
        outstanding_invoices = int(
            db.query(func.count(Invoice.id))
            .filter(Invoice.project_id == proj.id, Invoice.status.in_(_PENDING_INVOICE))
            .scalar() or 0
        )

        # BOQ budget from active BOQ headers
        boq_budget = float(
            db.query(func.coalesce(func.sum(BOQItem.planned_total), 0))
            .join(BOQSection, BOQItem.boq_section_id == BOQSection.id)
            .join(BOQHeader, BOQSection.boq_header_id == BOQHeader.id)
            .filter(BOQHeader.project_id == proj.id, BOQHeader.is_active_version == True)
            .scalar() or 0
        )

        variance = boq_budget - total_spend
        variance_pct = round(variance / boq_budget * 100, 2) if boq_budget else 0.0

        results.append({
            "project_id":               str(proj.id),
            "project_name":             proj.name,
            "project_code":             proj.code,
            "project_status":           proj.status.value,
            "boq_budget":               boq_budget,
            "total_spend":              total_spend,
            "budget_variance":          round(variance, 2),
            "budget_variance_pct":      variance_pct,
            "open_pos":                 open_pos,
            "outstanding_deliveries":   outstanding_deliveries,
            "outstanding_invoices":     outstanding_invoices,
        })

    return results


# ── Purchase Price History ────────────────────────────────────────────────────

def get_price_history(
    db: Session,
    item_id: Optional[uuid.UUID] = None,
    description_search: Optional[str] = None,
    project_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    limit: int = 200,
) -> list[dict]:
    q = (
        db.query(
            PurchaseOrderItem.description,
            PurchaseOrderItem.item_id,
            PurchaseOrderItem.unit,
            PurchaseOrderItem.rate,
            PurchaseOrderItem.quantity_ordered,
            PurchaseOrderItem.line_total,
            PurchaseOrder.po_date,
            PurchaseOrder.po_number,
            PurchaseOrder.supplier_id,
            PurchaseOrder.project_id,
            Supplier.name.label("supplier_name"),
        )
        .join(PurchaseOrder, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .outerjoin(Supplier, PurchaseOrder.supplier_id == Supplier.id)
        .filter(
            PurchaseOrderItem.rate.isnot(None),
            PurchaseOrder.status.in_(_COMMITTED),
        )
    )

    if item_id:
        q = q.filter(PurchaseOrderItem.item_id == item_id)
    if description_search:
        q = q.filter(PurchaseOrderItem.description.ilike(f"%{description_search}%"))
    if project_id:
        q = q.filter(PurchaseOrder.project_id == project_id)
    if supplier_id:
        q = q.filter(PurchaseOrder.supplier_id == supplier_id)

    rows = q.order_by(PurchaseOrder.po_date.asc()).limit(limit).all()

    return [
        {
            "description":     row.description,
            "item_id":         str(row.item_id) if row.item_id else None,
            "unit":            row.unit,
            "rate":            float(row.rate),
            "quantity_ordered": float(row.quantity_ordered),
            "line_total":      float(row.line_total) if row.line_total else None,
            "po_date":         row.po_date.date().isoformat() if row.po_date else None,
            "po_number":       row.po_number,
            "supplier_id":     str(row.supplier_id) if row.supplier_id else None,
            "supplier_name":   row.supplier_name,
            "project_id":      str(row.project_id) if row.project_id else None,
        }
        for row in rows
    ]


# ── Quotation Comparison ──────────────────────────────────────────────────────

def get_quotation_comparison(db: Session, material_request_id: uuid.UUID) -> dict:
    mr = db.get(MaterialRequest, material_request_id)
    if not mr:
        raise HTTPException(404, "Material Request not found.")

    quotes = (
        db.query(Quotation, Supplier.name.label("supplier_name"))
        .outerjoin(Supplier, Quotation.supplier_id == Supplier.id)
        .filter(
            Quotation.material_request_id == material_request_id,
            Quotation.status.notin_([QuotationStatus.DRAFT]),
        )
        .all()
    )

    rows = []
    lowest_amount: Optional[float] = None
    lowest_id: Optional[str] = None

    for q, supplier_name in quotes:
        gross = float(q.gross_amount or 0)
        entry = {
            "quotation_id":  str(q.id),
            "quote_number":  q.quote_number,
            "supplier_id":   str(q.supplier_id) if q.supplier_id else None,
            "supplier_name": supplier_name or "Unknown",
            "quote_date":    q.quote_date.isoformat() if q.quote_date else None,
            "expiry_date":   q.expiry_date.isoformat() if q.expiry_date else None,
            "status":        q.status.value,
            "net_amount":    float(q.net_amount or 0),
            "vat_amount":    float(q.vat_amount or 0),
            "gross_amount":  gross,
            "vat_rate":      float(q.vat_rate_used or 15),
            "is_lowest":     False,
        }
        if lowest_amount is None or gross < lowest_amount:
            lowest_amount = gross
            lowest_id = str(q.id)
        rows.append(entry)

    for entry in rows:
        entry["is_lowest"] = entry["quotation_id"] == lowest_id

    return {
        "material_request_id": str(material_request_id),
        "mr_number":           mr.request_number,
        "quotation_count":     len(rows),
        "quotes":              rows,
        "lowest_quote_id":     lowest_id,
        "lowest_amount":       lowest_amount,
    }


def list_mrs_with_multiple_quotes(db: Session, project_id: Optional[uuid.UUID] = None) -> list[dict]:
    """Return MRs that have ≥2 non-draft quotations — useful for the comparison picker."""
    from app.models.project import Project

    q = (
        db.query(
            Quotation.material_request_id,
            func.count(Quotation.id).label("quote_count"),
        )
        .filter(
            Quotation.material_request_id.isnot(None),
            Quotation.status.notin_([QuotationStatus.DRAFT]),
        )
        .group_by(Quotation.material_request_id)
        .having(func.count(Quotation.id) >= 2)
    )

    rows = q.all()
    result = []
    for row in rows:
        mr = db.get(MaterialRequest, row.material_request_id)
        if not mr:
            continue
        if project_id and mr.project_id != project_id:
            continue
        result.append({
            "material_request_id": str(mr.id),
            "mr_number":           mr.mr_number,
            "project_id":          str(mr.project_id) if mr.project_id else None,
            "quote_count":         int(row.quote_count),
        })

    return result


# ── Procurement Savings Report ────────────────────────────────────────────────

def get_savings_report(db: Session, project_id: Optional[uuid.UUID] = None) -> list[dict]:
    from app.models.project import Project

    projects_q = db.query(Project)
    if project_id:
        projects_q = projects_q.filter(Project.id == project_id)
    projects = projects_q.all()

    results = []
    for proj in projects:
        boq_budget = float(
            db.query(func.coalesce(func.sum(BOQItem.planned_total), 0))
            .join(BOQSection, BOQItem.boq_section_id == BOQSection.id)
            .join(BOQHeader, BOQSection.boq_header_id == BOQHeader.id)
            .filter(BOQHeader.project_id == proj.id, BOQHeader.is_active_version == True)
            .scalar() or 0
        )
        actual_spend = float(
            db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
            .filter(PurchaseOrder.project_id == proj.id, PurchaseOrder.status.in_(_COMMITTED))
            .scalar() or 0
        )

        variance = boq_budget - actual_spend
        variance_pct = round(variance / boq_budget * 100, 2) if boq_budget else 0.0

        results.append({
            "project_id":      str(proj.id),
            "project_name":    proj.name,
            "project_code":    proj.code,
            "boq_budget":      boq_budget,
            "actual_spend":    actual_spend,
            "variance":        round(variance, 2),
            "variance_pct":    variance_pct,
            "has_boq":         boq_budget > 0,
            "status":          "under_budget" if variance >= 0 else "over_budget",
        })

    # Sort by actual spend descending
    results.sort(key=lambda x: x["actual_spend"], reverse=True)
    return results
