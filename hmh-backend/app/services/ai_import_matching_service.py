"""
AI Document Import — reconciliation engine.

Resolves an uploaded document's business context (project, site, supplier) and
links it into the procurement chain:

    Material Request -> Purchase Order -> Goods Receipt -> Supplier Invoice -> Payment

Order of arrival is irrelevant. Matching is recomputed from scratch every time
`rematch_document` runs, and posting a new record re-runs matching for the
documents that were waiting on it, so an invoice uploaded on Monday links
itself to a purchase order uploaded on Wednesday without anyone intervening.

Two rules shape everything here:

  * AI proposes, deterministic code decides. A match only reaches CONFIRMED
    through an exact reference hit or an explicit human decision. Every fuzzy
    result stays PROPOSED and keeps the document in review.
  * Ambiguity is never resolved silently. When two candidates score within
    AMBIGUITY_MARGIN of each other the match is recorded as AMBIGUOUS with both
    candidates listed, and the document cannot auto-post.

Every match carries a plain-language `explanation` for the UI.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.ai_import import AIImportDocument, AIImportMatch
from app.models.delivery import Delivery
from app.models.enums import AIImportDocumentType, AIImportMatchStatus
from app.models.invoice import Invoice
from app.models.item import Item
from app.models.material_request import MaterialRequest
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder
from app.models.site import Site
from app.models.supplier import Supplier
from app.schemas.ai_import import DocumentExtractionPayload

logger = get_logger(__name__)

# Target type used for recorded reference conflicts. They are never usable as
# matches; they exist so the policy engine can block on the evidence.
CONFLICT_TARGET_TYPE = "purchase_order_conflict"

# A candidate must beat the runner-up by this margin to be chosen at all.
AMBIGUITY_MARGIN = 0.08
# Below this, a fuzzy candidate is not even worth proposing.
MIN_PROPOSAL_SCORE = 0.60
# A name match at or above this is strong enough to propose as the supplier.
STRONG_NAME_SCORE = 0.85


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise(text: Optional[str]) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _similarity(a: Optional[str], b: Optional[str]) -> float:
    a_n, b_n = _normalise(a), _normalise(b)
    if not a_n or not b_n:
        return 0.0
    if a_n == b_n:
        return 1.0
    # A short name fully contained in a longer one is a strong signal
    # ("Build-It" vs "Build-It Durban North (Pty) Ltd").
    if len(a_n) >= 4 and (a_n in b_n or b_n in a_n):
        return max(0.88, SequenceMatcher(None, a_n, b_n).ratio())
    return SequenceMatcher(None, a_n, b_n).ratio()


def _ref_key(value: Optional[str]) -> str:
    """Comparison key for document references: case and punctuation insensitive."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


# ── Unit conversion ───────────────────────────────────────────────────────────

# Conversions to a canonical base so a PO in tonnes reconciles against a
# delivery note in kilograms. Deliberately small: only conversions that are
# unambiguous in construction supply are listed.
_UNIT_BASE: dict[str, tuple[str, Decimal]] = {
    "kg": ("kg", Decimal("1")),
    "kgs": ("kg", Decimal("1")),
    "kilogram": ("kg", Decimal("1")),
    "kilograms": ("kg", Decimal("1")),
    "t": ("kg", Decimal("1000")),
    "ton": ("kg", Decimal("1000")),
    "tons": ("kg", Decimal("1000")),
    "tonne": ("kg", Decimal("1000")),
    "tonnes": ("kg", Decimal("1000")),
    "g": ("kg", Decimal("0.001")),
    "l": ("l", Decimal("1")),
    "litre": ("l", Decimal("1")),
    "litres": ("l", Decimal("1")),
    "liter": ("l", Decimal("1")),
    "liters": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "kl": ("l", Decimal("1000")),
    "m": ("m", Decimal("1")),
    "metre": ("m", Decimal("1")),
    "metres": ("m", Decimal("1")),
    "meter": ("m", Decimal("1")),
    "meters": ("m", Decimal("1")),
    "mm": ("m", Decimal("0.001")),
    "cm": ("m", Decimal("0.01")),
    "km": ("m", Decimal("1000")),
    "m2": ("m2", Decimal("1")),
    "sqm": ("m2", Decimal("1")),
    "m3": ("m3", Decimal("1")),
    "cube": ("m3", Decimal("1")),
    "ea": ("ea", Decimal("1")),
    "each": ("ea", Decimal("1")),
    "no": ("ea", Decimal("1")),
    "unit": ("ea", Decimal("1")),
    "units": ("ea", Decimal("1")),
    "bag": ("bag", Decimal("1")),
    "bags": ("bag", Decimal("1")),
    "pocket": ("bag", Decimal("1")),
    "pockets": ("bag", Decimal("1")),
}


