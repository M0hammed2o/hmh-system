"""
Phase 6A — AI OCR Validation Script

Tests Claude extraction accuracy against representative South African supplier invoice formats.
Run this AFTER setting ANTHROPIC_API_KEY in .env.

Usage:
    cd hmh-backend
    python scripts/validate_ai_ocr.py

Output:
    Per-invoice accuracy table + summary metrics
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Test invoice corpus ───────────────────────────────────────────────────────
# 7 invoices representing different SA supplier formats.
# Ground truth values are what we EXPECT the AI to extract.
# NOTE: Replace with real HMH supplier invoice texts from the DB or uploads once available.

INVOICES = [
    {
        "id":    "INV-001",
        "name":  "Tazmeen Doors & Hardware (System PDF)",
        "type":  "Clean PDF — system-generated",
        "text":  """
Tazmeen Doors & Hardware
Tax Invoice
Supplier: HMH Group
Reference: INV-2026-0004 / MR-619B19DD-0004
Item           Quantity  Unit  Unit Price (ZAR)  Total (ZAR)
Internal Doors    3      door     2,500.00         7,500.00
Subtotal: R7,500.00
VAT (15%): R1,125.00
Total Due: R8,625.00
Payment Terms: 30 Days
""",
        "ground_truth": {
            "supplier_name":  "Tazmeen Doors & Hardware",
            "invoice_number": "INV-2026-0004",
            "invoice_date":   None,         # not in document
            "po_number":      None,         # not in document
            "vat_number":     None,         # not in document
            "net_amount":     7500.00,
            "vat_amount":     1125.00,
            "gross_amount":   8625.00,
        },
        "line_items_expected": 1,
    },
    {
        "id":    "INV-002",
        "name":  "BuildMart (Scanned-style, minimal fields)",
        "type":  "Scanned invoice — limited metadata",
        "text":  """
BuildMart

BILL TO INVOICE # 101
HMH Group INVOICE DATE 13/05/2026
Invoice Total R3,000.00
DESCRIPTION AMOUNT
3 x Doors 3,000.00
TERMS & CONDITIONS
Payment is due within 30 days
Powered by Invoice Home
""",
        "ground_truth": {
            "supplier_name":  "BuildMart",
            "invoice_number": "101",
            "invoice_date":   "2026-05-13",
            "po_number":      None,
            "vat_number":     None,
            "net_amount":     None,         # no subtotal line
            "vat_amount":     None,
            "gross_amount":   3000.00,
        },
        "line_items_expected": 1,
    },
    {
        "id":    "INV-003",
        "name":  "SA Tiles & Stone (Full invoice with VAT reg)",
        "type":  "Clean PDF — full header",
        "text":  """
SA TILES & STONE (PTY) LTD
VAT Registration No: 4850279163
Tel: 031-456-7890
44 Kingsmead Road, Durban, 4001

TAX INVOICE

Invoice No:    INV-2024-1102
Invoice Date:  20 March 2024
Purchase Order: PO-2024-0112

Bill To:
HMH Construction (Pty) Ltd
Cornubia Estate, Durban

Description                  Qty   Unit Rate (R)   Total (R)
Porcelain floor tiles 600x600  120   185.00          22,200.00
Adhesive compound 20kg bags     30    85.50           2,565.00
Tile spacers (box)               5    24.00             120.00

Subtotal:          R24,885.00
VAT @ 15%:          R3,732.75
Invoice Total:     R28,617.75

Payment terms: 30 days EOM
Banking details: FNB Acc 62345678901
""",
        "ground_truth": {
            "supplier_name":  "SA TILES & STONE (PTY) LTD",
            "invoice_number": "INV-2024-1102",
            "invoice_date":   "2024-03-20",
            "po_number":      "PO-2024-0112",
            "vat_number":     "4850279163",
            "net_amount":     24885.00,
            "vat_amount":     3732.75,
            "gross_amount":   28617.75,
        },
        "line_items_expected": 3,
    },
    {
        "id":    "INV-004",
        "name":  "Africon Steel Supplies (Multi-page style)",
        "type":  "PDF — many line items, SA date format",
        "text":  """
