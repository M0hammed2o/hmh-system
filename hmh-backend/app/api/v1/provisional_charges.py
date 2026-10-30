"""
Pending supplier charges — money asked for in advance, not money owed.

Deliberately its own router rather than a filter on the invoice routes. A
pro-forma is not a payable, and an endpoint that can return both behind a
flag is an endpoint whose results will eventually be summed into an Accounts
Payable total by a caller who did not read the flag.

Reading is open to the same roles that may read invoices. Writing happens
through document import, or by cancelling a request that will not be
honoured; a charge is never settled from here — it is closed by the
supplier's tax invoice being recorded.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.dependencies import (
    ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, check_project_access,
)
from app.models.enums import ProvisionalChargeStatus
from app.schemas.common import ApiSuccess
from app.services import provisional_charge_service as charges

project_provisional_router = APIRouter(
    prefix="/projects/{project_id}/provisional-charges",
    tags=["provisional charges"],
)
provisional_router = APIRouter(prefix="/provisional-charges", tags=["provisional charges"])


def _serialise(charge) -> dict:
    return {
        "id": str(charge.id),
        "reference": charge.reference,
        "supplier_id": str(charge.supplier_id),
        "supplier_name": charge.supplier.name if charge.supplier else None,
        "project_id": str(charge.project_id),
        "purchase_order_id": (
            str(charge.purchase_order_id) if charge.purchase_order_id else None
        ),
        # The number, not just the id: a screen that shows a UUID for "matched
        # order" has not told anybody which order it matched.
        "purchase_order_number": (
            charge.purchase_order.po_number if charge.purchase_order else None
        ),
        "quotation_id": str(charge.quotation_id) if charge.quotation_id else None,
        "issue_date": charge.issue_date.isoformat() if charge.issue_date else None,
        "due_date": charge.due_date.isoformat() if charge.due_date else None,
        "subtotal_amount": (
            float(charge.subtotal_amount) if charge.subtotal_amount is not None else None
        ),
        "vat_amount": float(charge.vat_amount) if charge.vat_amount is not None else None,
        "total_amount": float(charge.total_amount),
        "status": charge.status.value,
        "settled_by_invoice_id": (
            str(charge.settled_by_invoice_id) if charge.settled_by_invoice_id else None
        ),
        "settled_by_invoice_number": (
            charge.settled_by_invoice.invoice_number if charge.settled_by_invoice else None
        ),
        "payment_evidence_detected": charge.payment_evidence_detected,
        "payment_evidence_note": charge.payment_evidence_note,
        "notes": charge.notes,
        "created_at": charge.created_at.isoformat() if charge.created_at else None,
    }


@project_provisional_router.get(
    "/", response_model=ApiSuccess[list[dict]], dependencies=[ALL_ROLES],
)
def list_provisional_charges(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[ProvisionalChargeStatus] = Query(
        None, description="PENDING, INVOICED or CANCELLED. Omit for all.",
    ),
):
    check_project_access(db, current_user, project_id)
    return ApiSuccess(
        data=[_serialise(c) for c in charges.list_charges(db, project_id, status=status)]
    )


@project_provisional_router.get(
    "/summary", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES],
)
def provisional_summary(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    What suppliers have asked for in advance and not yet invoiced.

    Reported next to Accounts Payable and never added to it: this answers
    "what might we be asked to pay", Accounts Payable answers "what do we
    owe". The response says so in words, because a bare number on a screen
    invites exactly the addition this separation exists to prevent.
    """
    check_project_access(db, current_user, project_id)
    pending = charges.list_charges(db, project_id, status=ProvisionalChargeStatus.PENDING)
    return ApiSuccess(data={
        "pending_count": len(pending),
        "pending_total": charges.outstanding_total(db, project_id),
        "payment_evidence_count": sum(
            1 for c in pending if c.payment_evidence_detected
        ),
        "meaning": (
            "Requested by suppliers in advance and not yet invoiced. This is not "
            "owed and is not part of Accounts Payable — each becomes a liability "
            "only when the supplier issues a tax invoice for the same purchase."
        ),
    })


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@provisional_router.post(
    "/{charge_id}/cancel", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE],
)
def cancel_provisional_charge(
    charge_id: uuid.UUID, body: CancelRequest, db: DbSession, current_user: CurrentUser,
):
    """Withdraw a request for payment that will not be honoured."""
    charge = charges.get_charge(db, charge_id)
    check_project_access(db, current_user, charge.project_id)
    charges.cancel_charge(db, charge, current_user.id, body.reason)
    db.commit()
    db.refresh(charge)
    return ApiSuccess(data=_serialise(charge), message="Pending charge cancelled.")
