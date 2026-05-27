"""
Gmail → OCR → PO Matching pipeline test script — HMH Construction OS.

Simulates the full Phase E pipeline end-to-end without sending email or
touching production Gmail. Useful for validating the pipeline against a
real or synthetic attachment file.

Usage
-----
    python scripts/test_gmail_ocr_pipeline.py <filepath> [document_type]

Document types (default: INVOICE)
    INVOICE  DELIVERY_NOTE  PURCHASE_ORDER  FUEL_SLIP  PAYMENT_PROOF  QUOTE

Examples
--------
    python scripts/test_gmail_ocr_pipeline.py invoice.pdf
    python scripts/test_gmail_ocr_pipeline.py delivery.jpg DELIVERY_NOTE
    python scripts/test_gmail_ocr_pipeline.py po.pdf PURCHASE_ORDER

What the script does
--------------------
1.  Classifies the file using classify_document() (keyword + extension heuristics).
2.  Calls extract_document_data() — uses Google Vision if configured, else pytesseract.
3.  Runs _find_best_po_match() — 3-tier: exact PO number → supplier email → fuzzy name.
4.  Scores confidence with _score_match() (same weights as prod: 0.55 / 0.25 / 0.20).
5.  Checks for a duplicate invoice (if doc_type == INVOICE).
6.  Prints a full reconciliation suggestion dict — labelled requires_review=True.
7.  Prints a proof-pack summary if a matching PO is found.

All output is SUGGESTIONS ONLY.  Nothing is written to the database.
Human review and approval are always required before any record is created.
"""

import os
import sys
import json
import pprint

# ── Path bootstrap ────────────────────────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# ── Env ───────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend_dir, ".env"))


def _hr(char: str = "─", width: int = 72) -> None:
    print(char * width)


def _section(title: str) -> None:
    _hr()
    print(f"  {title}")
    _hr()


def _print_suggestion(s: dict) -> None:
    _section("RECONCILIATION SUGGESTION")
    print(f"  File           : {s.get('filename')}")
    print(f"  Document type  : {s.get('document_type')}")
    print(f"  Extraction     : {s.get('extraction_status')}")
    print(f"  Invoice #      : {s.get('invoice_number')}")
    print(f"  DN #           : {s.get('delivery_note_number')}")
    print(f"  PO # (doc)     : {s.get('po_number_from_doc')}")
    print(f"  Supplier name  : {s.get('supplier_name')}")
    print(f"  Supplier email : {s.get('supplier_email')}")
    print(f"  Total amount   : {s.get('total_amount')}")
    print(f"  Date           : {s.get('date')}")
    print()
    print(f"  Matched PO     : {s.get('matched_po') or '— none —'}")
    print(f"  Match conf.    : {s.get('match_confidence', 0.0):.0%}")
    print(f"  Issues         : {s.get('issues') or '(none)'}")
    print(f"  Warnings       : {s.get('extraction_warnings') or '(none)'}")
    print()
    req = s.get("requires_review", True)
    print(f"  ⚠  requires_review = {req}   ← human approval always required")


