"""Supplier routes."""

import uuid

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import ALL_ROLES, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "/suggest",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def suggest_suppliers(
    db: DbSession,
    name: str = Query(..., min_length=2, description="Extracted supplier name to match"),
    limit: int = Query(3, le=10),
):
    """
    Fuzzy-match an extracted supplier name against known active suppliers.

    Used by OCR review panel to suggest which supplier matches the name found on an invoice.
    Returns up to `limit` results ranked by similarity.
    Algorithm: exact > starts-with > word overlap > substring.
    """
    from app.models.supplier import Supplier
    import re as _re

    name_lower = name.strip().lower()
    name_words = set(_re.split(r"\W+", name_lower)) - {"", "pty", "ltd", "cc", "inc", "the"}

    suppliers = (
        db.query(Supplier)
        .filter(Supplier.is_active == True)  # noqa: E712
        .all()
    )

    scored = []
    for s in suppliers:
        n = s.name.lower()
        n_words = set(_re.split(r"\W+", n)) - {"", "pty", "ltd", "cc", "inc", "the"}

        if n == name_lower:
            score = 1.0
        elif n.startswith(name_lower) or name_lower.startswith(n):
            score = 0.85
        elif name_words and n_words:
            overlap = len(name_words & n_words)
            union   = len(name_words | n_words)
            score   = overlap / union  # Jaccard similarity
        elif name_lower in n or n in name_lower:
            score = 0.3
        else:
            score = 0.0

        if score > 0.1:
            scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    return ApiSuccess(data=[
        {"id": str(s.id), "name": s.name, "email": s.email, "score": round(score, 3)}
        for score, s in scored[:limit]
    ])


@router.get(
    "/",
    response_model=ApiSuccess[list[SupplierRead]],
    dependencies=[ALL_ROLES],
)
def list_suppliers(
    db: DbSession,
    include_inactive: bool = Query(False),
):
    suppliers = supplier_service.list_suppliers(db, include_inactive)
    return ApiSuccess(data=[SupplierRead.model_validate(s) for s in suppliers])


@router.get(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[ALL_ROLES],
)
def get_supplier(supplier_id: uuid.UUID, db: DbSession):
    s = supplier_service.get_supplier(db, supplier_id)
    return ApiSuccess(data=SupplierRead.model_validate(s))


