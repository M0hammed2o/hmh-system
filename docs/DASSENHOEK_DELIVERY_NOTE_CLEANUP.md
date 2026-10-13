# Dassenhoek — duplicated BOQ quantities and delivery-note cleanup

Investigated 2026-10-14 on branch `feat/ai-document-import`.

**The short version: the duplication is not in your data. It is in the
dashboard's arithmetic, and it is fixed.**

One delivery of 100 bags was being reported as 200 because two BOQ rows
describe the same catalogue item, and each of them claimed the whole
delivery. Deleting delivery notes would not have fixed it — it would have
destroyed good records and left the arithmetic defect in place to do the
same thing to the next delivery.

A cleanup utility exists for the separate case of genuinely duplicated
delivery notes, but **nothing has been run against live data**, and this
document cannot list Dassenhoek's actual delivery notes. Section 5 explains
why and what is needed to complete that part.

---

## 1. Root cause

`hmh-backend/app/api/v1/site_dashboard.py`, in both material-summary
endpoints:

| Endpoint | Function |
|---|---|
| `GET /site-dashboard/{site_id}/lots/{lot_id}/material-summary` | `lot_material_summary` |
| `GET /projects/{project_id}/lots/{lot_id}/material-summary` | `project_lot_material_summary` |

Each held its own copy of a BOQ de-duplication step. That step collapsed BOQ
rows using a key built from the **typed description and unit**:

```python
key = (
    _re.sub(r"\s+", " ", (bi.raw_description or "").lower().strip()),
    (bi.unit or "").lower(),
)
```

Delivered and used quantities, however, are looked up by **`item_id`** — the
catalogue item:

```python
delivered_by_item = {r[0]: float(r[1]) for r in rows}   # keyed by item_id
```

The two keys disagree. Two BOQ rows that point at the same catalogue item but
were typed differently — `"Cement 42.5N 50kg"` in one section and
`"Cement 42.5N 50kg bag"` in another, or one with a trailing supplier note —
both survive de-duplication, and each then looks up the delivered quantity by
the *same* `item_id` and reports the *full* figure.

One delivery. Two rows. Twice the quantity, and twice the cost that follows
from it.

What makes it read as a data problem rather than an arithmetic one: the
display name comes from the **catalogue item**, not from the typed text. So
the two rows render with identical descriptions. On screen it looks exactly
like the BOQ line was captured twice, which is why the obvious response is to
go looking for duplicate delivery notes to delete.

### Reproduced

`hmh-backend/tests/test_site_dashboard_boq_duplication.py`, before the fix:

```
one 100-bag delivery reported as 200.0 across 2 BOQ row(s):
  [('Cement 42.5N 50kg bag', 100.0), ('Cement 42.5N 50kg bag', 100.0)]
```

Three rows sharing an item gave 300. The error scales with the number of BOQ
rows pointing at the item, which is why a busy lot shows a wilder figure than
a quiet one.

### The fix

Identity is now the catalogue item when there is one, and the description
only when there is not. A row is registered under both keys, so a
non-catalogue row still merges into the catalogue row it duplicates:

```python
item_key = ("item", bi.item_id) if bi.item_id else None
desc_key = _desc_key(bi)
...
assert len(_seen_item_ids) == len(set(_seen_item_ids)), (
    "BOQ deduplication left two rows sharing a catalogue item; delivered "
    "quantities would be double-counted"
)
```

The allocated quantity of a merged row is added to the survivor, so the BOQ
allocation total is unchanged — only the delivered and used figures stop
multiplying. The assertion makes a regression fail loudly rather than quietly
inflating a number again.

Applied to **both** endpoints. They had drifted into holding two copies of
the same logic; fixing one would have left the other wrong.

---

## 2. What this means for the figures on screen

| Figure | Was | Now |
|---|---|---|
| BOQ allocated quantity | correct | correct (unchanged) |
| Delivered quantity | multiplied by the number of BOQ rows sharing the item | counted once |
| Used quantity | same multiplication | counted once |
| Remaining / over | derived from the above, so wrong | correct |
| Cost figures derived from delivered | overstated | correct |

No database values were wrong. Nothing needs correcting in the ledger for
**this** defect — the dashboard will show the right numbers on the next page
load after deployment.

---

## 3. Tests that stop it coming back

`tests/test_site_dashboard_boq_duplication.py` — 10 tests, all passing:

