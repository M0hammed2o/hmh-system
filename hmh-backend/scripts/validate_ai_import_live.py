"""
Live extraction check against the fictional sample documents.

This is `docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` section 4 as one
command. It calls the real Anthropic API on the four generated sample PDFs,
compares what comes back against the known answer key, and prints a verdict.

It is safe to run at any time:
  * the documents are entirely fictional — no HMH data leaves the network
  * nothing is written to the database and nothing is posted
  * it reads no business records

    python scripts/validate_ai_import_live.py [sample_dir]

Exit code 0 = pass, 1 = marginal, 2 = fail, 3 = could not run.

Cost: roughly $0.02–0.10 at claude-opus-5-5 rates for all four documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings                                 # noqa: E402
from app.models.enums import AIImportDocumentType                    # noqa: E402
from app.services import ai_import_extraction_service as extraction  # noqa: E402

# Imported from the generator so the answer key cannot drift from the samples.
from scripts.generate_ai_import_samples import (                     # noqa: E402
    LINES,
    PROJECT,
    SUPPLIER,
    VAT_RATE,
    generate,
)

GREEN, AMBER, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _subtotal() -> float:
    return round(sum(q * p for _, q, _, p in LINES), 2)


def _vat() -> float:
    return round(_subtotal() * VAT_RATE / 100, 2)


def _total() -> float:
    return round(_subtotal() + _vat(), 2)


# What each sample document must yield. Only fields the document actually
# carries are listed — a field absent from the paper is not a failure.
EXPECTED: dict[str, dict] = {
    "01_material_request": {
        "document_type": AIImportDocumentType.MATERIAL_REQUEST,
        "fields": {
            "document_number": "MR-SAMPLE-014",
            "issue_date": "2026-03-04",
            "project_number": PROJECT["code"],
        },
        "line_count": len(LINES),
        "critical": ("document_number",),
    },
    "02_purchase_order": {
        "document_type": AIImportDocumentType.PURCHASE_ORDER,
        "fields": {
            "document_number": "PO-SAMPLE-2291",
            "supplier_name": SUPPLIER["name"],
            "supplier_vat_number": SUPPLIER["vat"],
            "total_amount": _total(),
            "subtotal_amount": _subtotal(),
            "vat_amount": _vat(),
        },
        "line_count": len(LINES),
        "critical": ("document_number", "supplier_name", "total_amount"),
    },
    "03_delivery_note": {
        "document_type": AIImportDocumentType.DELIVERY_NOTE,
        "fields": {
            "supplier_name": SUPPLIER["name"],
            "purchase_order_reference": "PO-SAMPLE-2291",
            "delivery_date": "2026-03-18",
        },
        "line_count": len(LINES),
        "critical": ("supplier_name", "purchase_order_reference"),
    },
    "04_supplier_invoice": {
        "document_type": AIImportDocumentType.SUPPLIER_INVOICE,
        "fields": {
            "document_number": "INV-SAMPLE-50231",
            "issue_date": "2026-03-20",
            "due_date": "2026-04-19",
            "supplier_name": SUPPLIER["name"],
            "supplier_vat_number": SUPPLIER["vat"],
            "purchase_order_reference": "PO-SAMPLE-2291",
            "subtotal_amount": _subtotal(),
            "vat_amount": _vat(),
            "total_amount": _total(),
        },
        "line_count": len(LINES),
        "critical": ("document_number", "supplier_name", "total_amount"),
    },
}


def _same(expected, actual) -> bool:
    if expected is None or actual is None:
        return expected == actual
    if isinstance(expected, (int, float)):
        try:
            return abs(float(actual) - float(expected)) <= 0.02
        except (TypeError, ValueError):
            return False
    # Text: compare case-insensitively, ignoring punctuation and spacing, so
    # "Umhlanga Building Supplies CC" matches "UMHLANGA BUILDING SUPPLIES CC".
    import re
    norm = lambda v: re.sub(r"[^a-z0-9]", "", str(v).lower())       # noqa: E731
    return norm(expected) == norm(actual)


def main() -> int:
    sample_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_documents")

    print("=" * 78)
    print("AI DOCUMENT IMPORT — LIVE EXTRACTION CHECK")
    print("=" * 78)

    if not extraction.ai_available():
        print(f"\n{RED}Cannot run: ANTHROPIC_API_KEY is not configured.{RESET}")
        print("\nSet it in the environment (never in a committed file) and re-run:")
        print("  Render   -> hmh-test-backend -> Environment -> ANTHROPIC_API_KEY")
        print("  Locally  -> add it to hmh-backend/.env (gitignored)")
        return 3

    model = extraction.ai_model()
    print(f"\nModel:   {model}")
    print(f"Samples: {sample_dir.resolve()}")

    if not sample_dir.exists() or not list(sample_dir.glob("*.pdf")):
        print(f"{DIM}Samples not found — generating them.{RESET}")
        generate(sample_dir)

    print(f"\n{DIM}All four documents are fictional. Nothing in them is HMH data.{RESET}\n")

    results: list[tuple[str, int, int, list[str], list[str]]] = []
    total_cost = 0.0
    total_in = total_out = 0

    for stem, spec in EXPECTED.items():
        matches = sorted(sample_dir.glob(f"{stem}*.pdf"))
        if not matches:
            print(f"{RED}MISSING{RESET} {stem}: no sample file")
            results.append((stem, 0, len(spec["fields"]), ["file missing"], []))
            continue
        path = matches[0]
        content = path.read_bytes()

        print(f"{path.name}")
        try:
            payload = extraction.analyse_document(
                file_bytes=content,
                mime_type="application/pdf",
                file_path=str(path),
                file_name=path.name,
            )
        except Exception as exc:                                     # noqa: BLE001
            print(f"  {RED}extraction failed:{RESET} {type(exc).__name__}: {exc}\n")
            results.append((stem, 0, len(spec["fields"]), [f"{type(exc).__name__}"], []))
            continue

        if payload.cost_usd:
            total_cost += payload.cost_usd
        total_in += payload.input_tokens or 0
        total_out += payload.output_tokens or 0

        wrong: list[str] = []
        missing: list[str] = []
        correct = 0

        type_ok = payload.document_type == spec["document_type"]
        mark = f"{GREEN}ok{RESET}" if type_ok else f"{RED}wrong{RESET}"
        print(f"  type              {payload.document_type.value:22} {mark}")
        if not type_ok:
            wrong.append(f"type={payload.document_type.value}")

        for name, want in spec["fields"].items():
            got = payload.value(name)
            if got is None or str(got).strip() == "":
                print(f"  {name:18}{DIM}(not read){RESET:22} {AMBER}missing{RESET}")
                missing.append(name)
            elif _same(want, got):
                correct += 1
                print(f"  {name:18}{str(got)[:22]:22} {GREEN}ok{RESET}")
            else:
                print(f"  {name:18}{str(got)[:22]:22} {RED}expected {want}{RESET}")
                wrong.append(name)

        n_lines = len(payload.line_items)
        lines_ok = n_lines == spec["line_count"]
        mark = f"{GREEN}ok{RESET}" if lines_ok else f"{AMBER}expected {spec['line_count']}{RESET}"
        print(f"  line items        {n_lines:<22} {mark}")
        if not lines_ok:
            wrong.append(f"line_count={n_lines}")

        failed_sums = [c for c in payload.arithmetic_checks if not c.passed]
        if payload.arithmetic_checks:
            if failed_sums:
                print(f"  arithmetic        {RED}{len(failed_sums)} check(s) failed{RESET}")
                for c in failed_sums[:2]:
                    print(f"                    {DIM}{c.message}{RESET}")
            else:
                print(f"  arithmetic        {GREEN}all {len(payload.arithmetic_checks)} checks pass{RESET}")

        print(f"  {DIM}confidence {payload.overall_confidence:.0%} · "
              f"{payload.extraction_mode} · {payload.input_tokens}+{payload.output_tokens} tokens "
              f"· ${payload.cost_usd or 0:.4f}{RESET}\n")

        results.append((stem, correct, len(spec["fields"]), wrong, missing))

    # ── Verdict ──────────────────────────────────────────────────────────
    print("=" * 78)
    total_fields = sum(r[2] for r in results)
    total_correct = sum(r[1] for r in results)
    accuracy = (total_correct / total_fields * 100) if total_fields else 0

    critical_failures: list[str] = []
    for stem, _, _, wrong, missing in results:
        for field in EXPECTED.get(stem, {}).get("critical", ()):
            if field in wrong or field in missing:
                critical_failures.append(f"{stem}.{field}")

    print(f"Fields correct: {total_correct}/{total_fields} ({accuracy:.0f}%)")
    print(f"Cost:           ${total_cost:.4f} for {len(results)} documents "
          f"({total_in} in / {total_out} out tokens)")

    if critical_failures:
        print(f"\n{RED}VERDICT: FAIL{RESET}")
        print("  These must be read correctly and were not:")
        for f in critical_failures:
            print(f"    - {f}")
        print("\n  Do not pilot. Tune _SYSTEM_PROMPT in")
        print("  app/services/ai_import_extraction_service.py and re-run.")
        print("  Bump EXTRACTION_SCHEMA_VERSION / PROMPT_VERSION if the field set changes.")
        return 2

    if accuracy >= 95:
        print(f"\n{GREEN}VERDICT: PASS{RESET}")
        print("  The model reads a clean document correctly.")
        print("  Next: LIVE_VALIDATION.md section 5 — measure accuracy on ~20 real")
        print("  historical invoices in TEST, posting nothing.")
        return 0

    print(f"\n{AMBER}VERDICT: MARGINAL{RESET}")
    print("  Every critical field was read, but overall accuracy is below 95%.")
    print("  Usable with review. Tune the prompt before widening the pilot.")
    for stem, _, _, wrong, missing in results:
        if wrong or missing:
            print(f"    {stem}: wrong={wrong or '-'} missing={missing or '-'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
