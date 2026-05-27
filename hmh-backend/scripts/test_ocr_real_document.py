"""
OCR real-document test script — HMH Construction OS.

Usage:
    python scripts/test_ocr_real_document.py <filepath> [document_type]

Document types:
    INVOICE          (default)
    DELIVERY_NOTE
    PURCHASE_ORDER
    FUEL_SLIP
    PAYMENT_PROOF
    QUOTE

Examples:
    python scripts/test_ocr_real_document.py invoice.pdf INVOICE
    python scripts/test_ocr_real_document.py delivery_note.jpg DELIVERY_NOTE
    python scripts/test_ocr_real_document.py fuel_receipt.png FUEL_SLIP

Reads OCR config from .env. GOOGLE_APPLICATION_CREDENTIALS must be set for
Google Vision. Falls back to pytesseract if Vision is not configured.

Output:
    - Raw extracted text (truncated to 1500 chars)
    - Extracted structured fields
    - Match suggestions (PO, supplier fuzzy match)

OCR results are SUGGESTIONS only. Human review is always required.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.document_ai_service import extract_document_data, fuzzy_match_supplier

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

VALID_TYPES = {"INVOICE", "DELIVERY_NOTE", "PURCHASE_ORDER", "FUEL_SLIP", "PAYMENT_PROOF", "QUOTE"}


def _print_field(label: str, value, warn_if_none: bool = False) -> None:
    if value is not None and value != "":
        print(f"  {GREEN}✓{RESET}  {label:<28} {value}")
    elif warn_if_none:
        print(f"  {YELLOW}?{RESET}  {label:<28} {DIM}(not found){RESET}")
    else:
        print(f"  {DIM}—{RESET}  {label:<28} {DIM}(not applicable){RESET}")


def main() -> int:
    if len(sys.argv) < 2:
        print(f"\n{RED}Usage: python scripts/test_ocr_real_document.py <filepath> [document_type]{RESET}\n")
        print(f"Document types: {', '.join(sorted(VALID_TYPES))}")
        return 1

    filepath    = sys.argv[1]
    doc_type    = (sys.argv[2].upper() if len(sys.argv) >= 3 else "INVOICE")

    if not os.path.exists(filepath):
        print(f"\n{RED}File not found: {filepath}{RESET}\n")
        return 1

    if doc_type not in VALID_TYPES:
        print(f"\n{YELLOW}Unknown document type '{doc_type}'. Defaulting to INVOICE.{RESET}")
        doc_type = "INVOICE"

    print(f"\n{BOLD}OCR Document Test — HMH Construction OS{RESET}")
    print("─" * 55)
    print(f"  File        : {os.path.basename(filepath)}")
    print(f"  Type        : {doc_type}")
    print(f"  OCR Provider: {settings.OCR_PROVIDER}")
    print()

    # ── Run OCR ──────────────────────────────────────────────────────────────
    result = extract_document_data(filepath, doc_type)
    status = result["status"]

    status_color = {
        "EXTRACTED":         GREEN,
        "OCR_EXTRACTED":     CYAN,
        "NEEDS_REVIEW":      YELLOW,
        "EXTRACTION_FAILED": RED,
        "OCR_NOT_AVAILABLE": RED,
        "FAILED":            RED,
    }.get(status, YELLOW)

    print(f"{BOLD}Status:{RESET} {status_color}{status}{RESET}")

    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  {YELLOW}⚠{RESET}  {w}")

    # ── Raw text ─────────────────────────────────────────────────────────────
    raw = result.get("raw_text", "")
    if raw.strip():
        print(f"\n{BOLD}Extracted Text (first 1500 chars):{RESET}")
        print("─" * 55)
        preview = raw.strip()[:1500]
        print(preview)
        if len(raw.strip()) > 1500:
            print(f"{DIM}... [{len(raw.strip())} total chars]{RESET}")
        print("─" * 55)

    # ── Structured fields ─────────────────────────────────────────────────────
    fields = result.get("fields", {})
    print(f"\n{BOLD}Structured Fields:{RESET}")

    # Core fields (relevant to most types)
    _print_field("PO Number",            fields.get("po_number"),            warn_if_none=True)
    _print_field("Invoice Number",       fields.get("invoice_number"),       warn_if_none=(doc_type == "INVOICE"))
    _print_field("Delivery Note Number", fields.get("delivery_note_number"), warn_if_none=(doc_type == "DELIVERY_NOTE"))
    _print_field("Supplier Name",        fields.get("supplier_name"),        warn_if_none=True)
    _print_field("Supplier Email",       fields.get("supplier_email"))
    _print_field("Date",                 fields.get("date"),                 warn_if_none=True)
    _print_field("Total Amount",         fields.get("total_amount") and f"R{fields['total_amount']:,.2f}", warn_if_none=True)

    # Type-specific
    if doc_type == "INVOICE":
        _print_field("Subtotal",         fields.get("subtotal") and f"R{fields['subtotal']:,.2f}")
        _print_field("VAT Amount",       fields.get("vat_amount") and f"R{fields['vat_amount']:,.2f}")
        _print_field("Due Date",         fields.get("due_date"))

    if doc_type == "DELIVERY_NOTE":
        _print_field("Received By",      fields.get("received_by"))

    if doc_type == "FUEL_SLIP":
        _print_field("Station Name",         fields.get("station_name"))
        _print_field("Litres",               fields.get("litres") and f"{fields['litres']:.2f} L")
        _print_field("Vehicle Registration", fields.get("vehicle_registration"), warn_if_none=True)
        _print_field("Odometer (km)",        fields.get("odometer") and f"{fields['odometer']:,.0f}")

    if doc_type == "PAYMENT_PROOF":
        _print_field("Paid Amount",      fields.get("paid_amount") and f"R{fields['paid_amount']:,.2f}", warn_if_none=True)
        _print_field("Reference Number", fields.get("reference_number"), warn_if_none=True)
        _print_field("Beneficiary",      fields.get("beneficiary"),      warn_if_none=True)
        _print_field("Payment Date",     fields.get("payment_date"))

    # ── Line items ────────────────────────────────────────────────────────────
    items = result.get("items", [])
    if items:
        print(f"\n{BOLD}Line Items ({len(items)} found):{RESET}")
        for i, item in enumerate(items[:10], 1):
            qty   = item.get("quantity")
            price = item.get("unit_price")
            total = item.get("line_total")
            desc  = item.get("description", "")[:50]
            unit  = item.get("unit", "")
            line  = f"  {i:2}. {desc:<50} {str(qty or ''):<8} {unit:<8}"
            if price:
                line += f"  R{price:>10,.2f}"
            if total:
                line += f"  →  R{total:>10,.2f}"
            print(line)
        if len(items) > 10:
            print(f"  {DIM}... and {len(items) - 10} more items{RESET}")

    # ── Match suggestions ─────────────────────────────────────────────────────
    print(f"\n{BOLD}Match Suggestions:{RESET}")
    print(f"  {YELLOW}⚠  All suggestions require human review before any action is taken.{RESET}")

    po_num = fields.get("po_number")
    if po_num:
        print(f"  PO reference found in document: {CYAN}{po_num}{RESET}")
        print(f"    → Search for this PO in the system to link this document.")
    else:
        print(f"  {DIM}No PO number found — manual PO lookup required.{RESET}")

    supplier_name = fields.get("supplier_name")
    if supplier_name:
        print(f"  Extracted supplier name: {CYAN}{supplier_name}{RESET}")
        print(f"    → Run with a live DB connection to fuzzy-match against supplier records.")

    # ── Human review reminder ─────────────────────────────────────────────────
    print(f"\n{BOLD}Human Review Required:{RESET}")
    print(f"  {YELLOW}All extracted values are SUGGESTIONS only.{RESET}")
    print("  • Verify reference numbers against physical documents")
    print("  • Confirm amounts match the original document exactly")
    if doc_type == "INVOICE":
        print("  • Do NOT approve invoices based on OCR alone")
    elif doc_type == "PAYMENT_PROOF":
        print("  • Do NOT record payments based on OCR alone")
    elif doc_type == "DELIVERY_NOTE":
        print("  • Do NOT confirm deliveries based on OCR alone")

    print()
    return 0 if status in ("EXTRACTED", "OCR_EXTRACTED") else 1


if __name__ == "__main__":
    sys.exit(main())
