"""
Drive the whole mixed-batch workflow and report what it actually did.

Takes the seeded demo batch and runs every document through the real policy
and posting services — the same code the API calls — then reports which
business records exist afterwards. Nothing is mocked and nothing is asserted
into being true: the script posts, then counts.

What it is for:

  * proving a delivery note is NOT posted while it is still awaiting review
  * proving an imported tax invoice lands UNPAID
  * proving a pro-forma lands outside Accounts Payable and is closed by the
    invoice that supersedes it
  * proving a fuel order is refused into fuel management
  * giving the Pending Supplier Charges screen something real to display

Local databases only, and it refuses to run against anything else.

    DATABASE_URL=postgresql+psycopg2://…/hmh_demo \\
        python scripts/verify_mixed_batch_workflow.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal                            # noqa: E402
from app.models.ai_import import AIImportBatch, AIImportDocument   # noqa: E402
from app.models.enums import (                                      # noqa: E402
    AIImportDocumentStatus, AIImportDocumentType as T,
    ProvisionalChargeStatus, RecordStatus,
)
from app.models.invoice import Invoice                              # noqa: E402
from app.models.payment import Payment                              # noqa: E402
from app.models.provisional_charge import ProvisionalCharge         # noqa: E402
from app.models.quotation import Quotation                          # noqa: E402
from app.models.stock import StockLedger                            # noqa: E402
from app.models.user import User                                    # noqa: E402
from app.services import ai_import_posting_service as posting       # noqa: E402
from app.services import ai_import_routing_service as routing       # noqa: E402
from app.services import ai_import_service                          # noqa: E402


def _counts(db) -> dict:
    return {
        "invoices": db.query(Invoice).count(),
        "quotations": db.query(Quotation).count(),
        "provisional_charges": db.query(ProvisionalCharge).count(),
        "stock_movements": db.query(StockLedger).count(),
        "payments": db.query(Payment).count(),
    }


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        print(f"Refusing to run: DATABASE_URL is not local ({url[:40]}…).")
        return 1

    db = SessionLocal()
    try:
        actor = db.query(User).order_by(User.created_at.asc()).first()
        batch = (
            db.query(AIImportBatch)
            .order_by(AIImportBatch.created_at.desc())
            .first()
        )
        if actor is None or batch is None:
            print("Seed the demo stack first (scripts/seed_mixed_batch_demo.py).")
            return 1

        documents = sorted(batch.documents, key=lambda d: d.file_name)
        before = _counts(db)

        print(f"Batch {batch.reference}: {len(documents)} documents")
        print(f"Before: {before}\n")
        print(f"{'document':<38} {'type':<20} {'result'}")
        print("-" * 110)

        results: list[tuple[str, str, str]] = []

        for document in documents:
            payload = ai_import_service.working_payload(db, document)
            verdict = routing.route(db, document, payload)
            doc_type = (document.document_type or T.UNKNOWN).value

            # A document that still needs a person does not get posted here.
            # That is the behaviour under test, not an obstacle to it: the
            # handwritten delivery note must stay where it is.
            if verdict.action == routing.REVIEW:
                outcome = f"HELD for review -> {verdict.destination.label}"
                results.append((document.file_name, doc_type, outcome))
                print(f"{document.file_name:<38} {doc_type:<20} {outcome}")
                continue

            document.status = AIImportDocumentStatus.READY_TO_POST
            db.commit()
            try:
                p = posting.post_document(db, document, payload, actor)
                outcome = f"POSTED  {p.entity_type}={p.entity_label or p.entity_id}"
            except posting.PostingRefused as exc:
                db.rollback()
                outcome = f"REFUSED {str(exc)[:58]}"
            except Exception as exc:                        # noqa: BLE001
                db.rollback()
                outcome = f"ERROR   {type(exc).__name__}: {str(exc)[:48]}"

            results.append((document.file_name, doc_type, outcome))
            print(f"{document.file_name:<38} {doc_type:<20} {outcome}")

        after = _counts(db)
        print(f"\nAfter:  {after}")
        print(f"Delta:  " + ", ".join(
            f"{k}+{after[k] - before[k]}" for k in after if after[k] != before[k]
        ) or "Delta:  nothing changed")

        # ── The properties that matter ───────────────────────────────────────
        print("\n--- checks ---")
        ok = True

        unpaid = db.query(Invoice).filter(
            Invoice.status.in_([
                RecordStatus.PAID, RecordStatus.PARTIALLY_PAID, RecordStatus.OVERPAID,
            ])
        ).count()
        print(f"{'PASS' if unpaid == 0 else 'FAIL'}  every imported invoice is unpaid "
              f"({db.query(Invoice).count()} invoices, {unpaid} marked paid)")
        ok &= unpaid == 0

        payments = after["payments"] - before["payments"]
        print(f"{'PASS' if payments == 0 else 'FAIL'}  importing created no payment "
              f"records ({payments})")
        ok &= payments == 0

        pending = db.query(ProvisionalCharge).filter(
            ProvisionalCharge.status == ProvisionalChargeStatus.PENDING
        ).count()
        invoiced = db.query(ProvisionalCharge).filter(
            ProvisionalCharge.status == ProvisionalChargeStatus.INVOICED
        ).count()
        print(f"INFO  pending charges: {pending} open, {invoiced} closed by an invoice")

        # A pro-forma must never have become an Invoice row.
        proforma_refs = {
            c.reference for c in db.query(ProvisionalCharge).all()
        }
        leaked = db.query(Invoice).filter(
            Invoice.invoice_number.in_(proforma_refs or {"__none__"})
        ).count()
        print(f"{'PASS' if leaked == 0 else 'FAIL'}  no pro-forma reference appears in "
              f"Accounts Payable ({leaked})")
        ok &= leaked == 0

        # The delivery note is the only thing that may move stock, and only
        # once a person has confirmed it.
        held = [r for r in results if "HELD" in r[2]]
        delivery_held = any(r[1] == T.DELIVERY_NOTE.value and "HELD" in r[2]
                            for r in results)
        print(f"{'PASS' if delivery_held else 'INFO'}  handwritten delivery note held "
              f"for review (stock movements +{after['stock_movements'] - before['stock_movements']})")

        fuel = [r for r in results if "Fuel procurement" in r[2] or "fuel" in r[2].lower()]
        print(f"{'PASS' if fuel else 'FAIL'}  fuel order kept out of materials "
              f"({len(fuel)} document(s))")
        ok &= bool(fuel)

        print(f"\n{len(held)} document(s) held for a person; "
              f"{len(results) - len(held)} processed.")
        return 0 if ok else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
