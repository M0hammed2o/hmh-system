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
    ("quote-paints-QU07029334.pdf",    T.QUOTATION,          "Pinnacle Paints",      "QU07029334",        "453.27",   False, "Exterior PVA 20L"),
    ("quote-hardware-66689801.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/66689801",  "26600.38", False, "Assorted fixings"),
    ("quote-hardware-66901001.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/66901001",  "13884.98", False, "Roof sheeting"),
    ("quote-hardware-65845902.pdf",    T.QUOTATION,          "Riverside Hardware",   "BR1-QUT/65845902",  "3012.00",  False, "Door frames"),
    ("quote-timber-1047739.pdf",       T.QUOTATION,          "Timberline Supply",    "1047739",           "3742.56",  False, "Shutter ply 16mm"),

    ("po-005-glazing.pdf",             T.PURCHASE_ORDER,     "Clearview Glazing",    "PO-005",            "2242.40",  False, "Window panes 4mm"),
    ("po-006-steel.pdf",               T.PURCHASE_ORDER,     "Ironworks Trading",    "PO-006",            "8484.82",  False, "Rebar Y12"),
    ("po-007-plumbing.pdf",            T.PURCHASE_ORDER,     "Northgate Plumbing",   "PO-007",            "10500.00", True,  "Soil pipe 110mm"),
    ("po-008-aggregate.pdf",           T.PURCHASE_ORDER,     "Quarryside Aggregates", "PO-008",           "494.32",   False, "Crusher run G5"),
    ("po-009-blocks.pdf",              T.PURCHASE_ORDER,     "Maswell Blocks",       "PO-009",            "12254.00", False, "Maxi brick"),
    ("po-010-pickup.pdf",              T.PURCHASE_ORDER,     "Lakeside Builders Merchant", "PO-010",      "3699.55",  False, "Cement 42.5N"),
    ("po-011-formwork.pdf",            T.PURCHASE_ORDER,     "Timberline Supply",    "PO-011",            "6110.00",  False, "Formwork props"),
    # Routed to fuel management by its line items, not by its type.
    ("po-012-diesel.pdf",              T.PURCHASE_ORDER,     "Trackside Fuels",      "PO-012",            "13575.00", False, "500 Litres Diesel 50PPM"),

    ("proforma-merchant-QTE254210.pdf", T.PRO_FORMA_INVOICE, "Lakeside Builders Merchant", "QTE254210",   "3699.50",  True,  "Cement 42.5N"),
    ("proforma-blocks-QTE5895.pdf",    T.PRO_FORMA_INVOICE,  "Maswell Blocks",       "QTE5895",           "12254.00", False, "Maxi brick"),
    ("proforma-readymix-P89250.pdf",   T.PRO_FORMA_INVOICE,  "Vantage Readymix",     "P89250",            "17444.89", False, "25MPa concrete"),
    # Deliberately the same amount as P89250 under a different number: the
    # screen must raise it, not resolve it.
    ("proforma-readymix-P89381.pdf",   T.PRO_FORMA_INVOICE,  "Vantage Readymix",     "P89381",            "17444.89", False, "25MPa concrete"),
    ("proforma-coastal-SQ473889.pdf",  T.PRO_FORMA_INVOICE,  "Coastal Cement",       "SQ473889",          "3407.77",  False, "Cement 32.5N"),

    ("invoice-cement-91515003.pdf",    T.SUPPLIER_INVOICE,   "Coastal Cement",       "91515003",          "3412.03",  False, "Cement 32.5N"),
    ("invoice-aggregate-85956.pdf",    T.SUPPLIER_INVOICE,   "Quarryside Aggregates", "85956",            "494.32",   False, "Crusher run G5"),

    ("delivery-note-0084.pdf",         T.DELIVERY_NOTE,      "Ironworks Trading",    "0084",              None,       False, "Rebar Y12"),
]


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

        db.commit()
        print(f"Seeded batch {batch.reference} with {len(DOCUMENTS)} documents "
              f"on project {project.name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
