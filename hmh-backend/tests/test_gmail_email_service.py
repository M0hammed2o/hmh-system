"""
Tests for email_service.py

Covers:
- Mock mode: send_email returns MOCK_SENT, no SMTP connection
- send_po_email in mock mode: creates PoEmailLog with sent status
- send_po_email with missing supplier email: creates failed log
- send_supplier_po_email: looks up PO by ID and delegates
- PO email failure creates SystemAlert
"""

import uuid
import pytest
from datetime import datetime, timezone

from tests.conftest import (
    auth, login, make_user, make_project, make_site, make_supplier,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def email_setup(db, client):
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


def _make_po(db, project_id, supplier_id, created_by_id):
    """Insert a minimal PurchaseOrder directly via ORM."""
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus, VatMode
    from decimal import Decimal

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.DRAFT,
        po_date=now,
        total_amount=Decimal("1000.00"),
        subtotal_amount=Decimal("869.57"),
        vat_amount=Decimal("130.43"),
        created_by=uuid.UUID(created_by_id),
        created_at=now,
        updated_at=now,
    )
    db.add(po)
    db.flush()

    item = PurchaseOrderItem(
        purchase_order_id=po.id,
        description="Test Cement",
        quantity_ordered=Decimal("10"),
        quantity_received=Decimal("0"),
        unit="bags",
        rate=Decimal("100.00"),
        vat_mode=VatMode.INCLUSIVE,
        vat_rate=Decimal("15.00"),
        line_total=Decimal("1000.00"),
        created_at=now,
    )
    db.add(item)
    db.flush()
    return po


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSendEmail:
    """Tests for the generic send_email() function."""

    def test_mock_mode_returns_mock_sent(self):
        """With SMTP_ENABLED=false, send_email must return MOCK_SENT without connecting."""
        from app.services.email_service import send_email
        result = send_email(
            to_email="supplier@example.com",
            subject="Test subject",
            body="<p>Test body</p>",
        )
        assert result["status"] == "MOCK_SENT"
        assert result["error"] is None

    def test_mock_mode_does_not_raise(self):
        """Mock mode must never raise regardless of bad parameters."""
        from app.services.email_service import send_email
        result = send_email("", "subject", "body")
        assert result["status"] == "MOCK_SENT"


class TestSendPoEmail:
    """Tests for send_po_email() which stores PoEmailLog."""

    def test_mock_mode_creates_email_log(self, db, email_setup):
        """Mock mode creates PoEmailLog with sent status."""
        from app.services.email_service import send_po_email
        from app.models.purchase_order import PoEmailLog
        from app.models.enums import EmailStatus

        s = email_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        log = send_po_email(db, po)
        assert log.id is not None
        assert log.status == EmailStatus.sent
        assert log.purchase_order_id == po.id
        assert log.sent_at is not None

    def test_missing_supplier_email_creates_failed_log(self, db, email_setup):
        """A supplier with no email creates a failed PoEmailLog."""
        from app.models.supplier import Supplier
        from app.services.email_service import send_po_email
        from app.models.enums import EmailStatus

        s = email_setup
        # Clear the supplier email
        supplier = db.get(Supplier, uuid.UUID(s["supplier_id"]))
        supplier.email = None
        db.flush()

        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        log = send_po_email(db, po)
        assert log.status == EmailStatus.failed
        assert log.error_message is not None

    def test_email_log_contains_po_number_in_subject(self, db, email_setup):
        """The stored email subject includes the PO number."""
        from app.services.email_service import send_po_email

        s = email_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        log = send_po_email(db, po)
        assert po.po_number in (log.email_subject or "")

    def test_email_log_contains_document_instruction(self, db, email_setup):
        """The email body includes the procurement Gmail address."""
        from app.services.email_service import send_po_email

        s = email_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        log = send_po_email(db, po)
        assert "procurementhmhgroup@gmail.com" in (log.email_body or "")


class TestSendSupplierPoEmail:
    """Tests for the high-level send_supplier_po_email(po_id, db) wrapper."""

    def test_looks_up_po_by_id_and_sends(self, db, email_setup):
        from app.services.email_service import send_supplier_po_email
        from app.models.enums import EmailStatus

        s = email_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        log = send_supplier_po_email(po.id, db)
        assert log.status == EmailStatus.sent
        assert log.purchase_order_id == po.id

    def test_raises_value_error_for_unknown_po_id(self, db):
        from app.services.email_service import send_supplier_po_email

        with pytest.raises(ValueError, match="not found"):
            send_supplier_po_email(uuid.uuid4(), db)


class TestPoEmailViaApi:
    """Integration tests hitting the POST /purchase-orders/{id}/send-email endpoint."""

    def test_send_email_endpoint_returns_200(self, client, db, email_setup):
        s   = email_setup
        tok = s["tok"]

        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        r = client.post(
            f"/api/v1/purchase-orders/{po.id}/send-email",
            headers=auth(tok),
        )
        assert r.status_code in (200, 201), r.text
