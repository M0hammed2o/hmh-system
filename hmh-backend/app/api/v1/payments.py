"""Payment routes."""

import uuid

from fastapi import APIRouter

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