| Test | Guards |
|---|---|
| `test_one_delivery_is_not_counted_twice_when_two_boq_rows_share_an_item` | the exact reported symptom |
| `test_three_boq_rows_sharing_an_item_still_report_the_delivery_once` | that it does not merely halve |
| `test_usage_is_not_counted_twice_either` | the consumption side |
| `test_genuinely_different_materials_are_reported_separately` | that the fix does not over-merge |
| `test_allocation_across_sections_still_totals_correctly` | BOQ allocation preserved when rows merge |
| `test_non_catalog_boq_rows_are_unaffected` | free-text BOQ lines still work |
| `test_a_lot_with_no_deliveries_reports_zero` | no phantom quantities |
| `test_another_projects_delivery_does_not_leak_in` | project isolation |
| `test_project_lot_summary_does_not_duplicate_used_quantities` | the second endpoint |
| `test_project_lot_summary_still_totals_allocation_across_sections` | the second endpoint |

Verified load-bearing: reverting the fix fails 3 of them; restoring it passes
all 10.

---

## 3a. Prevention — the same note can no longer be posted twice

Investigating the above turned up a second, independent defect:
`delivery_service.create_delivery` had **no duplicate guard at all**. A
double-tapped submit, a retried request, or a historical document imported
twice each created a second delivery and a second set of stock movements.
Nothing downstream could tell the two apart afterwards.

That is the mechanism that would produce genuinely duplicated data — as
opposed to the dashboard defect, which produced a duplicated *display* of
correct data. Both had to be closed.

`_refuse_duplicate_note` now rejects a second delivery carrying a supplier
note number already recorded for that supplier on that project, with a 409
and a message naming the existing delivery:

> Delivery note DN-5150 from this supplier is already recorded on this
> project as DN-A1B2C3 (2026-03-18). Recording it again would count the same
> stock twice. Open that delivery to amend it, or use a different note
> number if this is a separate delivery.

Deliberately narrow, so it blocks duplicates without blocking real work:

| Case | Behaviour |
|---|---|
| Same supplier, same note number, same project | **Refused** |
| Differing only by case or surrounding space | **Refused** — `DN-5150` and ` dn-5150 ` are the same note |
| No note number (blank or absent) | Allowed — plenty of deliveries arrive without one, and blanks must not collide with each other |
| Same note number, different supplier | Allowed — note numbers are unique only within a supplier's own book |
| Same note number, different project | Allowed |
| The earlier delivery is `CANCELLED` | Allowed — so a note archived by the cleanup utility can be recaptured correctly |

Because the AI import posting path calls `create_delivery` like every other
caller, it inherits the guard: a re-imported document cannot post stock a
second time.

Covered by five tests in `tests/test_delivery_note_cleanup.py`, one per row
above. Verified load-bearing: removing the guard fails two of them.

---

## 4. The cleanup utility — for genuine duplicate delivery notes

The dashboard defect is fixed, but it is a separate question whether
Dassenhoek also has delivery notes that were genuinely captured twice — by a
re-submitted form, a retried request, or a re-imported historical document.
That would be real data duplication, and `scripts/cleanup_project_delivery_notes.py`
handles it.

### What it does

**Dry run by default.** `--apply` additionally requires `--i-have-a-backup`
and `--actor-email`. Without all three it reports and exits.

It classifies every delivery note on one project, by verified project UUID:

| Verdict | Signal |
|---|---|
| `DUPLICATE_NOTE_NUMBER` | the same supplier delivery-note number recorded more than once for that supplier. The **earliest** is treated as genuine and kept |
| `DUPLICATE_STOCK_POSTING` | one delivery with more than one `DELIVERY_RECEIVED` movement for the same item, whatever the note number says |
| `GENUINE` | neither signal |

Note numbers are compared case- and whitespace-insensitively. A blank note
number never pairs with another blank one. The same number from a *different*
supplier is not a duplicate.

### What it will not do

- **It deletes nothing.** Stock is reversed by writing a contra entry; the
  original ledger rows stay exactly where they are. A duplicate delivery is
  set to `CANCELLED` with a dated comment, never removed.
- **It never touches invoices, purchase orders or payments.**
- **It never leaves the named project.**
- **It skips any duplicate that carries an invoice.** Reversing a receipt an
  invoice was raised against changes what the paperwork says was delivered.
  The utility flags it `needs_human_decision` and leaves it alone.

