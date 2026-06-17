"""
Tests for GET /suppliers/{id}/documents endpoint.

Covers:
- Returns POs, invoices, deliveries, quotations for a supplier
- Returns Gmail email attachment records matched to this supplier's POs
- Gmail attachments include gmail_attachment_id for authenticated download
"""

import uuid
import tempfile
import os
from datetime import datetime, timezone

import pytest

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_po(db, project_id: str, supplier_id: str, owner_id: str, po_number: str = None):
    from app.models.purchase_order import PurchaseOrder
    from app.models.enums import RecordStatus
    from decimal import Decimal
    po = PurchaseOrder(
        po_number=po_number or f"PO-DOC-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.APPROVED,
        po_date=_now(),
        total_amount=Decimal("5000.00"),
        subtotal_amount=Decimal("4347.83"),
        vat_amount=Decimal("652.17"),
        created_by=uuid.UUID(owner_id),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(po)
    db.flush()
    return po


def _seed_email(db, po_number: str, from_email="supplier@test.com"):
    from app.models.incoming_email import IncomingEmail
    e = IncomingEmail(
        id=uuid.uuid4(),
        from_email=from_email,
        subject=f"Invoice for {po_number}",
        body_snippet="Please find attached.",
        received_at=_now(),
        has_attachments=True,
        processed_status="PROCESSED",
        matched_po_number=po_number,
        created_at=_now(),
    )
    db.add(e)
    db.flush()
    return e


def _seed_gmail_att(db, email_id, detected_type="INVOICE", filename=None):
    from app.models.incoming_email import IncomingEmailAttachment
    att = IncomingEmailAttachment(
        id=uuid.uuid4(),
        incoming_email_id=email_id,
        filename=filename or f"{detected_type.lower()}_{uuid.uuid4().hex[:6]}.pdf",
        file_path=f"/tmp/test_{uuid.uuid4().hex}.pdf",
        content_type="application/pdf",
        detected_type=detected_type,
        created_at=_now(),
    )
    db.add(att)
    db.flush()
    return att


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def doc_setup(db, client):
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    site     = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    tok      = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"], project_id=project["id"],
        site_id=site["id"], supplier_id=supplier["id"], tok=tok,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSupplierDocuments:
    def test_unknown_supplier_returns_404(self, client, db, doc_setup):
        tok = doc_setup["tok"]
        r = client.get(f"/api/v1/suppliers/{uuid.uuid4()}/documents", headers=auth(tok))
        assert r.status_code == 404

    def test_empty_supplier_returns_empty_list(self, client, db, doc_setup):
        tok = doc_setup["tok"]
        r = client.get(f"/api/v1/suppliers/{doc_setup['supplier_id']}/documents", headers=auth(tok))
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_po_appears_in_documents(self, client, db, doc_setup):
        s = doc_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        r = client.get(f"/api/v1/suppliers/{s['supplier_id']}/documents", headers=auth(s["tok"]))
        assert r.status_code == 200
        docs = r.json()["data"]
        po_docs = [d for d in docs if d["doc_type"] == "PURCHASE_ORDER"]
        assert len(po_docs) == 1
        assert po_docs[0]["ref_number"] == po.po_number

    def test_gmail_attachment_appears_in_documents(self, client, db, doc_setup):
        """
        Issue 2: Gmail attachment PDFs (from supplier emails) must appear
        in the supplier Document Centre with gmail_attachment_id set.
        """
        s = doc_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        email = _seed_email(db, po.po_number)
        gatt  = _seed_gmail_att(db, email.id, detected_type="INVOICE", filename="Invoice_from_email.pdf")
        db.commit()

        r = client.get(f"/api/v1/suppliers/{s['supplier_id']}/documents", headers=auth(s["tok"]))
        assert r.status_code == 200
        docs = r.json()["data"]

        gmail_docs = [d for d in docs if d.get("gmail_attachment_id") == str(gatt.id)]
        assert len(gmail_docs) == 1, (
            f"Expected 1 Gmail attachment doc, got {len(gmail_docs)}. All docs: {[d.get('gmail_attachment_id') for d in docs]}"
        )
        gd = gmail_docs[0]
        assert gd["doc_type"] == "INVOICE"
        assert gd["file_name"] == "Invoice_from_email.pdf"
        assert gd["attachment_type"] == "GMAIL"
        assert gd["is_attachment"] is True

    def test_gmail_attachment_doc_type_mapping(self, client, db, doc_setup):
        """Gmail attachment detected_type maps to the correct doc_type."""
        s = doc_setup
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        email = _seed_email(db, po.po_number)
        gatt_dn = _seed_gmail_att(db, email.id, detected_type="DELIVERY_NOTE")
        gatt_q  = _seed_gmail_att(db, email.id, detected_type="QUOTE")
        db.commit()

        r = client.get(f"/api/v1/suppliers/{s['supplier_id']}/documents", headers=auth(s["tok"]))
        assert r.status_code == 200
        docs = r.json()["data"]

        by_id = {d.get("gmail_attachment_id"): d for d in docs if d.get("gmail_attachment_id")}
        assert by_id[str(gatt_dn.id)]["doc_type"] == "DELIVERY_NOTE"
        assert by_id[str(gatt_q.id)]["doc_type"] == "QUOTATION"

    def test_gmail_attachments_only_for_matched_pos(self, client, db, doc_setup):
        """Gmail attachments from other suppliers' POs must not leak into this supplier's docs."""
        s = doc_setup
        other_supplier = make_supplier(db)
        po_mine  = _make_po(db, s["project_id"], s["supplier_id"],        s["owner_id"])
        po_other = _make_po(db, s["project_id"], other_supplier["id"],    s["owner_id"])
        db.commit()

        email_mine  = _seed_email(db, po_mine.po_number)
        email_other = _seed_email(db, po_other.po_number)
        gatt_mine  = _seed_gmail_att(db, email_mine.id,  detected_type="INVOICE")
        _seed_gmail_att(db, email_other.id, detected_type="INVOICE")
        db.commit()

        r = client.get(f"/api/v1/suppliers/{s['supplier_id']}/documents", headers=auth(s["tok"]))
        assert r.status_code == 200
        docs = r.json()["data"]

        gmail_ids = {d.get("gmail_attachment_id") for d in docs if d.get("gmail_attachment_id")}
        assert str(gatt_mine.id) in gmail_ids
        assert len(gmail_ids) == 1, f"Expected only 1 Gmail doc, got {gmail_ids}"
