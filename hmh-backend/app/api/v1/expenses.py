"""
Expense record endpoints.

POST /expenses/upload     — upload invoice/receipt, creates ExpenseRecord
GET  /expenses            — list expense records
GET  /expenses/{id}       — single expense
POST /expenses/{id}/approve
POST /expenses/{id}/reject
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/expenses", tags=["expenses"])

_EXPENSE_DIR = os.path.join(settings.UPLOAD_DIR, "expenses")


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", status_code=201, dependencies=[ALL_ROLES])
async def upload_expense(
    db: DbSession,
    current_user: CurrentUser,
    file: Optional[UploadFile] = File(None),
    category:       str = Form("OTHER"),
    supplier_name:  str = Form(...),
    project_id:     Optional[str] = Form(None),
    site_id:        Optional[str] = Form(None),
    lot_id:         Optional[str] = Form(None),
    vehicle_id:     Optional[str] = Form(None),
    invoice_number: Optional[str] = Form(None),
    amount:         Optional[float] = Form(None),
    notes:          Optional[str] = Form(None),
):
    from app.models.document_extraction import DocumentExtraction, ExpenseRecord

    now = datetime.now(timezone.utc)
    file_path: Optional[str] = None
    extraction_id: Optional[uuid.UUID] = None

    if file and file.filename:
        os.makedirs(_EXPENSE_DIR, exist_ok=True)
        ext = os.path.splitext(file.filename)[1] or ".bin"
        fname = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(_EXPENSE_DIR, fname)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Try extraction
        from app.services.document_ai_service import extract_document_data
        result = extract_document_data(file_path, "INVOICE")

        extraction = DocumentExtraction(
            source_type="EXPENSE",
            file_path=file_path,
            document_type="INVOICE",
            status=result["status"],
            raw_text=result.get("raw_text", ""),
            extracted_json=json.dumps(result),
            created_at=now,
        )
        db.add(extraction)
        db.flush()
        extraction_id = extraction.id

        # Auto-fill fields from extraction if not provided
        fields = result.get("fields", {})
        if not invoice_number:
            invoice_number = fields.get("invoice_number")
        if amount is None:
            amount = fields.get("total_amount")

    expense = ExpenseRecord(
        project_id=uuid.UUID(project_id) if project_id else None,
        site_id=uuid.UUID(site_id) if site_id else None,
        lot_id=uuid.UUID(lot_id) if lot_id else None,
        vehicle_id=uuid.UUID(vehicle_id) if vehicle_id else None,
        category=category,
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        amount=amount,
        file_path=file_path,
        status="NEEDS_REVIEW" if (file_path and not amount) else "UPLOADED",
        uploaded_by=current_user.id,
        notes=notes,
        extraction_id=extraction_id,
        created_at=now,
    )
    db.add(expense)
    db.commit()

    return ApiSuccess(
        data={"id": str(expense.id), "status": expense.status},
        message="Expense recorded.",
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[OFFICE_AND_ABOVE])
def list_expenses(db: DbSession, status: Optional[str] = None, limit: int = 50, offset: int = 0):
    from app.models.document_extraction import ExpenseRecord

    q = db.query(ExpenseRecord).order_by(ExpenseRecord.created_at.desc())
    if status:
        q = q.filter(ExpenseRecord.status == status.upper())
    total = q.count()
    rows  = q.offset(offset).limit(limit).all()

    return ApiSuccess(data={
        "total": total,
        "items": [_expense_summary(e) for e in rows],
    })


# ── Get ───────────────────────────────────────────────────────────────────────

@router.get("/{expense_id}", dependencies=[OFFICE_AND_ABOVE])
def get_expense(expense_id: uuid.UUID, db: DbSession):
    from app.models.document_extraction import ExpenseRecord

    e = db.query(ExpenseRecord).filter(ExpenseRecord.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found.")
    return ApiSuccess(data=_expense_summary(e))


# ── Approve / Reject ──────────────────────────────────────────────────────────

class ApproveBody(BaseModel):
    notes: Optional[str] = None


@router.post("/{expense_id}/approve", dependencies=[OFFICE_AND_ABOVE])
def approve_expense(expense_id: uuid.UUID, body: ApproveBody, db: DbSession, current_user: CurrentUser):
    from app.models.document_extraction import ExpenseRecord

    e = db.query(ExpenseRecord).filter(ExpenseRecord.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found.")
    if e.status in ("APPROVED", "PAID"):
        raise HTTPException(400, f"Expense is already {e.status}.")

    e.status      = "APPROVED"
    e.approved_by = current_user.id
    e.approved_at = datetime.now(timezone.utc)
    if body.notes:
        e.notes = (e.notes or "") + f"\n[Approved] {body.notes}"
    db.commit()
    return ApiSuccess(data={"id": str(e.id), "status": "APPROVED"}, message="Expense approved.")


@router.post("/{expense_id}/reject", dependencies=[OFFICE_AND_ABOVE])
def reject_expense(expense_id: uuid.UUID, body: ApproveBody, db: DbSession, current_user: CurrentUser):
    from app.models.document_extraction import ExpenseRecord

    e = db.query(ExpenseRecord).filter(ExpenseRecord.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found.")

    e.status      = "REJECTED"
    e.approved_by = current_user.id
    e.approved_at = datetime.now(timezone.utc)
    if body.notes:
        e.notes = (e.notes or "") + f"\n[Rejected] {body.notes}"
    db.commit()
    return ApiSuccess(data={"id": str(e.id), "status": "REJECTED"}, message="Expense rejected.")


# ── Serialiser ────────────────────────────────────────────────────────────────

def _expense_summary(e) -> dict:
    return {
        "id":             str(e.id),
        "category":       e.category,
        "supplier_name":  e.supplier_name,
        "invoice_number": e.invoice_number,
        "amount":         float(e.amount) if e.amount else None,
        "status":         e.status,
        "has_file":       bool(e.file_path),
        "notes":          e.notes,
        "created_at":     e.created_at.isoformat(),
        "approved_at":    e.approved_at.isoformat() if e.approved_at else None,
    }
