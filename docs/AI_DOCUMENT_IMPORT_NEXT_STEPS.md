# AI Document Import — Next Steps

Session continuity file. Read this and `AI_DOCUMENT_IMPORT_PROGRESS.md` before
continuing work. Last updated: 2026-10-13 (Phase 2).

## State

Phases 0–14 implemented, then a second session re-verified the safety
properties, validated the provider integration offline, completed the
operator interface and hardened storage. Two independent reviews have run;
both returned FAIL, and all eighteen defects between them are fixed and
regression-tested. Full detail in `AI_DOCUMENT_IMPORT_COMPLETION.md` §8b, §8c.

## The one thing that still matters most

**The live Anthropic API has still never been called.** There was no
`ANTHROPIC_API_KEY` in either session. Everything that can be checked without
one has been: the SDK accepts every parameter sent, the content blocks are
the documented shapes, the request cannot exceed the provider's size or page
limits, the schema is closed and matches the allowed field set, truncation
and refusal are reported as themselves, and no key is hardcoded. Real PDFs go
through the local text, page-count and classifier path correctly.

None of that establishes that the model reads real documents well.

`docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` is the procedure. It needs a key
and about ten minutes. `AI_IMPORT_AUTO_POST_ENABLED` must stay `false` until
section 4 of that runbook passes.

## Next tasks, in order

1. **Run the live validation runbook.** `scripts/generate_ai_import_samples.py`
   produces a four-document fictional transaction with a printed answer key,
   so the first live test needs no HMH data at all.
2. **Measure accuracy on real paperwork**, in the TEST environment, on closed
   historical transactions, one supplier at a time, posting nothing. Twenty
   documents gives a usable error rate. Runbook §5.
3. **Choose the model** on measured accuracy, not price. The dashboard reports
   real token use and cost per project.
4. **Procure a malware scanner.** The integration point exists
   (`AI_IMPORT_SCAN_URL`); nothing is wired to it. Content-type verification
   against magic bytes already runs unconditionally.
5. **Schedule the retention purge.** `POST /api/v1/internal/ai-import-retention`
   is cron-ready and defaults to a dry run; add it to `render.yaml` once the
   window is agreed.
6. **Credit notes.** Still classified, matched and stored as evidence but not
   postable, because the system has no credit-note record. Deliberately left
   undesigned rather than guessed at.

## Lessons from the verification passes

Two independent reviews found eighteen defects between them, several able to
corrupt the books, each time after the suite was already green. What the
tests kept missing:

- They tested the implementation's shape, not the guarantee. There was an
  idempotency test, but it only covered the clean duplicate-claim case that
  already worked — never a domain service that commits and *then* fails.
- Security tests covered the endpoints that obviously handle money, and
  skipped `add_manual_match` and the dashboard, which turned out to be the
  two holes.
- Two policy rules (`cross_project`, `supplier_conflict`) were dead code with
  no test, so nothing noticed they could never fire. The same was true of the
  `reversed_at` columns, and of the PO comparison on delivery notes.
- A fix can be weaker than its own docstring claims. The first round's
  idempotency fix trusted the exception *type* as evidence that a domain
  service had written nothing; the second round found a path where that was
  false. Pin an invariant with a test that fails when the invariant is
  removed, not with a comment.
- Cleanups applied to one case must be applied to the class. Clearing stale
  conflict rows was right; the same staleness in auto-confirmed matches went
  unnoticed for another round.

When adding to this module, write the test against the property
("a retry cannot move stock twice"), not against the code path you just wrote.

## Rules to keep if you change this code

These are load-bearing. Breaking one turns a safe import into a way to corrupt
the books:

1. **Never post a business record directly.** Always call the domain service.
2. **Never trust the model's arithmetic.** `verify_arithmetic` recomputes it.
3. **BLOCKED means blocked.** No role, no flag, no override.
4. **An invoice is not proof of delivery.** Only DELIVERY_NOTE and
   GOODS_RECEIVED_NOTE can move stock.
5. **Claim the idempotency key before calling the domain service**, never
   after — that ordering is what makes a crash safe.
6. **A missing value stays missing.** Never fill a gap with a guess.
7. **Legacy imports are labelled, not back-dated.** No fictitious approval
   history.
8. **`check_project_access` on every project-scoped path.**

## Blockers needing a human

- No `ANTHROPIC_API_KEY` available in the development environment.
- No real HMH supplier documents available to measure extraction accuracy.
- The decision to enable `AI_IMPORT_AUTO_POST_ENABLED` is a business call and
  should follow, not precede, measured accuracy.
