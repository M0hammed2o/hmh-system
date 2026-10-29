"""
Run real scanned documents through the real extraction pipeline.

Read-only. Nothing is written to any database, nothing is uploaded, and the
PDFs are read from where they already live rather than being copied into the
repository.

This exercises whichever strategies are configured — vision when an AI
provider is available, otherwise text extraction and the heading classifier.
Every row reports what actually came back, so a blank result is visibly a
blank result rather than being mistaken for a correct one.

    python scripts/verify_real_document_extraction.py <pdf-dir> [expected.json]

The optional second argument is a file of expected classifications, so the
run can report accuracy as well as output:

    { "20261019104502.pdf": "PRO_FORMA_INVOICE", ... }

It is deliberately **not** kept in this repository. The expectations are read
by eye from the documents, which makes them a record of who was invoiced for
what — keep the file beside the documents, outside version control.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.enums import AIImportDocumentType as T                  # noqa: E402
from app.services import ai_import_extraction_service as extraction      # noqa: E402
from app.services import ai_import_routing_service as routing            # noqa: E402

SRC = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("REAL_DOCUMENT_DIR", "")
)
if not SRC or not os.path.isdir(SRC):
    print(
        "Give the directory holding the scanned documents:\n"
        "    python scripts/verify_real_document_extraction.py <dir> [expected.json]\n"
        "Nothing is copied into the repository and nothing is uploaded."
    )
    raise SystemExit(1)

EXPECTED: dict[str, str] = {}
if len(sys.argv) > 2:
    with open(sys.argv[2], encoding="utf-8") as fh:
        EXPECTED = json.load(fh)

pdfs = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".pdf"))
if EXPECTED:
    pdfs = [f for f in pdfs if f in EXPECTED] or pdfs

print(f"AI provider configured: {extraction.ai_available()}")
print(f"Documents: {len(pdfs)} in {SRC}\n")

header = (f"{'file':<24}{'classified as':<20}{'chars':>7}  "
          f"{'fields':>6}  {'destination':<24}{'verdict'}")
print(header)
print("-" * len(header))

rows = []
for name in pdfs:
    path = os.path.join(SRC, name)
    try:
        text, _mode = extraction.extract_local_text(path)
    except Exception:                                            # noqa: BLE001
        text = ""

    actual, confidence = extraction._classify_from_text(text)
    chars = len(text or "")

    fields = 0
    try:
        from app.services.document_ai_service import extract_document_data
        legacy = extraction._REGEX_TYPE_MAP.get(actual, "OTHER")
        result = extract_document_data(path, legacy) or {}
        fields = len(result.get("fields") or {})
    except Exception:                                            # noqa: BLE001
        pass

    destination = routing.destination_for(actual).key

    expected = EXPECTED.get(name)
    if expected is None:
        verdict = f"read ({confidence:.2f})" if actual is not T.UNKNOWN else "no reading"
    elif actual.value == expected:
        verdict = f"MATCH ({confidence:.2f})"
    elif actual is T.UNKNOWN:
        verdict = "NO TEXT - needs the AI reader" if chars < 40 else "UNKNOWN from text"
    else:
        verdict = f"WRONG - expected {expected}"

    rows.append((name, actual, expected, chars, fields))
    print(f"{name:<24}{actual.value:<20}{chars:>7}  {fields:>6}  "
          f"{destination:<24}{verdict}")

# ── Summary ───────────────────────────────────────────────────────────────────
unknown = [r for r in rows if r[1] is T.UNKNOWN]
no_text = [r for r in rows if r[3] < 40]
any_field = [r for r in rows if r[4] > 0]

print("\n--- summary ---")
print(f"  documents                      {len(rows):>3}")
print(f"  yielded no readable text       {len(no_text):>3}")
print(f"  classified as UNKNOWN          {len(unknown):>3}")
print(f"  yielded at least one field     {len(any_field):>3}")

if EXPECTED:
    graded = [r for r in rows if r[2] is not None]
    correct = [r for r in graded if r[1].value == r[2]]
    wrong = [r for r in graded if r[1].value != r[2] and r[1] is not T.UNKNOWN]
    print(f"  correct                        {len(correct):>3}/{len(graded)}")
    print(f"  WRONG                          {len(wrong):>3}")
    for name, actual, expected, _c, _f in wrong:
        print(f"    {name}: expected {expected}, got {actual.value}")

    # The two failures that cost money, checked over the real scans.
    proforma_as_payable = [
        r for r in graded
        if r[2] == T.PRO_FORMA_INVOICE.value and r[1] is T.SUPPLIER_INVOICE
    ]
    invented_receipt = [
        r for r in graded
        if r[2] != T.DELIVERY_NOTE.value
        and r[1] in (T.DELIVERY_NOTE, T.GOODS_RECEIVED_NOTE)
    ]
    print(f"\n  pro-formas read as tax invoices      {len(proforma_as_payable)}  "
          f"{'PASS' if not proforma_as_payable else 'FAIL'}")
    print(f"  documents invented as goods receipts {len(invented_receipt)}  "
          f"{'PASS' if not invented_receipt else 'FAIL'}")
else:
    print("\n  (no expectations file given, so accuracy is not graded)")
