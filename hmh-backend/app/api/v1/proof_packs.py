"""
Proof pack endpoints — accounting-facing document bundles.

GET  /proof-packs           — list invoices with match status (accounting overview)
GET  /proof-packs/{id}      — full proof pack for one invoice
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.dependencies import OFFICE_AND_ABOVE, DbSession
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/proof-packs", tags=["proof-packs"])


@router.get("/", dependencies=[OFFICE_AND_ABOVE])
def list_proof_packs(db: DbSession, limit: int = 50, offset: int = 0):
    """
    List all invoices with their match status — for the accounting overview table.
    """
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from sqlalchemy.orm import joinedload

    invoices = (
        db.query(Invoice)
        .order_by(Invoice.captured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    rows = []
    for inv in invoices:
        supplier = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
        po = db.get(PurchaseOrder, inv.purchase_order_id) if inv.purchase_order_id else None
        match = (
            db.query(InvoiceMatchingResult)
            .filter(InvoiceMatchingResult.invoice_id == inv.id)
            .first()
        )
        rows.append({
            "invoice_id":     str(inv.id),
            "invoice_number": inv.invoice_number,
            "invoice_date":   inv.invoice_date.isoformat() if inv.invoice_date else None,
            "total_amount":   float(inv.total_amount or 0),
            "status":         inv.status.value if inv.status else None,
            "supplier_name":  supplier.name if supplier else None,
            "po_number":      po.po_number if po else None,
            "match_status":   match.match_status.value if match else "UNLINKED",
            "is_matched":     (match.match_status.value == "MATCHED") if match else False,
        })

    return ApiSuccess(data={"total": len(rows), "items": rows})


@router.get("/{invoice_id}", dependencies=[OFFICE_AND_ABOVE])
def get_proof_pack(invoice_id: uuid.UUID, db: DbSession):
    """
    Full proof pack for one invoice — for accounting sign-off.
    """
    from app.services.procurement_matching_service import build_proof_pack

    pack = build_proof_pack(invoice_id, db)
    if not pack:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return ApiSuccess(data=pack)
