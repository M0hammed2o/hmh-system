"""
Tests for procurement_matching_service.py

Covers:
- match_invoice_to_po: match by PO number in notes
- match_invoice_to_po: match by supplier
- match_invoice_to_po: unmatched → creates INVOICE_MISMATCH alert
- match_delivery_note_to_po: match by supplier
- match_delivery_note_to_po: unmatched → creates DELIVERY_WITHOUT_PO alert
- build_proof_pack: returns all required keys
- GET /proof-packs endpoint
- GET /proof-packs/{id} endpoint
"""

import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def match_setup(db, client):
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


def _make_po(db, project_id, supplier_id, created_by_id, total=1000.0):
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus, VatMode

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=f"PO-MATCH-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.SENT,
        po_date=now,
        total_amount=Decimal(str(total)),
        subtotal_amount=Decimal(str(round(total / 1.15, 2))),
        vat_amount=Decimal(str(round(total - total / 1.15, 2))),
        created_by=uuid.UUID(created_by_id),
        created_at=now,
        updated_at=now,
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderItem(
        purchase_order_id=po.id,
        description="Cement 50kg",
        quantity_ordered=Decimal("10"),
        quantity_received=Decimal("0"),
        unit="bags",
        rate=Decimal(str(total / 10)),
        vat_mode=VatMode.INCLUSIVE,
        vat_rate=Decimal("15.00"),
        line_total=Decimal(str(total)),
        created_at=now,
    ))
    db.flush()
    return po


def _make_invoice(db, project_id, supplier_id, captured_by, total=1000.0, notes=""):
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus

    now = datetime.now(timezone.utc)
    inv = Invoice(
        invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        total_amount=Decimal(str(total)),
        subtotal_amount=Decimal(str(round(total / 1.15, 2))),
        vat_amount=Decimal(str(round(total - total / 1.15, 2))),
        status=RecordStatus.SUBMITTED,
        captured_by=uuid.UUID(captured_by),
        captured_at=now,
        notes=notes,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_delivery(db, project_id, site_id, supplier_id, received_by):
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.enums import RecordStatus

    now = datetime.now(timezone.utc)
    d = Delivery(
        delivery_number=f"DN-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        site_id=uuid.UUID(site_id),
        received_by_user_id=uuid.UUID(received_by),
        delivery_date=now,
        delivery_status=RecordStatus.RECEIVED,
    )
    db.add(d)
    db.flush()
    db.add(DeliveryItem(
        delivery_id=d.id,
        description="Cement 50kg",
        quantity_received=Decimal("10"),
        quantity_expected=Decimal("10"),
        unit="bags",
        created_at=now,
    ))
    db.flush()
    return d


# ── Invoice matching tests ────────────────────────────────────────────────────

class TestMatchInvoiceToPo:
    def test_matches_by_supplier_when_po_exists(self, db, match_setup):
        s = match_setup
        po  = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        db.commit()

        from app.services.procurement_matching_service import match_invoice_to_po
        result = match_invoice_to_po(inv.id, db)

        assert result["matched"] is True
        assert result["po_number"] == po.po_number

    def test_matches_by_po_number_in_notes(self, db, match_setup):
        s  = match_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        inv = _make_invoice(
            db, s["project_id"], s["supplier_id"], s["owner_id"],
            notes=f"Reference: {po.po_number}",
        )
        db.commit()

        from app.services.procurement_matching_service import match_invoice_to_po
        result = match_invoice_to_po(inv.id, db)

        assert result["matched"] is True

    def test_unmatched_creates_alert(self, db, match_setup):
        """An invoice with no matching PO creates an INVOICE_MISMATCH alert."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s   = match_setup
        # No PO created — supplier with no open orders
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()

        from app.services.procurement_matching_service import match_invoice_to_po
        result = match_invoice_to_po(inv.id, db)

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()

        assert result["matched"] is False
        assert after > before

    def test_amount_mismatch_creates_alert(self, db, match_setup):
        """Invoice amount differs from PO → QUANTITY_MISMATCH status + alert."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s  = match_setup
        _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1500.0)
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()

        from app.services.procurement_matching_service import match_invoice_to_po
        result = match_invoice_to_po(inv.id, db)

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()

        # Amount mismatch should have created an alert
        assert after > before
        assert result.get("match_status") == "QUANTITY_MISMATCH"

    def test_returns_not_found_for_unknown_id(self, db):
        from app.services.procurement_matching_service import match_invoice_to_po
        result = match_invoice_to_po(uuid.uuid4(), db)
        assert result["matched"] is False
        assert "not found" in result["reason"].lower()


# ── Delivery note matching tests ──────────────────────────────────────────────

class TestMatchDeliveryNoteToPo:
    def test_matches_delivery_to_po_by_supplier(self, db, match_setup):
        s = match_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        d  = _make_delivery(db, s["project_id"], s["site_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        from app.services.procurement_matching_service import match_delivery_note_to_po
        result = match_delivery_note_to_po(d.id, db)

        assert result["matched"] is True
        assert result["po_number"] == po.po_number

    def test_unmatched_delivery_creates_alert(self, db, match_setup):
        """Delivery with no matching PO creates DELIVERY_WITHOUT_PO alert."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s = match_setup
        # No PO for this supplier
        d = _make_delivery(db, s["project_id"], s["site_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_WITHOUT_PO
        ).count()

        from app.services.procurement_matching_service import match_delivery_note_to_po
        result = match_delivery_note_to_po(d.id, db)

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_WITHOUT_PO
        ).count()

        assert result["matched"] is False
        assert after > before


# ── Proof pack tests ──────────────────────────────────────────────────────────

class TestBuildProofPack:
    def test_returns_required_top_level_keys(self, db, match_setup):
        s   = match_setup
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        from app.services.procurement_matching_service import build_proof_pack
        pack = build_proof_pack(inv.id, db)

        for key in ["invoice", "supplier", "purchase_order", "outgoing_emails",
                    "incoming_supplier_email", "delivery", "match_result",
                    "accounting_flags"]:
            assert key in pack, f"Missing key: {key}"

    def test_accounting_flags_present(self, db, match_setup):
        s   = match_setup
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        from app.services.procurement_matching_service import build_proof_pack
        pack = build_proof_pack(inv.id, db)

        flags = pack["accounting_flags"]
        for flag in ["is_matched", "missing_delivery_note", "missing_signature",
                     "missing_po", "ready_for_payment"]:
            assert flag in flags, f"Missing flag: {flag}"

    def test_empty_dict_for_unknown_invoice(self, db):
        from app.services.procurement_matching_service import build_proof_pack
        result = build_proof_pack(uuid.uuid4(), db)
        assert result == {}


# ── Proof pack API endpoint tests ─────────────────────────────────────────────

class TestProofPackEndpoints:
    def test_list_proof_packs(self, client, db, match_setup):
        s   = match_setup
        tok = s["tok"]
        _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        r = client.get("/api/v1/proof-packs/", headers=auth(tok))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert data["total"] >= 1

    def test_get_proof_pack_by_id(self, client, db, match_setup):
        s   = match_setup
        tok = s["tok"]
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        r = client.get(f"/api/v1/proof-packs/{inv.id}", headers=auth(tok))
        assert r.status_code == 200
        pack = r.json()["data"]
        assert "invoice" in pack
        assert "accounting_flags" in pack

    def test_unknown_proof_pack_returns_404(self, client, db, match_setup):
        tok = match_setup["tok"]
        r   = client.get(f"/api/v1/proof-packs/{uuid.uuid4()}", headers=auth(tok))
        assert r.status_code == 404