@router.post(
    "/",
    response_model=ApiSuccess[SupplierRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_supplier(body: SupplierCreate, db: DbSession):
    s = supplier_service.create_supplier(db, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier created.")


@router.patch(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession):
    s = supplier_service.update_supplier(db, supplier_id, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier updated.")


@router.get("/{supplier_id}/outstanding", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def supplier_outstanding(supplier_id: uuid.UUID, db: DbSession):
    """
    Return per-supplier financial summary: PO total, invoiced, paid, outstanding.
    """
    from datetime import date
    from sqlalchemy import func
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.enums import RecordStatus, PaymentStatus

    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")

    po_total = float(
        db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
        .filter(PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status.notin_([RecordStatus.CANCELLED, RecordStatus.REJECTED]))
        .scalar() or 0
    )
    invoice_total = float(
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
        .filter(Invoice.supplier_id == supplier_id,
                Invoice.status.notin_([RecordStatus.CANCELLED, RecordStatus.REJECTED]))
        .scalar() or 0
    )
    paid_total = float(
        db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
        .filter(Payment.supplier_id == supplier_id, Payment.status == PaymentStatus.PAID)
        .scalar() or 0
    )
    today = date.today()
    overdue = float(
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
        .filter(Invoice.supplier_id == supplier_id,
                Invoice.due_date < today,
                Invoice.status.notin_([RecordStatus.PAID, RecordStatus.CANCELLED]))
        .scalar() or 0
    )

    return ApiSuccess(data={
        "supplier_id":      str(supplier_id),
        "supplier_name":    s.name,
        "po_total":         po_total,
        "invoice_total":    invoice_total,
        "paid_total":       paid_total,
        "outstanding":      max(0.0, invoice_total - paid_total),
        "overdue_amount":   overdue,
    })


@router.get(
    "/{supplier_id}/procurement-history",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def supplier_procurement_history(supplier_id: uuid.UUID, db: DbSession):
    """
    Return a full procurement chain for this supplier:
    all POs (with linked quotation, MR, deliveries, invoices, payments)
    plus standalone quotations not yet linked to a PO.
    """
    from datetime import date as _date
    from sqlalchemy import func
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.models.payment import Payment
    from app.models.quotation import Quotation
    from app.models.enums import PaymentStatus, RecordStatus

    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")

    # ── All POs for this supplier ──────────────────────────────────────────────
    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.supplier_id == supplier_id)
        .order_by(PurchaseOrder.po_date.desc())
        .all()
    )

    po_ids = [po.id for po in pos]
    linked_quotation_ids: set = set()

    # Bulk-fetch deliveries for all POs
    all_deliveries = (
        db.query(Delivery)
        .filter(Delivery.purchase_order_id.in_(po_ids))
        .all()
    ) if po_ids else []
    deliveries_by_po: dict = {}
    for d in all_deliveries:
        deliveries_by_po.setdefault(str(d.purchase_order_id), []).append(d)

    # Bulk-fetch invoices for all POs
    all_invoices = (
        db.query(Invoice)
        .filter(Invoice.purchase_order_id.in_(po_ids))
        .order_by(Invoice.created_at)
        .all()
    ) if po_ids else []
    invoices_by_po: dict = {}
    invoice_ids = []
    for i in all_invoices:
        invoices_by_po.setdefault(str(i.purchase_order_id), []).append(i)
        invoice_ids.append(i.id)

    # Bulk-fetch payment totals per invoice
    paid_by_invoice: dict = {}
    if invoice_ids:
        rows = (
            db.query(Payment.invoice_id, func.coalesce(func.sum(Payment.amount_paid), 0).label("total"))
            .filter(Payment.invoice_id.in_(invoice_ids), Payment.status == PaymentStatus.PAID)
            .group_by(Payment.invoice_id)
            .all()
        )
        paid_by_invoice = {str(r.invoice_id): float(r.total) for r in rows}

    # Bulk-fetch quotations linked to these POs
    quotation_ids_from_po = [po.quotation_id for po in pos if po.quotation_id]
    quotations_by_id: dict = {}
    if quotation_ids_from_po:
        qs = db.query(Quotation).filter(Quotation.id.in_(quotation_ids_from_po)).all()
        for q in qs:
            quotations_by_id[str(q.id)] = q
            linked_quotation_ids.add(str(q.id))

    # Build PO chain data
    po_chains = []
    for po in pos:
        po_deliveries = deliveries_by_po.get(str(po.id), [])
        po_invoices = invoices_by_po.get(str(po.id), [])

        q_summary = None
        if po.quotation_id:
            q = quotations_by_id.get(str(po.quotation_id))
            if q:
                q_summary = {
                    "quotation_id": str(q.id),
                    "quote_number": q.quote_number,
                    "status": q.status.value,
                    "gross_amount": float(q.gross_amount or 0),
                    "vat_rate_used": float(q.vat_rate_used or 15.0),
                    "expiry_date": q.expiry_date.isoformat() if q.expiry_date else None,
                }

        invoice_list = [
            {
                "invoice_id": str(i.id),
                "invoice_number": i.invoice_number,
                "total_amount": float(i.total_amount or 0),
                "total_paid": paid_by_invoice.get(str(i.id), 0.0),
                "balance_due": round(float(i.total_amount or 0) - paid_by_invoice.get(str(i.id), 0.0), 2),
                "status": i.status.value,
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None,
            }
            for i in po_invoices
        ]

        delivery_list = [
            {
                "delivery_id": str(d.id),
                "delivery_number": d.delivery_number or str(d.id)[:8],
                "delivery_date": d.delivery_date.date().isoformat() if d.delivery_date else None,
                "status": d.delivery_status.value if d.delivery_status else None,
            }
            for d in po_deliveries
        ]

        total_invoiced = sum(i["total_amount"] for i in invoice_list)
        total_paid = sum(i["total_paid"] for i in invoice_list)

        # Chain status summary for indicators
        chain_status = {
            "has_mr": po.material_request_id is not None,
            "has_quotation": q_summary is not None,
            "quotation_status": q_summary["status"] if q_summary else None,
            "po_status": po.status.value,
            "has_delivery": len(delivery_list) > 0,
            "delivery_status": delivery_list[0]["status"] if delivery_list else None,
            "has_invoice": len(invoice_list) > 0,
            "invoice_status": invoice_list[0]["status"] if invoice_list else None,
            "total_invoiced": round(total_invoiced, 2),
            "total_paid": round(total_paid, 2),
            "is_fully_paid": total_invoiced > 0 and round(total_invoiced - total_paid, 2) <= 0,
        }

        po_chains.append({
            "po_id": str(po.id),
            "po_number": po.po_number,
            "po_date": po.po_date.date().isoformat() if po.po_date else None,
            "status": po.status.value,
            "total_amount": float(po.total_amount or 0),
            "subtotal_amount": float(po.subtotal_amount or 0),
            "vat_amount": float(po.vat_amount or 0),
            "project_id": str(po.project_id),
            "quotation": q_summary,
            "source_mr": {"mr_id": str(po.material_request_id)} if po.material_request_id else None,
            "deliveries": delivery_list,
            "invoices": invoice_list,
            "chain_status": chain_status,
        })

    # ── Standalone quotations (not linked to any PO for this supplier) ─────────
    all_supplier_quotations = (
        db.query(Quotation)
        .filter(Quotation.supplier_id == supplier_id)
        .order_by(Quotation.created_at.desc())
        .all()
    )
    standalone_quotations = [
        {
            "quotation_id": str(q.id),
            "quote_number": q.quote_number,
            "status": q.status.value,
            "quote_date": q.quote_date.isoformat() if q.quote_date else None,
            "expiry_date": q.expiry_date.isoformat() if q.expiry_date else None,
            "net_amount": float(q.net_amount or 0),
            "vat_amount": float(q.vat_amount or 0),
            "gross_amount": float(q.gross_amount or 0),
            "vat_rate_used": float(q.vat_rate_used or 15.0),
            "notes": q.notes,
            "created_at": q.created_at.isoformat(),
        }
        for q in all_supplier_quotations
        if str(q.id) not in linked_quotation_ids
    ]

    return ApiSuccess(data={
        "supplier_id": str(supplier_id),
        "supplier_name": s.name,
        "purchase_orders": po_chains,
        "standalone_quotations": standalone_quotations,
        "po_count": len(po_chains),
        "quotation_count": len(all_supplier_quotations),
    })


@router.get(
    "/{supplier_id}/documents",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def supplier_documents(supplier_id: uuid.UUID, db: DbSession):
    """Unified document list: POs, Invoices, Deliveries, Quotations, MRs, and manual Attachments."""
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.invoice import Invoice
    from app.models.delivery import Delivery
    from app.models.quotation import Quotation
    from app.models.attachment import Attachment
    from app.models.enums import AttachmentEntity, AttachmentType
    from app.schemas.attachment import AttachmentRead
    from app.models.user import User
    from sqlalchemy import or_

    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")

    docs = []
    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.supplier_id == supplier_id)
        .order_by(PurchaseOrder.po_date.desc())
        .all()
    )
    po_ids = [po.id for po in pos]

    # Build a map of PO id → latest saved PDF url (from auto-saved PO emails)
    po_pdf_map: dict = {}
    if po_ids:
        po_pdfs = (
            db.query(Attachment)
            .filter(
                Attachment.entity_type == AttachmentEntity.PURCHASE_ORDER,
                Attachment.entity_id.in_(po_ids),
                Attachment.attachment_type == AttachmentType.PO_DOCUMENT,
                Attachment.is_active == True,  # noqa: E712
            )
            .order_by(Attachment.uploaded_at.desc())
            .all()
        )
        for att in po_pdfs:
            key = str(att.entity_id)
            if key not in po_pdf_map:
                read = AttachmentRead.model_validate(att)
                po_pdf_map[key] = read.download_url

    # Find all MRs emailed to this supplier via MREmailLog (works before a PO exists)
    from app.models.mr_email_log import MREmailLog
    mr_email_logs = (
        db.query(MREmailLog)
        .filter(
            MREmailLog.supplier_id == supplier_id,
            MREmailLog.status.in_(["SENT", "MOCK_SENT"]),
        )
        .all()
    )
    mr_ids_for_supplier = list({log.material_request_id for log in mr_email_logs})

    for po in pos:
        docs.append({
            "doc_id":        str(po.id),
            "doc_type":      "PURCHASE_ORDER",
            "ref_number":    po.po_number or str(po.id)[:8],
            "title":         f"Purchase Order {po.po_number}",
            "date":          po.po_date.date().isoformat() if po.po_date else None,
            "amount":        float(po.total_amount or 0),
            "status":        po.status.value,
            "file_url":      po_pdf_map.get(str(po.id)),
            "file_name":     f"PO-{po.po_number}.pdf" if po.po_number else None,
            "is_attachment":  bool(po_pdf_map.get(str(po.id))),
            "detail_path":   f"/procurement?po={po.id}",
        })

    if po_ids:
        for inv in db.query(Invoice).filter(Invoice.purchase_order_id.in_(po_ids)).all():
            docs.append({
                "doc_id":       str(inv.id),
                "doc_type":     "INVOICE",
                "ref_number":   inv.invoice_number,
                "title":        f"Invoice {inv.invoice_number}",
                "date":         inv.invoice_date.isoformat() if inv.invoice_date else None,
                "amount":       float(inv.total_amount or 0),
                "status":       inv.status.value,
                "file_url":     None,
                "file_name":    None,
                "is_attachment": False,
                "detail_path":  f"/reconciliation",
            })
        for d in db.query(Delivery).filter(Delivery.purchase_order_id.in_(po_ids)).all():
            img = d.delivery_note_image_url or None
            docs.append({
                "doc_id":        str(d.id),
                "doc_type":      "DELIVERY_NOTE",
                "ref_number":    d.delivery_number or str(d.id)[:8],
                "title":         f"Delivery {d.delivery_number or str(d.id)[:8]}",
                "date":          d.delivery_date.date().isoformat() if d.delivery_date else None,
                "amount":        None,
                "status":        d.delivery_status.value if d.delivery_status else None,
                "file_url":      img,
                "file_name":     d.delivery_number or str(d.id)[:8],
                "is_attachment":  bool(img),
                "detail_path":   f"/deliveries",
            })

    for q in db.query(Quotation).filter(Quotation.supplier_id == supplier_id).all():
        docs.append({
            "doc_id":       str(q.id),
            "doc_type":     "QUOTATION",
            "ref_number":   q.quote_number,
            "title":        f"Quotation {q.quote_number}",
            "date":         q.quote_date.isoformat() if q.quote_date else None,
            "amount":       float(q.gross_amount or 0),
            "status":       q.status.value,
            "file_url":     None,
            "file_name":    None,
            "is_attachment": False,
            "detail_path":  f"/procurement",
        })

    # ── Material Requests emailed to this supplier ────────────────────────────
    if mr_ids_for_supplier:
        from app.models.material_request import MaterialRequest

        # MR records — show even when no PDF was saved (e.g. sent before this feature)
        mr_pdf_map: dict = {}  # mr_id → download_url for saved PDFs
        mr_pdfs = (
            db.query(Attachment)
            .filter(
                Attachment.entity_type == AttachmentEntity.MATERIAL_REQUEST,
                Attachment.entity_id.in_(mr_ids_for_supplier),
                Attachment.attachment_type == AttachmentType.PDF,
                Attachment.is_active == True,  # noqa: E712
            )
            .order_by(Attachment.uploaded_at.desc())
            .all()
        )
        for att in mr_pdfs:
            key = str(att.entity_id)
            if key not in mr_pdf_map:
                read = AttachmentRead.model_validate(att)
                mr_pdf_map[key] = (read.download_url, att.file_name)

        mrs = (
            db.query(MaterialRequest)
            .filter(MaterialRequest.id.in_(mr_ids_for_supplier))
            .order_by(MaterialRequest.created_at.desc())
            .all()
        )
        for mr in mrs:
            pdf_url, pdf_name = mr_pdf_map.get(str(mr.id), (None, None))
            docs.append({
                "doc_id":        str(mr.id),
                "doc_type":      "MATERIAL_REQUEST",
                "ref_number":    mr.request_number,
                "title":         f"Material Request {mr.request_number}",
                "date":          mr.created_at.date().isoformat() if mr.created_at else None,
                "amount":        None,
                "status":        mr.status.value if hasattr(mr.status, "value") else str(mr.status),
                "file_url":      pdf_url,
                "file_name":     pdf_name or f"MR-{mr.request_number}.pdf",
                "is_attachment": bool(pdf_url),
                "detail_path":   f"/procurement",
            })

    # ── Gmail email attachments: matched by PO number OR supplier email ───────
    from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment as GmailAttachment

    po_numbers = [po.po_number for po in pos if po.po_number]
    gmail_filter = []
    if po_numbers:
        gmail_filter.append(IncomingEmail.matched_po_number.in_(po_numbers))
    if s.email:
        gmail_filter.append(IncomingEmail.from_email == s.email)

    if gmail_filter:
        gmail_atts = (
            db.query(GmailAttachment)
            .join(IncomingEmail, GmailAttachment.incoming_email_id == IncomingEmail.id)
            .filter(or_(*gmail_filter))
            .distinct()
            .all()
        )
        _gmail_type_map = {
            "INVOICE": "INVOICE", "DELIVERY_NOTE": "DELIVERY_NOTE",
            "QUOTE": "QUOTATION", "PURCHASE_ORDER": "PURCHASE_ORDER",
        }
        seen_gmail_ids: set = set()
        for gatt in gmail_atts:
            if gatt.id in seen_gmail_ids:
                continue
            seen_gmail_ids.add(gatt.id)
            doc_type = _gmail_type_map.get(gatt.detected_type, "ATTACHMENT")
            docs.append({
                "doc_id":             str(gatt.id),
                "doc_type":           doc_type,
                "ref_number":         gatt.filename,
                "title":              gatt.filename,
                "date":               gatt.created_at.date().isoformat() if gatt.created_at else None,
                "amount":             None,
                "status":             "Email Attachment",
                "file_url":           None,
                "file_name":          gatt.filename,
                "is_attachment":      True,
                "attachment_type":    "GMAIL",
                "gmail_attachment_id": str(gatt.id),
            })

    raw_atts = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == AttachmentEntity.SUPPLIER,
            Attachment.entity_id == supplier_id,
            Attachment.is_active == True,  # noqa: E712
        )
        .order_by(Attachment.uploaded_at.desc())
        .all()
    )
    uploader_ids = {a.uploaded_by for a in raw_atts if a.uploaded_by}
    user_map: dict = {}
    if uploader_ids:
        for u in db.query(User).filter(User.id.in_(uploader_ids)).all():
            user_map[str(u.id)] = u.full_name

    for att in raw_atts:
        read = AttachmentRead.model_validate(att)
        read.uploaded_by_name = user_map.get(str(att.uploaded_by)) if att.uploaded_by else None
        docs.append({
            "doc_id":           str(att.id),
            "doc_type":         "ATTACHMENT",
            "ref_number":       att.file_name,
            "title":            att.file_name,
            "date":             att.uploaded_at.date().isoformat() if att.uploaded_at else None,
            "amount":           None,
            "status":           None,
            "file_url":         read.download_url,
            "file_name":        att.file_name,
            "is_attachment":    True,
            "attachment_type":  att.attachment_type.value,
            "file_size_display": read.file_size_display,
            "uploaded_by_name": read.uploaded_by_name,
            "is_image":         read.is_image,
            "caption":          att.caption,
            "mime_type":        att.mime_type,
        })

    docs.sort(key=lambda d: (d["date"] or "0000-00-00"), reverse=True)
    return ApiSuccess(data=docs, message=f"{len(docs)} document(s).")


@router.delete(
    "/{supplier_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_supplier(supplier_id: uuid.UUID, db: DbSession):
    """Soft-delete a supplier (set is_active=False). Historical records are preserved."""
    from app.models.supplier import Supplier
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")
    s.is_active = False
    db.commit()
    return ApiSuccess(data={"supplier_id": str(supplier_id), "name": s.name},
                      message=f"Supplier '{s.name}' deactivated.")


@router.delete(
    "/{supplier_id}/permanent",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def permanently_delete_supplier(supplier_id: uuid.UUID, db: DbSession):
    """
    Hard-delete a supplier row from the database.
    Refused if any linked records exist (POs, invoices, deliveries, payments,
    quotations, MR quotes, BOQ items, work-done entries).
    """
    from app.models.supplier import Supplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.invoice import Invoice
    from app.models.delivery import Delivery
    from app.models.payment import Payment
    from app.models.quotation import Quotation
    from app.models.mr_quote import MRQuote
    from app.models.boq import BOQItem
    from app.models.work_done import WorkDone
    from app.models.material_request import MaterialRequest, MRItem

    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found.")

    blocking: list[str] = []

    if db.query(PurchaseOrder.id).filter(PurchaseOrder.supplier_id == supplier_id).first():
        blocking.append("purchase orders")
    if db.query(Invoice.id).filter(Invoice.supplier_id == supplier_id).first():
        blocking.append("invoices")
    if db.query(Delivery.id).filter(Delivery.supplier_id == supplier_id).first():
        blocking.append("deliveries")
    if db.query(Payment.id).filter(Payment.supplier_id == supplier_id).first():
        blocking.append("payments")
    if db.query(Quotation.id).filter(Quotation.supplier_id == supplier_id).first():
        blocking.append("quotations")
    if db.query(MRQuote.id).filter(MRQuote.supplier_id == supplier_id).first():
        blocking.append("MR quotes")
    if db.query(BOQItem.id).filter(BOQItem.supplier_id == supplier_id).first():
        blocking.append("BOQ items")
    if db.query(WorkDone.id).filter(WorkDone.supplier_id == supplier_id).first():
        blocking.append("work-done entries")
    if db.query(MaterialRequest.id).filter(MaterialRequest.preferred_supplier_id == supplier_id).first():
        blocking.append("material requests")

    if blocking:
        raise HTTPException(
            409,
            f"Cannot permanently delete '{s.name}' — linked records exist: "
            + ", ".join(blocking)
            + ". Deactivate the supplier instead.",
        )

    name = s.name
    db.delete(s)
    db.commit()
    return ApiSuccess(data={"supplier_id": str(supplier_id), "name": name},
                      message=f"Supplier '{name}' permanently deleted.")
