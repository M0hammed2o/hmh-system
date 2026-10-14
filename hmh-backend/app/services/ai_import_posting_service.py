"""
AI Document Import — posting extracted documents as real business records.

Nothing in this module writes a business balance itself. Material requests,
purchase orders, deliveries, stock movements and supplier liabilities are all
created by the existing domain services, so every business rule, alert, audit
event and BOQ interaction those services implement applies unchanged:

    material request  -> mr_service.create_request
    purchase order    -> po_service.create_po
    goods receipt     -> delivery_service.create_delivery
    supplier invoice  -> invoice_service.create_invoice

Idempotency is two-phase. `_claim` inserts and commits a row in
ai_import_postings whose `idempotency_key` is UNIQUE *before* the domain
service runs, then `_complete` fills in the resulting entity id. A second
attempt — a retried job, a double-clicked button, a worker that restarted
mid-post — loses the race on the unique index and is refused. A claim left
without an entity id means the process died mid-post: it still blocks a
retry, and is reported for manual verification rather than silently redone.

That guard sits on top of the guards already in the domain layer:
`create_invoice` rejects a duplicate (supplier, invoice number), and
`receive_stock` refuses to write a second ledger entry for a delivery that
`create_delivery` has already posted.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging_config import get_logger
from app.models.ai_import import AIImportDocument, AIImportPosting
from app.models.enums import (
    AIImportDocumentStatus,
    AIImportDocumentType,
    AttachmentEntity,
    AttachmentType,
    AuditAction,
    DeliveryDestination,
    MRPriority,
)
from app.models.user import User
from app.schemas.ai_import import DocumentExtractionPayload
from app.services import ai_import_matching_service as matching
from app.services import audit_service

logger = get_logger(__name__)


class PostingRefused(ValidationError):
    """The document cannot be posted. Carries a reviewer-facing explanation."""


class AlreadyPosted(ConflictError):
    """A posting for this document and entity type already exists."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency_key(document_id: uuid.UUID, entity_type: str) -> str:
    """One posting of each entity type per document, forever."""
    return f"ai_import:{document_id}:{entity_type}"


# ── Two-phase claim ───────────────────────────────────────────────────────────

# Exceptions the domain services raise from their validation guards *before*
# they write anything. Only these make it safe to release a claim: any other
# failure may have happened after the service committed, in which case the
# claim must stand so a retry cannot create a second record.
_PRE_WRITE_ERRORS = (NotFoundError, ValidationError, ConflictError)

# A claim younger than this is treated as a post still in flight.
_IN_FLIGHT_MINUTES = 5


def _claim(
    db: Session,
    document: AIImportDocument,
    entity_type: str,
    actor_id: uuid.UUID,
    payload_snapshot: Optional[dict] = None,
) -> AIImportPosting:
    """
    Reserve the right to post, and commit the reservation before the domain
    service runs so the UNIQUE index holds across processes.

    The key is derived solely from (document, entity_type) and is never
    varied — a randomised or counter-based retry key would let two concurrent
    requests both insert, which is precisely what the unique index is for.
    A claim is only ever freed by `_release`, which deletes the row, so the
    key becomes available again without ever being duplicated.

    Raises AlreadyPosted when a claim already exists, whatever its state.
    """
    key = _idempotency_key(document.id, entity_type)

    existing = (
        db.query(AIImportPosting)
        .filter(AIImportPosting.idempotency_key == key)
        .first()
    )
    if existing:
        raise AlreadyPosted(_already_posted_message(existing, entity_type))

    posting = AIImportPosting(
        document_id=document.id,
        idempotency_key=key,
        entity_type=entity_type,
        entity_id=None,
        project_id=document.project_id,
        payload=payload_snapshot,
        posted_by=actor_id,
        posted_at=_now(),
    )
    db.add(posting)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent request. The other one owns the post.
        db.rollback()
        raise AlreadyPosted(
            f"This document is already being posted as a "
            f"{entity_type.replace('_', ' ')}. Wait for that attempt to finish."
        )
    db.refresh(posting)
    return posting


def _already_posted_message(existing: AIImportPosting, entity_type: str) -> str:
    noun = entity_type.replace("_", " ")
    if existing.reversed_at is not None:
        return (
            f"This document was already posted as a {noun} and that posting was reversed. "
            f"It is not imported a second time — re-upload the document if it genuinely "
            f"needs to be captured again."
        )
    if existing.entity_id is None:
        # A claim taken moments ago is almost certainly a post still running in
        # another request or worker, not an abandoned one. Saying "did not
        # finish" there sends the operator hunting for a phantom problem.
        age = _now() - existing.posted_at if existing.posted_at else None
        if age is not None and age < timedelta(minutes=_IN_FLIGHT_MINUTES):
            return (
                f"This document is being posted as a {noun} right now. Wait for that "
                f"attempt to finish before trying again."
            )
        return (
            f"A previous attempt to post this document as a {noun} did not finish. "
            f"It is not retried automatically: check in the destination module whether "
            f"the record exists, then resolve the attempt from the incomplete postings "
            f"list."
        )
    return (
        f"This document has already been posted as a {noun}"
        + (f" ({existing.entity_label})." if existing.entity_label else ".")
    )


