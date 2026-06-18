"""
Tests for automatic MR closure when all 7 pipeline steps complete.

GET /procurement/mrs/{mr_id}/pipeline auto-sets mr.status = CLOSED and
returns pipeline_complete = True when every step is COMPLETE.

Coverage:
 1. mr.status set to CLOSED on first call when all 7 steps are complete
 2. response mr_status == "CLOSED" when auto-closed
 3. pipeline_complete == True in response when all 7 steps complete
 4. pipeline_complete == False when pipeline is not finished
 5. Already-CLOSED MR is not mutated again (idempotent)
 6. Cancelled MR is not auto-closed
"""

import uuid
import pytest
from datetime import datetime, timezone

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_supplier,
)


# ── Builder ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_full_pipeline(db, project_id: str, site_id: str, supplier_id: str,
                        owner_id: str, mr_status: str = "CONVERTED_TO_PO"):
    """
    Build a complete 7-step procurement chain in the DB and return the MR id.

    Steps satisfied:
      1  MR_SUBMITTED     — mr.status in converted-to-po set
      2  OFFICE_APPROVAL  — mr.approved_at is set
      3  SUPPLIER_EMAIL   — MREmailLog status=SENT
      4  QUOTATION        — MRQuote status=APPROVED
      5  PURCHASE_ORDER   — PurchaseOrder linked to MR
      6  INVOICE          — Invoice linked to PO
      7  DELIVERY         — Delivery linked to PO
    """
    from app.models.material_request import MaterialRequest, MaterialRequestItem
    from app.models.mr_email_log import MREmailLog
    from app.models.mr_quote import MRQuote
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.invoice import Invoice
    from app.models.delivery import Delivery
    from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

    # Step 1+2 — Material Request
    mr = MaterialRequest(
        id=uuid.uuid4(),
        request_number=f"MR-{uuid.uuid4().hex[:8].upper()}",
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        requested_by=uuid.UUID(owner_id),
        preferred_supplier_id=uuid.UUID(supplier_id),
        priority=MRPriority.NORMAL,
        delivery_destination=DeliveryDestination.MAIN_WAREHOUSE,
        status=RecordStatus(mr_status),
        over_boq=False,
        requested_date=_now(),
        approved_at=_now(),
    )
    db.add(mr)
    db.flush()

    # MR item
    db.add(MaterialRequestItem(
        id=uuid.uuid4(),
        material_request_id=mr.id,
        description="Test Cement",
        requested_quantity=10,
        unit="bag",
    ))
    db.flush()

    # Step 3 — Email log (SENT status satisfies email_sent check)
    db.add(MREmailLog(
        id=uuid.uuid4(),
        material_request_id=mr.id,
        supplier_id=uuid.UUID(supplier_id),
        sent_to_email="supplier@test.com",
        email_subject="MR quotation request",
        status="SENT",
        sent_at=_now(),
        created_at=_now(),
    ))
    db.flush()

    # Step 4 — Approved quote
    db.add(MRQuote(
        id=uuid.uuid4(),
        material_request_id=mr.id,
        supplier_id=uuid.UUID(supplier_id),
        description="Test Cement",
        quoted_quantity=10,
        unit="bag",
        unit_price=100,
        total_price=1000,
        is_selected=True,
        source="MANUAL",
        status="APPROVED",
        approved_at=_now(),
        created_at=_now(),
    ))
    db.flush()

    # Step 5 — Purchase Order
    po = PurchaseOrder(
        id=uuid.uuid4(),
        po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        material_request_id=mr.id,
        created_by=uuid.UUID(owner_id),
        status=RecordStatus.APPROVED,
        po_date=_now(),
        total_amount=1000,
        subtotal_amount=869.57,
        vat_amount=130.43,
    )
    db.add(po)
    db.flush()

    db.add(PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po.id,
        description="Test Cement",
        quantity_ordered=10,
        quantity_received=10,
        unit="bag",
        rate=100,
        created_at=_now(),
    ))
    db.flush()

    # Step 6 — Invoice
    db.add(Invoice(
        id=uuid.uuid4(),
        invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        purchase_order_id=po.id,
        total_amount=1000,
        status=RecordStatus.APPROVED,
        captured_at=_now(),
    ))
    db.flush()

    # Step 7 — Delivery
    db.add(Delivery(
        id=uuid.uuid4(),
        delivery_number=f"DN-{uuid.uuid4().hex[:8].upper()}",
        purchase_order_id=po.id,
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        received_by_user_id=uuid.UUID(owner_id),
        delivery_date=_now(),
        delivery_status=RecordStatus.RECEIVED,
    ))
    db.flush()

    return mr


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMRPipelineAutoClose:

    def test_mr_status_set_to_closed_when_all_steps_complete(self, client, db, setup):
        """All 7 steps complete → mr.status must become CLOSED in the DB."""
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus

        s = setup
        mr = _make_full_pipeline(db, s["project_id"], s["site_id"],
                                  s["supplier_id"], s["owner_id"])

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text

        db.expire(mr)
        mr_fresh = db.get(MaterialRequest, mr.id)
        assert mr_fresh.status == RecordStatus.CLOSED, (
            f"Expected CLOSED, got {mr_fresh.status}"
        )

    def test_response_mr_status_is_closed_after_auto_close(self, client, db, setup):
        """Pipeline endpoint must return mr_status='CLOSED' in the response body."""
        s = setup
        mr = _make_full_pipeline(db, s["project_id"], s["site_id"],
                                  s["supplier_id"], s["owner_id"])

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["mr_status"] == "CLOSED", (
            f"Expected mr_status=CLOSED in response, got {data['mr_status']}"
        )

    def test_pipeline_complete_true_when_all_steps_done(self, client, db, setup):
        """pipeline_complete must be True when all 7 steps are COMPLETE."""
        s = setup
        mr = _make_full_pipeline(db, s["project_id"], s["site_id"],
                                  s["supplier_id"], s["owner_id"])

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["pipeline_complete"] is True, (
            "pipeline_complete must be True when all 7 steps are COMPLETE"
        )

    def test_pipeline_complete_false_when_incomplete(self, client, db, setup):
        """pipeline_complete must be False when the pipeline is not finished."""
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

        s = setup
        mr = MaterialRequest(
            id=uuid.uuid4(),
            request_number=f"MR-{uuid.uuid4().hex[:8].upper()}",
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            requested_by=uuid.UUID(s["owner_id"]),
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.MAIN_WAREHOUSE,
            status=RecordStatus.SUBMITTED,
            over_boq=False,
            requested_date=_now(),
        )
        db.add(mr)
        db.flush()

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["pipeline_complete"] is False, (
            "pipeline_complete must be False for an in-progress pipeline"
        )

    def test_already_closed_mr_is_not_mutated(self, client, db, setup):
        """Calling pipeline on an already-CLOSED MR must not error or change status."""
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus

        s = setup
        mr = _make_full_pipeline(db, s["project_id"], s["site_id"],
                                  s["supplier_id"], s["owner_id"],
                                  mr_status="CLOSED")

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text

        db.expire(mr)
        mr_fresh = db.get(MaterialRequest, mr.id)
        assert mr_fresh.status == RecordStatus.CLOSED, (
            "An already-CLOSED MR must remain CLOSED after a pipeline call"
        )

    def test_cancelled_mr_is_not_auto_closed(self, client, db, setup):
        """A CANCELLED MR must never be auto-closed by the pipeline endpoint."""
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

        s = setup
        mr = MaterialRequest(
            id=uuid.uuid4(),
            request_number=f"MR-{uuid.uuid4().hex[:8].upper()}",
            project_id=uuid.UUID(s["project_id"]),
            site_id=uuid.UUID(s["site_id"]),
            requested_by=uuid.UUID(s["owner_id"]),
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.MAIN_WAREHOUSE,
            status=RecordStatus.CANCELLED,
            over_boq=False,
            requested_date=_now(),
        )
        db.add(mr)
        db.flush()

        r = client.get(
            f"/api/v1/procurement/mrs/{mr.id}/pipeline",
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200, r.text

        db.expire(mr)
        mr_fresh = db.get(MaterialRequest, mr.id)
        assert mr_fresh.status == RecordStatus.CANCELLED, (
            "A CANCELLED MR must not be changed to CLOSED by the pipeline endpoint"
        )
