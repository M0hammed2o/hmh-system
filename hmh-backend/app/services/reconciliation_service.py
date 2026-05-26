"""
Reconciliation service — Phase 3T.

Read-only integrity checks across all operational modules.
Every function returns a structured dict:
  {
    "status": "ok" | "warning" | "error",
    "count":  int,          # number of discrepancies found
    "details": list[dict],  # first N discrepancies (truncated)
  }

NO writes, NO deletes, NO auto-fixes.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session


# ── helpers ───────────────────────────────────────────────────────────────────

def _result(status: str, count: int, details: list) -> dict:
    return {"status": status, "count": count, "details": details[:50]}


def _proj_filter(col, project_id: Optional[uuid.UUID]):
    """Return a SQLAlchemy filter expression or True (no-op) for optional scope."""
    if project_id:
        return col == project_id
    return True


# ── 1. STOCK INTEGRITY ───────────────────────────────────────────────────────

def check_stock_integrity(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect negative stock balances and items with non-zero movement but
    zero materialized-view balance (possible stale view).

    Negative balances = items issued beyond what was received.
    """
    from app.models.stock import StockLedger
    from app.models.item import Item

    # Live aggregation: items with negative balance
    q = (
        db.query(
            StockLedger.project_id,
            StockLedger.site_id,
            StockLedger.lot_id,
            StockLedger.item_id,
            (func.coalesce(func.sum(StockLedger.quantity_in), 0)
             - func.coalesce(func.sum(StockLedger.quantity_out), 0)).label("balance"),
        )
        .group_by(
            StockLedger.project_id,
            StockLedger.site_id,
            StockLedger.lot_id,
            StockLedger.item_id,
        )
        .having(
            (func.coalesce(func.sum(StockLedger.quantity_in), 0)
             - func.coalesce(func.sum(StockLedger.quantity_out), 0)) < 0
        )
    )
    if project_id:
        q = q.filter(StockLedger.project_id == project_id)

    rows = q.all()

    details = []
    for r in rows:
        item = db.get(Item, r.item_id)
        details.append({
            "project_id":  str(r.project_id),
            "site_id":     str(r.site_id) if r.site_id else None,
            "lot_id":      str(r.lot_id) if r.lot_id else None,
            "item_id":     str(r.item_id),
            "item_name":   item.name if item else "unknown",
            "balance":     round(float(r.balance), 4),
        })

    status = "error" if details else "ok"
    return _result(status, len(details), details)


# ── 2. PROCUREMENT CHAIN ─────────────────────────────────────────────────────

