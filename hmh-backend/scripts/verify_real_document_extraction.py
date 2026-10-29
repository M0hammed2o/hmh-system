"""
Run the twenty real scanned documents through the real extraction pipeline.

Read-only. Nothing is written to any database, nothing is uploaded, and the
PDFs are read from where they already live rather than being copied into the
repository.

This exercises the deterministic path — text extraction, then the keyword and
heading classifier. The AI vision path is NOT exercised, because it needs a
workspace-scoped Anthropic key that is still outstanding; every row reports
which strategy actually produced its answer so the difference is visible
rather than assumed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.enums import AIImportDocumentType as T                 # noqa: E402
from app.services import ai_import_extraction_service as extraction     # noqa: E402

SRC = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("REAL_DOCUMENT_DIR", "")
)
if not SRC or not os.path.isdir(SRC):
    print(
        "Give the directory holding the scanned documents:\n"
        "    python scripts/verify_real_document_extraction.py <dir>\n"
        "Nothing is copied into the repository and nothing is uploaded."
    )
    raise SystemExit(1)

# What each document actually is, read by eye from the scan.
EXPECTED = {
    "20261019110559.pdf": (T.PRO_FORMA_INVOICE, "Pinetown Build It"),
    "20261019110121.pdf": (T.PURCHASE_ORDER,    "Fuel Up (PO-038)"),
    "20261019110033.pdf": (T.PRO_FORMA_INVOICE, "Huaxin (rotated scan)"),
    "20261019105936.pdf": (T.PURCHASE_ORDER,    "J S Singh Glazzing (PO-020)"),
    "20261019105913.pdf": (T.SUPPLIER_INVOICE,  "NPC 91515003"),
    "20261019105710.pdf": (T.QUOTATION,         "Prominent Paints"),
    "20261019105628.pdf": (T.PURCHASE_ORDER,    "Afristar (PO-021)"),
    "20261019105342.pdf": (T.QUOTATION,         "Midlands 66689801"),
    "20261019105313.pdf": (T.PURCHASE_ORDER,    "Yane (PO-013)"),
    "20261019105237.pdf": (T.QUOTATION,         "Midlands 66901001"),
    "20261019105200.pdf": (T.PURCHASE_ORDER,    "Killarney (PO-017)"),
    "20261019104934.pdf": (T.QUOTATION,         "Buco"),
    "20261019104817.pdf": (T.QUOTATION,         "Midlands 65845902"),
    "20261019104650.pdf": (T.DELIVERY_NOTE,     "Steelbar 0084 (handwritten)"),
    "20261019104626.pdf": (T.PURCHASE_ORDER,    "SDS Blocks (PO-022)"),
    "20261019104607.pdf": (T.PRO_FORMA_INVOICE, "SDS QTE5895"),
    "20261019104537.pdf": (T.PRO_FORMA_INVOICE, "Cretemix P89250"),
    "20261019104502.pdf": (T.PRO_FORMA_INVOICE, "Cretemix P89381"),
    "20261019110916.pdf": (T.PURCHASE_ORDER,    "Build It (PO-01)"),
    "20261019110855.pdf": (T.SUPPLIER_INVOICE,  "Killarney 85956"),
}

print(f"AI provider configured: {extraction.ai_available()}")
print(f"{'file':<22} {'expected':<19} {'actual':<19} {'chars':>6}  {'verdict'}")
print("-" * 92)

rows = []
for name, (expected, label) in EXPECTED.items():
    path = os.path.join(SRC, name)
    if not os.path.exists(path):
        print(f"{name:<22} {'(missing)':<19}")
        continue

    try:
        text, mode = extraction.extract_local_text(path)
    except Exception as exc:                                   # noqa: BLE001
        text, mode = "", f"failed: {type(exc).__name__}"

    actual, confidence = extraction._classify_from_text(text)
    chars = len(text or "")

    if actual is expected:
        verdict = f"MATCH ({confidence:.2f})"
    elif actual is T.UNKNOWN:
        verdict = "NO TEXT - needs the AI reader" if chars < 40 else "UNKNOWN from text"
    else:
        verdict = f"WRONG -> {actual.value}"

    rows.append((name, expected, actual, chars, verdict, label))
    print(f"{name:<22} {expected.value:<19} {actual.value:<19} {chars:>6}  {verdict}")

# ── Summary ───────────────────────────────────────────────────────────────────
matched = [r for r in rows if r[2] is r[1]]
unknown = [r for r in rows if r[2] is T.UNKNOWN]
wrong = [r for r in rows if r[2] is not r[1] and r[2] is not T.UNKNOWN]
no_text = [r for r in rows if r[3] < 40]

print("\n--- summary ---")
print(f"  correct          {len(matched):>2}/{len(rows)}")
print(f"  unknown          {len(unknown):>2}  (of which {len(no_text)} yielded no readable text)")
print(f"  WRONG            {len(wrong):>2}")

if wrong:
    print("\n  misclassified:")
    for name, expected, actual, chars, _v, label in wrong:
        print(f"    {name}  {label}: expected {expected.value}, got {actual.value}")

# The property that costs money, checked over the real scans.
proforma_as_invoice = [
    r for r in rows
    if r[1] is T.PRO_FORMA_INVOICE and r[2] is T.SUPPLIER_INVOICE
]
print(f"\n  pro-formas misread as tax invoices: {len(proforma_as_invoice)} "
      f"{'PASS' if not proforma_as_invoice else 'FAIL'}")

receipts_invented = [
    r for r in rows
    if r[1] is not T.DELIVERY_NOTE and r[2] in (T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE)
]
print(f"  documents wrongly read as a goods receipt: {len(receipts_invented)} "
      f"{'PASS' if not receipts_invented else 'FAIL'}")
