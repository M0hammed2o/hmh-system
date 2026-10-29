# Release runbook — Bypass Orders mixed-document intake

Branch: `feat/quotations-and-proformas` (PR #7)
Production is at alembic **0079**; this release needs **0081**.

The order below is not arbitrary. The new backend code cannot run against
the 0079 schema: `payment_evidence_detected` is a mapped column, so every
query for an import document selects it, and the column does not exist yet.
**Migrate before deploying the backend.**

The migrations are safe to apply *before* the deploy, because the running
0079 code simply never looks at the new table or columns.

---

## 0. Confirm a recoverable backup

Supabase point-in-time recovery, or a snapshot taken now. Note the
timestamp or snapshot id — everything below assumes you can get back to it.

**Do not continue without this.** Nothing downstream is reversible by
reverting a commit.

## 1. Apply the migrations

```bash
cd hmh-backend
DATABASE_URL="<production connection string>" python -m alembic current     # expect 0079
DATABASE_URL="<production connection string>" python -m alembic upgrade head
DATABASE_URL="<production connection string>" python -m alembic current     # expect 0081
```

What it does, and nothing else:

| Revision | Change |
|---|---|
| 0080 | `ALTER TYPE ai_import_document_type_enum ADD VALUE IF NOT EXISTS` ×2 |
| 0081 | `CREATE TYPE provisional_charge_status_enum`, `CREATE TABLE provisional_charges` + 5 indexes, `ALTER TABLE ai_import_documents ADD COLUMN` ×2 |

No `UPDATE`, no `DELETE`, no `DROP` on the upgrade path. No existing row is
read or written.

**Rehearsed on a copy at 0079 holding users, projects, suppliers, invoices,
import batches and one document per existing document type: all eight
non-empty tables were byte-identical afterwards, comparing the columns that
existed before, and the five company records were unchanged.**

### Verify

```sql
SELECT version_num FROM alembic_version;                      -- 0081
SELECT count(*) FROM provisional_charges;                     -- 0
SELECT name FROM companies ORDER BY name;                     -- all five still there
SELECT count(*) FROM ai_import_documents
 WHERE payment_evidence_detected IS NULL;                     -- 0
SELECT unnest(enum_range(NULL::ai_import_document_type_enum)); -- includes QUOTATION, PRO_FORMA_INVOICE
```

## 2. Deploy the backend to Render

Manual deploy of `hmh-backend` from `main` once the PR is merged.

### Verify

```
GET /api/v1/ai-import/service-status
```

- `auto_post_enabled` must be **false**
- `workspace_scoped` should now be **present** in the response. Its presence
  is how you know the new build is live; see step 4 for its value.

## 3. Merge, which deploys the frontend

Merging PR #7 into `main` is what triggers the Vercel production build.
Doing it *after* steps 1 and 2 means the new screens find their endpoints
already there.

### Verify on https://app.hmhgroup.co.za

| Screen | Expected |
|---|---|
| Payments | a **Pending Charges** tab beside Invoices and Outstanding |
| Pending Charges | empty, with the notice that its total is not owed |
| Bypass Orders | a **Batch Review** tab |
| Invoices | unchanged; no pro-forma reference among them |

## 4. Anthropic workspace

The key is set (`extraction_available: true`), but it is organisation-scoped
and production's last extraction attempt was refused with *"This API key is
not scoped to a workspace"*.

Either:

- set **`ANTHROPIC_WORKSPACE_ID`** in the Render dashboard, or
- replace the key with one created **inside** a workspace, which carries its
  own scope and needs no variable.

Then re-check `service-status`: `workspace_scoped` must read **true**.

Until it does, documents are stored, hashed, de-duplicated and queued for
review, but nothing is read off them — every one of the twenty real scans is
a photograph with no text layer.

## 5. Still do not

- Turn on `AI_IMPORT_AUTO_POST_ENABLED`. It stays `false`.
- Bulk-import the twenty documents. One at a time, through review, after
  step 4 is green.
- Post the handwritten delivery note until somebody has checked the
  quantities against what actually arrived.
