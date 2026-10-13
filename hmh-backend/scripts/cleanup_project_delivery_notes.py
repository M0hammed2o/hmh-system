"""
Delivery-note cleanup for one project.

Built for the Dassenhoek duplication, but takes any project so it is not a
one-off script that rots. It reports what exists, classifies each delivery
note, and — only when told to — reverses the stock it posted and archives
the note.

DRY RUN BY DEFAULT. Nothing is changed unless --apply is passed, and
--apply additionally requires --i-have-a-backup.

What it will never do:
  * delete anything. Stock is reversed by writing a contra ledger entry,
    never by removing history; notes are archived, never dropped.
  * touch invoices, purchase orders or payments.
  * touch any project other than the one named.

    python scripts/cleanup_project_delivery_notes.py --project-id <uuid>
    python scripts/cleanup_project_delivery_notes.py --project-id <uuid> --json
    python scripts/cleanup_project_delivery_notes.py --project-id <uuid> \\
        --apply --i-have-a-backup --actor-email you@hmhgroup.co.za
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.enums import AuditAction, MovementType, RecordStatus   # noqa: E402


def _now():
    return datetime.now(timezone.utc)


# ── Classification ────────────────────────────────────────────────────────────

DUPLICATE_OF_NOTE = "DUPLICATE_NOTE_NUMBER"
DUPLICATE_LEDGER = "DUPLICATE_STOCK_POSTING"
GENUINE = "GENUINE"


def classify(db, project_id: uuid.UUID) -> dict:
    """
    Describe every delivery note on the project and say which are duplicates.

    Two independent duplicate signals, because they have different causes:

      * the same supplier delivery-note number recorded more than once for
        one supplier — a re-submitted or re-imported note;
      * more than one DELIVERY_RECEIVED ledger row for a single delivery —
        a double stock posting, whatever the note number says.

    The earliest note of a duplicate set is treated as genuine and kept; the
    later ones are the candidates for reversal.
    """
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.invoice import Invoice
    from app.models.project import Project
    from app.models.purchase_order import PurchaseOrder
    from app.models.site import Site
    from app.models.stock import StockLedger
    from app.models.supplier import Supplier

    project = db.get(Project, project_id)
    if project is None:
        raise SystemExit(f"No project with id {project_id}. Refusing to continue.")

    deliveries = (
        db.query(Delivery)
        .filter(Delivery.project_id == project_id)
        .order_by(Delivery.delivery_date.asc(), Delivery.created_at.asc())
        .all()
    )

    # Group by (supplier, note number) to find re-submitted notes.
    by_note: dict = defaultdict(list)
    for d in deliveries:
        number = (d.supplier_delivery_note_number or "").strip().upper()
        if number:
            by_note[(d.supplier_id, number)].append(d)

    rows: list[dict] = []
    for d in deliveries:
        # Both the delivery's own movements and any reversal already written
        # against it — a reversal carries the same reference_id, which is what
        # makes a second run a no-op rather than a second reversal.
        ledger = (
            db.query(StockLedger)
            .filter(
                StockLedger.reference_type.in_(["delivery", "delivery_reversal"]),
                StockLedger.reference_id == d.id,
            )
            .all()
        )
        received = [
            r for r in ledger
            if r.reference_type == "delivery"
            and r.movement_type == MovementType.DELIVERY_RECEIVED
        ]
        reversals = [r for r in ledger if r.reference_type == "delivery_reversal"]

        # Did this one delivery post stock more than once for the same item?
        per_item: dict = defaultdict(int)
        for r in received:
            per_item[r.item_id] += 1
        double_posted = {str(k): v for k, v in per_item.items() if v > 1}

        number = (d.supplier_delivery_note_number or "").strip().upper()
        siblings = by_note.get((d.supplier_id, number), []) if number else []
        is_later_duplicate = bool(number) and len(siblings) > 1 and siblings[0].id != d.id

        if is_later_duplicate:
            verdict, reason = DUPLICATE_OF_NOTE, (
                f"delivery note {number} from this supplier was already recorded as "
                f"{siblings[0].id}"
            )
        elif double_posted:
            verdict, reason = DUPLICATE_LEDGER, (
                f"{sum(double_posted.values())} stock movements for "
                f"{len(double_posted)} item(s) on one delivery"
            )
        else:
            verdict, reason = GENUINE, "no duplicate signal"

        supplier = db.get(Supplier, d.supplier_id) if d.supplier_id else None
        site = db.get(Site, d.site_id) if d.site_id else None
        po = db.get(PurchaseOrder, d.purchase_order_id) if d.purchase_order_id else None

        linked_invoices = []
        if po is not None:
            linked_invoices = [
                {"id": str(i.id), "invoice_number": i.invoice_number,
                 "total": float(i.total_amount or 0), "status": str(i.status)}
                for i in db.query(Invoice).filter(Invoice.purchase_order_id == po.id).all()
            ]

        boq_item_ids = sorted({str(r.boq_item_id) for r in ledger if r.boq_item_id})
        items = db.query(DeliveryItem).filter(DeliveryItem.delivery_id == d.id).all()

        rows.append({
            "delivery_id": str(d.id),
            "delivery_number": d.delivery_number,
            "supplier_note_number": d.supplier_delivery_note_number,
            "date": d.delivery_date.isoformat() if d.delivery_date else None,
            "supplier": supplier.name if supplier else None,
            "supplier_id": str(d.supplier_id) if d.supplier_id else None,
            "site": site.name if site else None,
            "site_id": str(d.site_id) if d.site_id else None,
            "status": str(d.delivery_status),
            "purchase_order": po.po_number if po else None,
            "purchase_order_id": str(po.id) if po else None,
            "line_count": len(items),
            "stock_movements": len(received),
            "already_reversed": len(reversals),
            "stock_in_total": round(sum(float(r.quantity_in or 0) for r in received), 3),
            "double_posted_items": double_posted,
            "boq_items_touched": boq_item_ids,
            "linked_invoices": linked_invoices,
            "verdict": verdict,
            "reason": reason,
            # Reversing a receipt that an invoice has already been raised
            # against changes what the paperwork says was delivered. Flag it
            # rather than deciding.
            "needs_human_decision": bool(linked_invoices) and verdict != GENUINE,
        })

    return {
        "project_id": str(project_id),
        "project_name": project.name,
        "project_code": getattr(project, "code", None),
        "generated_at": _now().isoformat(),
        "delivery_notes": rows,
        "totals": {
            "delivery_notes": len(rows),
            "genuine": sum(1 for r in rows if r["verdict"] == GENUINE),
            "duplicate_note_number": sum(1 for r in rows if r["verdict"] == DUPLICATE_OF_NOTE),
            "duplicate_stock_posting": sum(1 for r in rows if r["verdict"] == DUPLICATE_LEDGER),
            "needing_human_decision": sum(1 for r in rows if r["needs_human_decision"]),
            "stock_in_total": round(sum(r["stock_in_total"] for r in rows), 3),
            "stock_in_from_duplicates": round(
                sum(r["stock_in_total"] for r in rows if r["verdict"] != GENUINE), 3
            ),
        },
    }


# ── Cleanup ───────────────────────────────────────────────────────────────────

def plan(report: dict) -> list[dict]:
    """The exact changes --apply would make. Pure: touches nothing."""
    actions = []
    for row in report["delivery_notes"]:
        if row["verdict"] == GENUINE:
            continue
        if row["needs_human_decision"]:
            actions.append({
                "delivery_id": row["delivery_id"],
                "action": "SKIP",
                "detail": (
                    f"an invoice exists against {row['purchase_order']}; reversing this "
                    f"receipt changes what the paperwork says was delivered. Decide by hand."
                ),
            })
            continue
        if row["already_reversed"]:
            actions.append({
                "delivery_id": row["delivery_id"],
                "action": "SKIP",
                "detail": "already reversed",
            })
            continue
        actions.append({
            "delivery_id": row["delivery_id"],
            "action": "REVERSE_AND_ARCHIVE",
            "detail": (
                f"write {row['stock_movements']} contra stock entr(y/ies) totalling "
                f"-{row['stock_in_total']}, then set the delivery to CANCELLED"
            ),
            "stock_to_reverse": row["stock_in_total"],
        })
    return actions


def apply_cleanup(db, project_id: uuid.UUID, report: dict, actor_id, note: str) -> dict:
    """
    Execute the plan. Only called with --apply --i-have-a-backup.

    Stock is reversed by writing compensating entries, never by deleting
    ledger rows: the ledger is the audit trail and must keep showing that
    the mistake happened and was corrected.
    """
    from app.models.delivery import Delivery
    from app.models.stock import StockLedger
    from app.services import audit_service

    done, skipped = [], []
    for action in plan(report):
        if action["action"] == "SKIP":
            skipped.append(action)
            continue

        delivery_id = uuid.UUID(action["delivery_id"])
        delivery = db.get(Delivery, delivery_id)
        if delivery is None or delivery.project_id != project_id:
            skipped.append({**action, "detail": "not found in this project"})
            continue

        received = (
            db.query(StockLedger)
            .filter(
                StockLedger.reference_type == "delivery",
                StockLedger.reference_id == delivery_id,
                StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
            )
            .all()
        )
        for row in received:
            # A contra-entry: same movement type, negative quantity_in. Not an
            # ADJUSTMENT_SUBTRACT, which would be wrong twice over — stock on
            # hand is SUM(quantity_in) - SUM(quantity_out) everywhere, so either
            # form nets correctly there, but the lot material summary reads
            # delivered as SUM(quantity_in) WHERE movement_type IN
            # (DELIVERY_RECEIVED, TRANSFER_IN) and used as SUM(quantity_out)
            # with no movement-type filter at all. A quantity_out adjustment
            # would therefore leave the BOQ delivered figure overstated and
            # silently inflate the used figure instead. The contra-entry
            # reverses exactly the aggregate the duplicate inflated.
            db.add(StockLedger(
                project_id=row.project_id,
                site_id=row.site_id,
                lot_id=row.lot_id,
                item_id=row.item_id,
                boq_item_id=row.boq_item_id,
                movement_type=row.movement_type,
                reference_type="delivery_reversal",
                reference_id=delivery_id,
                quantity_in=-(row.quantity_in or 0),
                quantity_out=0,
                unit=row.unit,
                unit_cost=row.unit_cost,
                movement_date=_now(),
                entered_by=actor_id,
                notes=f"Reversal of duplicate delivery {delivery.delivery_number}: {note}",
                created_at=_now(),
            ))

        delivery.delivery_status = RecordStatus.CANCELLED
        delivery.comments = (
            f"{delivery.comments or ''}\n[CLEANUP {_now().date().isoformat()}] "
            f"Archived as a duplicate. Stock reversed. {note}"
        ).strip()

        audit_service.write_event(
            db, AuditAction.UPDATE, "delivery_cleanup", actor_id, delivery_id,
            after_value={
                "reversed_movements": len(received),
                "quantity_reversed": float(sum(r.quantity_in or 0 for r in received)),
                "verdict": next(
                    r["verdict"] for r in report["delivery_notes"]
                    if r["delivery_id"] == action["delivery_id"]
                ),
                "note": note,
            },
            notes="Duplicate delivery note archived and its stock reversed.",
        )
        done.append(action)

    db.commit()
    return {"reversed": done, "skipped": skipped}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-id", required=True, help="verified project UUID")
    ap.add_argument("--apply", action="store_true", help="make the changes")
    ap.add_argument("--i-have-a-backup", action="store_true",
                    help="required with --apply; confirms a restore point exists")
    ap.add_argument("--actor-email", help="who is running this (required with --apply)")
    ap.add_argument("--note", default="Duplicate delivery-note cleanup")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    try:
        project_id = uuid.UUID(args.project_id)
    except ValueError:
        print(f"'{args.project_id}' is not a UUID.")
        return 2

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        report = classify(db, project_id)
        actions = plan(report)

        if args.json:
            print(json.dumps({"report": report, "plan": actions}, indent=2))
        else:
            t = report["totals"]
            print(f"\nProject: {report['project_name']} ({report['project_code']})")
            print(f"  delivery notes            {t['delivery_notes']}")
            print(f"  genuine                   {t['genuine']}")
            print(f"  duplicate note number     {t['duplicate_note_number']}")
            print(f"  duplicate stock posting   {t['duplicate_stock_posting']}")
            print(f"  needing a human decision  {t['needing_human_decision']}")
            print(f"  stock received, total     {t['stock_in_total']}")
            print(f"  of which from duplicates  {t['stock_in_from_duplicates']}")
            print(f"\nPlanned actions ({len(actions)}):")
            for a in actions:
                print(f"  {a['action']:20} {a['delivery_id']}  {a['detail']}")
            if not actions:
                print("  none — nothing to clean up")

        if not args.apply:
            print("\nDRY RUN. Nothing was changed.")
            print("To execute: --apply --i-have-a-backup --actor-email <you>")
            return 0

        if not args.i_have_a_backup:
            print("\nRefusing to apply without --i-have-a-backup.")
            print("Take a database snapshot first; this writes compensating stock entries.")
            return 2
        if not args.actor_email:
            print("\nRefusing to apply without --actor-email: the audit trail needs an actor.")
            return 2

        from app.models.user import User
        actor = db.query(User).filter(User.email == args.actor_email).first()
        if actor is None:
            print(f"\nNo user with email {args.actor_email}.")
            return 2

        result = apply_cleanup(db, project_id, report, actor.id, args.note)
        print(f"\nAPPLIED. Reversed {len(result['reversed'])}, skipped {len(result['skipped'])}.")
        for s in result["skipped"]:
            print(f"  SKIPPED {s['delivery_id']}: {s['detail']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