def convert_quantity(
    quantity: Optional[float], from_unit: Optional[str], to_unit: Optional[str]
) -> Optional[Decimal]:
    """
    Convert between units of the same dimension.

    Returns None when the conversion is not known — callers must then treat the
    quantities as incomparable rather than assume they are equal.
    """
    if quantity is None:
        return None
    qty = Decimal(str(quantity))
    f_key = (from_unit or "").strip().lower().rstrip(".")
    t_key = (to_unit or "").strip().lower().rstrip(".")
    if not f_key or not t_key or f_key == t_key:
        return qty
    f_base = _UNIT_BASE.get(f_key)
    t_base = _UNIT_BASE.get(t_key)
    if not f_base or not t_base or f_base[0] != t_base[0]:
        return None
    return (qty * f_base[1]) / t_base[1]


# ── Candidate scoring ─────────────────────────────────────────────────────────

class Candidate:
    """One possible match with the evidence behind its score."""

    __slots__ = ("target_id", "label", "score", "method", "reasons", "evidence")

    def __init__(
        self,
        target_id: Optional[uuid.UUID],
        label: str,
        score: float,
        method: str,
        reasons: list[str],
        evidence: Optional[dict] = None,
    ) -> None:
        self.target_id = target_id
        self.label = label
        self.score = round(min(1.0, max(0.0, score)), 4)
        self.method = method
        self.reasons = reasons
        self.evidence = evidence or {}


def _choose(candidates: list[Candidate]) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """
    Pick the winner.

    Returns (winner, ambiguous, runners_up). An ambiguous result still returns
    the top candidate so the UI can show what was considered, but the caller
    must record it as AMBIGUOUS and never act on it.
    """
    viable = sorted(
        [c for c in candidates if c.score >= MIN_PROPOSAL_SCORE],
        key=lambda c: c.score, reverse=True,
    )
    if not viable:
        return None, False, []
    if len(viable) == 1:
        return viable[0], False, []
    ambiguous = (viable[0].score - viable[1].score) < AMBIGUITY_MARGIN
    return viable[0], ambiguous, viable[1:4]


def _record(
    db: Session,
    document: AIImportDocument,
    target_type: str,
    candidate: Optional[Candidate],
    ambiguous: bool,
    runners_up: list[Candidate],
    *,
    confirmed: bool = False,
) -> Optional[AIImportMatch]:
    """Persist one match row. Returns None when there was nothing to record."""
    if candidate is None:
        return None

    if ambiguous:
        status = AIImportMatchStatus.AMBIGUOUS
        explanation = (
            f"Could not choose between {len(runners_up) + 1} candidates for {target_type}: "
            + "; ".join(
                f"{c.label} (score {c.score:.2f})" for c in [candidate, *runners_up]
            )
            + ". A person must pick the correct one."
        )
    else:
        status = AIImportMatchStatus.CONFIRMED if confirmed else AIImportMatchStatus.PROPOSED
        explanation = f"{target_type.replace('_', ' ').capitalize()} matched to {candidate.label} because " \
                      + "; ".join(candidate.reasons) + "."

    match = AIImportMatch(
        document_id=document.id,
        target_type=target_type,
        target_id=candidate.target_id,
        target_label=candidate.label[:255],
        status=status,
        method=candidate.method,
        score=Decimal(str(candidate.score)),
        explanation=explanation,
        evidence={
            **candidate.evidence,
            "alternatives": [
                {"label": c.label, "score": c.score, "id": str(c.target_id) if c.target_id else None}
                for c in runners_up
            ],
        },
        created_at=_now(),
    )
    db.add(match)
    return match


# ── Supplier ──────────────────────────────────────────────────────────────────

def match_supplier(db: Session, payload: DocumentExtractionPayload) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """
    Resolve the supplier.

    A VAT number match is treated as an identity match — it is a registered,
    unique identifier — while a name match alone only ever proposes.
    """
    name = payload.value("supplier_name")
    vat = payload.value("supplier_vat_number")
    reg = payload.value("supplier_registration_number")

    if not any((name, vat, reg)):
        return None, False, []

    vat_key = _ref_key(str(vat)) if vat else ""
    candidates: list[Candidate] = []

    for supplier in db.query(Supplier).filter(Supplier.is_active.is_(True)).all():
        reasons: list[str] = []
        score = 0.0

        if vat_key and _ref_key(supplier.vat_number) == vat_key:
            score = 1.0
            reasons.append(f"the VAT number {vat} matches exactly")
        if name:
            name_score = _similarity(str(name), supplier.name)
            if name_score >= MIN_PROPOSAL_SCORE:
                reasons.append(
                    f"the supplier name on the document ('{name}') matches '{supplier.name}'"
                    + ("" if name_score >= 0.99 else f" closely (similarity {name_score:.0%})")
                )
                score = max(score, name_score)
        if supplier.code and reg and _ref_key(supplier.code) == _ref_key(str(reg)):
            score = max(score, 0.95)
            reasons.append(f"the registration/account number {reg} matches the supplier code")

        if score >= MIN_PROPOSAL_SCORE:
            candidates.append(Candidate(
                supplier.id, supplier.name, score,
                "supplier_vat" if score == 1.0 else "supplier_fuzzy",
                reasons,
                {"extracted_name": name, "extracted_vat": vat},
            ))

    return _choose(candidates)


