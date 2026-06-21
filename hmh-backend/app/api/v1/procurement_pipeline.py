"""
Procurement Pipeline API — Phase 4A.

Exposes the full 7-step procurement lifecycle for a Material Request so the
Procurement page can show a single, linear pipeline view instead of two
disconnected tabs.

Endpoints
---------
GET  /procurement/mrs/{mr_id}/pipeline
    Full pipeline state: MR details, 7 annotated steps, quotes, PO, invoice,
    delivery, and a missing-email warning when the supplier has no email.

POST /procurement/mrs/{mr_id}/quotes/{quote_id}/approve
    Approve a quote → auto-create PO → send PO email to supplier.
    Returns the new PO.

POST /procurement/mrs/{mr_id}/quotes/{quote_id}/reject
    Reject a quote with a reason → send rejection email → mark quote REJECTED.
    Optionally pass try_another_supplier_id to switch the preferred supplier on
    the MR so the next email goes to the new supplier.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/procurement", tags=["procurement-pipeline"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuoteApproveBody(BaseModel):
    notes: Optional[str] = None


class QuoteRejectBody(BaseModel):
    reason: str
    try_another_supplier_id: Optional[uuid.UUID] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quote_dict(q) -> dict:
    return {
        "id":               str(q.id),
        "supplier_id":      str(q.supplier_id),
        "description":      q.description,
        "quoted_quantity":  float(q.quoted_quantity),
        "unit":             q.unit,
        "unit_price":       float(q.unit_price),
        "total_price":      float(q.total_price or 0),
        "boq_unit_price":   float(q.boq_unit_price) if q.boq_unit_price is not None else None,
        "boq_variance_pct": _boq_variance(q),
        "source":           q.source,
        "status":           q.status,
        "notes":            q.notes,
        "rejection_reason": q.rejection_reason,
        "rejected_at":      q.rejected_at.isoformat() if q.rejected_at else None,
        "approved_at":      q.approved_at.isoformat() if q.approved_at else None,
        "is_selected":      q.is_selected,
        "created_at":       q.created_at.isoformat() if q.created_at else None,
    }


def _boq_variance(q) -> Optional[float]:
    """Return % over/under BOQ: positive = over budget, negative = under."""
    if q.boq_unit_price and q.boq_unit_price > 0:
        return round((float(q.unit_price) - float(q.boq_unit_price)) / float(q.boq_unit_price) * 100, 1)
    return None


def _step(step: int, key: str, label: str, status: str, **extra) -> dict:
    return {"step": step, "key": key, "label": label, "status": status, **extra}


# ── GET pipeline ──────────────────────────────────────────────────────────────

@router.get("/mrs/{mr_id}/pipeline", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def get_pipeline(mr_id: uuid.UUID, db: DbSession):
    """
    Return the full 7-step pipeline state for a Material Request.

    Step statuses:
      COMPLETE  — this step is done
      CURRENT   — this is the active step requiring action
      WAITING   — not yet reached
      BLOCKED   — reached but cannot proceed (e.g. no supplier email)
    """
    from sqlalchemy.orm import joinedload
    from app.models.material_request import MaterialRequest
    from app.models.mr_quote import MRQuote
    from app.models.mr_email_log import MREmailLog
    from app.models.purchase_order import PurchaseOrder
    from app.models.supplier import Supplier

    mr = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.id == mr_id)
        .first()
    )
    if not mr:
        raise HTTPException(404, "Material request not found.")

    # Resolve supplier info
    supplier: Optional[Supplier] = None
    if mr.preferred_supplier_id:
        supplier = db.get(Supplier, mr.preferred_supplier_id)
    supplier_has_email = bool(supplier and supplier.email)
    supplier_name      = supplier.name if supplier else None
    supplier_email     = supplier.email if supplier else None

    # Latest email log for this MR
    email_log = (
        db.query(MREmailLog)
        .filter(MREmailLog.material_request_id == mr_id)
        .order_by(MREmailLog.created_at.desc())
        .first()
    )
    email_sent = email_log and email_log.status in ("SENT", "MOCK_SENT")

    # Quotes
    quotes_raw = (
        db.query(MRQuote)
        .filter(MRQuote.material_request_id == mr_id)
        .order_by(MRQuote.created_at)
        .all()
    )
    quotes = [_quote_dict(q) for q in quotes_raw]
    pending_quotes  = [q for q in quotes if q["status"] == "PENDING"]
    approved_quotes = [q for q in quotes if q["status"] == "APPROVED"]

    # PO linked to this MR
    po = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.material_request_id == mr_id)
        .order_by(PurchaseOrder.created_at.desc())
        .first()
    )
    po_dict = None
    if po:
        po_sent = bool(po.email_logs and any(
            l.status in ("SENT", "MOCK_SENT") for l in po.email_logs
        ))
        po_dict = {
            "id":        str(po.id),
            "po_number": po.po_number,
            "status":    po.status.value if po.status else po.status,
            "total":     float(po.total_amount or 0),
            "sent":      po_sent,
        }

    # Invoice linked to PO
    invoice_dict = None
    if po:
        from app.models.invoice import Invoice
        inv = (
            db.query(Invoice)
            .filter(Invoice.purchase_order_id == po.id)
            .order_by(Invoice.created_at.desc())
            .first()
        )
        if inv:
            invoice_dict = {
                "id":             str(inv.id),
                "invoice_number": inv.invoice_number,
                "total_amount":   float(inv.total_amount or 0),
                "status":         inv.status.value if hasattr(inv.status, "value") else inv.status,
                "matches_po":     abs(float(inv.total_amount or 0) - float(po.total_amount or 0)) < 1,
            }

    # Delivery linked to PO
    delivery_dict = None
    if po:
        from app.models.delivery import Delivery
        delivery = (
            db.query(Delivery)
            .filter(Delivery.purchase_order_id == po.id)
            .order_by(Delivery.created_at.desc())
            .first()
        )
        if delivery:
            delivery_dict = {
                "id":                  str(delivery.id),
                "delivery_note_number": delivery.delivery_number,
                "status":              delivery.delivery_status.value if hasattr(delivery.delivery_status, "value") else str(delivery.delivery_status),
                "received_at":         delivery.created_at.isoformat() if delivery.created_at else None,
            }

    # ── Build step annotations ────────────────────────────────────────────────

    mr_status = mr.status.value if hasattr(mr.status, "value") else str(mr.status)

    _terminal = {"CONVERTED_TO_PO", "RECEIVED", "CLOSED", "CANCELLED"}
    is_submitted = mr_status in {"SUBMITTED", "PENDING_APPROVAL", "APPROVED"} | _terminal
    is_approved  = mr_status in {"APPROVED"} | _terminal
    is_converted = mr_status in _terminal

    def _s(done: bool, current: bool, blocked: bool = False) -> str:
        if done:    return "COMPLETE"
        if blocked: return "BLOCKED"
        if current: return "CURRENT"
        return "WAITING"

    steps = [
        _step(1, "MR_SUBMITTED", "Material Request",
              _s(is_submitted, not is_submitted),
              submitted_at=mr.created_at.isoformat() if mr.created_at else None,
              item_count=len(mr.items or [])),

        _step(2, "OFFICE_APPROVAL", "Office Approval",
              _s(is_approved, is_submitted and not is_approved),
              approved_at=mr.approved_at.isoformat() if mr.approved_at else None,
              over_boq=mr.over_boq),

        _step(3, "SUPPLIER_EMAIL", "Email to Supplier",
              _s(email_sent,
                 is_approved and not email_sent,
                 blocked=is_approved and not email_sent and not supplier_has_email),
              email_sent=email_sent,
              sent_to=email_log.sent_to_email if email_log else None,
              sent_at=email_log.sent_at.isoformat() if email_log and email_log.sent_at else None,
              email_status=email_log.status if email_log else None,
              supplier_name=supplier_name,
              supplier_email=supplier_email,
              missing_email=is_approved and not supplier_has_email),

        _step(4, "QUOTATION", "Supplier Quotation",
              _s(bool(approved_quotes),
                 email_sent and not approved_quotes,
                 blocked=False),
              quotes=quotes,
              pending_count=len(pending_quotes),
              approved_count=len(approved_quotes)),

        _step(5, "PURCHASE_ORDER", "Purchase Order",
              _s(bool(po), is_converted or bool(approved_quotes) and not po),
              po=po_dict),

        _step(6, "INVOICE", "Invoice Received",
              _s(bool(invoice_dict), bool(po) and not invoice_dict),
              invoice=invoice_dict),

        _step(7, "DELIVERY", "Delivery Confirmed",
              _s(bool(delivery_dict), bool(invoice_dict) and not delivery_dict),
              delivery=delivery_dict),
    ]

    # Current active step index (first non-COMPLETE step)
    current_step = next((s["step"] for s in steps if s["status"] != "COMPLETE"), 7)

    # Auto-close MR when all 7 steps are complete
    all_complete = all(s["status"] == "COMPLETE" for s in steps)
    if all_complete and mr_status not in ("CLOSED", "CANCELLED", "PAID", "MATCHED"):
        from app.models.enums import RecordStatus as _RS
        mr.status = _RS.CLOSED
        db.commit()
        mr_status = "CLOSED"
        logger.info("pipeline auto_close mr=%s — all 7 steps complete", mr_id)

    mr_items = [
        {
            "id":                     str(i.id),
            "description":            i.description,
            "requested_quantity":     float(i.requested_quantity or 0),
            "unit":                   i.unit,
            "over_boq_quantity":      float(i.over_boq_quantity) if i.over_boq_quantity else None,
            "preferred_supplier_id":  str(i.preferred_supplier_id) if i.preferred_supplier_id else None,
        }
        for i in (mr.items or [])
    ]

    return ApiSuccess(data={
        "mr_id":             str(mr.id),
        "mr_number":         mr.request_number,
        "mr_status":         mr_status,
        "pipeline_complete": all_complete,
        "priority":          mr.priority.value if hasattr(mr.priority, "value") else mr.priority,
        "project_id":        str(mr.project_id) if mr.project_id else None,
        "lot_id":            str(mr.lot_id) if mr.lot_id else None,
        "notes":             mr.notes,
        "over_boq":          mr.over_boq,
        "items":             mr_items,
        "current_step":      current_step,
        "steps":             steps,
        "supplier": {
            "id":        str(mr.preferred_supplier_id) if mr.preferred_supplier_id else None,
            "name":      supplier_name,
            "email":     supplier_email,
            "has_email": supplier_has_email,
        },
    })


# ── POST quote approve ────────────────────────────────────────────────────────

@router.post(
    "/mrs/{mr_id}/quotes/{quote_id}/approve",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def approve_quote(
    mr_id: uuid.UUID,
    quote_id: uuid.UUID,
    body: QuoteApproveBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Approve a supplier quote.

    1. Marks the quote as APPROVED (all other quotes for this MR stay PENDING).
    2. Converts the MR to a Purchase Order using the approved quote's price.
    3. Sends the PO email to the supplier.
    4. Returns the created PO.
    """
    from app.models.material_request import MaterialRequest
    from app.models.mr_quote import MRQuote
    from app.models.supplier import Supplier
    from app.services import mr_service
    from app.services.email_service import send_po_email

    mr = db.get(MaterialRequest, mr_id)
    if not mr:
        raise HTTPException(404, "Material request not found.")

    quote = db.get(MRQuote, quote_id)
    if not quote or quote.material_request_id != mr_id:
        raise HTTPException(404, "Quote not found for this MR.")
    if quote.status == "APPROVED":
        raise HTTPException(409, "This quote is already approved.")

    mr_status = mr.status.value if hasattr(mr.status, "value") else str(mr.status)
    if mr_status not in ("APPROVED", "CONVERTED_TO_PO"):
        raise HTTPException(422, f"MR must be APPROVED before a quote can be accepted. Current status: {mr_status}")

    now = datetime.now(timezone.utc)

    # Mark quote approved
    quote.status      = "APPROVED"
    quote.is_selected = True
    quote.approved_at = now

    # Build PO line items from this quote
    po_items = [{
        "description": quote.description,
        "quantity":    float(quote.quoted_quantity),
        "unit":        quote.unit or "",
        "rate":        float(quote.unit_price),
        "item_id":     str(quote.item_id) if quote.item_id else None,
    }]

    # Convert MR → PO using existing service
    try:
        result = mr_service.convert_to_po(
            db,
            mr_id=mr_id,
            supplier_id=quote.supplier_id,
            items_with_rates=po_items,
            actor_id=current_user.id,
        )
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    po = result if not isinstance(result, dict) else result.get("po")

    # Send PO email (best-effort)
    email_result: dict = {"status": "NOT_SENT", "sent_to": None}
    try:
        log = send_po_email(db, po, sent_by_id=current_user.id, mr_id=mr_id)
        email_result = {
            "status":  log.status if hasattr(log, "status") else str(log),
            "sent_to": log.sent_to_email if hasattr(log, "sent_to_email") else None,
        }
    except Exception:
        logger.exception("PO email failed after quote approval mr=%s", mr_id)

    db.commit()

    return ApiSuccess(
        data={
            "po_id":        str(po.id),
            "po_number":    po.po_number,
            "total_amount": float(po.total_amount or 0),
            "email":        email_result,
        },
        message=f"Quote approved. Purchase Order {po.po_number} created and emailed to supplier.",
    )


