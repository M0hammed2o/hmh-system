# AI Document Import — HMH Pilot Instructions

A step-by-step plan for putting the engine in front of HMH staff, in an order
that surfaces problems while they are still cheap.

Written for whoever runs the pilot — an office administrator with backend
access for the setup steps, and ordinary staff from step 4 onwards.

**Do not start at step 4.** Steps 1–3 cost almost nothing and are what stop a
pilot failing publicly.

---

## Before anything: the two blockers

| Blocker | Why it stops the pilot | Who clears it |
|---|---|---|
| No `ANTHROPIC_API_KEY` | The engine falls back to a keyword parser. It still stores, deduplicates and routes documents, but reads almost nothing — staff would conclude it does not work. | Whoever holds the Anthropic account |
| Extraction accuracy unmeasured | Nobody yet knows how well the model reads an HMH invoice. Piloting before measuring means staff discover the error rate for you, on real paperwork. | Step 2 below |

Neither is a code problem. Both must be cleared first.

---

## Step 1 — Prepare the environment (half a day)

1. Deploy the current build to **TEST**, not production. See
   `docs/TEST_ENVIRONMENT.md`; it has its own Supabase project and database.
2. Set on the TEST backend only:
   - `ANTHROPIC_API_KEY`
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — without these the engine
     **refuses** to store documents outside development rather than writing
     them to a disk that is wiped on redeploy. That refusal is deliberate.
   - Leave `AI_IMPORT_AUTO_POST_ENABLED=false`. Do not change it during the
     pilot.
3. Confirm the startup log shows `ai_import_worker=started ... auto_post=False`.
4. Run the offline contract check:
   `python -m pytest tests/test_ai_import_provider_contract.py -q` → 25 passed.

## Step 2 — Measure accuracy before involving staff (one day)

Follow `docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` sections 3–5.

1. Generate the fictional sample set and run the first live extraction
   against it. Check every field against the printed answer key.
2. Then take **twenty closed, historical invoices** from one supplier —
   already paid and reconciled, so nothing is at stake. Upload, review the
   extraction against the paper, record four things per document: was the
   supplier right, the invoice number right, the total right, the line count
   right. **Reject every one afterwards. Post nothing.**
3. Work out the error rate.

| Result | What to do |
|---|---|
| Supplier and total correct ≥95% | Proceed to step 3. |
| 85–95% | Usable with review, but tune the prompt first and re-measure. |
| Below 85% | Do not pilot. Either the prompt needs work or the scans are too poor; find out which before spending staff time. |

Record the figure. It is the number everyone will ask about.

## Step 3 — Dry run with one administrator (one day)

One office administrator, in TEST, on historical paperwork only.

1. Upload a complete four-document transaction — material request, purchase
   order, delivery note, invoice — for a transaction that is fully closed.
2. Walk the whole review flow: check the extraction against the original side
   by side, correct a field deliberately, set the project and supplier, link
   the purchase order by hand, read the "what needs doing" list.
3. Post all four, in order, and then verify in the destination modules:
   - the material request and purchase order are **DRAFT**, not approved
   - the project warehouse stock rose by exactly the delivered quantity
   - the purchase order's received quantity and status updated
   - the supplier invoice exists, is linked to the order, and is **not** paid
4. Upload the same four files again. Every one must come back **DUPLICATE**
   and post nothing.
5. Confirm the Reconciliation tab shows four posted transactions and a
   sensible AI cost.

If anything here surprises you, stop and raise it. This is the rehearsal.

## Step 4 — One supplier, two staff, two weeks (TEST)

1. Pick the supplier whose paperwork is most typical, and two staff who
   handle it.
2. Half an hour of training. The things that actually need saying:
   - Upload anything, in any order, in any mix. Sorting is not their job.
   - The amber "check this" markers show where the system was unsure. Those
     are the fields to look at; the green ones rarely need checking.
   - Red items must be resolved. They cannot be overridden, and that is on
     purpose.
   - Correcting a value is normal and is recorded. It is not a failure.
   - Nothing posts by itself. A person always presses the button.
3. Tell them explicitly: **report anything that looks wrong, especially if it
   looks plausible.** A confidently wrong total is far more dangerous than an
   obviously blank field.
4. Run every document through the normal paper process **as well**, and
   compare at the end of each week. The pilot is a shadow process, not a
   replacement.

Track weekly: documents uploaded, how many needed correction, how many were
blocked and why, how many were posted, and any case where the system was
wrong but looked right.

## Step 5 — Review before going near production

Go ahead only if all of these hold:

- No posting was wrong in a way a reviewer did not catch.
- No duplicate stock movement or duplicate liability occurred.
- Staff found the review screen workable without hand-holding.
- The error rate from step 2 held up on live paperwork.
- Someone understands the incomplete-postings list and has resolved one.

Then, for production:

1. Deploy, with `AI_IMPORT_AUTO_POST_ENABLED` still `false`.
2. Add the queue-drain and retention cron entries to `render.yaml`
   (retention defaults to a dry run; leave it that way for a month and read
   what it reports before setting `apply=true`).
3. Start with historical backlog, not live procurement. Live documents are
   the last step, not the first.
4. Revisit auto-posting only after months of clean operation, and then only
   for one document type. It is a business decision about risk appetite, not
   a technical switch.

---

## What to tell staff when something goes wrong

| Symptom | What it means | What they should do |
|---|---|---|
| "Needs review" with a list | Normal. The system is unsure or something does not line up. | Work through the list. Correct values against the paper. |
| Red "cannot be posted" | A duplicate, broken arithmetic, a cross-project reference, or a supplier conflict. | Do not try to force it. Fix the underlying problem or reject the document. |
| "Duplicate" | These exact bytes were uploaded before. | Nothing. It was not processed again, which is correct. |
| "Failed" | The file could not be read or the provider was unavailable. | Press "Read again". If it fails twice, upload a clearer scan. |
| Supplier or project blank | The document does not name it, or it is not in the system yet. | Set it by hand, or create the supplier first. |
| "A previous attempt did not finish" | A posting was interrupted. | Report it. An administrator resolves it from the incomplete-postings list after checking whether the record exists. |

## What to escalate immediately

- Any posted record that does not match the paper.
- Any stock figure that moved twice for one delivery.
- Any document that showed another project's information.

These are the failures the engine is built to make impossible. If one
happens, stop the pilot and report it rather than working around it.