# ── Project ───────────────────────────────────────────────────────────────────

def match_project(
    db: Session, payload: DocumentExtractionPayload, batch_project_id: Optional[uuid.UUID] = None,
) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """
    Resolve the project from the document, falling back to the batch hint.

    The hint only wins when the document itself names no project: an uploader's
    guess must never override what the paperwork says.
    """
    name = payload.value("project_name")
    number = payload.value("project_number")
    site_name = payload.value("site_name")

    candidates: list[Candidate] = []
    projects = db.query(Project).all()

    for project in projects:
        reasons: list[str] = []
        score = 0.0

        if number:
            for attr in ("code", "project_number", "reference"):
                existing = getattr(project, attr, None)
                if existing and _ref_key(str(existing)) == _ref_key(str(number)):
                    score = 1.0
                    reasons.append(f"the project number {number} matches exactly")
                    break
        if name:
            name_score = _similarity(str(name), project.name)
            if name_score >= MIN_PROPOSAL_SCORE:
                reasons.append(f"the project name on the document ('{name}') matches '{project.name}'")
                score = max(score, name_score)

        if score >= MIN_PROPOSAL_SCORE:
            candidates.append(Candidate(
                project.id, project.name, score,
                "project_reference" if score == 1.0 else "project_fuzzy",
                reasons, {"extracted_name": name, "extracted_number": number},
            ))

    # Site name can identify the project when the project name is absent.
    if not candidates and site_name:
        for site in db.query(Site).all():
            site_score = _similarity(str(site_name), site.name)
            if site_score >= STRONG_NAME_SCORE:
                project = db.get(Project, site.project_id)
                if project:
                    candidates.append(Candidate(
                        project.id, project.name, site_score * 0.9, "project_via_site",
                        [f"the delivery site '{site_name}' belongs to this project"],
                        {"site_id": str(site.id), "site_name": site.name},
                    ))

    winner, ambiguous, runners = _choose(candidates)

    if winner is None and batch_project_id:
        project = db.get(Project, batch_project_id)
        if project:
            return Candidate(
                project.id, project.name, 0.6, "batch_hint",
                ["the document names no project, so the project selected for this upload batch was used"],
                {"source": "batch_hint"},
            ), False, []

    return winner, ambiguous, runners


def match_site(db: Session, payload: DocumentExtractionPayload, project_id: Optional[uuid.UUID]) -> Optional[Candidate]:
    """Resolve the site within an already-resolved project."""
    site_name = payload.value("site_name")
    if not site_name or not project_id:
        return None
    best: Optional[Candidate] = None
    for site in db.query(Site).filter(Site.project_id == project_id).all():
        score = _similarity(str(site_name), site.name)
        if score >= STRONG_NAME_SCORE and (best is None or score > best.score):
            best = Candidate(
                site.id, site.name, score, "site_fuzzy",
                [f"the site named on the document ('{site_name}') matches '{site.name}'"],
            )
    return best


# ── Procurement chain ─────────────────────────────────────────────────────────