def _complete(
    db: Session,
    posting: AIImportPosting,
    entity_id: uuid.UUID,
    entity_label: str,
) -> AIImportPosting:
    posting.entity_id = entity_id
    posting.entity_label = entity_label[:255]
    db.commit()
    db.refresh(posting)
    return posting


def _written_row_count(db: Session, entity_type: str, project_id: Optional[uuid.UUID]) -> int:
    """
    How many records of this kind exist for the project right now.

    Sampled before a domain call and again if it fails, so the posting layer
    can see whether the service wrote something regardless of what it raised.
    """
    try:
        model = _load_entity_model(entity_type)
    except Exception:                               # noqa: BLE001 - unknown type
        return -1
    query = db.query(func.count()).select_from(model)
    if project_id is not None and hasattr(model, "project_id"):
        query = query.filter(model.project_id == project_id)
    try:
        return int(query.scalar() or 0)
    except Exception:                               # noqa: BLE001 - never block on this
        return -1


def _release(
    db: Session,
    posting_id: uuid.UUID,
    reason: str,
    *,
    entity_type: str,
    project_id: Optional[uuid.UUID],
    count_before: int,
) -> None:
    """
    Free a claim whose domain call failed without writing anything.

    Releasing a claim is the one operation that can let a document be posted
    twice, so it is not granted on the strength of the exception type alone.
    The exception type is a hint; the evidence is the row count.

    The rollback discards anything the failed call left uncommitted (which
    also expires the caller's ORM objects, so the claim is re-read by id).
    Anything that survives that rollback was committed — so if the count has
    gone up, the service wrote a record despite raising, and the claim stays
    put. That is the difference between a correctable mistake and a silent
    duplicate, and it does not depend on every domain service maintaining
    exception-type discipline forever.

    Deleting the row rather than flagging it means the original idempotency
    key is free again for a corrected retry, with the UNIQUE index intact.
    """
    db.rollback()

    count_after = _written_row_count(db, entity_type, project_id)
    if count_before >= 0 and count_after > count_before:
        logger.critical(
            "ai_import NOT releasing claim %s: %s rows for project %s went from %d to %d, "
            "so the domain service wrote a record before raising (%s). The claim stays so a "
            "retry cannot duplicate it; resolve it from the incomplete postings list.",
            posting_id, entity_type, project_id, count_before, count_after, reason,
        )
        return

    posting = db.get(AIImportPosting, posting_id)
    if posting is None:
        return
    logger.info(
        "ai_import released claim %s for document=%s: %s",
        posting.entity_type, posting.document_id, reason,
    )
    db.delete(posting)
    db.commit()


# ── Helpers shared by the posting paths ───────────────────────────────────────

