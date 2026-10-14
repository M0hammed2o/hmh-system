"""
AI Document Import — processing policy.

Decides whether a document is AUTO_ELIGIBLE, NEEDS_REVIEW or BLOCKED, and
says why in terms a non-technical reviewer can act on.

The ordering rule is absolute: any BLOCKED reason wins over everything else,
and any NEEDS_REVIEW reason prevents AUTO_ELIGIBLE. A document reaches
AUTO_ELIGIBLE only when *no* reason of either kind was raised.

Model confidence is one input among many and is never sufficient on its own.
High confidence on an invoice with no delivery evidence is still BLOCKED for
stock, and still NEEDS_REVIEW for the liability.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_import import AIImportDocument, AIImportMatch, AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    AIImportMatchStatus,
    AIImportProcessingOutcome,
)
from app.schemas.ai_import import DocumentExtractionPayload

BLOCKED = "BLOCKED"
REVIEW = "NEEDS_REVIEW"


class Reason:
    """One machine-readable policy finding."""

    __slots__ = ("code", "message", "severity", "field")

    def __init__(self, code: str, message: str, severity: str, field: Optional[str] = None) -> None:
        self.code = code
        self.message = message
        self.severity = severity
        self.field = field

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "field": self.field,
        }


# Fields each document type must resolve before it can be posted at all.
_REQUIRED_FIELDS: dict[AIImportDocumentType, tuple[str, ...]] = {
    AIImportDocumentType.MATERIAL_REQUEST: ("document_number",),
    AIImportDocumentType.PURCHASE_ORDER: ("document_number", "supplier_name"),
    AIImportDocumentType.SUPPLIER_INVOICE: ("document_number", "supplier_name", "total_amount"),
    AIImportDocumentType.SUPPLIER_CREDIT_NOTE: ("document_number", "supplier_name", "total_amount"),
    AIImportDocumentType.DELIVERY_NOTE: ("supplier_name",),
    AIImportDocumentType.GOODS_RECEIVED_NOTE: (),
    AIImportDocumentType.PAYMENT_PROOF: ("total_amount",),
}

# Document types whose posting moves stock. These carry the receipt-evidence rule.
STOCK_MOVING_TYPES = frozenset({
    AIImportDocumentType.DELIVERY_NOTE,
    AIImportDocumentType.GOODS_RECEIVED_NOTE,
})

# Document types whose posting creates or changes a financial liability.
FINANCIAL_TYPES = frozenset({
    AIImportDocumentType.SUPPLIER_INVOICE,
    AIImportDocumentType.SUPPLIER_CREDIT_NOTE,
})


def _match_for(db: Session, document_id: uuid.UUID, target_type: str) -> Optional[AIImportMatch]:
    return (
        db.query(AIImportMatch)
        .filter(
            AIImportMatch.document_id == document_id,
            AIImportMatch.target_type == target_type,
            AIImportMatch.status != AIImportMatchStatus.REJECTED,
        )
        .order_by(AIImportMatch.score.desc().nullslast())
        .first()
    )


def evaluate(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
) -> tuple[AIImportProcessingOutcome, list[dict]]:
    """
    Apply every policy rule and return the verdict with its reasons.

    Pure with respect to the database: it reads, it never writes.
    """
    reasons: list[Reason] = []

    # ── Document integrity ───────────────────────────────────────────────────
    if document.duplicate_of_id:
        reasons.append(Reason(
            "DUPLICATE_FILE",
            "This exact file has already been uploaded. Posting it again would "
            "duplicate the transaction.",
            BLOCKED,
        ))

    if document.document_type == AIImportDocumentType.UNKNOWN:
        reasons.append(Reason(
            "UNKNOWN_DOCUMENT_TYPE",
            "The document could not be identified. Choose the correct document type "
            "before it can be processed.",
            REVIEW,
        ))

    for warning in payload.warnings:
        if "prompt-injection" in warning:
            reasons.append(Reason(
                "SUSPICIOUS_CONTENT",
                "The document contains text that reads like an instruction to the system. "
                "It was treated as data, but a person must confirm this document is genuine.",
                BLOCKED,
            ))
            break

    if payload.extraction_mode == "none":
        reasons.append(Reason(
            "EXTRACTION_FAILED",
            "Nothing could be read from this file. Capture the details manually or "
            "upload a clearer scan.",
            REVIEW,
        ))

    # ── Arithmetic ───────────────────────────────────────────────────────────
    failed_checks = [c for c in payload.arithmetic_checks if not c.passed]
    if failed_checks:
        severity = BLOCKED if document.document_type in FINANCIAL_TYPES else REVIEW
        for check in failed_checks[:5]:
            reasons.append(Reason(
                "ARITHMETIC_INVALID",
                check.message or f"The {check.name.replace('_', ' ')} on this document does not add up.",
                severity,
                check.name,
            ))

    # ── Required fields ──────────────────────────────────────────────────────
    for field in _REQUIRED_FIELDS.get(document.document_type, ()):
        extracted = payload.fields.get(field)
        if extracted is None or not extracted.is_resolved:
            reasons.append(Reason(
                "MISSING_REQUIRED_FIELD",
                f"{field.replace('_', ' ').capitalize()} could not be read from the document "
                f"and is required for this document type.",
                REVIEW,
                field,
            ))

    # ── Business context ─────────────────────────────────────────────────────
    supplier_match = _match_for(db, document.id, "supplier")
    project_match = _match_for(db, document.id, "project")

    needs_supplier = document.document_type != AIImportDocumentType.MATERIAL_REQUEST
    if needs_supplier:
        if supplier_match and supplier_match.status == AIImportMatchStatus.AMBIGUOUS:
            reasons.append(Reason(
                "CONFLICTING_SUPPLIER",
                supplier_match.explanation or "More than one supplier matches this document.",
                BLOCKED,
            ))
        elif not document.supplier_id:
            reasons.append(Reason(
                "UNKNOWN_SUPPLIER",
                f"The supplier '{payload.value('supplier_name') or 'on this document'}' is not in the "
                f"supplier list. Link it to an existing supplier or create the supplier first.",
                REVIEW,
            ))

    if project_match and project_match.status == AIImportMatchStatus.AMBIGUOUS:
        reasons.append(Reason(
            "AMBIGUOUS_PROJECT",
            project_match.explanation or "More than one project matches this document.",
            REVIEW,
        ))
    elif not document.project_id:
        reasons.append(Reason(
            "UNKNOWN_PROJECT",
            "The project this document belongs to could not be determined. "
            "Select the project before posting.",
            REVIEW,
        ))

    # A reference pointing at another project's record, or at a different
    # supplier's order, is a hard stop. These rows are recorded as REJECTED
    # precisely because they are not usable as matches, so the status filter
    # is deliberately absent here — the evidence is the point.
    for match in db.query(AIImportMatch).filter(
        AIImportMatch.document_id == document.id,
    ).all():
        if (match.evidence or {}).get("cross_project"):
            reasons.append(Reason(
                "CROSS_TENANT_REFERENCE",
                f"This document refers to {match.target_label}, which belongs to a different project. "
                f"It cannot be posted here.",
                BLOCKED,
            ))
        if (match.evidence or {}).get("supplier_conflict"):
            reasons.append(Reason(
                "CONFLICTING_SUPPLIER",
                match.explanation or "The order referenced belongs to a different supplier.",
                BLOCKED,
            ))

    # ── Already posted ───────────────────────────────────────────────────────
    existing_posting = (
        db.query(AIImportPosting)
        .filter(
            AIImportPosting.document_id == document.id,
            AIImportPosting.reversed_at.is_(None),
        )
        .first()
    )
    if existing_posting:
        reasons.append(Reason(
            "ALREADY_POSTED",
            f"This document was already posted as {existing_posting.entity_type.replace('_', ' ')} "
            f"{existing_posting.entity_label or existing_posting.entity_id}.",
            BLOCKED,
        ))

    # ── Type-specific rules ──────────────────────────────────────────────────
    if document.document_type in FINANCIAL_TYPES:
        reasons.extend(_financial_rules(db, document, payload))
    if document.document_type in STOCK_MOVING_TYPES:
        reasons.extend(_receipt_rules(db, document, payload))
    if document.document_type == AIImportDocumentType.PURCHASE_ORDER:
        reasons.extend(_purchase_order_rules(db, document, payload))
    if document.document_type == AIImportDocumentType.PAYMENT_PROOF:
        reasons.append(Reason(
            "PAYMENT_NOT_AUTO_POSTED",
            "Proof of payment is recorded as evidence only. A payment must be captured "
            "through the payments screen against the invoice it settles.",
            REVIEW,
        ))

    # ── Legacy authorisation ─────────────────────────────────────────────────
    if document.is_legacy and not document.authorised_by:
        reasons.append(Reason(
            "LEGACY_AUTHORISATION_REQUIRED",
            "This is a historical document with no digital approval history. "
            "A manager must authorise the import, which records who vouched for the "
            "paper trail rather than pretending the digital approvals happened.",
            REVIEW,
        ))

    # ── Confidence floor ─────────────────────────────────────────────────────
    floor = float(settings.AI_IMPORT_MIN_AUTO_CONFIDENCE)
    if payload.overall_confidence < floor:
        reasons.append(Reason(
            "LOW_CONFIDENCE",
            f"Reading confidence is {payload.overall_confidence:.0%}, below the "
            f"{floor:.0%} required for automatic processing. Check the extracted values.",
            REVIEW,
        ))
    low_fields = [
        name for name, field in payload.fields.items()
        if field.is_resolved and field.confidence < 0.5 and not field.corrected
    ]
    if low_fields:
        reasons.append(Reason(
            "LOW_FIELD_CONFIDENCE",
            "These values were hard to read and need checking: "
            + ", ".join(n.replace("_", " ") for n in sorted(low_fields)[:8]) + ".",
            REVIEW,
        ))

    # ── Verdict ──────────────────────────────────────────────────────────────
    if any(r.severity == BLOCKED for r in reasons):
        outcome = AIImportProcessingOutcome.BLOCKED
    elif reasons:
        outcome = AIImportProcessingOutcome.NEEDS_REVIEW
    else:
        outcome = AIImportProcessingOutcome.AUTO_ELIGIBLE

    return outcome, [r.as_dict() for r in reasons]


# ── Type-specific rule sets ───────────────────────────────────────────────────

def _financial_rules(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> list[Reason]:
    reasons: list[Reason] = []

    duplicate = _match_for(db, document.id, "existing_invoice")
    if duplicate and duplicate.target_id:
        reasons.append(Reason(
            "DUPLICATE_INVOICE_NUMBER",
            duplicate.explanation or
            f"An invoice with this number already exists for this supplier.",
            BLOCKED,
        ))

    po_match = _match_for(db, document.id, "purchase_order")
    if not po_match or not po_match.target_id:
        reasons.append(Reason(
            "NO_PURCHASE_ORDER",
            "No purchase order could be found for this invoice. An unmatched invoice "
            "must be reviewed before the liability is recorded.",
            REVIEW,
        ))
    elif po_match.status == AIImportMatchStatus.AMBIGUOUS:
        reasons.append(Reason(
            "AMBIGUOUS_PURCHASE_ORDER",
            po_match.explanation or "More than one purchase order could match this invoice.",
            REVIEW,
        ))
    else:
        # Three-way match: the goods must be receipted before the invoice is
        # treated as payable without review.
        comparison = (po_match.evidence or {}).get("po_comparison")
        if comparison and comparison.get("has_discrepancies"):
            for discrepancy in comparison.get("discrepancies", [])[:5]:
                code = {
                    "PRICE_DIFFERENCE": "PRICE_DISCREPANCY",
                    "OVER_SUPPLY": "QUANTITY_DISCREPANCY",
                    "BILLED_BEYOND_RECEIPT": "INVOICE_FOR_UNDELIVERED_GOODS",
                    "NOT_ON_ORDER": "ITEM_NOT_ORDERED",
                    "TOTAL_DIFFERENCE": "TOTAL_DISCREPANCY",
                    "UNIT_NOT_COMPARABLE": "UNIT_NOT_COMPARABLE",
                }.get(discrepancy.get("status", ""), "PO_DISCREPANCY")
                reasons.append(Reason(
                    code,
                    discrepancy.get("message", "The invoice differs from the purchase order."),
                    REVIEW,
                ))

        if not _goods_receipted(db, po_match.target_id):
            reasons.append(Reason(
                "NO_GOODS_RECEIPT",
                "Nothing has been receipted against this purchase order yet. An invoice is "
                "not evidence that the goods arrived, so this cannot be approved automatically.",
                REVIEW,
            ))

    return reasons


def _goods_receipted(db: Session, po_id: Optional[uuid.UUID]) -> bool:
    """True when any quantity has been received against the purchase order."""
    if not po_id:
        return False
    from app.models.purchase_order import PurchaseOrder

    po = db.get(PurchaseOrder, po_id)
    if not po:
        return False
    return any(float(line.quantity_received or 0) > 0 for line in po.order_items)


def _receipt_rules(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> list[Reason]:
    """
    Rules for documents that would move stock.

    The central question Phase 6 turns on: is there evidence the goods were
    physically received? A delivery note or GRN is such evidence; an invoice
    is not, which is why invoices never reach this rule set.
    """
    reasons: list[Reason] = []

    # Discrepancies against the order. The comparison is computed for every
    # document with a matched order, but previously only invoices read it —
    # so a delivery of goods that were never ordered, or more than remains
    # outstanding, passed without comment.
    po_match = _match_for(db, document.id, "purchase_order")
    if po_match and po_match.target_id:
        comparison = (po_match.evidence or {}).get("po_comparison")
        if comparison and comparison.get("has_discrepancies"):
            for discrepancy in comparison.get("discrepancies", [])[:5]:
                code = {
                    "NOT_ON_ORDER": "ITEM_NOT_ORDERED",
                    "OVER_SUPPLY": "QUANTITY_DISCREPANCY",
                    "UNIT_NOT_COMPARABLE": "UNIT_NOT_COMPARABLE",
                }.get(discrepancy.get("status", ""))
                if code:
                    reasons.append(Reason(
                        code,
                        discrepancy.get("message", "This delivery differs from the order."),
                        REVIEW,
                    ))

    duplicate = _match_for(db, document.id, "existing_delivery")
    if duplicate and duplicate.target_id:
        reasons.append(Reason(
            "DUPLICATE_DELIVERY",
            duplicate.explanation or
            "This delivery note has already been recorded. Posting it again would "
            "increase stock twice for one physical delivery.",
            BLOCKED,
        ))

    if not payload.line_items:
        reasons.append(Reason(
            "NO_LINE_ITEMS",
            "No delivered items could be read from this document. Stock cannot be "
            "updated without knowing what arrived.",
            REVIEW,
        ))

    unresolved = [
        line for line in payload.line_items
        if line.quantity is None or not line.description
    ]
    if unresolved:
        reasons.append(Reason(
            "INCOMPLETE_LINE_ITEMS",
            f"{len(unresolved)} delivered line(s) are missing a description or a quantity.",
            REVIEW,
        ))

    # A receipt needs a receiving site: it is what the delivery record is
    # booked against, and stock is never moved to a guessed location.
    if document.is_legacy:
        reasons.append(Reason(
            "LEGACY_STOCK_DOUBLE_COUNT_RISK",
            "This is historical paperwork that will move stock. If these goods are "
            "already counted in an opening balance or a stocktake, posting it will "
            "count them a second time. Check the current balance before authorising. "
            "Note also that the stock movement is dated today, not the original "
            "delivery date.",
            REVIEW,
        ))

    if not document.site_id:
        reasons.append(Reason(
            "UNKNOWN_RECEIVING_LOCATION",
            "The site that received these goods could not be determined. Select the "
            "receiving site — stock is never booked in against a guessed location.",
            REVIEW,
            "site_name",
        ))

    return reasons


def _purchase_order_rules(
    db: Session, document: AIImportDocument, payload: DocumentExtractionPayload,
) -> list[Reason]:
    reasons: list[Reason] = []

    approver = payload.fields.get("approving_employee")
    if approver is None or not approver.is_resolved:
        reasons.append(Reason(
            "MISSING_AUTHORISATION",
            "No approving signatory could be read on this purchase order. An order "
            "without evidence of authorisation is never approved automatically.",
            REVIEW,
        ))

    existing = _match_for(db, document.id, "purchase_order")
    if existing and existing.target_id and existing.status == AIImportMatchStatus.CONFIRMED:
        reasons.append(Reason(
            "DUPLICATE_PURCHASE_ORDER",
            f"Purchase order {existing.target_label} already exists in the system.",
            BLOCKED,
        ))

    return reasons


# ── Status derivation ─────────────────────────────────────────────────────────

def status_for_outcome(
    outcome: AIImportProcessingOutcome, document: AIImportDocument,
) -> AIImportDocumentStatus:
    """
    Map a policy verdict onto the document's lifecycle state.

    AUTO_ELIGIBLE stops at READY_TO_POST unless auto-posting is switched on;
    the default is that a human still presses the button.
    """
    if outcome == AIImportProcessingOutcome.BLOCKED:
        return AIImportDocumentStatus.AWAITING_REVIEW
    if outcome == AIImportProcessingOutcome.NEEDS_REVIEW:
        if document.is_legacy and not document.authorised_by:
            return AIImportDocumentStatus.AWAITING_AUTHORISATION
        return AIImportDocumentStatus.AWAITING_REVIEW
    return AIImportDocumentStatus.READY_TO_POST


def may_post(outcome: AIImportProcessingOutcome) -> bool:
    """BLOCKED is never postable, whatever the caller's role."""
    return outcome != AIImportProcessingOutcome.BLOCKED


def blocking_reasons(reasons: list[dict]) -> list[dict]:
    return [r for r in reasons if r.get("severity") == BLOCKED]