def match_purchase_order(
    db: Session,
    payload: DocumentExtractionPayload,
    supplier_id: Optional[uuid.UUID],
    project_id: Optional[uuid.UUID],
) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """
    Find the purchase order this document relates to.

    An exact PO-number hit scores 1.0 and is the only path to a confirmed link.
    Without a reference the search falls back to supplier + amount + date
    proximity, which can only ever propose.
    """
    po_ref = payload.value("purchase_order_reference")
    candidates: list[Candidate] = []

    # Orders in this project are the candidates. Orders elsewhere are fetched
    # separately, only so that a reference pointing at another project's order
    # can be *reported* as a cross-project reference rather than silently
    # going unmatched — they are never selectable.
    query = db.query(PurchaseOrder)
    if project_id:
        query = query.filter(PurchaseOrder.project_id == project_id)
    orders = query.all()

    if po_ref:
        ref_key = _ref_key(str(po_ref))
        for po in orders:
            po_key = _ref_key(po.po_number)
            if not po_key:
                continue
            exact = po_key == ref_key
            # OCR commonly drops the "PO-" prefix or a leading zero block.
            contained = len(ref_key) >= 6 and (ref_key in po_key or po_key.endswith(ref_key))
            if exact or contained:
                reasons = [f"the purchase order reference {po_ref} matches {po.po_number}"]
                score = 1.0 if exact else 0.9
                if supplier_id and po.supplier_id == supplier_id:
                    reasons.append("the supplier is the same")
                elif supplier_id and po.supplier_id != supplier_id:
                    # A reference pointing at another supplier's order is a
                    # conflict, never a match. It is recorded separately by
                    # find_reference_conflicts, because a candidate scored
                    # below the proposal floor would be discarded by _choose
                    # and the evidence would never reach the database.
                    continue
                candidates.append(Candidate(
                    po.id, po.po_number, score, "exact_reference", reasons,
                    {"po_number": po.po_number, "extracted_reference": po_ref},
                ))

    # A purchase order imported from paper was given a freshly generated
    # number, so a later document quoting the *paper* number matches nothing
    # above. Resolve it through the posting that created the record.
    if not candidates and po_ref:
        imported = _po_imported_under_reference(db, str(po_ref), project_id)
        if imported is not None:
            candidates.append(Candidate(
                imported.id, imported.po_number, 0.97, "imported_reference",
                [f"reference {po_ref} is the number on the scanned order that created "
                 f"{imported.po_number}"],
                {"resolved_via_import": True, "paper_reference": str(po_ref)},
            ))

    if not candidates and supplier_id:
        total = payload.value("total_amount")
        issue_date = payload.value("issue_date")
        for po in orders:
            if po.supplier_id != supplier_id:
                continue
            reasons = ["the supplier is the same"]
            score = 0.55
            if total is not None and po.total_amount is not None:
                po_total = Decimal(str(po.total_amount))
                doc_total = Decimal(str(total))
                if po_total > 0:
                    delta = abs(po_total - doc_total) / po_total
                    if delta <= Decimal("0.01"):
                        score += 0.3
                        reasons.append(f"the document total {doc_total} matches the order total {po_total}")
                    elif delta <= Decimal("0.10"):
                        score += 0.1
                        reasons.append(
                            f"the document total {doc_total} is within 10% of the order total {po_total}"
                        )
            if issue_date and po.po_date:
                try:
                    doc_day = datetime.fromisoformat(str(issue_date)).date()
                    gap = abs((doc_day - po.po_date.date()).days)
                    if gap <= 60:
                        score += 0.05
                        reasons.append(f"the document date is within {gap} days of the order date")
                except (ValueError, TypeError):
                    pass
            if score >= MIN_PROPOSAL_SCORE:
                candidates.append(Candidate(
                    po.id, po.po_number, min(score, 0.89), "supplier_amount_date", reasons,
                    {"no_reference_on_document": True},
                ))

    return _choose(candidates)


def _po_imported_under_reference(
    db: Session, po_ref: str, project_id: Optional[uuid.UUID],
):
    """
    The purchase order created by importing a scanned order that carried this
    number on the paper.

    `po_service.create_po` mints its own `po_number`, so an imported
    historical order no longer carries the reference the supplier's later
    delivery notes and invoices quote. The import posting records the paper
    number, which is the only link between the two.
    """
    from app.models.ai_import import AIImportPosting

    ref_key = _ref_key(po_ref)
    if not ref_key:
        return None

    query = db.query(AIImportPosting).filter(
        AIImportPosting.entity_type == "purchase_order",
        AIImportPosting.entity_id.isnot(None),
        AIImportPosting.reversed_at.is_(None),
    )
    if project_id:
        query = query.filter(AIImportPosting.project_id == project_id)

    for posting in query.all():
        recorded = (posting.payload or {}).get("source_document_number")
        if recorded and _ref_key(str(recorded)) == ref_key:
            po = db.get(PurchaseOrder, posting.entity_id)
            if po is not None and (not project_id or po.project_id == project_id):
                return po
    return None


def find_reference_conflicts(
    db: Session,
    payload: DocumentExtractionPayload,
    supplier_id: Optional[uuid.UUID],
    project_id: Optional[uuid.UUID],
) -> list[Candidate]:
    """
    Purchase orders the document's reference points at but must not be used.

    Two kinds, both of which must be *recorded* rather than merely skipped:

      * `cross_project`     — the reference resolves to an order in another
        project. Posting here would move value across the project boundary.
      * `supplier_conflict` — the reference resolves to an order belonging to
        a different supplier than the document names.

    These are deliberately not returned as candidates: `_choose` discards
    anything below the proposal floor, so a low-scored conflict candidate
    would be silently dropped and the policy engine would never see it.
    `rematch_document` persists these directly as REJECTED matches whose
    evidence carries the flag.
    """
    po_ref = payload.value("purchase_order_reference")
    if not po_ref:
        return []
    ref_key = _ref_key(str(po_ref))
    if not ref_key:
        return []

    conflicts: list[Candidate] = []
    for po in db.query(PurchaseOrder).all():
        po_key = _ref_key(po.po_number)
        if not po_key:
            continue
        if not (po_key == ref_key or (len(ref_key) >= 6 and ref_key in po_key)):
            continue

        if project_id and po.project_id != project_id:
            conflicts.append(Candidate(
                po.id, po.po_number, 0.0, "cross_project_reference",
                [f"the reference {po_ref} matches {po.po_number}, which belongs to a "
                 f"different project"],
                {"cross_project": True, "other_project_id": str(po.project_id)},
            ))
        elif supplier_id and po.supplier_id != supplier_id:
            conflicts.append(Candidate(
                po.id, po.po_number, 0.0, "supplier_conflict_reference",
                [f"the reference {po_ref} matches {po.po_number}, but that order belongs "
                 f"to a different supplier"],
                {"supplier_conflict": True},
            ))
    return conflicts


