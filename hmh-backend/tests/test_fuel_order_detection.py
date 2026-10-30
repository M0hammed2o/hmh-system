"""
Telling a tank of diesel from a fuel filter.

Fuel is tracked in litres against a storage location; materials are tracked
in a warehouse. A purchase order for bulk fuel must leave the materials
path, or the delivery that follows receives diesel as though it were cement.

The opposite error is just as expensive and far easier to make. This company
buys a great deal of fuel-related hardware, and "OIL, FUEL. INLINE,
HYDRAULIC FILTERS" is a real line from its own repair history. Divert that
and a legitimate materials order is refused, with the buyer sent to a screen
that cannot record it.
"""

import pytest

from app.schemas.ai_import import (
    DocumentExtractionPayload, ExtractedField, ExtractedLineItem,
)
from app.services.ai_import_routing_service import _mentions_fuel


def _with_lines(*descriptions):
    payload = DocumentExtractionPayload()
    payload.line_items = [
        ExtractedLineItem(description=d, confidence=0.8) for d in descriptions
    ]
    return payload


# ── Bulk fuel ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("description", [
    "500 Litres Diesel 50PPM",          # PO-108, the real one
    "500 litres diesel delivered to tank",
    "Petrol 95 unleaded 200 litres",
    "Paraffin 20 litre drum",
    "Diesel 500ppm bulk",
])
def test_bulk_fuel_leaves_the_materials_path(description):
    assert _mentions_fuel(_with_lines(description)), description


def test_litres_outrank_a_part_word():
    """
    "Delivered to tank" would otherwise make a genuine bulk delivery look
    like hardware, because "tank" is a part word.
    """
    assert _mentions_fuel(_with_lines("1000 litres diesel into bulk tank"))


def test_a_grade_outranks_a_part_word():
    """Nobody buys a filter by the 50PPM."""
    assert _mentions_fuel(_with_lines("Diesel 50PPM tank fill"))


# ── Parts, which are ordinary materials ───────────────────────────────────────

@pytest.mark.parametrize("description", [
    "OIL, FUEL. INLINE, HYDRAULIC FILTERS",   # from the real repair history
    "Fuel filter element",
    "Diesel pump seal kit",
    "Fuel tank cap",
    "Fuel line hose 8mm",
    "Diesel injector nozzle",
    "Fuel gauge sender unit",
    "Water separator / fuel sedimenter",
])
def test_fuel_hardware_stays_an_ordinary_order(description):
    assert not _mentions_fuel(_with_lines(description)), description


def test_materials_with_no_fuel_word_are_untouched():
    assert not _mentions_fuel(_with_lines("Cement 42.5N", "Maxi brick", "Rebar Y12"))


def test_one_fuel_line_among_parts_is_enough():
    """
    A mixed order still has to be looked at by a person, and the fuel line is
    the reason.
    """
    assert _mentions_fuel(_with_lines("Fuel filter element", "500 Litres Diesel 50PPM"))


# ── The supplier's name is a hint, not a verdict ──────────────────────────────

def test_a_fuel_suppliers_name_does_not_divert_an_order_for_parts():
    """
    A fuel supplier sells filters too. The lines say what was bought.
    """
    payload = _with_lines("Fuel filter element", "Oil filter")
    payload.fields = {
        "supplier_name": ExtractedField(value="Trackside Fuels", confidence=0.9),
    }
    assert not _mentions_fuel(payload)


def test_the_header_is_used_when_no_line_could_be_read():
    """
    A thin extraction of a real fuel order still has to route correctly —
    that is the case the fallback exists for.
    """
    payload = DocumentExtractionPayload()
    payload.fields = {
        "supplier_name": ExtractedField(value="Trackside Diesel Supplies", confidence=0.9),
    }
    assert _mentions_fuel(payload)


def test_nothing_readable_at_all_is_not_fuel():
    assert not _mentions_fuel(DocumentExtractionPayload())
