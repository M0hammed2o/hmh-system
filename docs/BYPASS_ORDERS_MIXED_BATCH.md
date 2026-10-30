# Bypass Orders — mixed document intake

Date: 2026-10-29
Branch: `feat/quotations-and-proformas`
Migration head: `0081`

Written for the people who will run and maintain this: site and office staff
who use the screen, and whoever picks up the code next.

---

## 1. The problem this solves

A real intake is not a stack of invoices. One upload carries quotations,
purchase orders, pro-formas, tax invoices, a fuel order and a handwritten
delivery note, in no order, several of them scans of scans.

The consequences are nothing like uniform. Of a real batch of twenty
documents for Minerat Construction & Civils at Dassenhoek:

- **one** was evidence that goods arrived, and may move stock
- **two** were tax invoices, and create money owed
- **five** were pro-formas — requests for payment that are *not* owed
- **five** were quotations, which commit nobody
- **seven** were purchase orders, which commit spend but owe nothing
- **one** was 500 litres of diesel, which is not warehouse stock at all

Before this work the engine had no type for a quotation or a pro-forma, so
both were headed for `SUPPLIER_INVOICE` or `UNKNOWN`.

### Why the pro-forma is the dangerous one

A pro-forma invoice prints the word **INVOICE** across the top, carries an
invoice number and a VAT registration number, and asks to be paid. Every
signal that identifies a tax invoice is on it, and it is not one — it is a
request for payment *before* supply.

Book one into Accounts Payable and two things go wrong. The business
overstates what it owes today, and when the supplier issues the real tax
invoice for the same goods, it owes the same money twice.

That chain was in the batch three times over:

| Order | Follow-up document | Amount |
|---|---|---|
| PO-101 to Lakeside Merchant | Lakeside Builders Merchant pro-forma QTE880114 | R4 120.50 |
| PO-122 to Maswell Blocks | Maswell pro-forma QTE7410 | R14 300.00 |
| PO-117 to Quarryside | Quarryside **tax invoice** 85956 | R577.32 |

One purchase each. One liability each — and only when the tax invoice comes.

---

## 2. Where each document goes

`app/services/ai_import_routing_service.py` is the single source of truth.
The review screen, the manifest endpoint and the handover report all read it,
so none of them can tell an operator a different story about the same
document.

| Document type | Destination | What importing it does |
|---|---|---|
| Material request | Material Requests | Internal request. No supplier commitment. |
| **Quotation** | Procurement (`quotations`) | Records the price offer. No money owed, no stock. |
| Purchase order | Purchase Orders | Committed spend. Nothing owed, no stock until goods arrive. |
| **Pro-forma** | **Pending supplier charges** (`provisional_charges`) | Recorded *outside* Accounts Payable. Becomes a liability when the tax invoice arrives. |
| Tax invoice | Accounts Payable (`invoices`) | Creates the liability, **UNPAID**. Closes any pending charge on the same order. |
| Delivery note / GRN | Goods received | Increases stock in the **project warehouse**. Lot allocation is a separate step. |
| Fuel order | Fuel procurement | **Refused into materials.** See below. |
| Credit note | Evidence only | No credit-note record exists; applying the credit stays manual. |
| Payment proof | Payment reconciliation | Evidence. A person matches it to an invoice. |

Each row also carries a **manifest action**: `CREATE`, `LINK_EXISTING`,
`REVIEW` or `SKIP_DUPLICATE`.

### Fuel

PO-108 was 500 litres of 50PPM diesel. Routed as an ordinary purchase order
it creates a materials order, and the delivery that follows tries to receive
diesel into the warehouse as though it were cement.

Fuel is measured in litres against a **storage location**, and the document
never says which one. So posting is refused and the operator is sent to the
fuel screen. Guessing the tank would corrupt the fuel reconciliation.

**Fuel the commodity, not the word.** The workshop buys a great deal of
fuel-related hardware — `OIL, FUEL. INLINE, HYDRAULIC FILTERS` is a real
line from this company's repair history. Diverting that order would refuse a
legitimate purchase and send the buyer to a screen that cannot record it.

