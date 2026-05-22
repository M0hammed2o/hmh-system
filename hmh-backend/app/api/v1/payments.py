"""Payment routes."""

import csv
import io
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.payment import PaymentCreate, PaymentRead, PaymentUpdate
from app.services import payment_service
from app.schemas.invoice import InvoiceRead

project_payment_router = APIRouter(
    prefix="/projects/{project_id}/payments",
    tags=["payments"],
)
payment_router = APIRouter(prefix="/payments", tags=["payments"])


@project_payment_router.get(
    "/",
    response_model=ApiSuccess[list[PaymentRead]],
    dependencies=[ALL_ROLES],
)
def list_payments(project_id: uuid.UUID, db: DbSession):
    payments = payment_service.list_payments(db, project_id)
    return ApiSuccess(data=[PaymentRead.model_validate(p) for p in payments])


@project_payment_router.post(
    "/",
    response_model=ApiSuccess[PaymentRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_payment(
    project_id: uuid.UUID,
    body: PaymentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    payment = payment_service.create_payment(db, project_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment captured.")


@payment_router.get(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[ALL_ROLES],
)
def get_payment(payment_id: uuid.UUID, db: DbSession):
    payment = payment_service.get_payment(db, payment_id)
    return ApiSuccess(data=PaymentRead.model_validate(payment))


@payment_router.patch(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_payment(
    payment_id: uuid.UUID, body: PaymentUpdate, db: DbSession, current_user: CurrentUser
):
    payment = payment_service.update_payment(db, payment_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment updated.")


@payment_router.get(
    "/{payment_id}/activity",
    response_model=ApiSuccess[list[dict]],
    dependencies=[OFFICE_AND_ABOVE],
)
def get_payment_activity(payment_id: uuid.UUID, db: DbSession):
    """Human-readable activity timeline for a payment record."""
    from app.models.audit import AuditEvent
    from app.models.attachment import Attachment
    from app.models.enums import AttachmentEntity
    from app.core.storage import public_url as _pub

    p = db.get(__import__("app.models.payment", fromlist=["Payment"]).Payment, payment_id)
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, "Payment not found.")

    audit_rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_id == payment_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(30)
        .all()
    )
    attachments = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == AttachmentEntity.PAYMENT,
            Attachment.entity_id   == payment_id,
        )
        .order_by(Attachment.uploaded_at.desc())
        .all()
    )

    activity = []
    from app.models.user import User
    for a in audit_rows:
        actor = None
        if a.actor_id:
            u = db.get(User, a.actor_id)
            actor = u.full_name if u else None
        after = a.after_value or {}
        amt = after.get("amount_paid")
        if amt:
            desc = f"{actor or 'Office'} captured payment of {float(amt):,.2f}"
        else:
            desc = a.action.replace("_", " ").title()
        activity.append({
            "type": "status", "timestamp": a.created_at.isoformat(),
            "actor": actor or "System", "description": desc,
        })
    for att in attachments:
        activity.append({
            "type": "document", "timestamp": att.uploaded_at.isoformat(),
            "actor": None, "description": f"Proof uploaded: {att.file_name}",
            "url": _pub(att.stored_path), "is_image": att.mime_type.startswith("image/") if att.mime_type else False,
        })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return ApiSuccess(data=activity)


@project_payment_router.get(
    "/outstanding-summary",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def outstanding_summary(project_id: uuid.UUID, db: DbSession):
    """
    Return outstanding payment summary for a project:
    - Unpaid/overdue supplier invoices
    - Total outstanding amount
    - Approved but unpaid job cards (labour)
    """
    from datetime import date
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    from app.models.supplier import Supplier

    # Invoices that are not PAID or CANCELLED
    unpaid_statuses = [
        RecordStatus.DRAFT, RecordStatus.SUBMITTED, RecordStatus.RECEIVED,
        RecordStatus.APPROVED, RecordStatus.MATCHED,
    ]
    unpaid_invoices = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id, Invoice.status.in_(unpaid_statuses))
        .order_by(Invoice.due_date.asc())
        .all()
    )

    today = date.today()
    invoice_rows = []
    total_outstanding = 0.0
    overdue_amount = 0.0

    for inv in unpaid_invoices:
        supplier = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
        amt = float(inv.total_amount or 0)
        is_overdue = inv.due_date is not None and inv.due_date < today
        total_outstanding += amt
        if is_overdue:
            overdue_amount += amt
        invoice_rows.append({
            "invoice_id":      str(inv.id),
            "invoice_number":  inv.invoice_number,
            "supplier_name":   supplier.name if supplier else None,
            "total_amount":    amt,
            "due_date":        inv.due_date.isoformat() if inv.due_date else None,
            "status":          inv.status.value,
            "is_overdue":      is_overdue,
        })

    # Pending payments (LABOUR + SUPPLIER not yet PAID)
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus
    pending_payments = (
        db.query(Payment)
        .filter(
            Payment.project_id == project_id,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.APPROVED]),
        )
        .all()
    )
    pending_amount = sum(float(p.amount_paid or 0) for p in pending_payments)

    return ApiSuccess(data={
        "total_outstanding_invoices": total_outstanding,
        "overdue_amount":             overdue_amount,
        "pending_payments_amount":    pending_amount,
        "outstanding_invoices":       invoice_rows,
        "overdue_count":              sum(1 for i in invoice_rows if i["is_overdue"]),
    })