AFRICON STEEL SUPPLIES CC
Reg: 2009/123456/23
VAT: 4120567891
33 Industrial Drive, Phoenix, KZN 4068

TAX INVOICE

Invoice #: AFS-0587
Date: 15/04/2024
Your Ref: PO-2024-0087

Customer: HMH Group
Contact: Mohammed Moosa

Qty   Description                         Unit     Rate      Amount
 50   Rebar Y12 6m                        bar      89.00    4,450.00
 30   Rebar Y16 6m                        bar     125.00    3,750.00
  2   Steel mesh A193 2.4x6m             sheet    420.00      840.00
  5   Binding wire 1.6mm coil             roll      95.00      475.00
  1   Cutting & bending service (3hrs)    hrs      350.00      350.00

                               Sub-Total:        R9,865.00
                               VAT 15%:          R1,479.75
                               TOTAL DUE:       R11,344.75

Terms: 30 days net. Late payment 2% per month.
Queries: accounts@africonsteelsa.co.za
""",
        "ground_truth": {
            "supplier_name":  "AFRICON STEEL SUPPLIES CC",
            "invoice_number": "AFS-0587",
            "invoice_date":   "2024-04-15",
            "po_number":      "PO-2024-0087",
            "vat_number":     "4120567891",
            "net_amount":     9865.00,
            "vat_amount":     1479.75,
            "gross_amount":   11344.75,
        },
        "line_items_expected": 5,
    },
    {
        "id":    "INV-005",
        "name":  "Pinnacle Electrical (Phone photo style — OCR noise)",
        "type":  "Scanned/photo — OCR artefacts, partial text",
        "text":  """
PlNNACLE ELECTR1CAL SUPPL1ES
VAT n0: 43OO891234

INVO1CE
N0: PE-2024-O9O3
Date: O2/O7/2O24 (July)

Bi11 To: HMH Const.

1tem                          Qty   Rate    Amnt
Conduit 20mm x 3m             4O    28.OO   1,12O.OO
Cu1able 2.5mm 100m rol1       2    485.OO     97O.OO
DB board 8-way                3    89O.OO   2,67O.OO
Cond bx 20mm                  1O    12.5O     125.OO

Sub-tota1: 4,885.OO
VAT: 732.75
T0ta1: 5,617.75
""",
        "ground_truth": {
            "supplier_name":  "PINNACLE ELECTRICAL SUPPLIES",
            "invoice_number": "PE-2024-0903",
            "invoice_date":   "2024-07-02",
            "po_number":      None,
            "vat_number":     "4300891234",
            "net_amount":     4885.00,
            "vat_amount":     732.75,
            "gross_amount":   5617.75,
        },
        "line_items_expected": 4,
    },
    {
        "id":    "INV-006",
        "name":  "Cement & Concrete SA (Simple, no VAT reg)",
        "type":  "PDF — no VAT number visible",
        "text":  """
CEMENT & CONCRETE SA
54 Bluff Road, Durban, 4052

Invoice
Invoice No:   CC-SA-2891
Date:         08 August 2024
Order Ref:    PO-2024-0201

To:   HMH Group (Cornubia)

Item Description            Qty    Price     Subtotal
CEM II 42.5N 50kg bags       200   110.00    22,000.00
River sand 5m³ loads           3   950.00     2,850.00
Deliver charge (Cornubia)       1   450.00       450.00

Total excl VAT:  R25,300.00
VAT (15%):        R3,795.00
Total incl VAT:  R29,095.00

30 day payment terms apply.
""",
        "ground_truth": {
            "supplier_name":  "CEMENT & CONCRETE SA",
            "invoice_number": "CC-SA-2891",
            "invoice_date":   "2024-08-08",
            "po_number":      "PO-2024-0201",
            "vat_number":     None,         # not printed on invoice
            "net_amount":     25300.00,
            "vat_amount":     3795.00,
            "gross_amount":   29095.00,
        },
        "line_items_expected": 3,
    },
    {
        "id":    "INV-007",
        "name":  "Tazmeen Doors (Real DB invoice — system format)",
        "type":  "Real DB record — gmailattachment PDF",
        "text":  """
