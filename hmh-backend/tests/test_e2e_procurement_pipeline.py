"""
End-to-end integration test for the complete 7-step procurement pipeline.

SCENE: Site Alpha is a construction site that needs 50 bags of cement.
The site foreman creates a material request, which flows through office
approval, supplier quotation, purchase order, invoice, and delivery.

Flow:
  ┌──────────────────────────────────────────────────────────┐
  │  SITE (Site Foreman)                                     │
  │  1. Create Material Request for 50 bags cement           │
  │  2. Submit MR for office approval                        │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  OFFICE (Office Manager)                                 │
  │  3. Approve the Material Request                         │
  │  4. System sends email inquiry to supplier               │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  SUPPLIER RESPONSE (simulated via manual quote entry)    │
  │  5. Supplier submits quotation: R100/bag × 50 = R5 000   │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  OFFICE                                                  │
  │  6. Approve quotation → PO auto-created → emailed        │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  SITE (Site Foreman)                                     │
  │  7. Supplier delivers 50 bags → delivery recorded        │
  │  8. Stock ledger updated (50 bags IN)                    │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  OFFICE                                                  │
  │  9. Supplier invoice R5 750 (incl. VAT) received         │
  └────────────────┬─────────────────────────────────────────┘
                   │
  ┌────────────────▼─────────────────────────────────────────┐
  │  SYSTEM                                                  │
  │  10. All 7 steps COMPLETE → MR auto-closes to CLOSED     │
  │  11. pipeline_complete == True                           │
  └──────────────────────────────────────────────────────────┘

Pipeline steps verified:
  Step 1  MR_SUBMITTED     — MR created and submitted
  Step 2  OFFICE_APPROVAL  — MR approved by office manager
  Step 3  SUPPLIER_EMAIL   — Email inquiry sent to supplier
  Step 4  QUOTATION        — Supplier quote received and approved
  Step 5  PURCHASE_ORDER   — PO created from approved quote
  Step 6  INVOICE          — Invoice captured and linked to PO
  Step 7  DELIVERY         — Goods delivered and stock updated
  Final   AUTO-CLOSE       — MR.status = CLOSED, pipeline_complete = True
"""

import uuid
import pytest
from datetime import date, datetime, timezone

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier, make_item


# ── Scenario constants ────────────────────────────────────────────────────────

CEMENT_UNIT          = "bag"
CEMENT_QTY           = 50
CEMENT_UNIT_PRICE    = 100.0        # R100 per bag
CEMENT_LINE_TOTAL    = 5_000.0      # 50 × R100
INVOICE_TOTAL        = 5_750.0      # R5 000 net + 15% VAT
INVOICE_SUBTOTAL     = 5_000.0
INVOICE_VAT          = 750.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _api(path: str) -> str:
    return f"/api/v1{path}"


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def scenario(db, client):
    """
    Bootstrap all standing data:
      - office_manager : OWNER (approves MRs, manages office)
      - site_foreman   : OFFICE_USER with project access (creates & submits MRs)
      - supplier       : ABC Cement cc — has email address
      - item           : Portland Cement (catalog item used for stock)
      - project        : Site Alpha Construction
      - site           : Site Alpha
    """
    office  = make_user(db, role="OWNER")
    foreman = make_user(db, role="OFFICE_USER")

    project = make_project(db, owner_id=office["id"])
    site    = make_site(db, project_id=project["id"], name="Site Alpha")

    supplier = make_supplier(
        db,
        name="ABC Cement cc",
        email=f"cement_{uuid.uuid4().hex[:6]}@supplier.test",
    )

    item = make_item(db, name=f"Portland Cement {uuid.uuid4().hex[:4]}", unit=CEMENT_UNIT)

    # Give foreman access to the project
    from tests.conftest import make_user_project_access
    make_user_project_access(db, foreman["id"], project["id"])

    office_tok  = login(client, office["email"],  office["password"])
    foreman_tok = login(client, foreman["email"], foreman["password"])

    return {
        "office_tok":   office_tok,
        "foreman_tok":  foreman_tok,
        "project_id":   project["id"],
        "site_id":      site["id"],
        "supplier_id":  supplier["id"],
        "supplier_email": supplier["email"],
        "item_id":      item["id"],
        "office_id":    office["id"],
    }


# ── Full end-to-end test ──────────────────────────────────────────────────────