def _print_proof_pack(pack: dict) -> None:
    _section("PROOF PACK SUMMARY (read-only)")
    inv  = pack.get("invoice") or {}
    po   = pack.get("purchase_order") or {}
    sup  = pack.get("supplier") or {}
    flg  = pack.get("accounting_flags") or {}
    ocr  = pack.get("ocr_extraction")

    print(f"  Invoice        : {inv.get('number')} — R{inv.get('total', 0):,.2f}")
    print(f"  PO             : {po.get('number')} — R{po.get('total', 0):,.2f}")
    print(f"  Supplier       : {sup.get('name')} <{sup.get('email')}>")
    print()
    print(f"  Matched        : {flg.get('is_matched')}")
    print(f"  Ready to pay   : {flg.get('ready_for_payment')}")
    print(f"  Missing PO     : {flg.get('missing_po')}")
    print(f"  Missing DN     : {flg.get('missing_delivery_note')}")
    print(f"  Missing sig    : {flg.get('missing_signature')}")
    if ocr:
        print()
        print(f"  OCR status     : {ocr.get('status')}")
        print(f"  OCR doc type   : {ocr.get('document_type')}")
        print(f"  OCR fields     : {list((ocr.get('fields') or {}).keys()) or '(none)'}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    filepath = sys.argv[1]
    doc_type = sys.argv[2].upper() if len(sys.argv) > 2 else None

    if not os.path.isfile(filepath):
        print(f"ERROR: file not found: {filepath}")
        sys.exit(1)

    filename = os.path.basename(filepath)

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    _section("STEP 1 — CLASSIFY DOCUMENT")
    from app.services.gmail_reader_service import classify_document
    detected = classify_document(filename, filepath)
    effective = doc_type or detected
    print(f"  File           : {filename}")
    print(f"  Detected type  : {detected}")
    print(f"  Effective type : {effective}")

    # ── Step 2: Extract text / OCR ────────────────────────────────────────────
    _section("STEP 2 — OCR EXTRACTION")
    from app.services.document_ai_service import extract_document_data
    result = extract_document_data(filepath, effective)

    status   = result.get("status", "FAILED")
    raw_text = result.get("raw_text", "")
    fields   = result.get("fields") or {}
    items    = result.get("items") or []
    warnings = result.get("warnings") or []

    print(f"  Status         : {status}")
    print(f"  Raw text chars : {len(raw_text)}")
    print(f"  Warnings       : {warnings or '(none)'}")
    print()
    print("  Extracted fields:")
    for k, v in fields.items():
        print(f"    {k:20s} : {v}")
    if items:
        print()
        print(f"  Line items ({len(items)}):")
        for i, item in enumerate(items[:5], 1):
            print(f"    [{i}] {item}")
    if raw_text:
        print()
        snippet = raw_text[:600].replace("\n", " ↵ ")
        print(f"  Raw text snippet: {snippet}{'…' if len(raw_text) > 600 else ''}")

    # ── Step 3: PO match ──────────────────────────────────────────────────────
    _section("STEP 3 — PO MATCH (requires DB)")
    try:
        from app.core.database import SessionLocal
        from app.services.gmail_ocr_pipeline_service import (
            _find_best_po_match,
            _score_match,
            detect_duplicate_invoice,
        )

        db = SessionLocal()
        try:
            matched_po = _find_best_po_match(db, fields, effective)
            confidence, issues = _score_match(fields, effective, matched_po)

            if matched_po:
                print(f"  Matched PO     : {matched_po.po_number}")
                print(f"  Confidence     : {confidence:.0%}")
                print(f"  Issues         : {issues or '(none)'}")
            else:
                print("  No PO match found.")
                print(f"  Issues         : {issues}")

            # ── Step 4: Duplicate invoice check ───────────────────────────────
            if effective == "INVOICE" and fields.get("invoice_number"):
                _section("STEP 4 — DUPLICATE INVOICE CHECK")
                inv_num = fields["invoice_number"]
                is_dup = detect_duplicate_invoice(db, inv_num)
                print(f"  Invoice #      : {inv_num}")
                print(f"  Duplicate      : {'YES — review required' if is_dup else 'No'}")

            # ── Step 5: Reconciliation suggestion ─────────────────────────────
            _section("STEP 5 — RECONCILIATION SUGGESTION (synthetic, no att record)")
            suggestion = {
                "attachment_id":        None,
                "filename":             filename,
                "document_type":        effective,
                "extraction_status":    status,
                "invoice_number":       fields.get("invoice_number"),
                "delivery_note_number": fields.get("delivery_note_number"),
                "po_number_from_doc":   fields.get("po_number"),
                "supplier_name":        fields.get("supplier_name"),
                "supplier_email":       fields.get("supplier_email"),
                "total_amount":         fields.get("total_amount"),
                "date":                 fields.get("date"),
                "matched_po":           matched_po.po_number if matched_po else None,
                "matched_po_id":        str(matched_po.id) if matched_po else None,
                "match_confidence":     round(confidence, 2),
                "issues":               issues,
                "requires_review":      True,
                "extraction_warnings":  warnings,
            }
            _print_suggestion(suggestion)

            # ── Step 6: Proof pack (if invoice matched to PO) ─────────────────
            if matched_po and effective == "INVOICE":
                from app.models.invoice import Invoice
                invoice = (
                    db.query(Invoice)
                    .filter(Invoice.purchase_order_id == matched_po.id)
                    .order_by(Invoice.captured_at.desc())
                    .first()
                )
                if invoice:
                    _section("STEP 6 — PROOF PACK (most recent linked invoice)")
                    from app.services.procurement_matching_service import build_proof_pack
                    pack = build_proof_pack(invoice.id, db)
                    _print_proof_pack(pack)
                else:
                    _section("STEP 6 — PROOF PACK")
                    print("  No invoice linked to this PO yet — proof pack not available.")

        finally:
            db.close()

    except Exception as exc:
        print(f"  DB unavailable or error: {exc}")
        print("  Skipping PO match, duplicate check, and proof pack steps.")
        suggestion = {
            "attachment_id":        None,
            "filename":             filename,
            "document_type":        effective,
            "extraction_status":    status,
            "invoice_number":       fields.get("invoice_number"),
            "delivery_note_number": fields.get("delivery_note_number"),
            "po_number_from_doc":   fields.get("po_number"),
            "supplier_name":        fields.get("supplier_name"),
            "supplier_email":       fields.get("supplier_email"),
            "total_amount":         fields.get("total_amount"),
            "date":                 fields.get("date"),
            "matched_po":           None,
            "matched_po_id":        None,
            "match_confidence":     0.0,
            "issues":               ["no_db_connection"],
            "requires_review":      True,
            "extraction_warnings":  warnings,
        }
        _section("RECONCILIATION SUGGESTION (no DB — offline mode)")
        _print_suggestion(suggestion)

    _hr("═")
    print("  Pipeline complete.  requires_review=True on all output.")
    print("  No records were created or modified.")
    _hr("═")


if __name__ == "__main__":
    main()
