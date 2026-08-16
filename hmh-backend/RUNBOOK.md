# HMH Construction OS — Runbook

## Quick Start (local dev)

```cmd
cd hmh-backend

# 1. Start database
docker compose up -d db

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create/migrate schema
python scripts/create_db.py

# 4. Seed owner account
python scripts/seed_owner.py

# 5. Seed connected demo data
python scripts/seed_hmh_connected_demo.py

# 6. Start backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```cmd
cd hmh-frontend
npm install
npm run dev
```

Open: http://localhost:5173

---

## Login Accounts

| Role | Email | Password |
|------|-------|----------|
| Owner | admin@hmhgroup.com | Mohammed@1 |
| Office | office@hmhgroup.com | Office@1234 |
| Site | site@hmhgroup.com | Site@1234 |

---

## Run Automated Tests

```cmd
cd hmh-backend
pytest -q
```

Run specific flow:
```cmd
pytest tests/test_procurement_flow.py -v
pytest tests/test_stock_issue_to_lot.py -v
pytest tests/test_invoice_proof_pack.py -v
pytest tests/test_jobcard_approval.py -v
pytest tests/test_stage_tracking.py -v
```

Use a separate test DB (recommended):
```cmd
TEST_DATABASE_URL=postgresql://hmh:hmhdev@127.0.0.1:55432/hmh_test pytest -q
```

---

## Run End-to-End Script

```cmd
cd hmh-backend
python scripts/test_end_to_end.py
```

Against a different server:
```cmd
python scripts/test_end_to_end.py --base-url http://your-server:8000/api/v1
```

---

## Demo Flow (manual test)

1. **Owner dashboard** (`/owner`) — spend, alerts, pending approvals
2. **Projects → Cornubia → Lots** — 6 lots, each with BOQ icon
3. **Lot 1** → BOQ: 8/10 bags used (green bar)
4. **Lot 2** → BOQ: 20/10 bags OVER (red bar, alert present)
5. **Procurement → MR-001** → CONVERTED_TO_PO → PO-001 → email mock sent
6. **Procurement → MR-002** → PENDING_APPROVAL, Over BOQ flagged
7. **Deliveries → DEL-001** → 8/8 received, signed
8. **Deliveries → DEL-002** → 150/200 bags PARTIAL
9. **Reconciliation → INV-BZ-001** → Proof Pack → MATCHED ✓
10. **Reconciliation → INV-BZ-002** → Proof Pack → QUANTITY_MISMATCH ✗
11. **Alerts** → 2 open alerts, WhatsApp queue shows MOCK_SENT
12. **Labour → JC-LAB-001** → SITE_APPROVED → office approve → payment approve → paid
13. **Vehicles** → Hilux → tyre R2,800 + fuel R1,200

---

## Environment Variables (.env)

```
DATABASE_URL=postgresql://hmh:hmhdev@127.0.0.1:55432/hmh_system
SECRET_KEY=<64 char random string>
DEBUG=true
SMTP_ENABLED=false          # set true + credentials for real email
WHATSAPP_ENABLED=false      # set true + Meta credentials for real WhatsApp
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=hmh_verify_token
```

---

## Production Deployment (Render)

1. Set `DATABASE_URL` to Render PostgreSQL internal URL
2. Set `SECRET_KEY` to 64-char random string
3. Set `CORS_ORIGINS` to your Vercel frontend URL
4. Start Command is fail-closed via `render.yaml`: `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`. If overriding it in the Render dashboard, keep this exact sequence — the app no longer runs migrations from an in-process startup hook, so a bare `uvicorn ...` command would serve traffic against an un-migrated schema.
5. Set `RUN_STARTUP_SEED=true` for first deploy only (seeds owner account)
6. Set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` — **required** outside development/test as of 2026-08-03; startup now fails without them (`Settings.validate_production_storage`). Two buckets are needed in the Supabase project:
   - `hmh-uploads` — public: **true** (legacy: delivery notes/signatures, stock usage evidence, stage photos, generated MR/PO PDFs)
   - `hmh-evidence-private` (or your `SUPABASE_PRIVATE_BUCKET` value) — public: **false** (Fuel evidence and generic `/attachments/upload` records; served only via signed URLs through `GET /attachments/{id}/download`)
   Confirm both are correctly configured after deploy with `GET /admin/storage-status` (OWNER only) before relying on Fuel evidence capture.

---

## Known Limitations

- `stock_balances` materialized view must be refreshed manually after bulk imports
  (`REFRESH MATERIALIZED VIEW stock_balances;` in psql)
- WhatsApp meta templates need pre-approval (use MOCK mode for demo)
- Photo/signature capture stores to local disk — swap `UPLOAD_DIR` for S3/R2 in production
- OCR extraction not yet implemented — users manually correct delivery note data