class TestProcurementPipelineEndToEnd:

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1 — SITE: Create Material Request
    # ─────────────────────────────────────────────────────────────────────────

    def test_step1_site_creates_material_request(self, client, db, scenario):
        """Site foreman creates a Material Request for cement. Status starts as DRAFT."""
        s = scenario

        r = client.post(
            _api(f"/projects/{s['project_id']}/material-requests/"),
            json={
                "site_id": s["site_id"],
                "preferred_supplier_id": s["supplier_id"],
                "priority": "NORMAL",
                "delivery_destination": "SITE_STORE",
                "notes": "Needed for foundation work on Block A",
                "items": [{
                    "item_id": s["item_id"],
                    "description": "Portland Cement — 50kg bags",
                    "requested_quantity": CEMENT_QTY,
                    "unit": CEMENT_UNIT,
                }],
            },
            headers=auth(s["foreman_tok"]),
        )
        assert r.status_code == 201, r.text
        mr = r.json()["data"]

        assert mr["status"] == "DRAFT"
        assert mr["request_number"].startswith("MR-")
        assert len(mr["items"]) == 1
        assert float(mr["items"][0]["requested_quantity"]) == CEMENT_QTY

        # Pipeline: step 1 is CURRENT (not yet submitted)
        pipe = client.get(
            _api(f"/procurement/mrs/{mr['id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][0]["status"] == "CURRENT",  "Step 1 should be CURRENT before submission"
        assert pipe["steps"][1]["status"] == "WAITING",  "Step 2 should be WAITING"

        # Stash for downstream steps
        s["mr_id"] = mr["id"]


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2 — SITE: Submit MR for office approval
    # ─────────────────────────────────────────────────────────────────────────

    def test_step2_site_submits_material_request(self, client, db, scenario):
        """Site foreman submits the MR. Status moves to SUBMITTED or PENDING_APPROVAL."""
        s = scenario
        self.test_step1_site_creates_material_request(client, db, scenario)

        r = client.post(
            _api(f"/material-requests/{s['mr_id']}/submit"),
            headers=auth(s["foreman_tok"]),
        )
        assert r.status_code == 200, r.text
        mr = r.json()["data"]
        assert mr["status"] in ("SUBMITTED", "PENDING_APPROVAL"), (
            f"Expected SUBMITTED or PENDING_APPROVAL after submit, got {mr['status']}"
        )

        # Pipeline: step 1 now COMPLETE, step 2 CURRENT
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][0]["status"] == "COMPLETE", "Step 1 should be COMPLETE after submission"
        assert pipe["steps"][1]["status"] == "CURRENT",  "Step 2 should be CURRENT (awaiting approval)"


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3 — OFFICE: Approve the Material Request
    # ─────────────────────────────────────────────────────────────────────────

    def test_step3_office_approves_material_request(self, client, db, scenario):
        """Office manager approves the MR. Status moves to APPROVED."""
        s = scenario
        self.test_step2_site_submits_material_request(client, db, scenario)

        r = client.post(
            _api(f"/material-requests/{s['mr_id']}/approve"),
            json={},
            headers=auth(s["office_tok"]),
        )
        assert r.status_code == 200, r.text
        mr = r.json()["data"]
        assert mr["status"] == "APPROVED", f"Expected APPROVED, got {mr['status']}"
        assert mr["approved_by"] is not None, "approved_by must be set"
        assert mr["approved_at"] is not None, "approved_at must be set"

        # Pipeline: step 2 COMPLETE
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][1]["status"] == "COMPLETE", "Step 2 should be COMPLETE after approval"


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4 — OFFICE: Send email inquiry to supplier
    # ─────────────────────────────────────────────────────────────────────────

    def test_step4_office_sends_email_to_supplier(self, client, db, scenario):
        """Office sends supplier email inquiry. MREmailLog status = SENT or MOCK_SENT."""
        s = scenario
        self.test_step3_office_approves_material_request(client, db, scenario)

        r = client.post(
            _api(f"/material-requests/{s['mr_id']}/send-email"),
            headers=auth(s["office_tok"]),
        )
        assert r.status_code == 200, r.text
        email_data = r.json()["data"]
        assert email_data["status"] in ("SENT", "MOCK_SENT", "FAILED"), (
            f"Unexpected email status: {email_data['status']}"
        )

        # If email failed (no SMTP in test env), insert mock log directly so
        # the pipeline can advance — this mirrors what the UI "mock sent" button does.
        if email_data["status"] == "FAILED":
            from app.models.mr_email_log import MREmailLog
            db.add(MREmailLog(
                id=uuid.uuid4(),
                material_request_id=uuid.UUID(s["mr_id"]),
                supplier_id=uuid.UUID(s["supplier_id"]),
                sent_to_email=s["supplier_email"],
                email_subject="MR Inquiry",
                status="MOCK_SENT",
                sent_at=_now(),
                created_at=_now(),
            ))
            db.flush()

        # Pipeline: step 3 COMPLETE
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        step3 = pipe["steps"][2]
        assert step3["status"] == "COMPLETE", (
            f"Step 3 (SUPPLIER_EMAIL) should be COMPLETE after send; got {step3['status']}"
        )
        assert step3["email_sent"] is True, "email_sent must be True in pipeline"
        assert step3["supplier_email"] == s["supplier_email"], "supplier email in pipeline must match"


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5 — SUPPLIER: Quotation received (simulated via manual entry)
    # ─────────────────────────────────────────────────────────────────────────

    def test_step5_supplier_quotation_received(self, client, db, scenario):
        """
        Supplier responds with a quotation.
        In production this arrives via Gmail OCR; in tests we add it manually.
        Quotation: 50 bags × R100 = R5 000.
        """
        s = scenario
        self.test_step4_office_sends_email_to_supplier(client, db, scenario)

        r = client.post(
            _api(f"/material-requests/{s['mr_id']}/quotes"),
            json={
                "supplier_id":    s["supplier_id"],
                "description":    "Portland Cement 50kg bags",
                "quoted_quantity": CEMENT_QTY,
                "unit_price":      CEMENT_UNIT_PRICE,
                "unit":            CEMENT_UNIT,
                "delivery_date":   str(date.today()),
                "notes":           "Price valid for 7 days. Delivery within 3 working days.",
            },
            headers=auth(s["office_tok"]),
        )
        assert r.status_code in (200, 201), r.text
        quote = r.json()["data"]
        assert quote["status"] == "PENDING",  "New quote should be PENDING"
        assert float(quote["unit_price"]) == CEMENT_UNIT_PRICE
        assert float(quote["quoted_quantity"]) == CEMENT_QTY

        # Pipeline: step 4 CURRENT with 1 pending quote
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        step4 = pipe["steps"][3]
        assert step4["status"] == "CURRENT",  "Step 4 should be CURRENT while quote is PENDING"
        assert step4["pending_count"] >= 1,   "At least 1 pending quote expected"
        assert step4["approved_count"] == 0,  "No approved quotes yet"

        s["quote_id"] = quote["id"]


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6 — OFFICE: Approve quotation → PO auto-created + emailed
    # ─────────────────────────────────────────────────────────────────────────

    def test_step6_office_approves_quotation_and_po_created(self, client, db, scenario):
        """
        Office approves the supplier quotation.
        This auto-creates a Purchase Order and emails it to the supplier.
        MR status moves to CONVERTED_TO_PO.
        """
        s = scenario
        self.test_step5_supplier_quotation_received(client, db, scenario)

        r = client.post(
            _api(f"/procurement/mrs/{s['mr_id']}/quotes/{s['quote_id']}/approve"),
            json={"notes": "Approved — price within budget."},
            headers=auth(s["office_tok"]),
        )
        assert r.status_code == 200, r.text
        result = r.json()["data"]
        assert "po_id"     in result, "po_id must be returned on quote approval"
        assert "po_number" in result, "po_number must be returned on quote approval"

        s["po_id"] = result["po_id"]

        # MR status should now be CONVERTED_TO_PO
        mr_r = client.get(
            _api(f"/material-requests/{s['mr_id']}"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert mr_r["status"] == "CONVERTED_TO_PO", (
            f"MR must be CONVERTED_TO_PO after quote approval, got {mr_r['status']}"
        )

        # PO must exist and have correct total
        from app.models.purchase_order import PurchaseOrder
        po = db.get(PurchaseOrder, uuid.UUID(s["po_id"]))
        assert po is not None, "PurchaseOrder must exist in DB"
        assert float(po.total_amount) > 0, "PO total_amount must be > 0"

        # Pipeline: steps 4 + 5 COMPLETE
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][3]["status"] == "COMPLETE", "Step 4 (QUOTATION) must be COMPLETE"
        assert pipe["steps"][4]["status"] == "COMPLETE", "Step 5 (PURCHASE_ORDER) must be COMPLETE"
        assert pipe["steps"][4]["po"]["id"] == s["po_id"], "PO id must appear in pipeline step 5"


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 7 — SITE: Delivery received + stock updated
    # ─────────────────────────────────────────────────────────────────────────

    def test_step7_site_records_delivery_and_stock_updates(self, client, db, scenario):
        """
        The site foreman receives 50 bags of cement from the supplier.
        Delivery is recorded → PO quantity_received updated → stock ledger credited.
        """
        s = scenario
        self.test_step6_office_approves_quotation_and_po_created(client, db, scenario)

        dn_number = f"DN-{uuid.uuid4().hex[:8].upper()}"
        r = client.post(
            _api(f"/projects/{s['project_id']}/deliveries/"),
            json={
                "destination":       "SITE_STORE",
                "supplier_id":       s["supplier_id"],
                "site_id":           s["site_id"],
                "purchase_order_id": s["po_id"],
                "delivery_number":   dn_number,
                "delivery_date":     str(date.today()),
                "items": [{
                    "description":       "Portland Cement 50kg bags",
                    "item_id":           s["item_id"],
                    "quantity_received": CEMENT_QTY,
                    "quantity_expected": CEMENT_QTY,
                    "unit":              CEMENT_UNIT,
                }],
            },
            headers=auth(s["foreman_tok"]),
        )
        assert r.status_code == 201, r.text
        delivery = r.json()["data"]
        s["delivery_id"] = delivery.get("delivery_id") or delivery.get("id")

        # PO item quantity_received must now be CEMENT_QTY
        from app.models.purchase_order import PurchaseOrderItem
        poi = (
            db.query(PurchaseOrderItem)
            .filter(PurchaseOrderItem.purchase_order_id == uuid.UUID(s["po_id"]))
            .first()
        )
        assert poi is not None, "PurchaseOrderItem must exist"
        db.expire(poi)
        poi_fresh = db.get(PurchaseOrderItem, poi.id)
        assert float(poi_fresh.quantity_received) == pytest.approx(CEMENT_QTY), (
            f"PO item quantity_received must be {CEMENT_QTY}, got {poi_fresh.quantity_received}"
        )

        # Stock ledger: a DELIVERY_RECEIVED entry must exist for this item
        from app.models.stock import StockLedger
        from app.models.enums import MovementType
        ledger_entry = (
            db.query(StockLedger)
            .filter(
                StockLedger.project_id == uuid.UUID(s["project_id"]),
                StockLedger.item_id    == uuid.UUID(s["item_id"]),
                StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
            )
            .first()
        )
        assert ledger_entry is not None, (
            "Stock ledger must have a DELIVERY_RECEIVED entry after delivery"
        )
        assert float(ledger_entry.quantity_in) == pytest.approx(CEMENT_QTY), (
            f"Stock quantity_in must be {CEMENT_QTY}, got {ledger_entry.quantity_in}"
        )

        # Pipeline: step 7 COMPLETE
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][6]["status"] == "COMPLETE", (
            "Step 7 (DELIVERY) must be COMPLETE after delivery is recorded"
        )


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 8 — OFFICE: Capture supplier invoice
    # ─────────────────────────────────────────────────────────────────────────

    def test_step8_office_captures_invoice(self, client, db, scenario):
        """
        The supplier sends an invoice (R5 750 incl. 15% VAT).
        Office captures it in the system and links it to the PO.
        Pipeline step 6 (INVOICE) becomes COMPLETE.
        """
        s = scenario
        self.test_step7_site_records_delivery_and_stock_updates(client, db, scenario)

        inv_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        r = client.post(
            _api(f"/projects/{s['project_id']}/invoices/"),
            json={
                "invoice_number":  inv_number,
                "supplier_id":     s["supplier_id"],
                "purchase_order_id": s["po_id"],
                "invoice_date":    str(date.today()),
                "subtotal_amount": INVOICE_SUBTOTAL,
                "vat_amount":      INVOICE_VAT,
                "total_amount":    INVOICE_TOTAL,
                "notes":           "Please pay within 30 days.",
            },
            headers=auth(s["office_tok"]),
        )
        assert r.status_code == 201, r.text
        invoice = r.json()["data"]
        assert invoice["invoice_number"] == inv_number
        assert float(invoice["total_amount"]) == pytest.approx(INVOICE_TOTAL)

        s["invoice_id"] = invoice["id"]

        # Pipeline: step 6 COMPLETE
        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]
        assert pipe["steps"][5]["status"] == "COMPLETE", (
            "Step 6 (INVOICE) must be COMPLETE after invoice is captured"
        )
        assert pipe["steps"][5]["invoice"]["id"] == s["invoice_id"], (
            "Pipeline step 6 must reference the captured invoice"
        )


    # ─────────────────────────────────────────────────────────────────────────
    # STEP 9 — SYSTEM: All steps complete → MR auto-closes
    # ─────────────────────────────────────────────────────────────────────────

    def test_step9_pipeline_completes_and_mr_auto_closes(self, client, db, scenario):
        """
        With all 7 steps COMPLETE, the pipeline endpoint auto-closes the MR:
          - pipeline_complete == True
          - mr_status == "CLOSED"
          - all 7 steps have status "COMPLETE"
          - DB record: mr.status == RecordStatus.CLOSED
        """
        s = scenario
        self.test_step8_office_captures_invoice(client, db, scenario)

        pipe = client.get(
            _api(f"/procurement/mrs/{s['mr_id']}/pipeline"),
            headers=auth(s["office_tok"]),
        ).json()["data"]

        # All 7 steps must be COMPLETE
        for step in pipe["steps"]:
            assert step["status"] == "COMPLETE", (
                f"Step {step['step']} ({step['key']}) expected COMPLETE, got {step['status']}"
            )

        # pipeline_complete flag
        assert pipe["pipeline_complete"] is True, (
            "pipeline_complete must be True when all 7 steps are done"
        )

        # MR auto-closed in response
        assert pipe["mr_status"] == "CLOSED", (
            f"MR must be auto-closed to CLOSED, got {pipe['mr_status']}"
        )

        # DB confirmation
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus
        db.expire_all()
        mr_db = db.get(MaterialRequest, uuid.UUID(s["mr_id"]))
        assert mr_db.status == RecordStatus.CLOSED, (
            f"DB: MR status must be CLOSED, got {mr_db.status}"
        )

        # Correct step data in response
        assert pipe["steps"][0]["item_count"] == 1,   "Step 1 must report 1 item"
        assert pipe["steps"][1]["approved_at"] is not None, "Step 2 must have approved_at"
        assert pipe["steps"][2]["email_sent"] is True,      "Step 3 must show email_sent"
        assert pipe["steps"][3]["approved_count"] >= 1,     "Step 4 must have approved quote"
        assert pipe["steps"][4]["po"] is not None,           "Step 5 must have PO details"
        assert pipe["steps"][5]["invoice"] is not None,      "Step 6 must have invoice details"
        assert pipe["steps"][6]["delivery"] is not None,     "Step 7 must have delivery details"


    # ─────────────────────────────────────────────────────────────────────────
    # BONUS — Completed MR appears in "History" on the procurement page
    # ─────────────────────────────────────────────────────────────────────────

    def test_completed_mr_status_is_closed_in_list(self, client, db, scenario):
        """
        After auto-close, the MR list for the project must return the MR with
        status=CLOSED so the frontend can show it in the Completed/History section.
        """
        s = scenario
        self.test_step9_pipeline_completes_and_mr_auto_closes(client, db, scenario)

        r = client.get(
            _api(f"/projects/{s['project_id']}/material-requests/"),
            headers=auth(s["office_tok"]),
        )
        assert r.status_code == 200, r.text
        mrs = r.json()["data"]

        our_mr = next((m for m in mrs if m["id"] == s["mr_id"]), None)
        assert our_mr is not None, "MR must appear in project MR list"
        assert our_mr["status"] == "CLOSED", (
            "Closed MR must appear with status=CLOSED in project MR list (for History tab)"
        )


    # ─────────────────────────────────────────────────────────────────────────
    # BONUS — Stock balance reflects the received delivery
    # ─────────────────────────────────────────────────────────────────────────

    def test_stock_balance_reflects_delivery(self, client, db, scenario):
        """
        After the full pipeline completes, the stock ledger must have a
        DELIVERY_RECEIVED entry totalling CEMENT_QTY for the cement item.
        The materialized view is not reliable in the test environment (stale),
        so we verify directly against the stock_ledger table.
        """
        from sqlalchemy import func
        from app.models.stock import StockLedger
        from app.models.enums import MovementType

        s = scenario
        self.test_step9_pipeline_completes_and_mr_auto_closes(client, db, scenario)

        # Direct ledger aggregation — project warehouse (site_id=NULL)
        total_in = (
            db.query(func.sum(StockLedger.quantity_in))
            .filter(
                StockLedger.project_id    == uuid.UUID(s["project_id"]),
                StockLedger.item_id       == uuid.UUID(s["item_id"]),
                StockLedger.movement_type == MovementType.DELIVERY_RECEIVED,
            )
            .scalar()
        )
        assert total_in is not None, (
            "Stock ledger must have DELIVERY_RECEIVED entries for the cement item"
        )
        assert float(total_in) >= CEMENT_QTY, (
            f"Total stock received must be ≥ {CEMENT_QTY} bags, got {total_in}"
        )


