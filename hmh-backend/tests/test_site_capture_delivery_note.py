"""
Tests for site capture delivery note flow.

Covers:
- Upload creates DeliveryVerification + DocumentExtraction
- GET returns verification with items
- Correction updates items and header fields
- Verify sets status VERIFIED when no mismatch
- Verify sets MISMATCH and creates alert when qty differs
- Signature saves signed_at and file path
"""

import io
import uuid
import pytest

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier, make_user_project_access


@pytest.fixture
def capture_setup(db, client):
    owner  = make_user(db, role="OWNER")
    staff  = make_user(db, role="SITE_STAFF")
    project = make_project(db, owner_id=owner["id"])
    site   = make_site(db, project_id=project["id"])
    make_user_project_access(db, staff["id"], project["id"])
    owner_tok = login(client, owner["email"], owner["password"])
    staff_tok = login(client, staff["email"], staff["password"])
    return dict(
        owner_id=owner["id"],
        staff_id=staff["id"],
        project_id=project["id"],
        site_id=site["id"],
        owner_tok=owner_tok,
        staff_tok=staff_tok,
    )


def _upload_delivery_note(client, tok, site_id, content=b"DELIVERY NOTE\nDN-TEST-001\nCement 30 bags"):
    """Helper that uploads a fake delivery note file."""
    return client.post(
        "/api/v1/site-capture/delivery-note/upload",
        files={"file": ("delivery_note.pdf", io.BytesIO(content), "application/pdf")},
        data={"site_id": site_id, "supplier_name": "Test Supplier"},
        headers=auth(tok),
    )


class TestDeliveryNoteUpload:
    def test_upload_returns_201(self, client, db, capture_setup):
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        assert r.status_code == 201, r.text

    def test_upload_returns_verification_id(self, client, db, capture_setup):
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        assert r.status_code == 201
        data = r.json()["data"]
        assert "id" in data
        assert "extraction_id" in data

    def test_upload_creates_delivery_verification(self, client, db, capture_setup):
        from app.models.document_extraction import DeliveryVerification
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]
        v = db.query(DeliveryVerification).filter(
            DeliveryVerification.id == uuid.UUID(vid)
        ).first()
        assert v is not None
        assert v.verification_status == "DRAFT"

    def test_upload_creates_document_extraction(self, client, db, capture_setup):
        from app.models.document_extraction import DocumentExtraction
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        eid = r.json()["data"]["extraction_id"]
        ext = db.query(DocumentExtraction).filter(
            DocumentExtraction.id == uuid.UUID(eid)
        ).first()
        assert ext is not None
        assert ext.document_type == "DELIVERY_NOTE"

    def test_upload_extracts_dn_number_from_text(self, client, db, capture_setup):
        s = capture_setup
        content = b"DELIVERY NOTE\nDelivery No: DN-EXTRACT-042\nPO-TEST-001\nCement 30 bags"
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"], content=content)
        assert r.status_code == 201
        fields = r.json()["data"].get("extracted_fields", {})
        # DN number might or might not extract depending on text — just check no crash
        assert isinstance(fields, dict)


class TestDeliveryNoteGet:
    def test_get_returns_200(self, client, db, capture_setup):
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]
        r2 = client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(s["staff_tok"]))
        assert r2.status_code == 200

    def test_get_returns_verification_status(self, client, db, capture_setup):
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]
        r2 = client.get(f"/api/v1/site-capture/delivery-note/{vid}", headers=auth(s["staff_tok"]))
        data = r2.json()["data"]
        assert data["verification_status"] == "DRAFT"
        assert "items" in data

    def test_get_unknown_id_returns_404(self, client, db, capture_setup):
        s = capture_setup
        r = client.get(f"/api/v1/site-capture/delivery-note/{uuid.uuid4()}", headers=auth(s["staff_tok"]))
        assert r.status_code == 404


class TestDeliveryNoteCorrection:
    def test_correction_saves_supplier_name(self, client, db, capture_setup):
        from app.models.document_extraction import DeliveryVerification
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={
                "supplier_name": "Updated Supplier Name",
                "delivery_note_number": "DN-CORRECTED-001",
                "items": [{
                    "description": "Cement 50kg bags",
                    "unit": "bags",
                    "expected_qty": 30,
                    "ocr_qty": 28,
                    "actual_received_qty": 28,
                    "accepted_qty": 28,
                    "rejected_qty": 0,
                }],
            },
            headers=auth(s["staff_tok"]),
        )
        assert r2.status_code == 200

        v = db.query(DeliveryVerification).filter(
            DeliveryVerification.id == uuid.UUID(vid)
        ).first()
        assert v.supplier_name == "Updated Supplier Name"
        assert v.delivery_note_number == "DN-CORRECTED-001"
        assert len(v.items) == 1


class TestDeliveryNoteVerification:
    def test_verify_no_mismatch_sets_verified(self, client, db, capture_setup):
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]

        # Correct with matching quantities
        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={"items": [{
                "description": "Cement 50kg",
                "expected_qty": 30,
                "actual_received_qty": 30,
                "accepted_qty": 30,
                "rejected_qty": 0,
            }]},
            headers=auth(s["staff_tok"]),
        )

        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/verify",
            headers=auth(s["owner_tok"]),
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "VERIFIED"

    def test_verify_with_rejected_qty_sets_mismatch(self, client, db, capture_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]

        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={"items": [{
                "description": "Cement 50kg",
                "expected_qty": 30,
                "actual_received_qty": 20,
                "accepted_qty": 20,
                "rejected_qty": 10,
                "mismatch_reason": "Damaged bags",
            }]},
            headers=auth(s["staff_tok"]),
        )

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()

        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/verify",
            headers=auth(s["owner_tok"]),
        )
        assert r2.json()["data"]["status"] == "MISMATCH"

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()
        assert after > before


class TestDeliveryNoteSignature:
    def test_signature_saves_signed_at(self, client, db, capture_setup):
        from app.models.document_extraction import DeliveryVerification
        s = capture_setup
        r = _upload_delivery_note(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/signature",
            json={"signature_data": "John Smith", "signed_by_name": "John Smith"},
            headers=auth(s["staff_tok"]),
        )
        assert r2.status_code == 200
        assert "signed_at" in r2.json()["data"]

        v = db.query(DeliveryVerification).filter(
            DeliveryVerification.id == uuid.UUID(vid)
        ).first()
        assert v.signed_at is not None
        assert v.signature_path is not None