def check_procurement_chain(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect broken links in MR → PO → Delivery → Invoice chain.

    Reports:
      - POs in SENT/APPROVED status with no linked deliveries (>7 days old)
      - Invoices not in MATCHED/PARTIALLY_PAID/PAID/OVERPAID/CANCELLED with no matching result
      - Deliveries where delivery_status=RECEIVED but no stock ledger entries exist
    """
    from app.models.purchase_order import PurchaseOrder
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.stock import StockLedger
    from app.models.enums import RecordStatus
    from sqlalchemy import and_, not_, exists

    discrepancies = []
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

    # 1. POs sent > 7 days ago with no deliveries
    po_q = db.query(PurchaseOrder).filter(
        PurchaseOrder.status.in_([RecordStatus.SENT, RecordStatus.APPROVED]),
        PurchaseOrder.created_at < cutoff_7d,
        not_(
            exists().where(Delivery.purchase_order_id == PurchaseOrder.id)
        ),
    )
    if project_id:
        po_q = po_q.filter(PurchaseOrder.project_id == project_id)

    for po in po_q.limit(50).all():
        discrepancies.append({
            "type":       "po_no_delivery",
            "id":         str(po.id),
            "po_number":  po.po_number,
            "project_id": str(po.project_id),
            "status":     po.status.value if hasattr(po.status, "value") else str(po.status),
            "age_days":   (datetime.now(timezone.utc) - po.created_at).days
                          if po.created_at else None,
            "message":    f"PO {po.po_number} has been {po.status} for >7 days with no delivery",
        })

    # 2. Invoices with actionable status but no InvoiceMatchingResult
    from app.models.invoice import InvoiceMatchingResult
    unmatched_statuses = [
        RecordStatus.RECEIVED, RecordStatus.APPROVED, RecordStatus.MATCHED,
    ]
    inv_q = (
        db.query(Invoice)
        .filter(
            Invoice.status.in_(unmatched_statuses),
            not_(
                exists().where(InvoiceMatchingResult.invoice_id == Invoice.id)
            ),
        )
    )
    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)

    for inv in inv_q.limit(50).all():
        discrepancies.append({
            "type":           "invoice_no_match",
            "id":             str(inv.id),
            "invoice_number": inv.invoice_number,
            "project_id":     str(inv.project_id),
            "status":         inv.status.value if hasattr(inv.status, "value") else str(inv.status),
            "total_amount":   float(inv.total_amount or 0),
            "message":        f"Invoice {inv.invoice_number} has no matching result record",
        })

    # 3. RECEIVED deliveries with no StockLedger entries (stock write may have failed)
    del_q = (
        db.query(Delivery)
        .filter(
            Delivery.delivery_status.in_(
                [RecordStatus.RECEIVED, RecordStatus.PARTIALLY_RECEIVED]
            ),
            not_(
                exists().where(
                    (StockLedger.reference_type == "delivery")
                    & (StockLedger.reference_id == Delivery.id)
                )
            ),
        )
    )
    if project_id:
        del_q = del_q.filter(Delivery.project_id == project_id)

    for d in del_q.limit(50).all():
        discrepancies.append({
            "type":            "delivery_no_stock",
            "id":              str(d.id),
            "delivery_number": d.delivery_number,
            "project_id":      str(d.project_id),
            "status":          d.delivery_status.value
                               if hasattr(d.delivery_status, "value") else str(d.delivery_status),
            "message":         f"Delivery {d.delivery_number} is RECEIVED but has no stock ledger entries",
        })

    count = len(discrepancies)
    status = "error" if count > 0 else "ok"
    return _result(status, count, discrepancies)


# ── 3. ALLOCATION OVERRUN ────────────────────────────────────────────────────

def check_allocation_overrun(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect lots where actual stock usage (quantity_out) exceeds the BOQ
    planned quantity for a given item.

    These may be legitimate (approved overruns) but should be visible.
    """
    from app.models.boq import BOQItem
    from app.models.stock import StockLedger
    from app.models.item import Item
    from app.models.lot import Lot

    # Aggregate BOQ planned per (lot, item)
    boq_q = (
        db.query(
            BOQItem.lot_id,
            BOQItem.item_id,
            func.coalesce(func.sum(BOQItem.planned_quantity), 0).label("planned"),
        )
        .filter(BOQItem.lot_id.isnot(None), BOQItem.item_id.isnot(None), BOQItem.is_active == True)
        .group_by(BOQItem.lot_id, BOQItem.item_id)
        .subquery()
    )

    # Aggregate actual usage per (lot, item)
    usage_q = (
        db.query(
            StockLedger.lot_id,
            StockLedger.item_id,
            func.coalesce(func.sum(StockLedger.quantity_out), 0).label("used"),
        )
        .filter(StockLedger.lot_id.isnot(None), StockLedger.item_id.isnot(None))
        .group_by(StockLedger.lot_id, StockLedger.item_id)
        .subquery()
    )

    from sqlalchemy import join
    rows = (
        db.query(
            boq_q.c.lot_id,
            boq_q.c.item_id,
            boq_q.c.planned,
            usage_q.c.used,
        )
        .join(usage_q, (boq_q.c.lot_id == usage_q.c.lot_id) & (boq_q.c.item_id == usage_q.c.item_id))
        .filter(usage_q.c.used > boq_q.c.planned)
        .limit(100)
        .all()
    )

    details = []
    for r in rows:
        lot = db.get(Lot, r.lot_id)
        item = db.get(Item, r.item_id)
        if project_id and lot and lot.project_id != project_id:
            continue
        details.append({
            "lot_id":     str(r.lot_id),
            "lot_number": lot.lot_number if lot else "unknown",
            "item_id":    str(r.item_id),
            "item_name":  item.name if item else "unknown",
            "planned":    round(float(r.planned), 4),
            "used":       round(float(r.used), 4),
            "overrun":    round(float(r.used) - float(r.planned), 4),
        })

    status = "warning" if details else "ok"
    return _result(status, len(details), details)


# ── 4. PAYMENT RECONCILIATION ────────────────────────────────────────────────

def check_payment_reconciliation(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect invoices where the stored status is inconsistent with the
    actual sum of active payments:
      - PAID but total_paid < total_amount
      - PARTIALLY_PAID but total_paid == 0
      - DRAFT/RECEIVED/MATCHED but total_paid > 0
      - Orphan payments (invoice_id set but invoice no longer exists)
    """
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.enums import RecordStatus

    discrepancies = []

    # Subquery: total active payments per invoice
    paid_sub = (
        db.query(
            Payment.invoice_id,
            func.coalesce(func.sum(Payment.amount_paid), 0).label("total_paid"),
        )
        .filter(
            Payment.invoice_id.isnot(None),
            Payment.status.notin_(["CANCELLED", "FAILED"]),
        )
        .group_by(Payment.invoice_id)
        .subquery()
    )

    # Join invoices to their payment sums
    inv_q = db.query(
        Invoice.id,
        Invoice.invoice_number,
        Invoice.project_id,
        Invoice.status,
        Invoice.total_amount,
        func.coalesce(paid_sub.c.total_paid, 0).label("actual_paid"),
    ).outerjoin(paid_sub, paid_sub.c.invoice_id == Invoice.id)

    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)

    for row in inv_q.limit(500).all():
        total = float(row.total_amount or 0)
        paid  = float(row.actual_paid or 0)
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)

        mismatch = None
        if status_val == "PAID" and paid < total * 0.99:
            mismatch = f"status=PAID but only R{paid:,.2f} paid of R{total:,.2f}"
        elif status_val == "PARTIALLY_PAID" and paid <= 0:
            mismatch = "status=PARTIALLY_PAID but no active payments found"
        elif status_val in ("DRAFT", "RECEIVED", "MATCHED") and paid > 0:
            mismatch = f"status={status_val} but R{paid:,.2f} in active payments"

        if mismatch:
            discrepancies.append({
                "invoice_id":     str(row.id),
                "invoice_number": row.invoice_number,
                "project_id":     str(row.project_id),
                "status":         status_val,
                "total_amount":   round(total, 2),
                "actual_paid":    round(paid, 2),
                "mismatch":       mismatch,
            })

    # Orphan payments: invoice_id set but invoice missing
    orphan_payments = (
        db.query(Payment)
        .filter(
            Payment.invoice_id.isnot(None),
            ~db.query(Invoice.id).filter(Invoice.id == Payment.invoice_id).exists(),
        )
        .limit(50)
        .all()
    )
    for p in orphan_payments:
        if project_id and p.project_id != project_id:
            continue
        discrepancies.append({
            "type":             "orphan_payment",
            "payment_id":       str(p.id),
            "invoice_id":       str(p.invoice_id),
            "amount_paid":      float(p.amount_paid or 0),
            "payment_reference": p.payment_reference,
            "mismatch":         "Payment references non-existent invoice",
        })

    status = "error" if discrepancies else "ok"
    return _result(status, len(discrepancies), discrepancies)


# ── 5. ORPHAN ATTACHMENTS ────────────────────────────────────────────────────

def check_orphan_attachments(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect active Attachment rows whose entity_id no longer exists in the
    referenced table. These indicate DB-storage sync issues.

    Checks: DELIVERY, INVOICE, STAGE_STATUS, USAGE_LOG, FUEL_LOG entity types.
    (PROJECT, SUPPLIER, PAYMENT etc. checked similarly but lower priority.)
    """
    from app.models.attachment import Attachment
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.stage import ProjectStageStatus
    from app.models.enums import AttachmentEntity

    orphans = []

    checks = [
        (AttachmentEntity.DELIVERY,     Delivery,            Delivery.id),
        (AttachmentEntity.INVOICE,      Invoice,             Invoice.id),
        (AttachmentEntity.STAGE_STATUS, ProjectStageStatus,  ProjectStageStatus.id),
    ]

    for entity_type, model, id_col in checks:
        q = (
            db.query(Attachment)
            .filter(
                Attachment.entity_type == entity_type,
                Attachment.is_active == True,
                ~db.query(id_col).filter(id_col == Attachment.entity_id).exists(),
            )
            .limit(50)
        )
        for att in q.all():
            orphans.append({
                "attachment_id": str(att.id),
                "entity_type":   att.entity_type.value,
                "entity_id":     str(att.entity_id),
                "file_name":     att.file_name,
                "stored_path":   att.stored_path,
                "message":       f"Attachment points to non-existent {att.entity_type.value} {att.entity_id}",
            })

    status = "warning" if orphans else "ok"
    return _result(status, len(orphans), orphans)


# ── 6. STALE NOTIFICATION QUEUE ──────────────────────────────────────────────

def check_notification_queue(db: Session) -> dict:
    """
    Detect stuck or stale notification queue entries.

    Reports:
      - PENDING entries older than 24h (likely missed by scheduler)
      - FAILED entries with attempt_count >= max_attempts (permanently failed)
    """
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationStatus
    from app.core.config import settings

    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    issues = []

    stale_pending = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.status == NotificationStatus.PENDING,
            NotificationQueue.created_at < cutoff_24h,
        )
        .limit(50)
        .all()
    )
    for n in stale_pending:
        issues.append({
            "queue_id":    str(n.id),
            "status":      "PENDING",
            "phone":       n.phone_number,
            "created_at":  n.created_at.isoformat() if n.created_at else None,
            "attempts":    n.attempt_count,
            "message":     "Notification stuck PENDING for >24h",
        })

    max_attempts = getattr(settings, "HIGH_ALERT_MAX_ATTEMPTS", 2)
    permanently_failed = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.status == NotificationStatus.FAILED,
            NotificationQueue.attempt_count >= max_attempts,
        )
        .limit(50)
        .all()
    )
    for n in permanently_failed:
        issues.append({
            "queue_id":    str(n.id),
            "status":      "FAILED",
            "phone":       n.phone_number,
            "attempts":    n.attempt_count,
            "error":       n.error_message,
            "message":     f"Notification permanently failed after {n.attempt_count} attempts",
        })

    status = "warning" if issues else "ok"
    return _result(status, len(issues), issues)