def match_material_request(
    db: Session, payload: DocumentExtractionPayload, project_id: Optional[uuid.UUID],
) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    mr_ref = payload.value("material_request_reference") or payload.value("document_number")
    if not mr_ref:
        return None, False, []

    ref_key = _ref_key(str(mr_ref))
    query = db.query(MaterialRequest)
    if project_id:
        query = query.filter(MaterialRequest.project_id == project_id)

    candidates: list[Candidate] = []
    for mr in query.all():
        mr_key = _ref_key(mr.request_number)
        if not mr_key:
            continue
        if mr_key == ref_key:
            candidates.append(Candidate(
                mr.id, mr.request_number, 1.0, "exact_reference",
                [f"the material request number {mr_ref} matches {mr.request_number}"],
            ))
        elif len(ref_key) >= 6 and ref_key in mr_key:
            candidates.append(Candidate(
                mr.id, mr.request_number, 0.85, "partial_reference",
                [f"the reference {mr_ref} appears in {mr.request_number}"],
            ))
    return _choose(candidates)


def match_existing_invoice(
    db: Session, payload: DocumentExtractionPayload, supplier_id: Optional[uuid.UUID],
) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """
    Look for an invoice already in the system with this number and supplier.

    A hit means the liability already exists: this is the duplicate-invoice
    signal, not a relationship to build.
    """
    number = payload.value("document_number") or payload.value("invoice_reference")
    if not number or not supplier_id:
        return None, False, []

    key = _ref_key(str(number))
    candidates: list[Candidate] = []
    for invoice in db.query(Invoice).filter(Invoice.supplier_id == supplier_id).all():
        if _ref_key(invoice.invoice_number) == key:
            candidates.append(Candidate(
                invoice.id, invoice.invoice_number, 1.0, "exact_reference",
                [f"invoice {invoice.invoice_number} from this supplier is already captured"],
                {"duplicate": True, "status": str(invoice.status)},
            ))
    return _choose(candidates)


def match_existing_delivery(
    db: Session, payload: DocumentExtractionPayload, supplier_id: Optional[uuid.UUID],
) -> tuple[Optional[Candidate], bool, list[Candidate]]:
    """Find a delivery already recorded under this supplier delivery-note number."""
    number = payload.value("delivery_reference") or payload.value("document_number")
    if not number or not supplier_id:
        return None, False, []

    key = _ref_key(str(number))
    candidates: list[Candidate] = []
    for delivery in db.query(Delivery).filter(Delivery.supplier_id == supplier_id).all():
        for field in (delivery.supplier_delivery_note_number, delivery.delivery_number):
            if field and _ref_key(field) == key:
                candidates.append(Candidate(
                    delivery.id, field, 1.0, "exact_reference",
                    [f"delivery note {field} from this supplier is already recorded"],
                    {"already_received": str(delivery.delivery_status)},
                ))
                break
    return _choose(candidates)


# ── Catalogue items ───────────────────────────────────────────────────────────

def match_line_items(db: Session, payload: DocumentExtractionPayload) -> list[dict]:
    """
    Map each document line onto the material catalogue.

    Supplier wording rarely equals the catalogue name, so item_aliases — the
    existing table of alternative names — is searched alongside the name itself.

    Returns one entry per line, always: an unmatched line is reported with
    item_id None so the reviewer sees the gap rather than a silent omission.
    """
    items = db.query(Item).filter(Item.is_active.is_(True)).all()

    # alias text -> item id, so a supplier's own code or wording resolves.
    alias_index: dict[str, uuid.UUID] = {}
    for item in items:
        for alias in item.aliases:
            if alias.alias_name:
                alias_index[_ref_key(alias.alias_name)] = item.id
                alias_index.setdefault(_normalise(alias.alias_name), item.id)
    by_id = {item.id: item for item in items}

    results: list[dict] = []
    for index, line in enumerate(payload.line_items):
        best: Optional[Item] = None
        best_score = 0.0
        runner_score = 0.0

        # An exact alias or stock-code hit short-circuits the fuzzy search.
        alias_hit: Optional[uuid.UUID] = None
        for probe in (line.stock_code, line.description):
            if not probe:
                continue
            alias_hit = alias_index.get(_ref_key(probe)) or alias_index.get(_normalise(probe))
            if alias_hit:
                break
        if alias_hit and alias_hit in by_id:
            best, best_score, runner_score = by_id[alias_hit], 1.0, 0.0
        else:
            for item in items:
                score = _similarity(line.description, item.name) if line.description else 0.0
                if score > best_score:
                    runner_score, best_score, best = best_score, score, item
                elif score > runner_score:
                    runner_score = score

        matched = best is not None and best_score >= 0.72
        ambiguous = matched and (best_score - runner_score) < AMBIGUITY_MARGIN

        converted = None
        if matched and best is not None:
            converted = convert_quantity(line.quantity, line.unit, getattr(best, "default_unit", None))

        results.append({
            "index": index,
            "description": line.description,
            "stock_code": line.stock_code,
            "quantity": line.quantity,
            "unit": line.unit,
            "item_id": str(best.id) if matched and best and not ambiguous else None,
            "item_name": best.name if matched and best else None,
            "item_unit": getattr(best, "default_unit", None) if matched and best else None,
            "converted_quantity": float(converted) if converted is not None else None,
            "unit_convertible": converted is not None,
            "score": round(best_score, 4),
            "ambiguous": ambiguous,
            "explanation": (
                f"'{line.description}' matched catalogue item '{best.name}'"
                + (f" (similarity {best_score:.0%})" if best_score < 1.0 else " by stock code or alias")
                if matched and best and not ambiguous else
                f"'{line.description}' could not be matched to a single catalogue item"
            ),
        })
    return results