So litres or a fuel grade (50PPM, 500PPM) settle it outright: nobody buys a
filter by the 500 litres, and *"delivered to tank"* would otherwise make a
genuine bulk delivery look like hardware. Only when neither is present do
part words — filter, pump, seal, injector, sender — rule the line out. The
supplier's name is a hint and never a verdict, because a fuel supplier sells
filters too; it is consulted only when no line item could be read at all.

---

## 3. Accounts Payable

**Every imported invoice starts UNPAID.** Payment status is derived from
`Payment` rows by `payment_service._recalculate_invoice_status` and from
nothing else. Partial payments, dates, methods and references are recorded
there as they always were.

### PAID stamps

Two documents in the batch arrived stamped PAID. A stamp is a claim made by
whoever held it — it may mean the money left the bank, or that somebody
intended to pay, or that a stamp and a pile of paper met on the same desk.

The claim is recorded on the document
(`ai_import_documents.payment_evidence_detected` and
`payment_evidence_note`) and shown as:

> Payment evidence detected — verification required. … This is a claim
> printed on the paperwork, not a bank record: nothing has been marked as
> paid.

It never settles anything.

### Pending charges are reported separately

`provisional_charge_service.outstanding_total()` answers *"what might we be
asked to pay"*. Accounts Payable answers *"what do we owe"*. They are
deliberately different calls, because a screen that can accidentally add one
to the other is a screen that eventually will.

---

## 4. How double-counting is prevented

Four independent guards, at different layers:

1. **Same file twice** — SHA-256 checksum at upload sets `duplicate_of_id`;
   the manifest action becomes `SKIP_DUPLICATE`.
2. **Same reference twice** — enforced by the database, not by the code path
   that happens to be inserting:
   - `invoices`: supplier + invoice number (`invoice_service`)
   - `quotations`: `quote_number` is globally unique
   - `provisional_charges`: `uq_provisional_charge_supplier_reference`
   - deliveries: `_refuse_duplicate_note` on supplier note number
3. **Pro-forma superseded by its tax invoice** — posting an invoice calls
   `provisional_charge_service.find_pending_for_invoice` and closes the
   matching charge, which then leaves the pending total.
4. **Same amount, different number** — the two Vantage Readymix pro-formas carry an
   identical R20 360.89 eleven days apart. One reading is a second pour, the
   other is the same pour scanned twice, and nothing on the paper
   distinguishes them. The manifest **raises the question** and never
   resolves it.

### Why the charge is matched on the order, not the amount

A pro-forma and the tax invoice that follows it routinely differ — delivery
charges, part supply, a price change between quote and supply. Matching on
amount would leave the charge open whenever they did.

Supplier alone is not safe either: a supplier with two open pro-formas would
have an arbitrary one closed by an unrelated invoice. So the purchase order
is the key, and an invoice without one closes nothing.

---

## 5. Classification

Two passes, in `ai_import_extraction_service._classify_from_text`:

1. **Decisive markers** — a heading that settles the type outright.
2. **Keyword scoring** — only when no heading is found. A tie returns
   `UNKNOWN`.

Three rules were learned from the real paperwork:

**Negations are stripped.** PO-122 carries a handwritten *"No Delivery
note"*. Read as a marker, that phrase turns a purchase order into proof of
delivery for goods the annotation explicitly says never arrived.

**Position decides, not list order.** A delivery note cites the order it
fulfils; an order is annotated about the delivery note that never came.
Neither ordering of the marker list can be right for both — but a heading is
at the top of a page and a reference is in the body, so the earliest
surviving marker wins.

**Two types on one line is ambiguity.** That is not a heading followed by a
reference; it is one line mentioning both, and nothing about the layout says
which the document is. Returns `UNKNOWN`.

