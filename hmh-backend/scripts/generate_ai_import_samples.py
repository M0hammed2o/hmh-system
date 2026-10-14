"""
Generate a non-sensitive sample document set for AI Document Import testing.

Produces four PDFs describing one coherent procurement transaction — a
material request, a purchase order, a delivery note and a supplier invoice —
using an entirely fictional supplier and project. Nothing here is HMH data,
so the set can be sent to an AI provider, attached to a ticket or shared with
a vendor without disclosing anything.

Use it to run the first live extraction test (see
docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md) before pointing the engine at
real paperwork.

    python scripts/generate_ai_import_samples.py [output_dir]

Defaults to ./sample_documents. Deliberately writes outside the repo tree
only if you pass an absolute path.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Fictional parties. Any resemblance to a real supplier is unintended. ──────
SUPPLIER = {
    "name": "Umhlanga Building Supplies CC",
    "vat": "4350198762",
    "reg": "2011/044821/23",
    "address": "17 Flanders Drive, Mount Edgecombe, 4302",
    "terms": "30 days from statement",
    "bank": "Acct 62xxxxxx914 / Branch 250655",
}
PROJECT = {"name": "Riverside Park Phase 2", "code": "SAMPLE-RP2", "site": "Block C"}

LINES = [
    # description, qty, unit, unit price
    ("Cement 42.5N 50kg bag", 120, "bag", 118.50),
    ("River sand", 8, "m3", 410.00),
    ("Brickforce 75mm x 20m roll", 15, "roll", 96.75),
]
VAT_RATE = 15


def _money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ")


def _totals() -> tuple[float, float, float]:
    subtotal = round(sum(q * p for _, q, _, p in LINES), 2)
    vat = round(subtotal * VAT_RATE / 100, 2)
    return subtotal, vat, round(subtotal + vat, 2)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Heading1"], fontSize=16, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9, textColor=colors.grey),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13),
        "h2": ParagraphStyle("h", parent=base["Heading2"], fontSize=11, spaceBefore=10),
    }


def _line_table(include_prices: bool) -> Table:
    if include_prices:
        head = ["Description", "Qty", "Unit", "Unit price", "Line total"]
        rows = [
            [d, str(q), u, _money(p), _money(round(q * p, 2))]
            for d, q, u, p in LINES
        ]
        widths = [72 * mm, 18 * mm, 18 * mm, 28 * mm, 28 * mm]
    else:
        head = ["Description", "Qty", "Unit"]
        rows = [[d, str(q), u] for d, q, u, _ in LINES]
        widths = [110 * mm, 25 * mm, 25 * mm]

    table = Table([head, *rows], colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _totals_table() -> Table:
    subtotal, vat, total = _totals()
    table = Table(
        [
            ["Subtotal", _money(subtotal)],
            [f"VAT @ {VAT_RATE}%", _money(vat)],
            ["Total due", _money(total)],
        ],
        colWidths=[40 * mm, 32 * mm],
        hAlign="RIGHT",
    )
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _build(path: Path, title: str, meta: list[tuple[str, str]], body) -> None:
    st = _styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=title,
    )
    flow = [
        Paragraph(title, st["title"]),
        Paragraph("SAMPLE DOCUMENT — fictional parties, for system testing only", st["sub"]),
        Spacer(1, 8),
    ]
    meta_table = Table(
        [[Paragraph(f"<b>{k}</b>", st["body"]), Paragraph(v, st["body"])] for k, v in meta],
        colWidths=[45 * mm, 120 * mm], hAlign="LEFT",
    )
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    flow.append(meta_table)
    flow.append(Spacer(1, 10))
    flow.extend(body)
    doc.build(flow)


def generate(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    st = _styles()
    written: list[Path] = []

    # 1 — Material request (internal, no pricing)
    p = out_dir / "01_material_request_MR-SAMPLE-014.pdf"
    _build(
        p, "MATERIAL REQUEST",
        [
            ("Request number", "MR-SAMPLE-014"),
            ("Date", "2026-03-04"),
            ("Project", f"{PROJECT['name']} ({PROJECT['code']})"),
            ("Site", PROJECT["site"]),
            ("Requested by", "S. Dlamini (Site Manager)"),
            ("Required by", "2026-03-18"),
        ],
        [Paragraph("Materials requested", st["h2"]), _line_table(include_prices=False)],
    )
    written.append(p)

    # 2 — Purchase order (issued to the supplier)
    p = out_dir / "02_purchase_order_PO-SAMPLE-2291.pdf"
    _build(
        p, "PURCHASE ORDER",
        [
            ("Order number", "PO-SAMPLE-2291"),
            ("Date", "2026-03-06"),
            ("Supplier", SUPPLIER["name"]),
            ("Supplier VAT no.", SUPPLIER["vat"]),
            ("Project", f"{PROJECT['name']} ({PROJECT['code']})"),
            ("Against request", "MR-SAMPLE-014"),
            ("Delivery address", f"{PROJECT['site']}, {PROJECT['name']}"),
            ("Approved by", "M. Naidoo (Procurement Lead)"),
        ],
        [
            Paragraph("Items ordered", st["h2"]), _line_table(include_prices=True),
            Spacer(1, 8), _totals_table(),
        ],
    )
    written.append(p)

    # 3 — Delivery note (from the supplier, no pricing)
    p = out_dir / "03_delivery_note_DN-SAMPLE-7781.pdf"
    _build(
        p, "DELIVERY NOTE",
        [
            ("Delivery note no.", "DN-SAMPLE-7781"),
            ("Date", "2026-03-18"),
            ("From", f"{SUPPLIER['name']}, {SUPPLIER['address']}"),
            ("Your order", "PO-SAMPLE-2291"),
            ("Deliver to", f"{PROJECT['site']}, {PROJECT['name']}"),
            ("Vehicle", "ND 418 762"),
            ("Driver", "P. Mthembu"),
            ("Received by", "T. Khumalo"),
        ],
        [
            Paragraph("Goods delivered", st["h2"]), _line_table(include_prices=False),
            Spacer(1, 14),
            Paragraph(
                "Received in good order and condition.<br/><br/>"
                "Signature: ______________________&nbsp;&nbsp;&nbsp;Date: ____________",
                st["body"],
            ),
        ],
    )
    written.append(p)

    # 4 — Supplier invoice
    subtotal, vat, total = _totals()
    p = out_dir / "04_supplier_invoice_INV-SAMPLE-50231.pdf"
    _build(
        p, "TAX INVOICE",
        [
            ("Invoice number", "INV-SAMPLE-50231"),
            ("Invoice date", "2026-03-20"),
            ("Due date", "2026-04-19"),
            ("From", f"{SUPPLIER['name']}, {SUPPLIER['address']}"),
            ("VAT registration no.", SUPPLIER["vat"]),
            ("Company reg. no.", SUPPLIER["reg"]),
            ("Your order", "PO-SAMPLE-2291"),
            ("Delivery note", "DN-SAMPLE-7781"),
            ("Project", f"{PROJECT['name']} ({PROJECT['code']})"),
            ("Payment terms", SUPPLIER["terms"]),
            ("Banking details", SUPPLIER["bank"]),
        ],
        [
            Paragraph("Charges", st["h2"]), _line_table(include_prices=True),
            Spacer(1, 8), _totals_table(),
            Spacer(1, 10),
            Paragraph(
                f"Amount due: R {_money(total)}. "
                f"E &amp; OE. This is a sample document for system testing.",
                st["body"],
            ),
        ],
    )
    written.append(p)
    return written


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_documents")
    written = generate(out_dir)

    subtotal, vat, total = _totals()
    print(f"Wrote {len(written)} sample documents to {out_dir.resolve()}:")
    for p in written:
        print(f"  {p.name}  ({p.stat().st_size / 1024:.0f} KB)")
    print("\nExpected extraction, for checking the live result:")
    print(f"  supplier_name   {SUPPLIER['name']}")
    print(f"  supplier VAT    {SUPPLIER['vat']}")
    print(f"  project code    {PROJECT['code']}")
    print(f"  PO reference    PO-SAMPLE-2291")
    print(f"  invoice number  INV-SAMPLE-50231")
    print(f"  subtotal        {_money(subtotal)}")
    print(f"  VAT ({VAT_RATE}%)       {_money(vat)}")
    print(f"  total           {_money(total)}")
    print(f"  line items      {len(LINES)}")
    print("\nAll parties are fictional. Nothing in this set is HMH data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