# ── Three-way comparison ──────────────────────────────────────────────────────

def compare_against_purchase_order(
    db: Session,
    payload: DocumentExtractionPayload,
    po_id: uuid.UUID,
    mode: str = "receipt",
) -> dict:
    """
    Compare a delivery note or an invoice against its purchase order.

    The two modes ask different questions, and conflating them produces false
    alarms on ordinary paperwork:

      * `receipt`  — a delivery note. The quantity is measured against what is
        still outstanding (ordered less already received), so a delivery of
        more than remains is an over-supply.
      * `billing`  — an invoice. The quantity is measured against what was
        ordered, and separately against what has actually been received. An
        invoice for goods already receipted is the normal case and must not be
        reported as over-supply; an invoice for goods *not* yet received is the
        overbilling signal that matters.

    Reports only what can be compared: where a unit cannot be converted, the
    line is reported as not comparable rather than as matching.
    """
    po = db.get(PurchaseOrder, po_id)
    if not po:
        return {"available": False, "reason": "Purchase order not found."}
    billing = mode == "billing"

    po_lines = list(po.order_items)
    discrepancies: list[dict] = []
    line_results: list[dict] = []

    for line in payload.line_items:
        best_poi = None
        best_score = 0.0
        for poi in po_lines:
            score = _similarity(line.description, poi.description)
            if score > best_score:
                best_score, best_poi = score, poi

        if best_poi is None or best_score < 0.65:
            entry = {
                "description": line.description,
                "matched_po_line": None,
                "status": "NOT_ON_ORDER",
                "message": f"'{line.description}' does not appear on purchase order {po.po_number}.",
            }
            line_results.append(entry)
            discrepancies.append(entry)
            continue

        ordered = Decimal(str(best_poi.quantity_ordered or 0))
        received_already = Decimal(str(best_poi.quantity_received or 0))
        doc_qty = convert_quantity(line.quantity, line.unit, best_poi.unit)

        entry: dict[str, Any] = {
            "description": line.description,
            "matched_po_line": str(best_poi.id),
            "po_description": best_poi.description,
            "po_unit": best_poi.unit,
            "ordered_quantity": float(ordered),
            "already_received": float(received_already),
            "document_quantity": line.quantity,
            "document_unit": line.unit,
            "status": "OK",
        }

        if doc_qty is None:
            entry["status"] = "UNIT_NOT_COMPARABLE"
            entry["message"] = (
                f"'{line.description}' is in {line.unit or 'an unstated unit'} but the order is in "
                f"{best_poi.unit or 'an unstated unit'}. The quantities cannot be compared automatically."
            )
            discrepancies.append(entry)
        else:
            entry["converted_quantity"] = float(doc_qty)
            outstanding = ordered - received_already

            if billing:
                # Billed more than was ever ordered.
                if doc_qty > ordered:
                    entry["status"] = "OVER_SUPPLY"
                    entry["message"] = (
                        f"'{line.description}': {doc_qty} {best_poi.unit or ''} invoiced exceeds "
                        f"the ordered quantity of {ordered}."
                    ).strip()
                    discrepancies.append(entry)
                # Billed for goods that have not been receipted.
                elif doc_qty > received_already:
                    entry["status"] = "BILLED_BEYOND_RECEIPT"
                    entry["message"] = (
                        f"'{line.description}': {doc_qty} invoiced but only {received_already} "
                        f"has been received. Confirm the delivery before paying for the balance."
                    )
                    discrepancies.append(entry)
                elif doc_qty < ordered:
                    entry["status"] = "PARTIAL"
                    entry["message"] = (
                        f"'{line.description}': {doc_qty} of {ordered} ordered — a partial invoice."
                    )
            else:
                if doc_qty > outstanding:
                    entry["status"] = "OVER_SUPPLY"
                    entry["message"] = (
                        f"'{line.description}': {doc_qty} {best_poi.unit or ''} exceeds the outstanding "
                        f"order quantity of {outstanding}."
                    ).strip()
                    discrepancies.append(entry)
                elif doc_qty < outstanding:
                    entry["status"] = "PARTIAL"
                    entry["message"] = (
                        f"'{line.description}': {doc_qty} of {outstanding} outstanding — a partial supply."
                    )

        if line.unit_price is not None and best_poi.rate is not None:
            po_rate = Decimal(str(best_poi.rate))
            doc_rate = Decimal(str(line.unit_price))
            entry["po_rate"] = float(po_rate)
            entry["document_rate"] = float(doc_rate)
            if po_rate > 0:
                delta = (doc_rate - po_rate) / po_rate
                entry["price_variance_pct"] = float(round(delta * 100, 2))
                if abs(delta) > Decimal("0.01"):
                    price_entry = {
                        **entry,
                        "status": "PRICE_DIFFERENCE",
                        "message": (
                            f"'{line.description}' is charged at {doc_rate} but was ordered at "
                            f"{po_rate} ({delta * 100:+.1f}%)."
                        ),
                    }
                    discrepancies.append(price_entry)

        line_results.append(entry)

    total = payload.value("total_amount")
    total_check: Optional[dict] = None
    if total is not None and po.total_amount is not None:
        doc_total = Decimal(str(total))
        po_total = Decimal(str(po.total_amount))
        diff = doc_total - po_total
        total_check = {
            "document_total": float(doc_total),
            "po_total": float(po_total),
            "difference": float(diff),
            "within_tolerance": abs(diff) <= Decimal("0.02"),
        }
        if not total_check["within_tolerance"]:
            discrepancies.append({
                "status": "TOTAL_DIFFERENCE",
                "message": (
                    f"The document total {doc_total} differs from the purchase order total "
                    f"{po_total} by {diff:+.2f}."
                ),
            })

    return {
        "available": True,
        "po_id": str(po.id),
        "po_number": po.po_number,
        "lines": line_results,
        "total_check": total_check,
        "discrepancies": discrepancies,
        "has_discrepancies": bool(discrepancies),
    }