The AI prompt carries the same distinction explicitly, including the
instruction to return `UNKNOWN` rather than defaulting to `SUPPLIER_INVOICE`
when only an invoice number is legible.

---

## 6. Stock and the BOQ

Unchanged by this work, and worth restating because it is what keeps a
guessed allocation impossible:

- Only a delivery note or GRN may increase stock. A purchase order never can.
- An imported receipt lands in the **project warehouse**. Supplying a lot at
  posting time is *rejected*, not ignored — allocation is a separate,
  deliberate step on the warehouse screen.
- **A receipt is held for review until a person confirms it.** Stock is the
  one thing here that is physically wrong if it is wrong: a receipt posted
  from a misread quantity puts materials on the system that are not on site,
  and the error surfaces weeks later as a shortage nobody can explain. The
  batch's only delivery note is handwritten on a carbon-copy book. Any line
  whose quantity was not read confidently is named, because "needs review"
  without saying why invites a rubber stamp.
- PO-117 names lot **A599**. Dassenhoek has A17 and A175; production
  reconciliation confirmed A599 does not exist. Nothing allocates to it,
  because nothing allocates to any lot at import.

---

## 7. Using it

**Bypass Orders → Batch Review.** After an upload the screen opens here
rather than on the flat document queue, because a batch of twenty needs to be
seen whole before it is approved one row at a time.

Each row states the detected type, supplier, project, amount, destination,
what importing would do, and any question attached to it. Type, supplier and
project are correctable in place — those are the three things a reader can
see are wrong at a glance — and the destination updates with the correction.

Nothing on the screen writes anything. Approval still happens per document.

---

## 8. What the real scans actually contain

Measured, not assumed. All twenty documents were run through the real
extraction path with `scripts/verify_real_document_extraction.py`:

| | |
|---|---|
| Documents with a text layer | **0 of 20** |
| Characters extracted by the deterministic parser | **0** |
| Classified correctly without the AI reader | **0** |
| **Misclassified** | **0** |
| Pro-formas misread as tax invoices | **0** |
| Documents wrongly read as a goods receipt | **0** |

Every one is a photograph. `pypdf` reports one page holding three to five
embedded images and no text, and the OCR fallback refuses them ("Bad image
data").

Two things follow, and they pull in opposite directions.

**The safety properties hold on real paperwork.** Nothing is guessed. Every
document returns `UNKNOWN`, which routes to review, so no liability is
invented and no stock moves. The expensive failure — a pro-forma booked as a
tax invoice — does not occur, because nothing is classified at all.

**The capability is zero without the AI reader.** The deterministic parser
cannot read any of this company's paperwork, so it is a safety net and not a
fallback. Classification is verified against transcribed text, which is what
the vision model would return; the step that turns a photograph into that
text is **not verified** and cannot be until the Anthropic workspace key
exists.

---

## 9. Pending Supplier Charges

**Payments → Pending Charges.** A tab beside the payables tabs, never inside
them. Each row shows the supplier, the reference, the amount, the matched
purchase order by number, the status, and the tax invoice that closed it if
one has arrived.

The panel loads its own figures and contributes nothing to the outstanding
totals on the other tabs. It states, in the server's own words, that its
total is not owed — because a bare number on a finance screen gets added to
the other numbers on the same screen.

Withdrawing a request requires a reason. A charge that simply vanished
leaves nobody able to say later whether the supplier was refused, paid or
forgotten.

---

## 10. Known gaps

| Gap | Status |
|---|---|
| **Live AI extraction** | Blocked. Needs a workspace-scoped Anthropic key or `ANTHROPIC_WORKSPACE_ID`. Without it extraction falls back to the deterministic parser, which reads header fields only. |
| Supplier credit notes | Still evidence-only; no credit-note record exists. |
| Payment proof posting | Evidence-only; matching to an invoice stays manual. |
| Fuel order posting | Deliberately refused — the document never names a storage location. |
| Suppliers absent from production | Lakeside Merchant and Clearview Glazing. Documents naming them route to `REVIEW`. |