# ── POST quote reject ─────────────────────────────────────────────────────────

@router.post(
    "/mrs/{mr_id}/quotes/{quote_id}/reject",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def reject_quote(
    mr_id: uuid.UUID,
    quote_id: uuid.UUID,
    body: QuoteRejectBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Reject a supplier quote.

    1. Marks the quote as REJECTED with the given reason.
    2. Sends a rejection email to the supplier with the reason.
    3. If try_another_supplier_id is provided, updates the MR's preferred
       supplier so the next email goes to the new supplier.

    Returns {"quote_id", "email_status", "switched_supplier": bool}.
    """
    from app.models.material_request import MaterialRequest
    from app.models.mr_quote import MRQuote
    from app.models.supplier import Supplier
    from app.services.email_service import send_quote_rejection_email

    if not body.reason or not body.reason.strip():
        raise HTTPException(422, "A rejection reason is required.")

    mr = db.get(MaterialRequest, mr_id)
    if not mr:
        raise HTTPException(404, "Material request not found.")

    quote = db.get(MRQuote, quote_id)
    if not quote or quote.material_request_id != mr_id:
        raise HTTPException(404, "Quote not found for this MR.")
    if quote.status == "REJECTED":
        raise HTTPException(409, "This quote is already rejected.")

    now = datetime.now(timezone.utc)
    quote.status           = "REJECTED"
    quote.rejection_reason = body.reason.strip()
    quote.rejected_at      = now

    # Optionally switch to another supplier
    switched_supplier = False
    if body.try_another_supplier_id:
        new_supplier = db.get(Supplier, body.try_another_supplier_id)
        if not new_supplier:
            raise HTTPException(404, "Replacement supplier not found.")
        mr.preferred_supplier_id = body.try_another_supplier_id  # type: ignore[assignment]
        switched_supplier = True

    db.commit()

    # Send rejection email
    email_result = send_quote_rejection_email(
        db, mr, quote, body.reason.strip(), sent_by_id=current_user.id
    )

    return ApiSuccess(
        data={
            "quote_id":         str(quote.id),
            "status":           "REJECTED",
            "email_status":     email_result["status"],
            "sent_to":          email_result["sent_to"],
            "switched_supplier": switched_supplier,
        },
        message=(
            "Quote rejected and supplier notified."
            + (" Switched to new supplier." if switched_supplier else "")
        ),
    )


# ── DELETE quote ──────────────────────────────────────────────────────────────

@router.delete(
    "/mrs/{mr_id}/quotes/{quote_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_quote(
    mr_id: uuid.UUID,
    quote_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Delete a PENDING quote.

    Only PENDING quotes may be deleted — approved quotes are part of the
    committed procurement record and cannot be removed.
    This is primarily used to clear incorrectly auto-extracted email quotes
    so the email can be re-processed and produce correct records.
    """
    from app.models.mr_quote import MRQuote

    quote = db.get(MRQuote, quote_id)
    if not quote or quote.material_request_id != mr_id:
        raise HTTPException(404, "Quote not found for this MR.")
    if quote.status != "PENDING":
        raise HTTPException(409, f"Only PENDING quotes can be deleted (this quote is {quote.status}).")

    db.delete(quote)
    db.commit()
    return ApiSuccess(data={"quote_id": str(quote_id), "deleted": True}, message="Quote deleted.")