# ── Orchestration ─────────────────────────────────────────────────────────────

def rematch_document(
    db: Session,
    document: AIImportDocument,
    payload: DocumentExtractionPayload,
) -> list[AIImportMatch]:
    """
    Recompute every match for one document.

    Every machine-generated match is cleared first, so a re-run produces a
    current picture rather than accumulating one. The rule is ownership, not
    status: anything with `decided_by IS NULL` was computed and is recomputed
    here, whatever state it reached. A human decision is kept, because it
    outranks any recomputation.

    Filtering on status instead would be a bug with teeth. `_record` writes
    some matches as CONFIRMED straight away (an exact reference hit, a
    duplicate invoice number), and those also have `decided_by IS NULL`. If
    they survived, correcting a misread invoice number would leave the old
    DUPLICATE_INVOICE_NUMBER block in place forever, and correcting a purchase
    order reference would leave two CONFIRMED order matches — with
    `best_match` free to return the superseded one and the goods receipt
    booked against the wrong order.
    """
    db.query(AIImportMatch).filter(
        AIImportMatch.document_id == document.id,
        AIImportMatch.decided_by.is_(None),
    ).delete(synchronize_session=False)

    human_decided = {
        m.target_type: m for m in
        db.query(AIImportMatch).filter(
            AIImportMatch.document_id == document.id,
            AIImportMatch.decided_by.isnot(None),
        ).all()
    }

    created: list[AIImportMatch] = []

    # Supplier
    if "supplier" in human_decided:
        document.supplier_id = human_decided["supplier"].target_id
    else:
        cand, ambiguous, runners = match_supplier(db, payload)
        match = _record(
            db, document, "supplier", cand, ambiguous, runners,
            confirmed=bool(cand and cand.method == "supplier_vat"),
        )
        if match:
            created.append(match)
        if cand and not ambiguous:
            document.supplier_id = cand.target_id

    # Project
    if "project" in human_decided:
        document.project_id = human_decided["project"].target_id
    else:
        batch_hint = document.batch.project_id if document.batch else None
        cand, ambiguous, runners = match_project(db, payload, batch_hint)
        match = _record(
            db, document, "project", cand, ambiguous, runners,
            confirmed=bool(cand and cand.method == "project_reference"),
        )
        if match:
            created.append(match)
        if cand and not ambiguous:
            document.project_id = cand.target_id

    # Site
    if "site" not in human_decided:
        site_cand = match_site(db, payload, document.project_id)
        if site_cand:
            match = _record(db, document, "site", site_cand, False, [])
            if match:
                created.append(match)
            document.site_id = site_cand.target_id
    elif human_decided["site"].target_id:
        document.site_id = human_decided["site"].target_id

    # Purchase order
    if "purchase_order" not in human_decided:
        cand, ambiguous, runners = match_purchase_order(
            db, payload, document.supplier_id, document.project_id
        )
        match = _record(
            db, document, "purchase_order", cand, ambiguous, runners,
            confirmed=bool(cand and cand.method == "exact_reference"),
        )
        if match:
            created.append(match)

    # Conflicting references — recorded even though they are never usable,
    # because the policy engine blocks on the evidence they carry.
    for conflict in find_reference_conflicts(
        db, payload, document.supplier_id, document.project_id
    ):
        db.add(AIImportMatch(
            document_id=document.id,
            target_type=CONFLICT_TARGET_TYPE,
            target_id=conflict.target_id,
            target_label=conflict.label[:255],
            status=AIImportMatchStatus.REJECTED,
            method=conflict.method,
            score=Decimal("0"),
            explanation="This document cannot use " + (conflict.label or "that order")
                        + " because " + "; ".join(conflict.reasons) + ".",
            evidence=conflict.evidence,
            created_at=_now(),
        ))

    # Material request
    if document.document_type in (
        AIImportDocumentType.MATERIAL_REQUEST,
        AIImportDocumentType.PURCHASE_ORDER,
    ) and "material_request" not in human_decided:
        cand, ambiguous, runners = match_material_request(db, payload, document.project_id)
        match = _record(
            db, document, "material_request", cand, ambiguous, runners,
            confirmed=bool(cand and cand.method == "exact_reference"),
        )
        if match:
            created.append(match)

    # Existing records that would make this a duplicate
    if document.document_type in (
        AIImportDocumentType.SUPPLIER_INVOICE,
        AIImportDocumentType.SUPPLIER_CREDIT_NOTE,
    ):
        cand, ambiguous, runners = match_existing_invoice(db, payload, document.supplier_id)
        match = _record(db, document, "existing_invoice", cand, ambiguous, runners, confirmed=True)
        if match:
            created.append(match)

    if document.document_type in (
        AIImportDocumentType.DELIVERY_NOTE,
        AIImportDocumentType.GOODS_RECEIVED_NOTE,
    ):
        cand, ambiguous, runners = match_existing_delivery(db, payload, document.supplier_id)
        match = _record(db, document, "existing_delivery", cand, ambiguous, runners, confirmed=True)
        if match:
            created.append(match)

    db.flush()
    return created


