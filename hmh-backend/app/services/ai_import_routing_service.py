"""
Where a document goes, and what will happen to it.

One upload can carry twenty mixed documents: quotations, purchase orders,
pro-formas, tax invoices, a handwritten delivery note and a fuel order. Each
belongs in a different module, and the consequences differ enormously — of a
real batch of twenty, one moved stock, two created a liability, and the rest
created nothing at all. Before anybody clicks approve they need to see which
is which, stated in the same words on the review screen, in the manifest and
in the API.

This module is that single source of truth. It is read-only with respect to
the database and decides two things per document:

  destination   the module the record belongs in, in business language
  action        CREATE, LINK_EXISTING, REVIEW or SKIP_DUPLICATE

The action deliberately overlaps with, rather than replaces, the policy
verdict in ai_import_policy_service. Policy answers "may this be posted at
all"; routing answers "what would posting it do, and where". A document can
be policy-clean and still need review here, because the system cannot tell a
second pour of concrete from the same pro-forma scanned twice.

Nothing here posts, writes or guesses. Where the evidence is ambiguous the
answer is REVIEW, which is a person's job and not a default to be improved
away later.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_import import AIImportDocument, AIImportExtraction
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    ProvisionalChargeStatus,
)
from app.models.invoice import Invoice
from app.models.provisional_charge import ProvisionalCharge
from app.models.quotation import Quotation
from app.services import ai_import_matching_service as matching
from app.services.ai_import_extraction_service import DocumentExtractionPayload


# ── Manifest actions ──────────────────────────────────────────────────────────

CREATE = "CREATE"
LINK_EXISTING = "LINK_EXISTING"
REVIEW = "REVIEW"
SKIP_DUPLICATE = "SKIP_DUPLICATE"


# ── Destination modules ───────────────────────────────────────────────────────
# The key is stable and safe to branch on; the label is what a person reads.

@dataclass(frozen=True)
class Destination:
    key: str
    label: str
    # Plain-language statement of the consequence, shown next to the action so
    # nobody has to know what "post" means in order to approve one.
    effect: str


PROCUREMENT = Destination(
    "procurement", "Procurement",
    "Recorded as a supplier price offer. No money is owed and no stock moves.",
)
PURCHASE_ORDERS = Destination(
    "purchase_orders", "Purchase Orders",
    "Recorded as an order placed with the supplier. Committed spend, but nothing "
    "owed and no stock until the goods arrive.",
)
PROVISIONAL_CHARGES = Destination(
    "provisional_charges", "Pending supplier charges",
    "Recorded as a request for payment in advance, shown separately from Accounts "
    "Payable. It becomes a liability only when the supplier's tax invoice arrives.",
)
ACCOUNTS_PAYABLE = Destination(
    "accounts_payable", "Accounts Payable",
    "Creates a supplier liability, UNPAID. Payment is recorded separately when it "
    "is actually made.",
)
GOODS_RECEIVED = Destination(
    "goods_received", "Goods received / project stock",
    "Increases stock in the project warehouse. Allocation to a lot happens "
    "afterwards, on the warehouse screen.",
)
FUEL_PROCUREMENT = Destination(
    "fuel_procurement", "Fuel procurement",
    "Belongs in fuel management, not materials. Fuel is measured in litres against "
    "a storage location and never becomes warehouse stock.",
)
PAYMENT_RECONCILIATION = Destination(
    "payment_reconciliation", "Payment reconciliation",
    "Evidence of a payment. It is matched to an invoice by a person; a document "
    "never marks anything as paid by itself.",
)
MATERIAL_REQUESTS = Destination(
    "material_requests", "Material Requests",
    "Recorded as an internal request for materials. No supplier commitment.",
)
EVIDENCE_ONLY = Destination(
    "evidence_only", "Evidence only",
    "Stored and searchable against the supplier and project. Nothing is created.",
)
UNROUTED = Destination(
    "unrouted", "Not yet routed",
    "The document type is not identified, so there is no destination. Set the "
    "correct type first.",
)


_BY_TYPE: dict[AIImportDocumentType, Destination] = {
    AIImportDocumentType.MATERIAL_REQUEST: MATERIAL_REQUESTS,
    AIImportDocumentType.QUOTATION: PROCUREMENT,
    AIImportDocumentType.PURCHASE_ORDER: PURCHASE_ORDERS,
    AIImportDocumentType.PRO_FORMA_INVOICE: PROVISIONAL_CHARGES,
    AIImportDocumentType.SUPPLIER_INVOICE: ACCOUNTS_PAYABLE,
    AIImportDocumentType.DELIVERY_NOTE: GOODS_RECEIVED,
    AIImportDocumentType.GOODS_RECEIVED_NOTE: GOODS_RECEIVED,
    AIImportDocumentType.SUPPLIER_CREDIT_NOTE: EVIDENCE_ONLY,
    AIImportDocumentType.PAYMENT_PROOF: PAYMENT_RECONCILIATION,
    AIImportDocumentType.UNKNOWN: UNROUTED,
}


def destination_for(doc_type: Optional[AIImportDocumentType]) -> Destination:
    """The module a document type belongs in, ignoring its current state."""
    return _BY_TYPE.get(doc_type or AIImportDocumentType.UNKNOWN, UNROUTED)


# ── Fuel detection ────────────────────────────────────────────────────────────
# A fuel purchase order looks like any other purchase order. Routed as one it
# creates a materials order, and the delivery that follows tries to put 500
# litres of diesel into the warehouse as though it were cement. Fuel is tracked
# by litres against a storage location in its own module, so the two must not
# mix.

_FUEL_WORDS = (
    "diesel", "petrol", "paraffin", "50ppm", "500ppm", "10ppm",
    "unleaded", "lubricant", "fuel",
)


def _line_description(item) -> Optional[str]:
    if isinstance(item, dict):
        return item.get("description")
    return getattr(item, "description", None)


def _mentions_fuel(payload: DocumentExtractionPayload) -> bool:
    haystacks: list[str] = []
    for name in ("supplier_name", "notes"):
        value = payload.value(name)
        if value:
            haystacks.append(str(value))
    for item in (payload.line_items or []):
        description = _line_description(item)
        if description:
            haystacks.append(str(description))
    blob = " ".join(haystacks).lower()
    return any(word in blob for word in _FUEL_WORDS)


# ── Routing verdict ───────────────────────────────────────────────────────────

@dataclass
class RoutingVerdict:
    destination: Destination
    action: str
    # Why this action, in one sentence a site manager can act on.
    reason: str
    # Existing record this document relates to, when one was found.
    linked_label: Optional[str] = None
    linked_type: Optional[str] = None
    linked_id: Optional[uuid.UUID] = None
    # Further things a person must settle before approving. Not blocking on
    # their own — they are what the review screen asks about.
    review_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "destination": self.destination.key,
            "destination_label": self.destination.label,
            "effect": self.destination.effect,
            "action": self.action,
            "reason": self.reason,
            "linked_label": self.linked_label,
            "linked_type": self.linked_type,
            "linked_id": str(self.linked_id) if self.linked_id else None,
            "review_notes": list(self.review_notes),
        }


def _amount(payload: DocumentExtractionPayload) -> Optional[Decimal]:
    raw = payload.value("total_amount")
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _reference(payload: DocumentExtractionPayload) -> Optional[str]:
    value = payload.value("document_number")
    return str(value).strip() if value else None


# ── Duplicate detection, per destination ──────────────────────────────────────
#
# The file-level duplicate — the same bytes uploaded twice — is caught at
# upload and recorded on document.duplicate_of_id. What is caught here is the
# harder one: a different file describing a purchase that is already in the
# system. Those are found on the supplier's own reference, because that is the
# only identifier both documents are guaranteed to share.

def _existing_quotation(db: Session, reference: Optional[str]) -> Optional[Quotation]:
    if not reference:
        return None
    return db.query(Quotation).filter(Quotation.quote_number == reference).first()


def _existing_provisional(
    db: Session, document: AIImportDocument, reference: Optional[str],
) -> Optional[ProvisionalCharge]:
    if not reference or not document.supplier_id:
        return None
    return (
        db.query(ProvisionalCharge)
        .filter(
            ProvisionalCharge.supplier_id == document.supplier_id,
            ProvisionalCharge.reference == reference,
        )
        .first()
    )


def _existing_invoice(
    db: Session, document: AIImportDocument, reference: Optional[str],
) -> Optional[Invoice]:
    if not reference or not document.supplier_id:
        return None
    return (
        db.query(Invoice)
        .filter(
            Invoice.supplier_id == document.supplier_id,
            Invoice.invoice_number == reference,
        )
        .first()
    )


def _sibling_with_same_amount(
    db: Session, document: AIImportDocument, amount: Optional[Decimal],
) -> Optional[AIImportDocument]:
    """
    Another document in the same batch, same type and supplier, for the same
    money.

    Two Cretemix pro-formas in the real batch carry identical totals of
    R17 444.89 under different numbers and dates. One reading is a second
    pour; the other is the same pour scanned twice. Nothing on the paper
    distinguishes them, so this never decides — it raises the question.
    """
    if amount is None or document.supplier_id is None:
        return None
    siblings = (
        db.query(AIImportDocument)
        .filter(
            AIImportDocument.batch_id == document.batch_id,
            AIImportDocument.id != document.id,
            AIImportDocument.document_type == document.document_type,
            AIImportDocument.supplier_id == document.supplier_id,
            AIImportDocument.status != AIImportDocumentStatus.REJECTED,
        )
        .all()
    )
    for sibling in siblings:
        # is_current, not the newest by date. A re-extraction or a human
        # correction can leave a later row that is not the one in force, and
        # reading the wrong one would compare against a superseded total.
        extraction = (
            db.query(AIImportExtraction)
            .filter(
                AIImportExtraction.document_id == sibling.id,
                AIImportExtraction.is_current.is_(True),
            )
            .first()
        )
        if extraction is None:
            continue
        raw = (extraction.fields or {}).get("total_amount")
        if isinstance(raw, dict):
            raw = raw.get("value")
        if raw in (None, ""):
            continue
        try:
            if Decimal(str(raw)) == amount:
                return sibling
        except (InvalidOperation, ValueError):
            continue
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

_MISSING_CONTEXT_PREFIXES = ("The supplier is not linked", "The project is not set")


def route(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
) -> RoutingVerdict:
    """
    Decide the destination and manifest action for one document.

    Read-only. Safe to call repeatedly, and called by both the manifest
    endpoint and the review screen so the two can never disagree.
    """
    doc_type = document.document_type or AIImportDocumentType.UNKNOWN
    destination = destination_for(doc_type)
    reference = _reference(payload)
    amount = _amount(payload)
    notes: list[str] = []

    # ── The same file, twice ─────────────────────────────────────────────────
    if document.duplicate_of_id:
        return RoutingVerdict(
            destination=destination,
            action=SKIP_DUPLICATE,
            reason="This exact file has already been uploaded. Importing it again "
                   "would duplicate the transaction.",
        )

    # ── Nothing to route ─────────────────────────────────────────────────────
    if doc_type == AIImportDocumentType.UNKNOWN:
        return RoutingVerdict(
            destination=UNROUTED,
            action=REVIEW,
            reason="The document type could not be identified, so there is no "
                   "destination. Set the type, then review the extracted fields.",
        )

    # ── Context every destination needs ──────────────────────────────────────
    if document.supplier_id is None:
        notes.append(
            "The supplier is not linked. Match it to an existing supplier, or create "
            "the supplier first — nothing can be filed against a name alone."
        )
    if document.project_id is None:
        notes.append("The project is not set.")
    if amount is None and doc_type not in (
        AIImportDocumentType.DELIVERY_NOTE,
        AIImportDocumentType.GOODS_RECEIVED_NOTE,
    ):
        notes.append("The total could not be read from the document.")

    # ── Fuel leaves the materials path entirely ──────────────────────────────
    if doc_type == AIImportDocumentType.PURCHASE_ORDER and _mentions_fuel(payload):
        return RoutingVerdict(
            destination=FUEL_PROCUREMENT,
            action=REVIEW,
            reason="This order is for fuel, which is tracked in litres against a "
                   "storage location rather than as warehouse stock. Capture it on "
                   "the fuel screen, against the storage location it was delivered "
                   "into — the document does not say which one.",
            review_notes=notes,
        )

    # ── Per-destination duplicate detection ──────────────────────────────────
    if doc_type == AIImportDocumentType.QUOTATION:
        existing_quote = _existing_quotation(db, reference)
        if existing_quote is not None:
            return RoutingVerdict(
                destination=destination, action=SKIP_DUPLICATE,
                reason=f"Quotation {reference} is already recorded.",
                linked_label=existing_quote.quote_number, linked_type="quotation",
                linked_id=existing_quote.id, review_notes=notes,
            )

    elif doc_type == AIImportDocumentType.PRO_FORMA_INVOICE:
        existing_charge = _existing_provisional(db, document, reference)
        if existing_charge is not None:
            return RoutingVerdict(
                destination=destination, action=SKIP_DUPLICATE,
                reason=f"Pro-forma {reference} from this supplier is already recorded "
                       f"as a pending charge.",
                linked_label=existing_charge.reference,
                linked_type="provisional_charge",
                linked_id=existing_charge.id, review_notes=notes,
            )
        twin = _sibling_with_same_amount(db, document, amount)
        if twin is not None:
            notes.append(
                f"{twin.file_name} is another pro-forma from the same supplier for the "
                f"same amount. Confirm these are two separate purchases before "
                f"importing both — the documents alone cannot tell them apart."
            )

    elif doc_type == AIImportDocumentType.SUPPLIER_INVOICE:
        existing_invoice = _existing_invoice(db, document, reference)
        if existing_invoice is not None:
            return RoutingVerdict(
                destination=destination, action=SKIP_DUPLICATE,
                reason=f"Invoice {reference} from this supplier is already recorded, "
                       f"so no second liability will be created.",
                linked_label=existing_invoice.invoice_number, linked_type="invoice",
                linked_id=existing_invoice.id, review_notes=notes,
            )

    # ── An order this document continues ─────────────────────────────────────
    linked_label: Optional[str] = None
    linked_type: Optional[str] = None
    linked_id: Optional[uuid.UUID] = None
    po_match = matching.best_match(db, document.id, "purchase_order")
    if po_match is not None and po_match.target_id:
        linked_label = po_match.target_label
        linked_type = "purchase_order"
        linked_id = po_match.target_id

    # ── A tax invoice that supersedes a pending charge ───────────────────────
    if doc_type == AIImportDocumentType.SUPPLIER_INVOICE and linked_id is not None:
        pending = (
            db.query(ProvisionalCharge)
            .filter(
                ProvisionalCharge.purchase_order_id == linked_id,
                ProvisionalCharge.status == ProvisionalChargeStatus.PENDING,
            )
            .first()
        )
        if pending is not None:
            notes.append(
                f"Pro-forma {pending.reference} is pending against the same order. "
                f"Recording this invoice will close it, so the purchase is counted "
                f"once and not twice."
            )

    # ── Payment evidence never settles anything ──────────────────────────────
    if document.payment_evidence_detected:
        notes.append(
            "Payment evidence detected — verification required. The document claims "
            "it has been paid; that claim is recorded as evidence only and does not "
            "mark anything as settled. Check it against the bank, then capture the "
            "payment against the invoice it pays."
        )

    missing_context = any(
        note.startswith(_MISSING_CONTEXT_PREFIXES) for note in notes
    )
    if missing_context:
        action = REVIEW
    elif linked_id is not None:
        action = LINK_EXISTING
    else:
        action = CREATE

    reason = {
        CREATE: f"A new record will be created in {destination.label}.",
        LINK_EXISTING: f"Will be recorded in {destination.label} and linked to "
                       f"{linked_label or 'the matched order'}.",
        REVIEW: "Missing context a person must supply before this can be imported.",
    }[action]

    return RoutingVerdict(
        destination=destination, action=action, reason=reason,
        linked_label=linked_label, linked_type=linked_type, linked_id=linked_id,
        review_notes=notes,
    )