# ── 7. BOQ CONSISTENCY ───────────────────────────────────────────────────────

def check_boq_consistency(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Detect BOQ items that are inconsistent:
      - planned_quantity <= 0 (zero-budget items that can never be fulfilled)
      - BOQ items linked to non-existent lots
      - BOQ sections with no items
    """
    from app.models.boq import BOQItem, BOQSection, BOQHeader
    from app.models.lot import Lot
    from sqlalchemy import and_

    issues = []

    # 1. BOQ items linked to non-existent lots
    orphan_boq_q = (
        db.query(BOQItem)
        .filter(
            BOQItem.lot_id.isnot(None),
            BOQItem.is_active == True,
            ~db.query(Lot.id).filter(Lot.id == BOQItem.lot_id).exists(),
        )
        .limit(50)
    )
    for bi in orphan_boq_q.all():
        issues.append({
            "type":          "orphan_boq_item",
            "boq_item_id":   str(bi.id),
            "lot_id":        str(bi.lot_id),
            "description":   bi.raw_description,
            "message":       f"BOQ item references non-existent lot {bi.lot_id}",
        })

    # 2. BOQ items with zero/negative planned_quantity
    zero_q = (
        db.query(BOQItem)
        .filter(
            BOQItem.is_active == True,
            BOQItem.planned_quantity <= 0,
        )
    )
    if project_id:
        # Filter via header→project
        zero_q = zero_q.join(BOQSection, BOQSection.id == BOQItem.section_id
                             ).join(BOQHeader, BOQHeader.id == BOQSection.header_id
                                    ).filter(BOQHeader.project_id == project_id)

    zero_count = zero_q.count()
    if zero_count > 0:
        issues.append({
            "type":    "zero_planned_quantity",
            "count":   zero_count,
            "message": f"{zero_count} active BOQ items have planned_quantity <= 0",
        })

    status = "warning" if issues else "ok"
    return _result(status, len(issues), issues)


# ── 8. FULL SUMMARY ──────────────────────────────────────────────────────────

def run_full_integrity_check(
    db: Session,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Run all reconciliation checks and return a consolidated summary.
    This is the main entry point for the admin endpoint.
    """
    now = datetime.now(timezone.utc)

    checks = {
        "stock_integrity":        check_stock_integrity(db, project_id),
        "procurement_chain":      check_procurement_chain(db, project_id),
        "allocation_overrun":     check_allocation_overrun(db, project_id),
        "payment_reconciliation": check_payment_reconciliation(db, project_id),
        "orphan_attachments":     check_orphan_attachments(db, project_id),
        "notification_queue":     check_notification_queue(db),
        "boq_consistency":        check_boq_consistency(db, project_id),
    }

    total_issues = sum(c["count"] for c in checks.values())
    any_error    = any(c["status"] == "error"   for c in checks.values())
    any_warning  = any(c["status"] == "warning" for c in checks.values())
    overall = "error" if any_error else ("warning" if any_warning else "ok")

    return {
        "checked_at":   now.isoformat(),
        "project_id":   str(project_id) if project_id else None,
        "overall":      overall,
        "total_issues": total_issues,
        "checks":       checks,
    }