def confirmed_target(
    db: Session, document_id: uuid.UUID, target_type: str,
) -> Optional[uuid.UUID]:
    """The target id of a confirmed match, or None. Proposals never count."""
    match = (
        db.query(AIImportMatch)
        .filter(
            AIImportMatch.document_id == document_id,
            AIImportMatch.target_type == target_type,
            AIImportMatch.status == AIImportMatchStatus.CONFIRMED,
        )
        .order_by(AIImportMatch.score.desc().nullslast())
        .first()
    )
    return match.target_id if match else None


def best_match(
    db: Session, document_id: uuid.UUID, target_type: str,
) -> Optional[AIImportMatch]:
    """The strongest non-rejected match of a type, confirmed or proposed."""
    return (
        db.query(AIImportMatch)
        .filter(
            AIImportMatch.document_id == document_id,
            AIImportMatch.target_type == target_type,
            AIImportMatch.status.in_([
                AIImportMatchStatus.CONFIRMED, AIImportMatchStatus.PROPOSED,
            ]),
        )
        .order_by(AIImportMatch.status.desc(), AIImportMatch.score.desc().nullslast())
        .first()
    )


def related_documents(db: Session, document: AIImportDocument) -> list[dict]:
    """
    Other uploaded documents that share this one's business context.

    This is what makes out-of-order upload visible to the user: an invoice
    uploaded first will list the purchase order that arrived days later.
    """
    if not (document.supplier_id or document.project_id):
        return []

    query = db.query(AIImportDocument).filter(AIImportDocument.id != document.id)
    if document.supplier_id:
        query = query.filter(AIImportDocument.supplier_id == document.supplier_id)

    if document.project_id:
        query = query.filter(AIImportDocument.project_id == document.project_id)
    else:
        # No project resolved yet, so there is no project boundary to relate
        # within. Matching on supplier alone would list other projects' files
        # to whoever can see this unclassified upload, so the comparison is
        # confined to the uploader's own documents.
        query = query.filter(
            AIImportDocument.uploaded_by == document.uploaded_by,
            AIImportDocument.project_id.is_(None),
        )

    own_targets = {
        (m.target_type, m.target_id)
        for m in document.matches
        if m.target_id and m.status != AIImportMatchStatus.REJECTED
    }

    out: list[dict] = []
    for other in query.order_by(AIImportDocument.created_at.desc()).limit(50).all():
        shared = [
            m.target_type for m in other.matches
            if (m.target_type, m.target_id) in own_targets
        ]
        out.append({
            "id": str(other.id),
            "file_name": other.file_name,
            "document_type": other.document_type.value,
            "status": other.status.value,
            "created_at": other.created_at.isoformat() if other.created_at else None,
            "shared_links": sorted(set(shared)),
        })
    # Documents sharing an actual linked record come first.
    out.sort(key=lambda d: (not d["shared_links"], d["created_at"] or ""), reverse=False)
    return out[:20]