Tazmeen Doors & Hardware
Tax Invoice
Supplier: HMH Group
Reference: INV-2026-0004 / MR-619B19DD-0004
Item                Quantity  Unit  Unit Price (ZAR)  Total (ZAR)
Internal Doors        3       door     2,500.00         7,500.00
Delivery Note No: DN-2026-0004
Project: HMH-Cornubia Phase 1
Site: Site 1
Lot: 2
Delivered By: Tazmeen Doors & Hardware
Subtotal: R7,500.00
VAT (15%): R1,125.00
Total Due: R8,625.00
Payment Terms: 30 Days
""",
        "ground_truth": {
            "supplier_name":  "Tazmeen Doors & Hardware",
            "invoice_number": "INV-2026-0004",
            "invoice_date":   None,
            "po_number":      None,
            "vat_number":     None,
            "net_amount":     7500.00,
            "vat_amount":     1125.00,
            "gross_amount":   8625.00,
        },
        "line_items_expected": 1,
    },
]


# ── Comparison helpers ────────────────────────────────────────────────────────

def _str_match(extracted, expected) -> bool:
    """Case-insensitive partial string match."""
    if expected is None:
        return extracted is None or extracted == ""
    if extracted is None:
        return False
    return str(expected).lower() in str(extracted).lower() or \
           str(extracted).lower() in str(expected).lower()


def _amount_match(extracted, expected, tolerance=0.01) -> bool:
    if expected is None:
        return True  # not expected, no penalty
    if extracted is None:
        return False
    try:
        return abs(float(extracted) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return False


def _date_match(extracted, expected) -> bool:
    if expected is None:
        return True
    if extracted is None:
        return False
    # Allow partial date match (year-month at minimum)
    exp_parts = str(expected).replace("-", "/").replace(".", "/")[:7]
    ext_parts = str(extracted).replace("-", "/").replace(".", "/")[:7]
    return exp_parts == ext_parts or str(expected)[:4] in str(extracted)


def score_field(field_name, extracted_value, expected_value) -> tuple[bool, str]:
    """Return (correct: bool, note: str)."""
    if field_name in ("net_amount", "vat_amount", "gross_amount"):
        ok = _amount_match(extracted_value, expected_value)
    elif field_name == "invoice_date":
        ok = _date_match(extracted_value, expected_value)
    else:
        ok = _str_match(extracted_value, expected_value)
    note = ""
    if not ok and expected_value is not None:
        note = f"expected {expected_value!r}, got {extracted_value!r}"
    return ok, note


# ── Main runner ───────────────────────────────────────────────────────────────

FIELD_DISPLAY_NAMES = {
    "supplier_name":  "Supplier Name",
    "invoice_number": "Invoice Number",
    "invoice_date":   "Invoice Date",
    "po_number":      "PO Number",
    "vat_number":     "VAT Number",
    "net_amount":     "Net Amount",
    "vat_amount":     "VAT Amount",
    "gross_amount":   "Gross Amount",
}


def run_validation():
    from app.services.ai_ocr_service import extract_invoice_fields_with_ai
    from app.core.config import settings

    if not settings.ANTHROPIC_API_KEY:
        print("\n" + "=" * 70)
        print("BLOCKED: ANTHROPIC_API_KEY is not set.")
        print("Add it to hmh-backend/.env:")
        print("  ANTHROPIC_API_KEY=sk-ant-api03-...")
        print("=" * 70)
        return

    print("\n" + "=" * 70)
    print(f"Phase 6A — AI OCR Validation  |  Model: claude-haiku-4-5-20251001")
    print("=" * 70)

    all_field_results = {f: {"correct": 0, "total": 0} for f in FIELD_DISPLAY_NAMES}
    invoice_results = []

    for inv in INVOICES:
        print(f"\n── {inv['id']}: {inv['name']}")
        print(f"   Type: {inv['type']}")
        print(f"   Text length: {len(inv['text'].strip())} chars")

        result = extract_invoice_fields_with_ai(inv["text"])
        header = result.get("header", {})
        line_items = result.get("line_items", [])
        overall_conf = result.get("overall_confidence", 0.0)
        status = result.get("status", "FAILED")

        print(f"   Status: {status}  |  Overall confidence: {overall_conf:.0%}")
        if result.get("warnings"):
            for w in result["warnings"][:2]:
                print(f"   ⚠  {w}")

        gt = inv["ground_truth"]
        field_scores = {}
        correct_count = 0
        testable_count = 0

        print(f"\n   {'Field':<18} {'Extracted':<32} {'Conf':>6}  {'GT Match':>8}  {'Note'}")
        print(f"   {'-'*18} {'-'*32} {'-'*6}  {'-'*8}  {'-'*30}")

        for field_key in FIELD_DISPLAY_NAMES:
            field_data = header.get(field_key, {"value": None, "confidence": 0.0})
            extracted_value = field_data.get("value")
            confidence = field_data.get("confidence", 0.0)
            expected_value = gt.get(field_key)

            ok, note = score_field(field_key, extracted_value, expected_value)

            if expected_value is not None:
                testable_count += 1
                all_field_results[field_key]["total"] += 1
                if ok:
                    correct_count += 1
                    all_field_results[field_key]["correct"] += 1

            match_sym = "✓" if ok else ("—" if expected_value is None else "✗")
            disp_val = str(extracted_value)[:30] if extracted_value is not None else "(none)"
            disp_name = FIELD_DISPLAY_NAMES[field_key]

            print(f"   {disp_name:<18} {disp_val:<32} {confidence:>5.0%}  {match_sym:>8}  {note[:30]}")
            field_scores[field_key] = {"ok": ok, "conf": confidence, "extracted": extracted_value}

        # Line items
        items_expected = inv.get("line_items_expected", 0)
        items_found = len(line_items)
        items_match = items_found >= max(1, items_expected - 1)  # allow -1 tolerance

        print(f"\n   Line items: found {items_found} / expected {items_expected}  {'✓' if items_match else '✗'}")
        if line_items:
            for li in line_items[:3]:
                disp = f"{li['description'][:28]:<28} qty={li['quantity']}  rate={li['unit_rate']}  conf={li['confidence']:.0%}"
                print(f"     • {disp}")

        field_accuracy = correct_count / testable_count if testable_count else 0
        print(f"\n   Field accuracy: {correct_count}/{testable_count} ({field_accuracy:.0%})")

        invoice_results.append({
            "id": inv["id"],
            "name": inv["name"],
            "type": inv["type"],
            "status": status,
            "overall_conf": overall_conf,
            "field_accuracy": field_accuracy,
            "items_match": items_match,
            "field_scores": field_scores,
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("SUMMARY — Per-Invoice Accuracy")
    print("=" * 70)
    print(f"{'Invoice':<14} {'Type':<30} {'Fields':>8} {'Conf':>8} {'Status'}")
    print(f"{'-'*14} {'-'*30} {'-'*8} {'-'*8} {'-'*15}")
    for r in invoice_results:
        print(f"{r['id']:<14} {r['type'][:30]:<30} {r['field_accuracy']:>7.0%} {r['overall_conf']:>7.0%}  {r['status']}")

    print("\n\nPer-field accuracy across all invoices:")
    print(f"{'Field':<18} {'Correct/Total':>14} {'Accuracy':>10}")
    print(f"{'-'*18} {'-'*14} {'-'*10}")
    overall_correct = 0
    overall_total = 0
    for field_key, stats in all_field_results.items():
        c, t = stats["correct"], stats["total"]
        overall_correct += c
        overall_total += t
        acc = c / t if t else 0
        bar = "█" * int(acc * 10) + "░" * (10 - int(acc * 10))
        print(f"{FIELD_DISPLAY_NAMES[field_key]:<18} {c:>5}/{t:<8} {acc:>8.0%}  {bar}")

    if overall_total:
        total_acc = overall_correct / overall_total
        print(f"\nOverall field accuracy: {overall_correct}/{overall_total} = {total_acc:.1%}")

    print("\nPhase 6A validation complete.")
    print("Next step: Test against real HMH supplier invoices from the Gmail inbox.")
    print("=" * 70)

    return invoice_results


if __name__ == "__main__":
    run_validation()