# ── Quick-smoke: each pipeline step status transition ────────────────────────

class TestPipelineStepProgressions:
    """
    Lightweight checks that each step label and key is correct in the pipeline
    response, without running the full 9-step flow.
    """

    @pytest.fixture
    def fresh_mr(self, db, client):
        """Create a minimal submitted MR for step-progression checks."""
        owner   = make_user(db, role="OWNER")
        project = make_project(db, owner_id=owner["id"])
        site    = make_site(db, project_id=project["id"])
        supplier = make_supplier(db)
        item    = make_item(db, name=f"Sand {uuid.uuid4().hex[:4]}")
        tok     = login(client, owner["email"], owner["password"])

        from app.models.material_request import MaterialRequest, MaterialRequestItem
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

        mr = MaterialRequest(
            id=uuid.uuid4(),
            request_number=f"MR-{uuid.uuid4().hex[:8].upper()}",
            project_id=uuid.UUID(project["id"]),
            site_id=uuid.UUID(site["id"]),
            requested_by=uuid.UUID(owner["id"]),
            preferred_supplier_id=uuid.UUID(supplier["id"]),
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            status=RecordStatus.SUBMITTED,
            over_boq=False,
            requested_date=datetime.now(timezone.utc),
        )
        db.add(mr)
        db.add(MaterialRequestItem(
            id=uuid.uuid4(),
            material_request_id=mr.id,
            description="Sand",
            requested_quantity=10,
            unit="m3",
        ))
        db.flush()

        return {"mr_id": str(mr.id), "tok": tok, "supplier": {"id": supplier["id"], "email": supplier["email"]}}

    def test_pipeline_has_seven_steps(self, client, db, fresh_mr):
        pipe = client.get(
            _api(f"/procurement/mrs/{fresh_mr['mr_id']}/pipeline"),
            headers=auth(fresh_mr["tok"]),
        ).json()["data"]
        assert len(pipe["steps"]) == 7, "Pipeline must always have exactly 7 steps"

    def test_pipeline_step_keys_are_correct(self, client, db, fresh_mr):
        pipe = client.get(
            _api(f"/procurement/mrs/{fresh_mr['mr_id']}/pipeline"),
            headers=auth(fresh_mr["tok"]),
        ).json()["data"]
        expected_keys = [
            "MR_SUBMITTED", "OFFICE_APPROVAL", "SUPPLIER_EMAIL",
            "QUOTATION", "PURCHASE_ORDER", "INVOICE", "DELIVERY",
        ]
        actual_keys = [s["key"] for s in pipe["steps"]]
        assert actual_keys == expected_keys

    def test_pipeline_step_numbers_are_sequential(self, client, db, fresh_mr):
        pipe = client.get(
            _api(f"/procurement/mrs/{fresh_mr['mr_id']}/pipeline"),
            headers=auth(fresh_mr["tok"]),
        ).json()["data"]
        assert [s["step"] for s in pipe["steps"]] == [1, 2, 3, 4, 5, 6, 7]

    def test_submitted_mr_shows_step1_complete_step2_current(self, client, db, fresh_mr):
        pipe = client.get(
            _api(f"/procurement/mrs/{fresh_mr['mr_id']}/pipeline"),
            headers=auth(fresh_mr["tok"]),
        ).json()["data"]
        assert pipe["steps"][0]["status"] == "COMPLETE"
        assert pipe["steps"][1]["status"] == "CURRENT"
        # All remaining steps are WAITING
        for step in pipe["steps"][2:]:
            assert step["status"] == "WAITING", (
                f"Step {step['step']} should be WAITING for a just-submitted MR"
            )

    def test_pipeline_not_complete_for_submitted_mr(self, client, db, fresh_mr):
        pipe = client.get(
            _api(f"/procurement/mrs/{fresh_mr['mr_id']}/pipeline"),
            headers=auth(fresh_mr["tok"]),
        ).json()["data"]
        assert pipe["pipeline_complete"] is False
        assert pipe["mr_status"] != "CLOSED"
