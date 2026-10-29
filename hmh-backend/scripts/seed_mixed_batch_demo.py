"""
Seed a twenty-document mixed batch for browser testing.

Builds the shape of a real construction intake — quotations, purchase
orders, pro-formas, tax invoices, a fuel order and a handwritten delivery
note — so the Batch Review screen can be exercised against real endpoints
and the real routing service.

Every name here is fictional. The suppliers, project and document numbers
are invented stand-ins for the real batch, so the seeded database, any
screenshot taken of it and anything committed from it disclose nothing.

What this does and does not prove
---------------------------------
It exercises the routing service, the manifest endpoint and the review UI
against real rows. It does NOT exercise AI extraction: the extractions are
written directly, because a live extraction needs a workspace-scoped
Anthropic key that is still an open blocker. Classification from document
text is covered by the backend suites instead.

    python scripts/seed_mixed_batch_demo.py

Refuses to run against anything but a local database.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal                         # noqa: E402
from app.models.ai_import import (                              # noqa: E402
    AIImportBatch, AIImportDocument, AIImportExtraction,
)
from app.models.enums import (                                   # noqa: E402
    AIImportBatchStatus, AIImportDocumentStatus, AIImportDocumentType as T,
)
from app.models.project import Project                           # noqa: E402
from app.models.supplier import Supplier                         # noqa: E402
from app.models.user import User                                 # noqa: E402


def _now():
    return datetime.now(timezone.utc)


# (file name, type, supplier, reference, total, paid stamp, line description)
DOCUMENTS = [
    ("quote-paints-QU08810220.pdf",    T.QUOTATION,          "Pinnacle Paints",      "QU08810220",        "528.27",   False, "Exterior PVA 20L"),
    ("quote-hardware-66689801.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/70110801",  "31050.38", False, "Assorted fixings"),
    ("quote-hardware-66901001.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/70220901",  "16210.98", False, "Roof sheeting"),
    ("quote-hardware-65845902.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/70330902",  "3516.00",  False, "Door frames"),
    ("quote-timber-1098220.pdf",       T.QUOTATION,          "Timberline Supply",    "1098220",           "4370.56",  False, "Shutter ply 16mm"),

    ("po-005-glazing.pdf",             T.PURCHASE_ORDER,     "Clearview Glazing",    "PO-005",            "2615.40",  False, "Window panes 4mm"),
    ("po-006-steel.pdf",               T.PURCHASE_ORDER,     "Ironworks Trading",    "PO-006",            "9910.82",  False, "Rebar Y12"),
    ("po-007-plumbing.pdf",            T.PURCHASE_ORDER,     "Northgate Plumbing",   "PO-007",            "12260.00", True,  "Soil pipe 110mm"),
    ("po-008-aggregate.pdf",           T.PURCHASE_ORDER,     "Quarryside Aggregates", "PO-008",           "577.32",   False, "Crusher run G5"),
    ("po-009-blocks.pdf",              T.PURCHASE_ORDER,     "Maswell Blocks",       "PO-009",            "14300.00", False, "Maxi brick"),
    ("po-010-pickup.pdf",              T.PURCHASE_ORDER,     "Lakeside Builders Merchant", "PO-1010",      "4120.55",  False, "Cement 42.5N"),
    ("po-011-formwork.pdf",            T.PURCHASE_ORDER,     "Timberline Supply",    "PO-1011",            "6110.00",  False, "Formwork props"),
    # Routed to fuel management by its line items, not by its type.
    ("po-012-diesel.pdf",              T.PURCHASE_ORDER,     "Trackside Fuels",      "PO-112",            "15880.00", False, "500 Litres Diesel 50PPM"),

    ("proforma-merchant-QTE880114.pdf", T.PRO_FORMA_INVOICE, "Lakeside Builders Merchant", "QTE880114",   "4120.50",  True,  "Cement 42.5N"),
    ("proforma-blocks-QTE7410.pdf",    T.PRO_FORMA_INVOICE,  "Maswell Blocks",       "QTE7410",           "14300.00", False, "Maxi brick"),
    ("proforma-readymix-P77120.pdf",   T.PRO_FORMA_INVOICE,  "Vantage Readymix",     "P77120",            "20360.89", False, "25MPa concrete"),
    # Deliberately the same amount as P77120 under a different number: the
    # screen must raise it, not resolve it.
    ("proforma-readymix-P77255.pdf",   T.PRO_FORMA_INVOICE,  "Vantage Readymix",     "P77255",            "20360.89", False, "25MPa concrete"),
    ("proforma-coastal-SQ441020.pdf",  T.PRO_FORMA_INVOICE,  "Coastal Cement",       "SQ441020",          "3990.77",  False, "Cement 32.5N"),

    ("invoice-cement-90220114.pdf",    T.SUPPLIER_INVOICE,   "Coastal Cement",       "90220114",          "3995.03",  False, "Cement 32.5N"),
    ("invoice-aggregate-85956.pdf",    T.SUPPLIER_INVOICE,   "Quarryside Aggregates", "85956",            "577.32",   False, "Crusher run G5"),

    ("delivery-note-0151.pdf",         T.DELIVERY_NOTE,      "Ironworks Trading",    "0151",              None,       False, "Rebar Y12"),
]


def _seed_settled_charge(db, project, suppliers, actor) -> None:
    """
    One pro-forma that has already been superseded by its tax invoice.

    Exists so the Pending Supplier Charges screen can be seen in all three
    of its states rather than only the open one. The reconciliation itself
    is driven by the real service, so what the screen shows is produced the
    same way production would produce it.
    """
    from datetime import date

    from app.models.enums import RecordStatus
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder
    from app.services import provisional_charge_service as charges

    supplier = suppliers["Maswell Blocks"]

    po = PurchaseOrder(
        po_number="PO-DEMO-009", project_id=project.id, supplier_id=supplier.id,
        po_date=date(2026, 8, 10), status=RecordStatus.APPROVED,
        created_by=actor.id, created_at=_now(), updated_at=_now(),
    )
    db.add(po)
    db.flush()

    charge = charges.create_charge(
        db, project_id=project.id, supplier_id=supplier.id,
        reference="QTE5721", total_amount=8140.00, actor_id=actor.id,
        issue_date=date(2026, 8, 11), purchase_order_id=po.id,
        notes="Demo row: already settled, to show the closed state.",
    )

    # The open requests the pro-forma documents in this batch would produce
    # once imported. Created directly so the screen has something to show
    # without the batch having been posted — the two are separate concerns,
    # and a seed that required posting would leave the Batch Review screen
    # with nothing left to review.
    # References deliberately different from the pro-forma documents in the
    # batch. If they matched, those documents would correctly be flagged as
    # duplicates of these rows, and the Batch Review screen would have
    # nothing left to demonstrate.
    for reference, name, amount in (
        ("P88120",   "Vantage Readymix",      20360.89),
        ("P88121",   "Vantage Readymix",      20360.89),
        ("QTE5410",  "Maswell Blocks",        14300.00),
        ("SQ470880", "Coastal Cement",         3990.77),
    ):
        charges.create_charge(
            db, project_id=project.id, supplier_id=suppliers[name].id,
            reference=reference, total_amount=amount, actor_id=actor.id,
            issue_date=date(2026, 8, 14),
            notes="Demo row: an open request awaiting the supplier's invoice.",
        )

    invoice = Invoice(
        invoice_number="MB-44120", supplier_id=supplier.id, project_id=project.id,
        purchase_order_id=po.id, invoice_date=date(2026, 8, 26),
        total_amount=8140.00, status=RecordStatus.DRAFT,
        captured_by=actor.id, captured_at=_now(),
    )
    db.add(invoice)
    db.flush()

    # Through the service, not by setting columns: the closure has to happen
    # the way it happens in production or the screen is showing a fiction.
    settled = charges.find_pending_for_invoice(db, invoice)
    assert settled is not None and settled.id == charge.id
    charges.settle_against_invoice(db, settled, invoice, actor.id)


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        print(f"Refusing to seed: DATABASE_URL is not local ({url[:40]}…).")
        return 1

    db = SessionLocal()
    try:
        actor = db.query(User).order_by(User.created_at.asc()).first()
        if actor is None:
            print("No users. Seed an owner first (scripts/seed_owner.py).")
            return 1

        project = db.query(Project).order_by(Project.created_at.asc()).first()
        if project is None:
            print("No projects. Seed a project first.")
            return 1

        # Suppliers, created only where missing so a re-run is harmless.
        wanted = {name for _, _, name, _, _, _, _ in DOCUMENTS}
        existing = {
            s.name: s for s in db.query(Supplier).filter(Supplier.name.in_(wanted)).all()
        }
        for name in sorted(wanted):
            if name not in existing:
                supplier = Supplier(name=name, is_active=True,
                                    created_at=_now(), updated_at=_now())
                db.add(supplier)
                db.flush()
                existing[name] = supplier

        batch = AIImportBatch(
            reference=f"DEMO-{uuid.uuid4().hex[:6].upper()}",
            project_id=project.id,
            status=AIImportBatchStatus.OPEN,
            notes="Fictional mixed batch for browser testing. No real supplier data.",
            uploaded_by=actor.id,
            created_at=_now(), updated_at=_now(),
        )
        db.add(batch)
        db.flush()

        for file_name, doc_type, supplier_name, reference, total, paid, line in DOCUMENTS:
            document = AIImportDocument(
                batch_id=batch.id,
                file_name=file_name,
                stored_path=f"supabase://ai_import/demo/{uuid.uuid4().hex}.pdf",
                mime_type="application/pdf",
                file_size_bytes=48_000,
                checksum_sha256=uuid.uuid4().hex * 2,
                page_count=1,
                status=AIImportDocumentStatus.AWAITING_REVIEW,
                document_type=doc_type,
                classification_confidence=0.82,
                project_id=project.id,
                # Two documents are deliberately left unlinked, so the screen
                # has something real to ask about.
                supplier_id=(
                    None if supplier_name in ("Lakeside Builders Merchant", "Clearview Glazing")
                    else existing[supplier_name].id
                ),
                payment_evidence_detected=paid,
                payment_evidence_note=(
                    "Payment evidence detected — verification required. The document "
                    "is stamped or marked 'paid'. This is a claim printed on the "
                    "paperwork, not a bank record: nothing has been marked as paid."
                    if paid else None
                ),
                uploaded_by=actor.id,
                created_at=_now(), updated_at=_now(),
            )
            db.add(document)
            db.flush()

            fields = {
                "supplier_name": {"value": supplier_name, "page": 1,
                                  "confidence": 0.88, "source": "text"},
                "document_number": {"value": reference, "page": 1,
                                    "confidence": 0.9, "source": "text"},
                "issue_date": {"value": date(2026, 8, 14).isoformat(), "page": 1,
                               "confidence": 0.8, "source": "text"},
            }
            if total is not None:
                fields["total_amount"] = {"value": total, "page": 1,
                                          "confidence": 0.9, "source": "text"}

            db.add(AIImportExtraction(
                document_id=document.id,
                schema_version="1.0",
                prompt_version="1.1",
                provider="seed",
                extraction_mode="text",
                fields=fields,
                line_items=[{
                    "description": line, "quantity": "1", "unit": "ea",
                    "unit_price": total, "line_total": total,
                    "page": 1, "confidence": 0.75,
                }],
                arithmetic_checks=[],
                warnings=[],
                overall_confidence=0.85,
                is_current=True,
                created_at=_now(),
            ))

        db.flush()
        _seed_settled_charge(db, project, existing, actor)

        db.commit()
        print(f"Seeded batch {batch.reference} with {len(DOCUMENTS)} documents "
              f"on project {project.name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
