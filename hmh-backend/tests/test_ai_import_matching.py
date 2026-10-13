"""
AI Document Import — reconciliation engine.

Covers supplier/project resolution, the procurement chain, unit conversion,
ambiguity handling and the three-way comparison against a purchase order.
Every test uses real database records created through the existing factories.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.enums import AIImportDocumentType, AIImportMatchStatus, RecordStatus
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_matching_service as matching
from tests.conftest import make_item, make_project, make_site, make_supplier, make_user
from tests.ai_import_fixtures import (
    delivery_note,
    field,
    line,
    make_import_document,
    raw_response,
    supplier_invoice,
)


def _payload(response: dict):
    return extraction._finalise(
        extraction._normalise(response, "vision", "anthropic", "stub")
    )


def _make_po(db, project_id, supplier_id, created_by, *, po_number=None, items=None, total=None):
    """Create a purchase order with line items directly."""
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=po_number or f"PO-{uuid.uuid4().hex[:8].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.APPROVED,
        po_date=now,
        subtotal_amount=0, vat_amount=0,
        total_amount=total if total is not None else 0,
        created_by=uuid.UUID(created_by),
        created_at=now, updated_at=now,
    )
    db.add(po)
    db.flush()
    for spec in (items or []):
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id,
            description=spec["description"],
            quantity_ordered=spec["quantity"],
            unit=spec.get("unit"),
            rate=spec.get("rate"),
            quantity_received=spec.get("received", 0),
            item_id=uuid.UUID(spec["item_id"]) if spec.get("item_id") else None,
            created_at=now,
        ))
    db.flush()
    db.refresh(po)
    return po


# ── Supplier matching ─────────────────────────────────────────────────────────

def test_exact_supplier_name_matches(db):
    supplier = make_supplier(db, name="Buildit Durban North")
    payload = _payload(supplier_invoice("Buildit Durban North"))

    cand, ambiguous, _ = matching.match_supplier(db, payload)

    assert cand is not None and not ambiguous
    assert str(cand.target_id) == supplier["id"]
    assert cand.score == 1.0


def test_fuzzy_supplier_name_matches_and_explains(db):
    make_supplier(db, name="Buildit Durban North (Pty) Ltd")
    payload = _payload(supplier_invoice("Buildit Durban North"))

    cand, ambiguous, _ = matching.match_supplier(db, payload)

    assert cand is not None and not ambiguous
    assert cand.method == "supplier_fuzzy"
    assert "Buildit" in " ".join(cand.reasons)


def test_vat_number_outranks_the_name(db):
    """A VAT number is a registered identifier; a trading name is not."""
    from app.models.supplier import Supplier

    right = db.get(Supplier, uuid.UUID(make_supplier(db, name="Totally Different Name")["id"]))
    right.vat_number = "4123456789"
    make_supplier(db, name="Acme Supplies")
    db.flush()

    response = supplier_invoice("Acme Supplies")
    response["fields"].append(field("supplier_vat_number", "4123456789"))
    payload = _payload(response)

    cand, _, _ = matching.match_supplier(db, payload)
    assert str(cand.target_id) == str(right.id)
    assert cand.method == "supplier_vat"


def test_two_near_identical_suppliers_are_ambiguous_not_guessed(db):
    make_supplier(db, name="Cement Direct Durban")
    make_supplier(db, name="Cement Direct Durbon")
    payload = _payload(supplier_invoice("Cement Direct Durban"))

    cand, ambiguous, runners = matching.match_supplier(db, payload)

    assert cand is not None
    assert ambiguous is True
    assert runners


def test_unknown_supplier_yields_no_match(db):
    make_supplier(db, name="Totally Unrelated Trading")
    payload = _payload(supplier_invoice("Zzqx Materials International"))

    cand, _, _ = matching.match_supplier(db, payload)
    assert cand is None


# ── Project matching ──────────────────────────────────────────────────────────

def test_project_matches_on_project_code(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    payload = _payload(supplier_invoice("Acme", project_code=project["code"]))

    cand, ambiguous, _ = matching.match_project(db, payload)

    assert cand is not None and not ambiguous
    assert str(cand.target_id) == project["id"]
    assert cand.score == 1.0


def test_batch_hint_is_used_only_when_the_document_names_no_project(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    payload = _payload(supplier_invoice("Acme", project_code=None))

    cand, _, _ = matching.match_project(db, payload, uuid.UUID(project["id"]))

    assert cand is not None
    assert cand.method == "batch_hint"
    assert "names no project" in " ".join(cand.reasons)


def test_document_project_overrides_the_batch_hint(db):
    owner = make_user(db, role="OWNER")
    named = make_project(db, owner["id"])
    hinted = make_project(db, owner["id"])
    payload = _payload(supplier_invoice("Acme", project_code=named["code"]))

    cand, _, _ = matching.match_project(db, payload, uuid.UUID(hinted["id"]))

    assert str(cand.target_id) == named["id"]


def test_site_name_resolves_the_project_when_the_project_is_unnamed(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    make_site(db, project["id"], name="Cornubia Block C")

    response = supplier_invoice("Acme", project_code=None)
    response["fields"].append(field("site_name", "Cornubia Block C"))
    payload = _payload(response)

    cand, _, _ = matching.match_project(db, payload)
    assert cand is not None
    assert str(cand.target_id) == project["id"]
    assert cand.method == "project_via_site"


# ── Purchase order matching ───────────────────────────────────────────────────

def test_invoice_matches_po_by_exact_reference(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    po = _make_po(db, project["id"], supplier["id"], owner["id"], po_number="PO-ABCD1234-0001")

    payload = _payload(supplier_invoice("Acme Supplies", po_reference="PO-ABCD1234-0001"))
    cand, ambiguous, _ = matching.match_purchase_order(
        db, payload, uuid.UUID(supplier["id"]), uuid.UUID(project["id"])
    )

    assert cand is not None and not ambiguous
    assert str(cand.target_id) == str(po.id)
    assert cand.method == "exact_reference"
    assert cand.score == 1.0


def test_po_reference_with_the_prefix_dropped_by_ocr_still_matches(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(db, project["id"], supplier["id"], owner["id"], po_number="PO-ABCD1234-0001")

    payload = _payload(supplier_invoice(supplier["name"], po_reference="ABCD1234-0001"))
    cand, _, _ = matching.match_purchase_order(
        db, payload, uuid.UUID(supplier["id"]), uuid.UUID(project["id"])
    )

    assert cand is not None
    assert str(cand.target_id) == str(po.id)


def test_reference_pointing_at_another_suppliers_po_is_not_matched(db):
    """
    A supplier conflict is evidence of a problem, not a match. It must never
    be selected, or an invoice would attach to the wrong supplier's order.
    """
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier_a = make_supplier(db, name="Supplier Alpha")
    supplier_b = make_supplier(db, name="Supplier Beta")
    _make_po(db, project["id"], supplier_b["id"], owner["id"], po_number="PO-CONFLICT-01")

    payload = _payload(supplier_invoice("Supplier Alpha", po_reference="PO-CONFLICT-01"))
    cand, _, _ = matching.match_purchase_order(
        db, payload, uuid.UUID(supplier_a["id"]), uuid.UUID(project["id"])
    )

    assert cand is None


def test_invoice_without_a_reference_falls_back_to_supplier_and_amount(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(db, project["id"], supplier["id"], owner["id"], total=13800.00)

    payload = _payload(supplier_invoice(supplier["name"], po_reference=None))
    cand, _, _ = matching.match_purchase_order(
        db, payload, uuid.UUID(supplier["id"]), uuid.UUID(project["id"])
    )

    assert cand is not None
    assert str(cand.target_id) == str(po.id)
    assert cand.method == "supplier_amount_date"
    # A heuristic match never scores high enough to look like a reference hit.
    assert cand.score < 0.9


def test_duplicate_invoice_number_for_the_same_supplier_is_found(db):
    from app.models.invoice import Invoice

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    now = datetime.now(timezone.utc)
    db.add(Invoice(
        invoice_number="INV-502",
        supplier_id=uuid.UUID(supplier["id"]),
        project_id=uuid.UUID(project["id"]),
        total_amount=13800.00,
        status=RecordStatus.DRAFT,
        captured_at=now, created_at=now, updated_at=now,
    ))
    db.flush()

    payload = _payload(supplier_invoice(supplier["name"], invoice_number="INV-502"))
    cand, _, _ = matching.match_existing_invoice(db, payload, uuid.UUID(supplier["id"]))

    assert cand is not None
    assert cand.evidence.get("duplicate") is True


# ── Unit conversion ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("qty,frm,to,expected", [
    (1, "t", "kg", 1000),
    (2500, "kg", "t", 2.5),
    (1, "m3", "m3", 1),
    (1500, "mm", "m", 1.5),
    (2, "kl", "l", 2000),
    (5, "bags", "bag", 5),
])
def test_unit_conversion(qty, frm, to, expected):
    assert float(matching.convert_quantity(qty, frm, to)) == pytest.approx(expected)


def test_incompatible_units_return_none_rather_than_a_wrong_number(db):
    """kg and m3 are not convertible; claiming they are would corrupt stock."""
    assert matching.convert_quantity(10, "kg", "m3") is None
    assert matching.convert_quantity(10, "bag", "l") is None


def test_unknown_unit_is_not_silently_treated_as_equal():
    assert matching.convert_quantity(10, "widgets", "kg") is None


# ── Catalogue items ───────────────────────────────────────────────────────────

def test_line_item_matches_catalogue_by_name(db):
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    payload = _payload(delivery_note("Acme", description="Cement 42.5N 50kg bag"))

    results = matching.match_line_items(db, payload)

    assert len(results) == 1
    assert results[0]["item_id"] == item["id"]
    assert results[0]["ambiguous"] is False


def test_line_item_matches_through_a_supplier_alias(db):
    from app.models.item import ItemAlias

    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    db.add(ItemAlias(
        item_id=uuid.UUID(item["id"]),
        alias_name="PPC SUREBUILD 50KG",
        created_at=datetime.now(timezone.utc),
    ))
    db.flush()

    payload = _payload(delivery_note("Acme", description="PPC SUREBUILD 50KG"))
    results = matching.match_line_items(db, payload)

    assert results[0]["item_id"] == item["id"]
    assert results[0]["score"] == 1.0


def test_unmatched_line_is_reported_rather_than_dropped(db):
    make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    payload = _payload(delivery_note("Acme", description="Zzqx proprietary compound"))

    results = matching.match_line_items(db, payload)

    assert len(results) == 1
    assert results[0]["item_id"] is None
    assert "could not be matched" in results[0]["explanation"]


# ── Three-way comparison ──────────────────────────────────────────────────────

def test_matching_invoice_against_po_reports_no_discrepancies(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"], total=13800.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag", "rate": 120.00}],
    )

    payload = _payload(supplier_invoice(supplier["name"], total="13800.00"))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    assert result["available"] is True
    assert result["has_discrepancies"] is False


def test_price_difference_against_the_po_is_detected(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"], total=12000.00,
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag", "rate": 120.00}],
    )

    # Invoiced at 150.00 against an ordered rate of 120.00.
    payload = _payload(supplier_invoice(
        supplier["name"], unit_price="150.00", line_total="15000.00",
        subtotal="15000.00", vat="2250.00", total="17250.00",
    ))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    codes = [d["status"] for d in result["discrepancies"]]
    assert "PRICE_DIFFERENCE" in codes
    price = next(d for d in result["discrepancies"] if d["status"] == "PRICE_DIFFERENCE")
    assert "150" in price["message"] and "120" in price["message"]


def test_over_supply_beyond_the_outstanding_order_is_detected(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"],
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100,
                "unit": "bag", "rate": 120.00, "received": 90}],
    )

    # Only 10 bags outstanding, but 50 are being delivered.
    payload = _payload(delivery_note(supplier["name"], quantity=50))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    assert any(d["status"] == "OVER_SUPPLY" for d in result["discrepancies"])


def test_partial_delivery_is_reported_as_partial_not_as_an_error(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"],
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag", "rate": 120.00}],
    )

    payload = _payload(delivery_note(supplier["name"], quantity=40))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    line_result = result["lines"][0]
    assert line_result["status"] == "PARTIAL"
    assert result["has_discrepancies"] is False   # a partial supply is normal


def test_item_not_on_the_order_is_flagged(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"],
        items=[{"description": "Cement 42.5N 50kg bag", "quantity": 100, "unit": "bag", "rate": 120.00}],
    )

    payload = _payload(delivery_note(supplier["name"], description="Diesel generator hire"))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    assert any(d["status"] == "NOT_ON_ORDER" for d in result["discrepancies"])


def test_tonnes_delivered_against_kilograms_ordered_are_converted(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"],
        items=[{"description": "Reinforcing steel", "quantity": 2000, "unit": "kg", "rate": 18.00}],
    )

    payload = _payload(delivery_note(
        supplier["name"], description="Reinforcing steel", quantity=2, unit="t",
    ))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    line_result = result["lines"][0]
    assert line_result["converted_quantity"] == pytest.approx(2000)
    assert line_result["status"] == "OK"


def test_incomparable_units_are_reported_not_assumed_equal(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db)
    po = _make_po(
        db, project["id"], supplier["id"], owner["id"],
        items=[{"description": "Ready mix concrete", "quantity": 10, "unit": "m3", "rate": 1500.00}],
    )

    payload = _payload(delivery_note(
        supplier["name"], description="Ready mix concrete", quantity=10, unit="kg",
    ))
    result = matching.compare_against_purchase_order(db, payload, po.id)

    assert any(d["status"] == "UNIT_NOT_COMPARABLE" for d in result["discrepancies"])


# ── Orchestration ─────────────────────────────────────────────────────────────

def test_rematch_resolves_and_records_the_full_context(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    po = _make_po(db, project["id"], supplier["id"], owner["id"], po_number="PO-REMATCH-01")

    document = make_import_document(
        db, uploaded_by=owner["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice(
        "Acme Supplies", po_reference="PO-REMATCH-01", project_code=project["code"],
    ))

    matching.rematch_document(db, document, payload)

    assert str(document.supplier_id) == supplier["id"]
    assert str(document.project_id) == project["id"]
    po_match = matching.best_match(db, document.id, "purchase_order")
    assert po_match is not None
    assert str(po_match.target_id) == str(po.id)
    assert po_match.status == AIImportMatchStatus.CONFIRMED
    assert "PO-REMATCH-01" in po_match.explanation


def test_rematch_preserves_a_human_decision(db):
    """A recomputation must not quietly undo what a reviewer chose."""
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    chosen = make_supplier(db, name="Chosen By Human")
    make_supplier(db, name="Acme Supplies")

    document = make_import_document(
        db, uploaded_by=owner["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    from app.models.ai_import import AIImportMatch
    db.add(AIImportMatch(
        document_id=document.id, target_type="supplier",
        target_id=uuid.UUID(chosen["id"]), status=AIImportMatchStatus.CONFIRMED,
        method="manual", decided_by=uuid.UUID(owner["id"]),
        decided_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    ))
    db.flush()

    payload = _payload(supplier_invoice("Acme Supplies", project_code=project["code"]))
    matching.rematch_document(db, document, payload)

    assert str(document.supplier_id) == chosen["id"]


def test_matching_explanations_are_human_readable(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    supplier = make_supplier(db, name="Acme Supplies")
    _make_po(db, project["id"], supplier["id"], owner["id"], po_number="PO-209")

    document = make_import_document(
        db, uploaded_by=owner["id"], document_type=AIImportDocumentType.SUPPLIER_INVOICE,
    )
    payload = _payload(supplier_invoice(
        "Acme Supplies", invoice_number="INV-502", po_reference="PO-209",
        project_code=project["code"],
    ))
    matching.rematch_document(db, document, payload)

    po_match = matching.best_match(db, document.id, "purchase_order")
    assert "PO-209" in po_match.explanation
    assert "because" in po_match.explanation
    assert po_match.explanation.endswith(".")