@project_payment_router.get(
    "/report",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def payment_report(
    project_id: uuid.UUID,
    db: DbSession,
    from_date:   Optional[date] = Query(None),
    to_date:     Optional[date] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
):
    """
    Monthly payment report: totals by supplier and by month.
    Used by the PaymentReportsPage.
    """
    from sqlalchemy import extract, func, text
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus
    from app.models.supplier import Supplier

    q = (
        db.query(Payment)
        .filter(
            Payment.project_id == project_id,
            Payment.status.notin_(["CANCELLED", "FAILED"]),
        )
    )
    if from_date:
        q = q.filter(Payment.payment_date >= from_date)
    if to_date:
        q = q.filter(Payment.payment_date <= to_date)
    if supplier_id:
        q = q.filter(Payment.supplier_id == supplier_id)

    payments = q.order_by(Payment.payment_date.asc().nullslast()).all()

    total_paid = sum(float(p.amount_paid) for p in payments)

    # Group by supplier
    by_supplier: dict = {}
    for p in payments:
        sid = str(p.supplier_id) if p.supplier_id else "unknown"
        by_supplier.setdefault(sid, {"supplier_id": sid, "supplier_name": None, "total": 0.0, "count": 0})
        by_supplier[sid]["total"] += float(p.amount_paid)
        by_supplier[sid]["count"] += 1

    # Resolve supplier names
    sup_ids = {uuid.UUID(k) for k in by_supplier if k != "unknown"}
    if sup_ids:
        for s in db.query(Supplier).filter(Supplier.id.in_(sup_ids)).all():
            if str(s.id) in by_supplier:
                by_supplier[str(s.id)]["supplier_name"] = s.name

    # Group by month (YYYY-MM)
    by_month: dict = {}
    for p in payments:
        key = p.payment_date.strftime("%Y-%m") if p.payment_date else "unknown"
        by_month.setdefault(key, {"month": key, "total": 0.0, "count": 0})
        by_month[key]["total"] += float(p.amount_paid)
        by_month[key]["count"] += 1

    return ApiSuccess(data={
        "project_id":    str(project_id),
        "total_paid":    total_paid,
        "payment_count": len(payments),
        "by_supplier":   sorted(by_supplier.values(), key=lambda x: -x["total"]),
        "by_month":      sorted(by_month.values(), key=lambda x: x["month"]),
    })


@project_payment_router.get(
    "/export",
    dependencies=[OFFICE_AND_ABOVE],
    response_class=StreamingResponse,
)
def export_payments_csv(
    project_id: uuid.UUID,
    db: DbSession,
    from_date:     Optional[date] = Query(None),
    to_date:       Optional[date] = Query(None),
    payment_type:  Optional[str]  = Query(None),
):
    """
    Download a CSV of all payments for the project, with optional date and type filters.
    Used by finance to generate monthly payment reports.
    """
    from app.models.payment import Payment
    from app.models.supplier import Supplier
    from datetime import datetime, timezone

    q = db.query(Payment).filter(Payment.project_id == project_id)

    if from_date:
        q = q.filter(Payment.payment_date >= from_date)
    if to_date:
        q = q.filter(Payment.payment_date <= to_date)
    if payment_type:
        q = q.filter(Payment.payment_type == payment_type.upper())

    payments = q.order_by(Payment.payment_date.desc(), Payment.created_at.desc()).all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date", "Reference", "Payment Type", "Supplier", "Amount (R)",
        "Status", "Notes", "Captured By",
    ])

    total = 0.0
    for p in payments:
        supplier_name = ""
        if p.supplier_id:
            s = db.get(Supplier, p.supplier_id)
            supplier_name = s.name if s else ""

        amount = float(p.amount_paid or 0)
        total += amount

        writer.writerow([
            p.payment_date.isoformat() if p.payment_date else "",
            p.payment_reference or "",
            p.payment_type.value if hasattr(p.payment_type, "value") else str(p.payment_type),
            supplier_name,
            f"{amount:.2f}",
            p.status.value if hasattr(p.status, "value") else str(p.status),
            (p.notes or "").replace("\n", " "),
            str(p.captured_by) if p.captured_by else "",
        ])

    # Totals row
    writer.writerow([])
    writer.writerow(["", "", "", "TOTAL", f"{total:.2f}", "", "", ""])

    output.seek(0)
    filename = f"payments_{project_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
