"""
Municipality Invoice service.

CRUD + Excel generation matching Cert 26 - Invoice 472.xlsx layout.
No auto-send, no auto-approve. The office lady controls everything.
"""

import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.municipality_invoice import MunicipalityInvoice, MunicipalityInvoiceItem
from app.models.project import Project


# ── Number generation ─────────────────────────────────────────────────────────

def _next_invoice_number(db: Session) -> str:
    count = db.query(MunicipalityInvoice).count()
    return f"IN{count + 1:05d}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, invoice_id: uuid.UUID) -> MunicipalityInvoice:
    inv = (
        db.query(MunicipalityInvoice)
        .options(joinedload(MunicipalityInvoice.items))
        .filter(MunicipalityInvoice.id == invoice_id)
        .first()
    )
    if not inv:
        raise NotFoundError(f"Municipality invoice {invoice_id} not found.")
    return inv


def _recalc(inv: MunicipalityInvoice) -> None:
    """Recompute subtotal, vat_amount, total_due from current items."""
    subtotal = sum(
        (item.total or Decimal("0")) for item in inv.items
    )
    inv.subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = inv.subtotal - (inv.previously_paid or Decimal("0"))
    if net < 0:
        net = Decimal("0")
    vat_rate = (inv.vat_rate or Decimal("15")) / Decimal("100")
    inv.vat_amount = (net * vat_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inv.total_due  = (net + inv.vat_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_invoices(
    db: Session,
    project_id: uuid.UUID,
    status: Optional[str] = None,
) -> list[MunicipalityInvoice]:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")
    q = (
        db.query(MunicipalityInvoice)
        .options(joinedload(MunicipalityInvoice.items))
        .filter(MunicipalityInvoice.project_id == project_id)
    )
    if status:
        q = q.filter(MunicipalityInvoice.status == status)
    return q.order_by(MunicipalityInvoice.created_at.desc()).all()


def get_invoice(db: Session, invoice_id: uuid.UUID) -> MunicipalityInvoice:
    return _get_or_404(db, invoice_id)


def create_invoice(
    db: Session,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    invoice_number: Optional[str] = None,
    cert_number: Optional[str] = None,
    invoice_date: Optional[date] = None,
    due_date: Optional[date] = None,
    client_name: str = "Ethekweni Municipality",
    client_vat_no: Optional[str] = None,
    client_address: Optional[str] = None,
    company_email: Optional[str] = None,
    project_description: Optional[str] = None,
    contract_reference: Optional[str] = None,
    previously_paid: Optional[Decimal] = None,
    vat_rate: Decimal = Decimal("15.00"),
    notes: Optional[str] = None,
    bank_name: Optional[str] = None,
    account_number: Optional[str] = None,
    branch_name: Optional[str] = None,
    branch_code: Optional[str] = None,
    items: Optional[list[dict]] = None,
) -> MunicipalityInvoice:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")

    inv_number = invoice_number or _next_invoice_number(db)
    if db.query(MunicipalityInvoice).filter(MunicipalityInvoice.invoice_number == inv_number).first():
        raise ValidationError(f"Invoice number {inv_number} already exists.")

    now = datetime.now(timezone.utc)
    inv = MunicipalityInvoice(
        invoice_number=inv_number,
        cert_number=cert_number,
        project_id=project_id,
        invoice_date=invoice_date or date.today(),
        due_date=due_date,
        client_name=client_name,
        client_vat_no=client_vat_no,
        client_address=client_address,
        company_email=company_email,
        project_description=project_description,
        contract_reference=contract_reference,
        previously_paid=previously_paid,
        vat_rate=vat_rate,
        subtotal=Decimal("0"),
        vat_amount=Decimal("0"),
        total_due=Decimal("0"),
        notes=notes,
        bank_name=bank_name,
        account_number=account_number,
        branch_name=branch_name,
        branch_code=branch_code,
        status="DRAFT",
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(inv)
    db.flush()

    for idx, item_data in enumerate(items or []):
        qty   = item_data.get("quantity")
        price = item_data.get("unit_price")
        total = item_data.get("total")
        if total is None and qty is not None and price is not None:
            total = (Decimal(str(qty)) * Decimal(str(price))).quantize(Decimal("0.01"))
        db.add(MunicipalityInvoiceItem(
            invoice_id  = inv.id,
            sort_order  = item_data.get("sort_order", idx),
            line_number = item_data.get("line_number"),
            description = item_data.get("description", ""),
            quantity    = Decimal(str(qty))    if qty    is not None else None,
            unit_price  = Decimal(str(price))  if price  is not None else None,
            total       = Decimal(str(total))  if total  is not None else None,
            disc_pct    = Decimal(str(item_data["disc_pct"])) if item_data.get("disc_pct") is not None else None,
            comments    = item_data.get("comments"),
            created_at  = now,
        ))

    db.flush()
    db.refresh(inv)
    _recalc(inv)
    db.commit()
    db.refresh(inv)
    return inv


def update_invoice(
    db: Session,
    invoice_id: uuid.UUID,
    **fields,
) -> MunicipalityInvoice:
    inv = _get_or_404(db, invoice_id)
    if inv.status == "FINALISED":
        raise ValidationError("Cannot edit a finalised invoice. Change status to DRAFT first.")

    simple = [
        "cert_number", "invoice_date", "due_date", "client_name", "client_vat_no",
        "client_address", "company_email", "project_description", "contract_reference",
        "previously_paid", "vat_rate", "notes", "bank_name", "account_number",
        "branch_name", "branch_code", "status",
    ]
    for key in simple:
        if key in fields and fields[key] is not None:
            setattr(inv, key, fields[key])

    # Replace items if provided
    if "items" in fields and fields["items"] is not None:
        for old in list(inv.items):
            db.delete(old)
        db.flush()
        now = datetime.now(timezone.utc)
        for idx, item_data in enumerate(fields["items"]):
            qty   = item_data.get("quantity")
            price = item_data.get("unit_price")
            total = item_data.get("total")
            if total is None and qty is not None and price is not None:
                total = (Decimal(str(qty)) * Decimal(str(price))).quantize(Decimal("0.01"))
            db.add(MunicipalityInvoiceItem(
                invoice_id  = inv.id,
                sort_order  = item_data.get("sort_order", idx),
                line_number = item_data.get("line_number"),
                description = item_data.get("description", ""),
                quantity    = Decimal(str(qty))   if qty   is not None else None,
                unit_price  = Decimal(str(price)) if price is not None else None,
                total       = Decimal(str(total)) if total is not None else None,
                disc_pct    = Decimal(str(item_data["disc_pct"])) if item_data.get("disc_pct") is not None else None,
                comments    = item_data.get("comments"),
                created_at  = now,
            ))
        db.flush()
        db.refresh(inv)

    _recalc(inv)
    inv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(inv)
    return inv


def delete_invoice(db: Session, invoice_id: uuid.UUID) -> None:
    inv = _get_or_404(db, invoice_id)
    if inv.status == "FINALISED":
        raise ValidationError("Cannot delete a finalised invoice.")
    db.delete(inv)
    db.commit()


# ── Excel export ──────────────────────────────────────────────────────────────

def export_excel(db: Session, invoice_id: uuid.UUID) -> bytes:
    """
    Generate an Excel file matching the Cert 26 - Invoice 472.xlsx layout.
    Returns raw bytes (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet).
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
    except ImportError:
        raise ValidationError("openpyxl is required for Excel export. Run: pip install openpyxl")

    inv = _get_or_404(db, invoice_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Invoice {inv.invoice_number}"

    def w(row: int, col: int, value, bold: bool = False, align: str = "left") -> None:
        cell = ws.cell(row=row, column=col, value=value)
        if bold:
            cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)

    # ── Column widths (approximate match to template) ─────────────────────────
    col_widths = {1: 8, 2: 3, 3: 45, 4: 12, 5: 3, 6: 14, 7: 14, 8: 40, 9: 22, 10: 16}
    for col_idx, width in col_widths.items():
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    # ── Header (right side) ───────────────────────────────────────────────────
    w(1, 8, "TAX INVOICE", bold=True)
    w(2, 8, inv.invoice_date.strftime("%Y-%m-%d") if inv.invoice_date else "")
    w(3, 8, "Page                                                     1")
    w(4, 8, f"Document Number                   {inv.invoice_number}")

    # ── Supplier email (left side) ────────────────────────────────────────────
    w(5, 1, "e-mail:")
    w(5, 4, inv.company_email or "")

    w(6, 8, "   Deliver To:")

    # ── Client info ───────────────────────────────────────────────────────────
    if inv.client_vat_no:
        w(7, 3, f"Client Vat No {inv.client_vat_no}")
    w(7, 8, inv.client_name or "")

    address_lines = (inv.client_address or "").split("\n")
    for i, line in enumerate(address_lines[:3]):
        w(8 + i, 8, line)

    # ── Reference header row ─────────────────────────────────────────────────
    ref_row = 10
    w(ref_row, 1, "Account")
    w(ref_row, 3, "Your Reference")
    w(ref_row, 6, "Tax Reference")
    w(ref_row, 8, "Sales Code")
    w(ref_row + 1, 6, "N/A")

    # ── Column headers ────────────────────────────────────────────────────────
    hdr = ref_row + 2
    w(hdr, 1, "Code",       bold=True)
    w(hdr, 3, "Description", bold=True)
    w(hdr, 4, "Quantity",   bold=True)
    w(hdr, 6, "Unit Price", bold=True)
    w(hdr, 7, "Total",      bold=True)
    w(hdr, 8, "Disc%",      bold=True)
    w(hdr, 9, "Tax",        bold=True)

    # ── Project / certificate block ───────────────────────────────────────────
    proj_row = hdr + 3
    if inv.project_description:
        w(proj_row,     3, inv.project_description, bold=True)
    if inv.contract_reference:
        w(proj_row + 1, 3, inv.contract_reference)
    cert_label = f"(to pay cert {inv.cert_number})" if inv.cert_number else ""
    subtotal_val = float(inv.subtotal or 0)
    w(proj_row + 2, 3, cert_label)
    w(proj_row + 2, 7, subtotal_val)
    w(proj_row + 2, 10, subtotal_val)

    # ── DESCRIPTION header ────────────────────────────────────────────────────
    desc_hdr_row = proj_row + 3
    w(desc_hdr_row, 3, "DESCRIPTION", bold=True)

    # ── Line items ────────────────────────────────────────────────────────────
    item_start = desc_hdr_row + 1
    for idx, item in enumerate(inv.items):
        r = item_start + idx
        w(r, 1, item.line_number or str(idx + 1))
        w(r, 3, item.description or "")
        if item.quantity is not None:
            w(r, 4, float(item.quantity))
        if item.unit_price is not None:
            w(r, 6, float(item.unit_price))
        if item.total is not None:
            w(r, 7, float(item.total))
        if item.disc_pct is not None:
            w(r, 8, float(item.disc_pct))

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes_row = item_start + len(inv.items) + 1
    if inv.notes:
        w(notes_row, 3, inv.notes)
        notes_row += 1

    # ── Banking details ───────────────────────────────────────────────────────
    bank_row = notes_row + 1
    if inv.bank_name:
        w(bank_row,     3, f"BANKING DETAILS : {inv.bank_name.upper()}")
        w(bank_row + 1, 3, f"ACCOUNT NUMBER : {inv.account_number or ''}")
        w(bank_row + 2, 3, f"BRANCH  : {inv.branch_name or ''}")
        w(bank_row + 3, 3, f"BRANCH CODE: {inv.branch_code or ''}")
        totals_row = bank_row + 5
    else:
        totals_row = bank_row + 1

    # ── Totals section ────────────────────────────────────────────────────────
    sub = float(inv.subtotal or 0)
    prev = float(inv.previously_paid or 0)
    net  = max(0.0, sub - prev)
    vat  = float(inv.vat_amount or 0)
    due  = float(inv.total_due or 0)

    w(totals_row,     9, "Sub Total",           bold=True)
    w(totals_row,     10, sub)
    w(totals_row + 1, 1, "Signature: ")
    w(totals_row + 2, 9, "Sub Total",           bold=True)
    w(totals_row + 2, 10, sub)
    w(totals_row + 3, 9, "Less Previously paid", bold=True)
    w(totals_row + 3, 10, prev if prev > 0 else 0)
    w(totals_row + 4, 9, "Sub Total",           bold=True)
    w(totals_row + 4, 10, net)
    w(totals_row + 5, 9, f"Vat @{float(inv.vat_rate or 15):.0f}%", bold=True)
    w(totals_row + 5, 10, vat)
    w(totals_row + 6, 9, "Now Due ",             bold=True)
    w(totals_row + 6, 10, due)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
