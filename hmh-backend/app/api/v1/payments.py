"""Payment routes."""

import csv
import io
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.resource_access import get_and_check_project_resource, secure_project_lookup
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, check_project_access
from app.models.payment import Payment
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
def list_payments(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
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
    check_project_access(db, current_user, project_id)
    payment = payment_service.create_payment(db, project_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment captured.")


@payment_router.get(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[ALL_ROLES],
)
def get_payment(payment_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    payment = secure_project_lookup(payment_service.get_payment(db, payment_id), db, current_user)
    return ApiSuccess(data=PaymentRead.model_validate(payment))


@payment_router.patch(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_payment(
    payment_id: uuid.UUID, body: PaymentUpdate, db: DbSession, current_user: CurrentUser
):
    get_and_check_project_resource(db, current_user, Payment, payment_id, "Payment not found.")
    payment = payment_service.update_payment(db, payment_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment updated.")


@payment_router.get(
    "/{payment_id}/activity",
    response_model=ApiSuccess[list[dict]],
    dependencies=[OFFICE_AND_ABOVE],
)
def get_payment_activity(payment_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Human-readable activity timeline for a payment record."""
    from app.models.audit import AuditEvent
    from app.models.attachment import Attachment
    from app.models.enums import AttachmentEntity
    from app.core.storage import public_url as _pub

    get_and_check_project_resource(db, current_user, Payment, payment_id, "Payment not found.")

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
def outstanding_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Return outstanding payment summary for a project:
    - Unpaid/overdue supplier invoices
    - Total outstanding amount
    - Approved but unpaid job cards (labour)
    """
    check_project_access(db, current_user, project_id)
    from datetime import date
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    from app.models.supplier import Supplier

    # All invoices with an outstanding balance (not PAID / CANCELLED / REJECTED)
    unpaid_statuses = [
        RecordStatus.DRAFT, RecordStatus.SUBMITTED, RecordStatus.RECEIVED,
        RecordStatus.APPROVED, RecordStatus.MATCHED,
        RecordStatus.INVOICED, RecordStatus.PARTIALLY_PAID,  # Phase 3L fix
    ]
    unpaid_invoices = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id, Invoice.status.in_(unpaid_statuses))
        .order_by(Invoice.due_date.asc().nullslast())
        .all()
    )

    if not unpaid_invoices:
        return ApiSuccess(data={
            "total_outstanding_invoices": 0.0,
            "overdue_amount":             0.0,
            "pending_payments_amount":    0.0,
            "outstanding_invoices":       [],
            "overdue_count":              0,
        })

    # Bulk: total paid per invoice (so we can calculate real outstanding balance)
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus
    from sqlalchemy import func as _f

    invoice_ids = [inv.id for inv in unpaid_invoices]
    paid_rows = (
        db.query(Payment.invoice_id, _f.coalesce(_f.sum(Payment.amount_paid), 0).label("total"))
        .filter(
            Payment.invoice_id.in_(invoice_ids),
            Payment.status.notin_(["CANCELLED", "FAILED"]),
        )
        .group_by(Payment.invoice_id)
        .all()
    )
    paid_by_invoice = {str(r.invoice_id): float(r.total) for r in paid_rows}

    # Bulk: supplier names
    supplier_ids = {inv.supplier_id for inv in unpaid_invoices if inv.supplier_id}
    supplier_names = {}
    if supplier_ids:
        for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all():
            supplier_names[str(s.id)] = s.name

    today = date.today()
    invoice_rows = []
    total_outstanding = 0.0
    overdue_amount = 0.0

    for inv in unpaid_invoices:
        total_amt  = float(inv.total_amount or 0)
        total_paid = paid_by_invoice.get(str(inv.id), 0.0)
        balance    = max(0.0, total_amt - total_paid)

        # Skip invoices where balance is actually zero (edge: status not updated yet)
        if balance <= 0 and total_paid >= total_amt:
            continue

        is_overdue = inv.due_date is not None and inv.due_date < today
        total_outstanding += balance
        if is_overdue:
            overdue_amount += balance

        invoice_rows.append({
            "invoice_id":         str(inv.id),
            "invoice_number":     inv.invoice_number,
            "supplier_name":      supplier_names.get(str(inv.supplier_id)) if inv.supplier_id else None,
            "total_amount":       total_amt,
            "total_paid":         round(total_paid, 2),
            "outstanding_balance": round(balance, 2),
            "due_date":           inv.due_date.isoformat() if inv.due_date else None,
            "status":             inv.status.value,
            "is_overdue":         is_overdue,
        })

    # Pending payments (not yet PAID)
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
        "total_outstanding_invoices": round(total_outstanding, 2),
        "overdue_amount":             round(overdue_amount, 2),
        "pending_payments_amount":    round(pending_amount, 2),
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
    current_user: CurrentUser,
    from_date:   Optional[date] = Query(None),
    to_date:     Optional[date] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
):
    """
    Monthly payment report: totals by supplier and by month.
    Used by the PaymentReportsPage.
    """
    check_project_access(db, current_user, project_id)
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
    "/aging",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def payment_aging(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Invoice aging report: unpaid invoices grouped into 5 overdue bands.

    Bands:
      current   — due date in the future or no due date
      1_30      — 1–30 days overdue
      31_60     — 31–60 days overdue
      61_90     — 61–90 days overdue
      90_plus   — 91+ days overdue

    Returns each band with: count, total_outstanding, invoices[].
    Calculated using real outstanding balance (total_amount − payments), not raw total_amount.
    """
    check_project_access(db, current_user, project_id)
    from app.models.invoice import Invoice
    from app.models.supplier import Supplier
    from app.models.enums import RecordStatus, PaymentStatus
    from sqlalchemy import func as _f

    unpaid_statuses = [
        RecordStatus.DRAFT, RecordStatus.SUBMITTED, RecordStatus.RECEIVED,
        RecordStatus.APPROVED, RecordStatus.MATCHED,
        RecordStatus.INVOICED, RecordStatus.PARTIALLY_PAID,
    ]

    invoices = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id, Invoice.status.in_(unpaid_statuses))
        .all()
    )

    if not invoices:
        empty_band = {"count": 0, "total_outstanding": 0.0, "invoices": []}
        return ApiSuccess(data={
            "as_of": date.today().isoformat(),
            "current": empty_band, "1_30": empty_band,
            "31_60": empty_band, "61_90": empty_band, "90_plus": empty_band,
            "grand_total": 0.0,
        })

    # Bulk paid amounts
    inv_ids = [i.id for i in invoices]
    paid_rows = (
        db.query(Payment.invoice_id, _f.coalesce(_f.sum(Payment.amount_paid), 0).label("total"))
        .filter(Payment.invoice_id.in_(inv_ids), Payment.status.notin_(["CANCELLED", "FAILED"]))
        .group_by(Payment.invoice_id)
        .all()
    )
    paid_map = {str(r.invoice_id): float(r.total) for r in paid_rows}

    # Bulk supplier names
    sup_ids = {i.supplier_id for i in invoices if i.supplier_id}
    sup_names: dict = {}
    if sup_ids:
        for s in db.query(Supplier).filter(Supplier.id.in_(sup_ids)).all():
            sup_names[str(s.id)] = s.name

    today_dt = date.today()
    bands: dict = {
        "current": {"count": 0, "total_outstanding": 0.0, "invoices": []},
        "1_30":    {"count": 0, "total_outstanding": 0.0, "invoices": []},
        "31_60":   {"count": 0, "total_outstanding": 0.0, "invoices": []},
        "61_90":   {"count": 0, "total_outstanding": 0.0, "invoices": []},
        "90_plus": {"count": 0, "total_outstanding": 0.0, "invoices": []},
    }

    grand_total = 0.0
    for inv in invoices:
        total_amt  = float(inv.total_amount or 0)
        total_paid = paid_map.get(str(inv.id), 0.0)
        balance    = max(0.0, total_amt - total_paid)
        if balance <= 0:
            continue

        # Determine band
        if not inv.due_date or inv.due_date >= today_dt:
            band_key = "current"
        else:
            days_overdue = (today_dt - inv.due_date).days
            if days_overdue <= 30:
                band_key = "1_30"
            elif days_overdue <= 60:
                band_key = "31_60"
            elif days_overdue <= 90:
                band_key = "61_90"
            else:
                band_key = "90_plus"

        bands[band_key]["count"] += 1
        bands[band_key]["total_outstanding"] += balance
        bands[band_key]["invoices"].append({
            "invoice_id":         str(inv.id),
            "invoice_number":     inv.invoice_number,
            "supplier_name":      sup_names.get(str(inv.supplier_id)) if inv.supplier_id else None,
            "total_amount":       total_amt,
            "total_paid":         round(total_paid, 2),
            "outstanding_balance": round(balance, 2),
            "due_date":           inv.due_date.isoformat() if inv.due_date else None,
            "status":             inv.status.value,
        })
        grand_total += balance

    # Round totals
    for band in bands.values():
        band["total_outstanding"] = round(band["total_outstanding"], 2)

    return ApiSuccess(data={
        "as_of":       today_dt.isoformat(),
        **bands,
        "grand_total": round(grand_total, 2),
    })


@project_payment_router.get(
    "/export",
    dependencies=[OFFICE_AND_ABOVE],
    response_class=StreamingResponse,
)
def export_payments_csv(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    from_date:     Optional[date] = Query(None),
    to_date:       Optional[date] = Query(None),
    payment_type:  Optional[str]  = Query(None),
):
    """
    Download a CSV of all payments for the project, with optional date and type filters.
    Used by finance to generate monthly payment reports.
    """
    check_project_access(db, current_user, project_id)
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