### Why a contra entry rather than an adjustment

This matters, and getting it wrong would have looked like it worked.

Stock on hand is `SUM(quantity_in) - SUM(quantity_out)` everywhere in the
codebase, so an `ADJUSTMENT_SUBTRACT` with a `quantity_out` nets correctly
*there*. But the lot material summary reads:

- delivered as `SUM(quantity_in)` where `movement_type IN (DELIVERY_RECEIVED, TRANSFER_IN)`
- used as `SUM(quantity_out)` **with no movement-type filter at all**

An adjustment would therefore have left the BOQ delivered figure still
overstated, and silently inflated the used figure by the same amount —
replacing one wrong number with two. The utility instead writes the same
movement type with a **negative `quantity_in`** and `reference_type =
"delivery_reversal"`, which reverses precisely the aggregate the duplicate
inflated, in every view.

This is pinned by `test_reversal_corrects_the_boq_delivered_quantity` and
`test_reversal_does_not_show_up_as_consumption`; swapping in the adjustment
form fails them.

### Running it

```bash
cd hmh-backend

# Report only. Changes nothing.
python scripts/cleanup_project_delivery_notes.py --project-id <uuid>

# Machine-readable, for attaching to an approval request.
python scripts/cleanup_project_delivery_notes.py --project-id <uuid> --json

# Execute, after a snapshot exists.
python scripts/cleanup_project_delivery_notes.py --project-id <uuid> \
    --apply --i-have-a-backup --actor-email <you>@hmhgroup.co.za
```

The dry run prints the project name and code — **check it is Dassenhoek
before going further.** It then prints the per-note classification and the
exact planned actions.

### Its own tests

`tests/test_delivery_note_cleanup.py` — 21 tests, all passing: classification
in both directions, the dry run changing nothing, reversal correcting the BOQ
delivered figure *and* stock on hand without registering as consumption,
nothing deleted, an audit event written, a second run being a no-op,
invoice-linked duplicates skipped, and another project left untouched.

---

## 5. What this report cannot tell you

The brief asks for every Dassenhoek delivery note by ID, reference, date,
supplier, linked PO, stock movements and before/after totals.

**I cannot produce that list, because no database containing Dassenhoek is
reachable from this environment.** Specifically:

| Looked in | Result |
|---|---|
| The repository | 0 occurrences of "Dassenhoek" in any file |
| `hmh_system_backup_20260713.sql` (846 KB, 76 `COPY` blocks) | 0 occurrences |
| Local scratch databases (`hmh_test`, `hmh_mig`, `hmh_deploy`) | test fixtures only |
| `DATABASE_URL` / Supabase credentials | not configured in this environment |

Any delivery-note IDs, suppliers, dates, duplicate counts or before-and-after
totals in this document would be invented. There are none, and there should
be none.

**Nothing has been executed against production. No live data has been
changed.**

### To complete section 5

1. Find the project UUID:
   ```sql
   SELECT id, code, name FROM projects WHERE name ILIKE '%dassenhoek%';
   ```
2. Take a database snapshot (Supabase → Database → Backups, or
   `pg_dump`). The utility refuses `--apply` without `--i-have-a-backup`, but
   that flag is an assertion by the operator, not a check — the snapshot has
   to actually exist.
3. Run the dry run with `--json` and attach the output to the approval
   request. That output *is* the per-note table this section is missing.
4. Decide, note by note, on anything marked `needs_human_decision`.
5. Only then run with `--apply`.
6. Re-open the lot material summary and confirm the figures.

Expect the dry run to find **no** duplicates. The symptom is fully explained
by the dashboard defect, and that is now fixed. If it does find some, they are
a second, independent problem — which is exactly why "delete the delivery
notes" was the wrong first move.

---

## 6. Status

| Item | Status |
|---|---|
| Root cause identified | Done — dashboard aggregation, both endpoints |
| Code defect fixed | Done, 10 regression tests |
| Duplicate posting guard added | Done, 5 tests — `create_delivery` had none |
| Cleanup utility built | Done, 21 tests, dry run by default |
| Per-note Dassenhoek inventory | **Blocked** — no reachable database |
| Before/after live totals | **Blocked** — same |
| Production data changed | **No. Nothing has been executed.** |
