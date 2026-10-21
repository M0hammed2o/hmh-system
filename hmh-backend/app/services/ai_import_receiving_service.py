"""
Where an imported goods receipt has actually got to.

A delivery note that has been posted is not the end of the story. Posting
writes a goods receipt into the **project warehouse**; putting those
materials against a BOQ lot is a separate, deliberate step, because guessing
which lot consumed which bag of cement would corrupt the figures the site
runs on.

Nothing here moves stock. It reads the ledger the posting wrote and reports
how far the material has travelled, so the screen can say "posted, awaiting
lot allocation" rather than leaving someone to wonder why a delivery they
approved is not on the BOQ.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_import import AIImportPosting
from app.models.enums import MovementType

# Where the material is, after a receipt has been posted.
NOT_A_RECEIPT = "NOT_A_RECEIPT"
NOT_POSTED = "NOT_POSTED"
IN_PROJECT_WAREHOUSE = "IN_PROJECT_WAREHOUSE"
PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
ALLOCATED_TO_LOT = "ALLOCATED_TO_LOT"

# A cent of rounding either way is not a shortfall.
TOLERANCE = 0.005


def _deliveries_for(db: Session, document_id: uuid.UUID) -> list[uuid.UUID]:
    """Delivery ids this document posted, ignoring any since reversed."""
    rows = (
        db.query(AIImportPosting.entity_id)
        .filter(
            AIImportPosting.document_id == document_id,
            AIImportPosting.entity_type == "delivery",
            AIImportPosting.reversed_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows if r[0]]


def receiving_progress(db: Session, document) -> dict:
    """
    How far this document's materials have travelled.

    Returns the stage, the quantities behind it and the next action a person
    can take. Read-only: it never writes, and never guesses a lot.
    """
    from app.models.enums import AIImportDocumentType
    from app.models.stock import StockLedger

    if document.document_type != AIImportDocumentType.DELIVERY_NOTE:
        # Only physical delivery evidence moves stock. An invoice or an order
        # is a commitment, not a receipt, and must never read as one.
        return {
            "stage": NOT_A_RECEIPT,
            "label": "Not a goods receipt",
            "detail": "Only delivery notes move stock. Orders and invoices do not.",
            "received_qty": 0.0,
            "allocated_qty": 0.0,
            "awaiting_allocation_qty": 0.0,
            "next_action": None,
        }

    delivery_ids = _deliveries_for(db, document.id)
    if not delivery_ids:
        return {
            "stage": NOT_POSTED,
            "label": "Not yet posted",
            "detail": "No goods receipt has been posted from this document yet.",
            "received_qty": 0.0,
            "allocated_qty": 0.0,
            "awaiting_allocation_qty": 0.0,
            "next_action": "Review and post the delivery to record the stock.",
        }

    received_rows = (
        db.query(StockLedger)
        .filter(
            StockLedger.reference_type == "delivery",
            StockLedger.reference_id.in_(delivery_ids),
            StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
        )
        .all()
    )
    received = float(sum(float(r.quantity_in or 0) for r in received_rows))

    if received <= TOLERANCE:
        return {
            "stage": NOT_POSTED,
            "label": "Posted, but no stock recorded",
            "detail": "A delivery exists but no stock movement was written against it.",
            "received_qty": 0.0,
            "allocated_qty": 0.0,
            "awaiting_allocation_qty": 0.0,
            "next_action": "Check the delivery — this needs someone to look at it.",
        }

    # Anything already sitting against a lot arrived there directly.
    straight_to_lot = float(
        sum(float(r.quantity_in or 0) for r in received_rows if r.lot_id is not None)
    )

    # Of what landed in the project warehouse, how much has since been issued
    # onward to a lot? Warehouse dispatch writes TRANSFER_IN at lot level.
    project_ids = {r.project_id for r in received_rows if r.project_id}
    item_ids = {r.item_id for r in received_rows if r.item_id}
    transferred = 0.0
    if project_ids and item_ids:
        transferred = float(
            db.query(func.coalesce(func.sum(StockLedger.quantity_in), 0))
            .filter(
                StockLedger.project_id.in_(project_ids),
                StockLedger.item_id.in_(item_ids),
                StockLedger.lot_id.isnot(None),
                StockLedger.movement_type == MovementType.TRANSFER_IN,
            )
            .scalar() or 0
        )

    # Transfers are project-wide, not traceable to one delivery, so this is
    # capped at what this receipt brought in. It answers "is any of this still
    # waiting?", not "which bag went where".
    allocated = min(received, straight_to_lot + transferred)
    awaiting = max(received - allocated, 0.0)

    if awaiting <= TOLERANCE:
        stage, label = ALLOCATED_TO_LOT, "Allocated to a BOQ lot"
        detail = "The received materials have been issued to a lot."
        next_action = None
    elif allocated > TOLERANCE:
        stage, label = PARTIALLY_ALLOCATED, "Partly allocated to a BOQ lot"
        detail = f"{awaiting:,.2f} of {received:,.2f} is still in the project warehouse."
        next_action = "Issue the remainder to a lot from Project Warehouse."
    else:
        stage, label = IN_PROJECT_WAREHOUSE, "In the project warehouse"
        detail = (
            "The stock is recorded, but nothing has been issued to a BOQ lot yet, "
            "so it will not appear against a lot's materials."
        )
        next_action = "Issue these materials to a lot from Project Warehouse."

    return {
        "stage": stage,
        "label": label,
        "detail": detail,
        "received_qty": round(received, 3),
        "allocated_qty": round(allocated, 3),
        "awaiting_allocation_qty": round(awaiting, 3),
        "next_action": next_action,
    }


def pipeline_stage(db: Session, document) -> dict:
    """
    One description of where this document stands, end to end.

    The document's own status covers upload through posting. It stops there,
    which is exactly where the confusion starts: a delivery can be POSTED and
    still be nowhere near a BOQ. This continues the story.
    """
    from app.models.enums import AIImportDocumentStatus as S

    status = document.status
    receiving = receiving_progress(db, document)

    simple = {
        S.UPLOADED: ("UPLOADED", "Uploaded", "Waiting to be read."),
        S.QUEUED: ("QUEUED", "Queued", "Waiting for the reader."),
        S.PROCESSING: ("PROCESSING", "Processing", "Being read now."),
        S.EXTRACTED: ("PROCESSING", "Processing", "Being read now."),
        S.CLASSIFIED: ("PROCESSING", "Processing", "Being read now."),
        S.MATCHING: ("PROCESSING", "Processing", "Matching against your records."),
        S.AWAITING_REVIEW: ("AWAITING_REVIEW", "Awaiting review", "Someone needs to check what was read."),
        S.AWAITING_AUTHORISATION: ("AWAITING_AUTHORISATION", "Awaiting authorisation", "Needs a manager to authorise it."),
        S.READY_TO_POST: ("READY_TO_POST", "Ready to post", "Reviewed and ready to create the records."),
        S.FAILED: ("FAILED", "Failed", document.failure_reason or "This document needs someone to look at it."),
        S.REJECTED: ("REJECTED", "Rejected", document.rejection_reason or "Rejected during review."),
        S.DUPLICATE: ("DUPLICATE", "Already uploaded", "The same file was uploaded before."),
    }

    if status in simple:
        stage, label, detail = simple[status]
        return {
            "stage": stage, "label": label, "detail": detail,
            "next_action": None, "receiving": receiving,
        }

    # POSTED / PARTIALLY_POSTED — the records exist, so the question becomes
    # where the materials got to.
    if receiving["stage"] in (IN_PROJECT_WAREHOUSE, PARTIALLY_ALLOCATED, ALLOCATED_TO_LOT):
        return {
            "stage": receiving["stage"],
            "label": receiving["label"],
            "detail": receiving["detail"],
            "next_action": receiving["next_action"],
            "receiving": receiving,
        }

    return {
        "stage": "POSTED",
        "label": "Posted",
        "detail": "Records were created from this document.",
        "next_action": None,
        "receiving": receiving,
    }