def _require(value: Any, message: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise PostingRefused(message)
    return value


def _as_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except (ValueError, TypeError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _legacy_note(document: AIImportDocument, payload: DocumentExtractionPayload) -> str:
    """
    The provenance line written onto every imported record.

    A historical document must never look like it went through the digital
    workflow, so the note says plainly where it came from and, for a legacy
    import, who vouched for the paper trail.
    """
    parts = [
        f"Imported from scanned document '{document.file_name}' "
        f"via AI Document Import on {_now().date().isoformat()}."
    ]
    if document.is_legacy:
        parts.append(
            "LEGACY IMPORT: this record reflects paperwork created outside the system. "
            "It did not go through the digital approval workflow."
        )
        if document.authorised_by:
            parts.append(f"Legacy import authorised by user {document.authorised_by}.")
    issue_date = payload.value("issue_date")
    if issue_date:
        parts.append(f"Original document date: {issue_date}.")
    doc_number = payload.value("document_number")
    if doc_number:
        parts.append(f"Original document number: {doc_number}.")
    if payload.model:
        parts.append(f"Extracted by {payload.provider}/{payload.model} ({payload.extraction_mode} mode).")
    return " ".join(parts)


def _attach_source(db: Session, document: AIImportDocument, entity: AttachmentEntity, entity_id: uuid.UUID) -> None:
    """
    Link the original scan to the record it produced.

    The file is already in private storage, so this registers an Attachment row
    pointing at the same stored path rather than re-uploading the bytes.
    """
    from app.models.attachment import Attachment

    attachment_type = (
        AttachmentType.DELIVERY_NOTE if entity == AttachmentEntity.DELIVERY
        else AttachmentType.INVOICE_COPY if entity == AttachmentEntity.INVOICE
        else AttachmentType.PDF if document.mime_type == "application/pdf"
        else AttachmentType.PHOTO
    )
    db.add(Attachment(
        entity_type=entity,
        entity_id=entity_id,
        file_name=document.file_name,
        stored_path=document.stored_path,
        file_url=document.stored_path,
        mime_type=document.mime_type,
        file_size_bytes=document.file_size_bytes,
        attachment_type=attachment_type,
        uploaded_by=document.uploaded_by,
        uploaded_at=_now(),
        is_active=True,
        caption=f"Source document for AI import {str(document.id)[:8]}",
    ))
    db.flush()


def _safe_site_id(
    db: Session, document: AIImportDocument, project_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """
    The document's site, but only if it belongs to the posting project.

    A site can be left stranded on a document whose project is changed
    afterwards. `invoice_service` and `po_service` do not check the pairing
    (only `delivery_service` does), so a stale site would otherwise be written
    onto another project's invoice or order.
    """
    if not document.site_id:
        return None

    from app.models.site import Site
    site = db.get(Site, document.site_id)
    if site is None or site.project_id != project_id:
        logger.warning(
            "ai_import dropping site=%s on document=%s: not in project %s",
            document.site_id, document.id, project_id,
        )
        return None
    return document.site_id


def _matched_item_ids(db: Session, payload: DocumentExtractionPayload) -> list[Optional[uuid.UUID]]:
    """Catalogue item id per extracted line, None where no single item matched."""
    results = matching.match_line_items(db, payload)
    return [
        uuid.UUID(r["item_id"]) if r.get("item_id") else None
        for r in results
    ]


# ── Phase 4: material request ─────────────────────────────────────────────────

def post_material_request(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
    actor: User,
) -> AIImportPosting:
    """
    Create a material request from a scanned request form.

    The request is created in DRAFT and is deliberately left there. Submitting
    and approving it stays a human action in the existing workflow: a scan of a
    paper request is evidence that someone asked for materials, not evidence
    that the request was approved.

    No stock is reserved, consumed or received here — a material request has
    never moved stock in this system and does not start to now.
    """
    from app.schemas.material_request import MaterialRequestCreate, MaterialRequestItemCreate
    from app.services import mr_service

    project_id = _require(
        document.project_id,
        "The project for this material request is not set. Assign a project first.",
    )
    if not payload.line_items:
        raise PostingRefused(
            "No requested items could be read from this document, so there is nothing to request."
        )

    item_ids = _matched_item_ids(db, payload)
    items: list[MaterialRequestItemCreate] = []
    for index, line in enumerate(payload.line_items):
        quantity = _as_float(line.quantity)
        if quantity is None or quantity <= 0:
            raise PostingRefused(
                f"Line {index + 1} ('{line.description or 'no description'}') has no usable quantity. "
                f"Correct it before posting."
            )
        items.append(MaterialRequestItemCreate(
            item_id=item_ids[index] if index < len(item_ids) else None,
            description=(line.description or "").strip() or "Imported line item",
            requested_quantity=quantity,
            unit=line.unit,
            remarks=f"Imported from {document.file_name}",
        ))

    data = MaterialRequestCreate(
        site_id=document.site_id,
        priority=MRPriority.NORMAL,
        delivery_destination=DeliveryDestination.SITE_STORE,
        needed_by_date=_as_date(payload.value("delivery_date")),
        notes=_legacy_note(document, payload),
        items=items,
    )

    snapshot = {
        "type": "material_request",
        "items": len(items),
        "project_id": str(project_id),
        # The number printed on the paper. The record gets a freshly
        # generated one, so without this the two can never be connected
        # and a later document quoting the paper number finds nothing.
        "source_document_number": payload.value("document_number"),
    }
    # Sampled before the call so a release can be refused if the service
    # wrote a record despite raising. See _release.
    _rows_before = _written_row_count(db, "material_request", project_id)
    posting = _claim(db, document, "material_request", actor.id, snapshot)
    try:
        mr = mr_service.create_request(db, project_id, data, actor.id)
    except _PRE_WRITE_ERRORS as exc:
        # Rejected by the service's own validation before it wrote anything,
        # so the claim is freed and a corrected retry is possible.
        _release(
            db, posting.id, str(exc),
            entity_type=posting.entity_type,
            project_id=project_id,
            count_before=_rows_before,
        )
        raise
    except Exception:
        # The service may already have committed before failing. Leave the
        # claim standing: a retry must be refused, and the attempt is reported
        # by incomplete_postings() for a person to verify.
        logger.exception(
            "ai_import posting failed after the claim was taken; claim left "
            "in place for document=%s", document.id,
        )
        raise

    _attach_source(db, document, AttachmentEntity.MATERIAL_REQUEST, mr.id)
    audit_service.write_event(
        db, AuditAction.CREATE, "ai_import_material_request", actor.id, mr.id,
        after_value={
            "request_number": mr.request_number,
            "source_document": str(document.id),
            "is_legacy": document.is_legacy,
        },
        notes="Created from an imported document. Left in DRAFT: approvals were not simulated.",
    )
    return _complete(db, posting, mr.id, mr.request_number)


# ── Phase 5: purchase order ───────────────────────────────────────────────────

def post_purchase_order(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
    actor: User,
) -> AIImportPosting:
    """
    Create a purchase order from a scanned order.

    Created in DRAFT. `po_service.approve_po` is never called from here: an
    order whose authorisation exists only on paper is not silently approved,
    and the missing-authorisation policy reason keeps it visible.
    """
    from app.schemas.purchase_order import POItemCreate, PurchaseOrderCreate
    from app.services import po_service

    project_id = _require(
        document.project_id, "The project for this purchase order is not set."
    )
    supplier_id = _require(
        document.supplier_id,
        "The supplier for this purchase order is not set. Link or create the supplier first.",
    )
    if not payload.line_items:
        raise PostingRefused("No ordered items could be read from this document.")

    item_ids = _matched_item_ids(db, payload)
    items: list[POItemCreate] = []
    for index, line in enumerate(payload.line_items):
        quantity = _as_float(line.quantity)
        if quantity is None or quantity <= 0:
            raise PostingRefused(
                f"Line {index + 1} ('{line.description or 'no description'}') has no usable quantity."
            )
        items.append(POItemCreate(
            description=(line.description or "").strip() or "Imported line item",
            quantity_ordered=quantity,
            unit=line.unit,
            rate=_as_float(line.unit_price),
            item_id=item_ids[index] if index < len(item_ids) else None,
        ))

    mr_match = matching.best_match(db, document.id, "material_request")

    data = PurchaseOrderCreate(
        supplier_id=supplier_id,
        site_id=_safe_site_id(db, document, project_id),
        material_request_id=mr_match.target_id if mr_match else None,
        expected_delivery_date=_as_date(payload.value("delivery_date")),
        notes=_legacy_note(document, payload),
        items=items,
    )

    snapshot = {
        "type": "purchase_order",
        "items": len(items),
        "supplier_id": str(supplier_id),
        "source_document_number": payload.value("document_number"),
    }
    # Sampled before the call so a release can be refused if the service
    # wrote a record despite raising. See _release.
    _rows_before = _written_row_count(db, "purchase_order", project_id)
    posting = _claim(db, document, "purchase_order", actor.id, snapshot)
    try:
        po = po_service.create_po(db, project_id, data, actor.id)
    except _PRE_WRITE_ERRORS as exc:
        # Rejected by the service's own validation before it wrote anything,
        # so the claim is freed and a corrected retry is possible.
        _release(
            db, posting.id, str(exc),
            entity_type=posting.entity_type,
            project_id=project_id,
            count_before=_rows_before,
        )
        raise
    except Exception:
        # The service may already have committed before failing. Leave the
        # claim standing: a retry must be refused, and the attempt is reported
        # by incomplete_postings() for a person to verify.
        logger.exception(
            "ai_import posting failed after the claim was taken; claim left "
            "in place for document=%s", document.id,
        )
        raise

    _attach_source(db, document, AttachmentEntity.PURCHASE_ORDER, po.id)
    audit_service.write_event(
        db, AuditAction.CREATE, "ai_import_purchase_order", actor.id, po.id,
        after_value={
            "po_number": po.po_number,
            "source_document": str(document.id),
            "supplier_document_number": payload.value("document_number"),
            "is_legacy": document.is_legacy,
        },
        notes="Created from an imported document in DRAFT. Approval was not inferred from the scan.",
    )
    return _complete(db, posting, po.id, po.po_number)


# ── Phase 6: goods receipt ────────────────────────────────────────────────────

def post_goods_receipt(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
    actor: User,
    destination: DeliveryDestination,
) -> AIImportPosting:
    """
    Record a delivery and move the stock.

    Only reachable for DELIVERY_NOTE and GOODS_RECEIVED_NOTE — the policy
    engine keeps invoices out, because an invoice is a demand for payment and
    not evidence that anything arrived.

    `delivery_service.create_delivery` is the whole receipt: it creates the
    Delivery and its items, increases `PurchaseOrderItem.quantity_received`,
    moves the purchase order to PARTIALLY_RECEIVED/RECEIVED, raises the partial
    delivery alert, links any open procurement reconciliation, and writes the
    `StockLedger` rows. `receive_stock` is not called afterwards: it guards on
    an existing ledger row for the delivery, so after `create_delivery` it is a
    no-op, and calling it would only imply a second posting that never happens.

    Stock lands in the receiving project's warehouse (`project_id` set,
    `site_id`/`lot_id` NULL) — the same routing the manual delivery screen
    produces. It is project stock, never a company-wide central pool, so
    material delivered for one project is not shown as available to another.

    Allocating received stock onward to a specific lot is a separate, existing
    step (issue/transfer from the project warehouse); `destination=LOT` is
    therefore refused here rather than given a shortcut the manual UI has not
    got. See docs/AI_DOCUMENT_IMPORT_COMPLETION.md.
    """
    from app.schemas.delivery import DeliveryCreate, DeliveryItemCreate
    from app.services import delivery_service

    if document.document_type not in (
        AIImportDocumentType.DELIVERY_NOTE, AIImportDocumentType.GOODS_RECEIVED_NOTE,
    ):
        raise PostingRefused(
            f"A {document.document_type.value.replace('_', ' ').lower()} is not evidence that goods "
            f"were received, so it cannot update stock. Upload the delivery note or goods received note."
        )

    project_id = _require(document.project_id, "The project for this delivery is not set.")
    supplier_id = _require(
        document.supplier_id,
        "The supplier for this delivery is not set. Link or create the supplier first.",
    )
    site_id = _require(
        document.site_id,
        "A receiving site is required to record a delivery. Select the site the goods arrived at.",
    )
    if destination == DeliveryDestination.LOT:
        raise PostingRefused(
            "Receiving an imported delivery straight into a lot is not supported. "
            "Post the delivery into the project warehouse, then issue the material to "
            "the lot through the warehouse screen so the existing allocation and "
            "BOQ overrun checks run."
        )
    if not payload.line_items:
        raise PostingRefused("No delivered items could be read from this document.")

    po_match = matching.best_match(db, document.id, "purchase_order")
    po_id = po_match.target_id if po_match else None

    # Map each read line onto a purchase order line where one exists, so the
    # existing service can update outstanding order quantities correctly.
    po_line_map: dict[int, uuid.UUID] = {}
    if po_id:
        comparison = matching.compare_against_purchase_order(db, payload, po_id)
        for index, line_result in enumerate(comparison.get("lines", [])):
            matched = line_result.get("matched_po_line")
            if matched:
                po_line_map[index] = uuid.UUID(matched)

    item_ids = _matched_item_ids(db, payload)
    items: list[DeliveryItemCreate] = []
    for index, line in enumerate(payload.line_items):
        quantity = _as_float(line.quantity)
        if quantity is None or quantity <= 0:
            raise PostingRefused(
                f"Line {index + 1} ('{line.description or 'no description'}') has no usable "
                f"received quantity. Stock is never moved on a guessed figure."
            )
        items.append(DeliveryItemCreate(
            description=(line.description or "").strip() or "Imported line item",
            quantity_received=quantity,
            quantity_expected=quantity,
            unit=line.unit,
            item_id=item_ids[index] if index < len(item_ids) else None,
            purchase_order_item_id=po_line_map.get(index),
        ))

    data = DeliveryCreate(
        supplier_id=supplier_id,
        site_id=site_id,
        purchase_order_id=po_id,
        supplier_delivery_note_number=(
            payload.value("delivery_reference") or payload.value("document_number")
        ),
        delivery_date=_delivery_datetime(payload),
        comments=_legacy_note(document, payload),
        receiver_name=payload.value("received_by"),
        items=items,
    )

    snapshot = {
        "type": "goods_receipt",
        "destination": destination.value,
        "items": len(items),
        "purchase_order_id": str(po_id) if po_id else None,
        "source_document_number": payload.value("document_number"),
    }
    # Sampled before the call so a release can be refused if the service
    # wrote a record despite raising. See _release.
    _rows_before = _written_row_count(db, "goods_receipt", project_id)
    posting = _claim(db, document, "goods_receipt", actor.id, snapshot)

    try:
        # The whole receipt: delivery, items, PO quantities, stock ledger, alerts.
        delivery = delivery_service.create_delivery(db, project_id, data, actor.id)
    except _PRE_WRITE_ERRORS as exc:
        # Rejected by the service's own validation before it wrote anything,
        # so the claim is freed and a corrected retry is possible.
        _release(
            db, posting.id, str(exc),
            entity_type=posting.entity_type,
            project_id=project_id,
            count_before=_rows_before,
        )
        raise
    except Exception:
        # The service may already have committed before failing. Leave the
        # claim standing: a retry must be refused, and the attempt is reported
        # by incomplete_postings() for a person to verify.
        logger.exception(
            "ai_import posting failed after the claim was taken; claim left "
            "in place for document=%s", document.id,
        )
        raise

    _attach_source(db, document, AttachmentEntity.DELIVERY, delivery.id)
    audit_service.write_event(
        db, AuditAction.CREATE, "ai_import_goods_receipt", actor.id, delivery.id,
        after_value={
            "delivery_number": delivery.delivery_number,
            "destination": destination.value,
            "source_document": str(document.id),
            "is_legacy": document.is_legacy,
            "lines": len(items),
        },
        notes="Stock updated from an imported delivery document via the standard delivery service.",
    )
    db.commit()
    return _complete(db, posting, delivery.id, delivery.delivery_number or str(delivery.id)[:8])


def _delivery_datetime(payload: DocumentExtractionPayload) -> Optional[datetime]:
    raw = payload.value("delivery_date") or payload.value("issue_date")
    parsed = _as_date(raw)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


# ── Phase 7: supplier invoice ─────────────────────────────────────────────────

def post_supplier_invoice(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
    actor: User,
) -> AIImportPosting:
    """
    Record the supplier liability.

    Uses invoice_service.create_invoice, which owns the (supplier, invoice
    number) uniqueness rule and the supplier-balance relationship. No parallel
    ledger is written here.

    The invoice is created in the service's own DRAFT state. Payment status is
    never set from a document: it is derived from Payment rows by
    payment_service._recalculate_invoice_status, and an invoice stamped "PAID"
    by a supplier is a claim, not a settlement record.
    """
    from app.schemas.invoice import InvoiceCreate
    from app.services import invoice_service

    project_id = _require(document.project_id, "The project for this invoice is not set.")
    supplier_id = _require(
        document.supplier_id,
        "The supplier for this invoice is not set. Link or create the supplier first.",
    )
    invoice_number = _require(
        payload.value("document_number"),
        "The invoice number could not be read. It is required to record the liability "
        "and to prevent the same invoice being captured twice.",
    )
    total = _as_float(payload.value("total_amount"))
    if total is None:
        raise PostingRefused("The invoice total could not be read, so no liability can be recorded.")
    if total <= 0:
        raise PostingRefused(
            f"The invoice total reads as {total}. A liability is never recorded from a "
            f"zero or negative figure — check the extracted value."
        )

    po_match = matching.best_match(db, document.id, "purchase_order")

    data = InvoiceCreate(
        invoice_number=str(invoice_number).strip(),
        supplier_id=supplier_id,
        site_id=_safe_site_id(db, document, project_id),
        purchase_order_id=po_match.target_id if po_match else None,
        invoice_date=_as_date(payload.value("issue_date")),
        due_date=_as_date(payload.value("due_date")),
        subtotal_amount=_as_float(payload.value("subtotal_amount")),
        vat_amount=_as_float(payload.value("vat_amount")),
        total_amount=total,
        vat_rate_used=_as_float(payload.value("vat_rate")),
        notes=_legacy_note(document, payload),
    )

    snapshot = {
        "type": "invoice",
        "invoice_number": data.invoice_number,
        "total_amount": total,
        "supplier_id": str(supplier_id),
    }
    # Sampled before the call so a release can be refused if the service
    # wrote a record despite raising. See _release.
    _rows_before = _written_row_count(db, "invoice", project_id)
    posting = _claim(db, document, "invoice", actor.id, snapshot)
    try:
        invoice = invoice_service.create_invoice(db, project_id, data, actor.id)
    except ConflictError as exc:
        # The domain layer's own duplicate guard fired, before it wrote
        # anything. This is the backstop behind the duplicate-invoice policy
        # rule, not a redundant check.
        _release(
            db, posting.id, str(exc),
            entity_type=posting.entity_type,
            project_id=project_id,
            count_before=_rows_before,
        )
        raise PostingRefused(
            f"Invoice {data.invoice_number} already exists for this supplier, so no second "
            f"liability was created."
        ) from exc
    except _PRE_WRITE_ERRORS as exc:
        # Rejected by the service's own validation before it wrote anything,
        # so the claim is freed and a corrected retry is possible.
        _release(
            db, posting.id, str(exc),
            entity_type=posting.entity_type,
            project_id=project_id,
            count_before=_rows_before,
        )
        raise
    except Exception:
        # The service may already have committed before failing. Leave the
        # claim standing: a retry must be refused, and the attempt is reported
        # by incomplete_postings() for a person to verify.
        logger.exception(
            "ai_import posting failed after the claim was taken; claim left "
            "in place for document=%s", document.id,
        )
        raise

    _attach_source(db, document, AttachmentEntity.INVOICE, invoice.id)
    audit_service.write_event(
        db, AuditAction.CREATE, "ai_import_invoice", actor.id, invoice.id,
        after_value={
            "invoice_number": invoice.invoice_number,
            "total_amount": float(invoice.total_amount),
            "purchase_order_id": str(data.purchase_order_id) if data.purchase_order_id else None,
            "source_document": str(document.id),
            "is_legacy": document.is_legacy,
        },
        notes="Supplier liability recorded from an imported invoice. Payment status remains "
              "derived from recorded payments.",
    )
    return _complete(db, posting, invoice.id, invoice.invoice_number)


# ── Unsupported postings ──────────────────────────────────────────────────────

_UNSUPPORTED: dict[AIImportDocumentType, str] = {
    AIImportDocumentType.SUPPLIER_CREDIT_NOTE: (
        "This system has no credit note record, so a credit cannot be posted against the "
        "supplier balance. The credit note is stored as evidence and linked to the invoice "
        "it relates to; apply the credit manually when settling that invoice. "
        "See docs/AI_DOCUMENT_IMPORT_COMPLETION.md for this known gap."
    ),
    AIImportDocumentType.PAYMENT_PROOF: (
        "Proof of payment is stored as evidence only. Capture the payment on the payments "
        "screen against the invoice it settles so the invoice status is derived from a real "
        "payment record rather than from a document."
    ),
    AIImportDocumentType.UNKNOWN: (
        "The document type is not identified, so there is no posting path. "
        "Set the correct document type first."
    ),
}


# ── Entry point ───────────────────────────────────────────────────────────────

def post_document(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
    actor: User,
    *,
    destination: Optional[DeliveryDestination] = None,
    lot_id: Optional[uuid.UUID] = None,
    overrun_reason: Optional[str] = None,
) -> AIImportPosting:
    """
    Post a document through the path its type dictates.

    Callers must have already checked the policy verdict: this function trusts
    that a BLOCKED document never reaches it, and enforces only the invariants
    that belong to posting itself.

    `lot_id` and `overrun_reason` are accepted so the API contract stays stable,
    but imported receipts go to the project warehouse, so supplying them is
    rejected rather than quietly ignored.
    """
    doc_type = document.document_type

    if lot_id is not None or overrun_reason is not None:
        raise PostingRefused(
            "An imported delivery is received into the project warehouse, so a lot or "
            "an overrun reason cannot be applied at this step. Post the receipt first, "
            "then issue the material to the lot through the warehouse screen."
        )

    if doc_type in _UNSUPPORTED:
        raise PostingRefused(_UNSUPPORTED[doc_type])

    if doc_type == AIImportDocumentType.MATERIAL_REQUEST:
        posting = post_material_request(db, document, payload, actor)
    elif doc_type == AIImportDocumentType.PURCHASE_ORDER:
        posting = post_purchase_order(db, document, payload, actor)
    elif doc_type in (AIImportDocumentType.DELIVERY_NOTE, AIImportDocumentType.GOODS_RECEIVED_NOTE):
        posting = post_goods_receipt(
            db, document, payload, actor,
            destination=destination or DeliveryDestination.SITE_STORE,
        )
    elif doc_type == AIImportDocumentType.SUPPLIER_INVOICE:
        posting = post_supplier_invoice(db, document, payload, actor)
    else:
        raise PostingRefused(
            f"No posting path is implemented for {doc_type.value.replace('_', ' ').lower()}."
        )

    document.status = AIImportDocumentStatus.POSTED
    db.commit()
    return posting


def incomplete_postings(db: Session) -> list[AIImportPosting]:
    """
    Claims that never recorded an entity id.

    Each one is a process that died mid-post. The business record may or may
    not exist, so these are listed for a person to check rather than retried.
    """
    return (
        db.query(AIImportPosting)
        .filter(
            AIImportPosting.entity_id.is_(None),
            AIImportPosting.reversed_at.is_(None),
        )
        .order_by(AIImportPosting.posted_at.desc())
        .all()
    )


# ── Resolving an interrupted posting ──────────────────────────────────────────

# The record type each posting kind creates, for the "it does exist" path.
_POSTED_ENTITY_MODELS: dict[str, str] = {
    "material_request": "app.models.material_request:MaterialRequest",
    "purchase_order":   "app.models.purchase_order:PurchaseOrder",
    "goods_receipt":    "app.models.delivery:Delivery",
    "invoice":          "app.models.invoice:Invoice",
}


def _load_entity_model(entity_type: str):
    import importlib

    path = _POSTED_ENTITY_MODELS.get(entity_type)
    if not path:
        raise PostingRefused(f"'{entity_type}' is not a resolvable posting type.")
    module_name, class_name = path.split(":")
    return getattr(importlib.import_module(module_name), class_name)


def _entity_label(entity) -> str:
    for attr in ("invoice_number", "po_number", "request_number", "delivery_number"):
        value = getattr(entity, attr, None)
        if value:
            return str(value)
    return str(entity.id)[:8]


def resolve_incomplete_posting(
    db: Session,
    posting_id: uuid.UUID,
    resolution: str,
    actor: User,
    note: str,
    entity_id: Optional[uuid.UUID] = None,
) -> Optional[AIImportPosting]:
    """
    Close out a posting attempt that was interrupted after its claim was taken.

    An interrupted claim deliberately blocks every retry, because the business
    record may or may not have been created. That protects the books, but on
    its own it would leave the document permanently stuck. This is the way
    out, and it is a human decision backed by a look at the destination
    module:

      * `link`    — the record does exist. Its id is recorded against the
                    claim, finishing the posting; the document becomes POSTED.
      * `discard` — the record does not exist. The claim is deleted, freeing
                    the idempotency key so the document can be posted properly.

    Choosing `discard` when the record *does* exist would allow a duplicate,
    so the note explaining what was checked is mandatory and audited. `link`
    verifies the record genuinely exists, belongs to the document's project,
    and is not already claimed by another document.

    Returns the completed posting for `link`, and None for `discard` (the row
    is gone).
    """
    posting = db.get(AIImportPosting, posting_id)
    if posting is None:
        raise NotFoundError(f"Posting {posting_id} not found.")
    if posting.entity_id is not None:
        raise ConflictError(
            f"This posting already points at {posting.entity_type.replace('_', ' ')} "
            f"{posting.entity_label or posting.entity_id}; there is nothing to resolve."
        )
    if posting.reversed_at is not None:
        raise ConflictError("This posting attempt has already been resolved.")
    if not note or len(note.strip()) < 3:
        raise ValidationError(
            "Describe what you found in the destination module. This decision cannot "
            "be reconstructed later without it."
        )

    document = db.get(AIImportDocument, posting.document_id)
    if document is None:
        raise NotFoundError("The document behind this posting no longer exists.")

    if resolution == "link":
        if entity_id is None:
            raise ValidationError(
                "Supply the id of the record that was created, or choose discard if "
                "no record exists."
            )
        model = _load_entity_model(posting.entity_type)
        entity = db.get(model, entity_id)
        if entity is None:
            raise NotFoundError(
                f"No {posting.entity_type.replace('_', ' ')} with that id exists. "
                f"If the record was never created, choose discard instead."
            )
        entity_project = getattr(entity, "project_id", None)
        if document.project_id and entity_project and entity_project != document.project_id:
            raise ValidationError(
                "That record belongs to a different project than the document."
            )
        # Guard against attaching one record to two documents.
        clash = (
            db.query(AIImportPosting)
            .filter(
                AIImportPosting.entity_type == posting.entity_type,
                AIImportPosting.entity_id == entity_id,
                AIImportPosting.reversed_at.is_(None),
                AIImportPosting.id != posting.id,
            )
            .first()
        )
        if clash:
            raise ConflictError(
                f"That record is already recorded against import document "
                f"{clash.document_id}. Linking it here would claim one record twice."
            )

        posting.entity_id = entity_id
        posting.entity_label = _entity_label(entity)[:255]
        document.status = AIImportDocumentStatus.POSTED
        audit_service.write_event(
            db, AuditAction.UPDATE, "ai_import_posting_resolved", actor.id, posting.id,
            after_value={
                "resolution": "link",
                "entity_type": posting.entity_type,
                "entity_id": str(entity_id),
                "document_id": str(document.id),
                "note": note.strip(),
            },
            notes="Interrupted posting resolved: the record was found and linked.",
        )
        db.commit()
        db.refresh(posting)
        return posting

    if resolution == "discard":
        audit_service.write_event(
            db, AuditAction.UPDATE, "ai_import_posting_resolved", actor.id, posting.id,
            after_value={
                "resolution": "discard",
                "entity_type": posting.entity_type,
                "document_id": str(document.id),
                "note": note.strip(),
            },
            notes="Interrupted posting discarded: no record was created. The document "
                  "may be posted again.",
        )
        # Delete rather than merely flag, so the original idempotency key is
        # free again and _claim keeps working off the unchanging key.
        db.delete(posting)
        if document.status == AIImportDocumentStatus.POSTED:
            document.status = AIImportDocumentStatus.AWAITING_REVIEW
        db.commit()
        return None

    raise ValidationError(
        f"'{resolution}' is not a resolution. Use link when the record exists, "
        f"discard when it does not."
    )


def incomplete_posting_details(db: Session) -> list[dict]:
    """Interrupted postings with enough context for someone to go and check."""
    out: list[dict] = []
    for posting in incomplete_postings(db):
        document = db.get(AIImportDocument, posting.document_id)
        out.append({
            "posting_id": str(posting.id),
            "document_id": str(posting.document_id),
            "document_name": document.file_name if document else None,
            "document_status": document.status.value if document else None,
            "entity_type": posting.entity_type,
            "project_id": str(posting.project_id) if posting.project_id else None,
            "payload": posting.payload,
            "posted_by": str(posting.posted_by),
            "posted_at": posting.posted_at.isoformat() if posting.posted_at else None,
            "what_to_do": (
                f"Check the {posting.entity_type.replace('_', ' ')} list for this project. "
                f"If the record exists, resolve as link with its id. If it does not, "
                f"resolve as discard and the document can be posted again."
            ),
        })
    return out
