"""Service layer for ProcurementReconciliation — Phase 4."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import ReconciliationStatus
from app.models.procurement_reconciliation import ProcurementReconciliation
from app.schemas.procurement_reconciliation import (
    ProcurementReconciliationCreate,
    ProcurementReconciliationUpdate,
)

from app.core.config import settings as _settings
_VARIANCE_THRESHOLD = _settings.RECONCILIATION_VARIANCE_THRESHOLD  # configurable via RECONCILIATION_VARIANCE_THRESHOLD env var (default R 1.00)


# ── Variance computation ──────────────────────────────────────────────────────

def _field_row(name: str, a_label: str, a_val, b_label: str, b_val) -> dict:
    a = float(a_val or 0)
    b = float(b_val or 0)
    diff = round(b - a, 2)
    diff_pct = round(abs(diff) / a * 100, 4) if a else (0.0 if diff == 0 else 100.0)
    return {
        "name":        name,
        "a_label":     a_label,
        "a_value":     a,
        "b_label":     b_label,
        "b_value":     b,
        "diff":        diff,
        "diff_pct":    diff_pct,
        "has_variance": abs(diff) > _VARIANCE_THRESHOLD,
    }


def compute_variances(po, invoice, quotation=None, delivery=None) -> dict:
    comparisons = []

    # 1. Quotation vs PO
    if quotation:
        fields = [
            _field_row("Net Amount",   "Quotation", quotation.net_amount,   "PO", po.subtotal_amount),
            _field_row("VAT Amount",   "Quotation", quotation.vat_amount,   "PO", po.vat_amount),
            _field_row("Gross Amount", "Quotation", quotation.gross_amount, "PO", po.total_amount),
        ]
        comparisons.append({"label": "Quotation vs PO", "fields": fields})

    # 2. PO vs Invoice
    if invoice:
        fields = [
            _field_row("Net Amount",   "PO", po.subtotal_amount, "Invoice", invoice.subtotal_amount),
            _field_row("VAT Amount",   "PO", po.vat_amount,      "Invoice", invoice.vat_amount),
            _field_row("Gross Amount", "PO", po.total_amount,    "Invoice", invoice.total_amount),
        ]
        comparisons.append({"label": "PO vs Invoice", "fields": fields})

    # 3. Delivery item quantities vs PO items (summary level)
    if delivery:
        po_items = po.order_items if hasattr(po, "order_items") else []
        del_items = delivery.items if hasattr(delivery, "items") else []
        qty_ordered = sum(float(i.quantity_ordered or 0) for i in po_items)
        qty_received = sum(float(i.quantity_received or 0) for i in del_items)
        fields = [
            _field_row("Total Quantity", "PO Ordered", qty_ordered, "Delivery Received", qty_received),
        ]
        comparisons.append({"label": "PO vs Delivery", "fields": fields})

    total_variances = sum(
        1 for comp in comparisons for f in comp["fields"] if f["has_variance"]
    )
    has_variance = total_variances > 0

    return {
        "comparisons":      comparisons,
        "has_variance":     has_variance,
        "total_variances":  total_variances,
        "threshold_rands":  _VARIANCE_THRESHOLD,
    }


# ── Number generation ─────────────────────────────────────────────────────────

def _next_recon_number(db: Session) -> str:
    year = datetime.now(tz=timezone.utc).year
    prefix = f"REC-{year}-"
    count = (
        db.query(func.count(ProcurementReconciliation.id))
        .filter(ProcurementReconciliation.reconciliation_number.like(f"{prefix}%"))
        .scalar() or 0
    )
    return f"{prefix}{count + 1:04d}"


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_reconciliations(
    db: Session,
    status: Optional[ReconciliationStatus] = None,
    supplier_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ProcurementReconciliation]:
    from app.models.purchase_order import PurchaseOrder

    q = db.query(ProcurementReconciliation)
    if status:
        q = q.filter(ProcurementReconciliation.status == status)
    if supplier_id or project_id:
        q = q.join(
            PurchaseOrder,
            ProcurementReconciliation.purchase_order_id == PurchaseOrder.id,
            isouter=True,
        )
        if supplier_id:
            q = q.filter(PurchaseOrder.supplier_id == supplier_id)
        if project_id:
            q = q.filter(PurchaseOrder.project_id == project_id)
    return (
        q.order_by(ProcurementReconciliation.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def get_reconciliation(db: Session, recon_id: uuid.UUID) -> ProcurementReconciliation:
    r = db.get(ProcurementReconciliation, recon_id)
    if not r:
        raise HTTPException(404, "Reconciliation record not found.")
    return r


def create_reconciliation(
    db: Session,
    data: ProcurementReconciliationCreate,
    created_by: Optional[uuid.UUID] = None,
) -> ProcurementReconciliation:
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder
    from app.models.quotation import Quotation

    po = db.get(PurchaseOrder, data.purchase_order_id)
    if not po:
        raise HTTPException(404, "Purchase Order not found.")

    invoice  = db.get(Invoice,   data.invoice_id)  if data.invoice_id  else None
    delivery = db.get(Delivery,  data.delivery_id) if data.delivery_id else None
    quotation = db.get(Quotation, data.quotation_id) if data.quotation_id else None

    # Auto-resolve quotation from PO if not supplied
    if not quotation and po.quotation_id:
        quotation = db.get(Quotation, po.quotation_id)

    # Compute variances
    variance_data = compute_variances(po, invoice, quotation, delivery)

    # Determine status
    if invoice is None:
        status = ReconciliationStatus.PENDING
    elif variance_data["has_variance"]:
        status = ReconciliationStatus.VARIANCE_DETECTED
    else:
        status = ReconciliationStatus.MATCHED

    recon = ProcurementReconciliation(
        reconciliation_number=_next_recon_number(db),
        status=status,
        purchase_order_id=data.purchase_order_id,
        invoice_id=data.invoice_id,
        delivery_id=data.delivery_id,
        quotation_id=quotation.id if quotation else data.quotation_id,
        material_request_id=data.material_request_id or po.material_request_id,
        variance_data=variance_data,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(recon)
    db.commit()
    db.refresh(recon)
    return recon


def update_reconciliation(
    db: Session,
    recon_id: uuid.UUID,
    data: ProcurementReconciliationUpdate,
    reviewed_by: Optional[uuid.UUID] = None,
) -> ProcurementReconciliation:
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder
    from app.models.quotation import Quotation

    recon = get_reconciliation(db, recon_id)

    # If document links changed, recompute variances
    relink = data.invoice_id or data.delivery_id or data.quotation_id
    if relink:
        if data.invoice_id:
            recon.invoice_id = data.invoice_id
        if data.delivery_id:
            recon.delivery_id = data.delivery_id
        if data.quotation_id:
            recon.quotation_id = data.quotation_id

        po = db.get(PurchaseOrder, recon.purchase_order_id)
        invoice  = db.get(Invoice,   recon.invoice_id)  if recon.invoice_id  else None
        delivery = db.get(Delivery,  recon.delivery_id) if recon.delivery_id else None
        quotation = db.get(Quotation, recon.quotation_id) if recon.quotation_id else None

        recon.variance_data = compute_variances(po, invoice, quotation, delivery)

        # Auto-update status if not explicitly set
        if data.status is None:
            if invoice is None:
                recon.status = ReconciliationStatus.PENDING
            elif recon.variance_data["has_variance"]:
                recon.status = ReconciliationStatus.VARIANCE_DETECTED
            else:
                recon.status = ReconciliationStatus.MATCHED

    if data.status is not None:
        recon.status = data.status
        # Record reviewer when approving or rejecting
        if data.status in (ReconciliationStatus.APPROVED, ReconciliationStatus.REJECTED):
            recon.reviewed_by = reviewed_by
            recon.reviewed_at = datetime.now(tz=timezone.utc)

    if data.notes is not None:
        recon.notes = data.notes

    db.commit()
    db.refresh(recon)
    return recon


def delete_reconciliation(db: Session, recon_id: uuid.UUID) -> None:
    recon = get_reconciliation(db, recon_id)
    db.delete(recon)
    db.commit()


# ── Dashboard ─────────────────────────────────────────────────────────────────

def get_dashboard_stats(db: Session) -> dict:
    rows = (
        db.query(ProcurementReconciliation.status, func.count(ProcurementReconciliation.id))
        .group_by(ProcurementReconciliation.status)
        .all()
    )
    counts = {r.status: r[1] for r in rows}

    pending           = counts.get(ReconciliationStatus.PENDING,           0)
    matched           = counts.get(ReconciliationStatus.MATCHED,           0)
    variance_detected = counts.get(ReconciliationStatus.VARIANCE_DETECTED, 0)
    approved          = counts.get(ReconciliationStatus.APPROVED,          0)
    rejected          = counts.get(ReconciliationStatus.REJECTED,          0)

    return {
        "pending":           pending,
        "matched":           matched,
        "variance_detected": variance_detected,
        "approved":          approved,
        "rejected":          rejected,
        "awaiting_review":   matched + variance_detected,
        "total":             pending + matched + variance_detected + approved + rejected,
    }


# ── Detail resolver ───────────────────────────────────────────────────────────

def build_detail(db: Session, recon: ProcurementReconciliation) -> dict:
    """Return a serialisable detail dict with resolved document summaries."""
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.models.purchase_order import PurchaseOrder
    from app.models.quotation import Quotation
    from app.models.supplier import Supplier
    from app.models.user import User

    base = {
        "id": str(recon.id),
        "reconciliation_number": recon.reconciliation_number,
        "status": recon.status.value,
        "purchase_order_id": str(recon.purchase_order_id) if recon.purchase_order_id else None,
        "invoice_id": str(recon.invoice_id) if recon.invoice_id else None,
        "delivery_id": str(recon.delivery_id) if recon.delivery_id else None,
        "quotation_id": str(recon.quotation_id) if recon.quotation_id else None,
        "material_request_id": str(recon.material_request_id) if recon.material_request_id else None,
        "variance_data": recon.variance_data,
        "notes": recon.notes,
        "reviewed_by": str(recon.reviewed_by) if recon.reviewed_by else None,
        "reviewed_at": recon.reviewed_at.isoformat() if recon.reviewed_at else None,
        "created_by": str(recon.created_by) if recon.created_by else None,
        "created_at": recon.created_at.isoformat(),
        "updated_at": recon.updated_at.isoformat(),
    }

    # Reviewer name
    if recon.reviewed_by:
        u = db.get(User, recon.reviewed_by)
        base["reviewed_by_name"] = u.full_name if u else None
    else:
        base["reviewed_by_name"] = None

    # PO summary
    if recon.purchase_order_id:
        po = db.get(PurchaseOrder, recon.purchase_order_id)
        if po:
            supplier_name = None
            if po.supplier_id:
                s = db.get(Supplier, po.supplier_id)
                supplier_name = s.name if s else None
            base["po"] = {
                "po_id": str(po.id),
                "po_number": po.po_number,
                "po_date": po.po_date.date().isoformat() if po.po_date else None,
                "status": po.status.value,
                "subtotal_amount": float(po.subtotal_amount or 0),
                "vat_amount": float(po.vat_amount or 0),
                "total_amount": float(po.total_amount or 0),
                "supplier_id": str(po.supplier_id),
                "supplier_name": supplier_name,
                "project_id": str(po.project_id),
            }
        else:
            base["po"] = None
    else:
        base["po"] = None

    # Invoice summary
    if recon.invoice_id:
        inv = db.get(Invoice, recon.invoice_id)
        if inv:
            base["invoice"] = {
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "subtotal_amount": float(inv.subtotal_amount or 0),
                "vat_amount": float(inv.vat_amount or 0),
                "total_amount": float(inv.total_amount or 0),
                "status": inv.status.value,
                "vat_rate_used": float(inv.vat_rate_used or 15),
            }
        else:
            base["invoice"] = None
    else:
        base["invoice"] = None

    # Delivery summary
    if recon.delivery_id:
        d = db.get(Delivery, recon.delivery_id)
        if d:
            base["delivery"] = {
                "delivery_id": str(d.id),
                "delivery_number": d.delivery_number or str(d.id)[:8],
                "delivery_date": d.delivery_date.date().isoformat() if d.delivery_date else None,
                "status": d.delivery_status.value,
                "items_count": len(d.items),
            }
        else:
            base["delivery"] = None
    else:
        base["delivery"] = None

    # Quotation summary
    if recon.quotation_id:
        q = db.get(Quotation, recon.quotation_id)
        if q:
            base["quotation"] = {
                "quotation_id": str(q.id),
                "quote_number": q.quote_number,
                "quote_date": q.quote_date.isoformat() if q.quote_date else None,
                "status": q.status.value,
                "net_amount": float(q.net_amount or 0),
                "vat_amount": float(q.vat_amount or 0),
                "gross_amount": float(q.gross_amount or 0),
                "vat_rate_used": float(q.vat_rate_used or 15),
            }
        else:
            base["quotation"] = None
    else:
        base["quotation"] = None

    # MR summary
    if recon.material_request_id:
        mr = db.get(MaterialRequest, recon.material_request_id)
        if mr:
            base["material_request"] = {
                "mr_id": str(mr.id),
                "mr_number": mr.mr_number,
                "status": mr.status.value,
            }
        else:
            base["material_request"] = None
    else:
        base["material_request"] = None

    return base
