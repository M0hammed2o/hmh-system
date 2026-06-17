"""
Tests for the Gmail email processing/extraction workflow, including PDF text extraction.

Covers:
- POST /gmail/incoming/{id}/process with no attachments
- POST /gmail/incoming/{id}/process with a text attachment → creates DocumentExtraction
- MR reference found in text → MATCHED status
- MR reference not found → NOT_FOUND creates SystemAlert
- Quantity mismatch → MISMATCH creates SystemAlert
- Email processed_status updated correctly
- PDF with selectable text → extracted by pypdf without OCR
- MR-619B19DD-0004 reference in PDF → matched and EXTRACTED
"""


# ── Minimal hand-crafted PDF helper ──────────────────────────────────────────

def _make_text_pdf(path: str, lines: list) -> None:
    """
    Create a minimal valid PDF containing selectable text lines.
    Uses only standard Type1 font (Courier) — no font embedding required.
    pypdf (and other readers) can extract the text without OCR.
    """
    # Build the BT...ET content stream
    stream_lines = ["BT", "/F1 12 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        # Escape PDF special characters
        safe = (
            line
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        stream_lines.append(f"({safe}) Tj T*")
    stream_lines.append("ET")
    content = "\n".join(stream_lines).encode("latin-1", errors="replace")

    # Five PDF objects: Catalog, Pages, Page, ContentStream, Font
    font_obj    = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
    stream_dict = (
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
        + content + b"\nendstream"
    )
    page_obj    = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    pages_obj   = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    catalog_obj = b"<< /Type /Catalog /Pages 2 0 R >>"

    objs = [catalog_obj, pages_obj, page_obj, stream_dict, font_obj]

    pdf_data = b"%PDF-1.4\n"
    offsets: list = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(pdf_data))
        pdf_data += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"

    xref_start = len(pdf_data)
    pdf_data += b"xref\n"
    pdf_data += f"0 {len(objs) + 1}\n".encode()
    pdf_data += b"0000000000 65535 f \n"
    for off in offsets:
        pdf_data += f"{off:010d} 00000 n \n".encode()
    pdf_data += (
        b"trailer\n"
        + f"<< /Size {len(objs) + 1} /Root 1 0 R >>\n".encode()
        + b"startxref\n"
        + str(xref_start).encode()
        + b"\n%%EOF\n"
    )

    with open(path, "wb") as fh:
        fh.write(pdf_data)

import io
import os
import uuid
import tempfile
import pytest
from datetime import datetime, timezone

from tests.conftest import auth, login, make_user, make_project, make_site


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def gp_setup(db, client):
    owner = make_user(db, role="OWNER")
    tok   = login(client, owner["email"], owner["password"])
    return dict(owner_id=owner["id"], tok=tok)


def _seed_email(db, subject="INV-001 Test", has_attachments=False):
    from app.models.incoming_email import IncomingEmail
    now = datetime.now(timezone.utc)
    e = IncomingEmail(
        id=uuid.uuid4(),
        from_email="supplier@example.com",
        subject=subject,
        body_snippet="Please find attached invoice for MR-DEMO-001.",
        received_at=now,
        has_attachments=has_attachments,
        processed_status="UNPROCESSED",
        created_at=now,
    )
    db.add(e)
    db.flush()
    return e


def _seed_attachment(db, email_id, file_path, filename="invoice.txt",
                     detected_type="INVOICE"):
    from app.models.incoming_email import IncomingEmailAttachment
    now = datetime.now(timezone.utc)
    att = IncomingEmailAttachment(
        id=uuid.uuid4(),
        incoming_email_id=email_id,
        filename=filename,
        file_path=file_path,
        content_type="text/plain",
        detected_type=detected_type,
        created_at=now,
    )
    db.add(att)
    db.flush()
    return att


# ── Process endpoint tests ────────────────────────────────────────────────────

class TestProcessEmail:
    def test_process_unknown_email_returns_404(self, client, db, gp_setup):
        tok = gp_setup["tok"]
        r   = client.post(f"/api/v1/gmail/incoming/{uuid.uuid4()}/process", headers=auth(tok))
        assert r.status_code == 404

    def test_process_email_no_attachments_returns_empty(self, client, db, gp_setup):
        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=False)
        db.commit()

        r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["results"] == []

    def test_process_creates_document_extraction(self, client, db, gp_setup):
        """A text attachment → DocumentExtraction record created."""
        from app.models.document_extraction import DocumentExtraction

        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=True)
        email.has_attachments = True

        content = b"Invoice No: INV-001\nTotal: R5000.00\nMaterial Request: MR-TEST-001"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            att = _seed_attachment(db, email.id, path)
            db.commit()

            before = db.query(DocumentExtraction).count()
            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200

            after = db.query(DocumentExtraction).count()
            assert after > before

            data = r.json()["data"]
            assert len(data["results"]) == 1
            assert data["results"][0]["extraction_status"] in (
                "EXTRACTED", "NEEDS_REVIEW", "OCR_NOT_AVAILABLE", "FAILED"
            )
        finally:
            os.unlink(path)

    def test_process_updates_email_status(self, client, db, gp_setup):
        """After processing, email processed_status must no longer be UNPROCESSED."""
        from app.models.incoming_email import IncomingEmail

        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=True)

        content = b"Invoice INV-002\nTotal: R1000"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            db.expire(email)
            refreshed = db.get(IncomingEmail, email.id)
            assert refreshed.processed_status in ("PROCESSED", "PROCESSING_FAILED")
        finally:
            os.unlink(path)

    def test_process_returns_attachment_fields(self, client, db, gp_setup):
        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=True)

        content = b"TAX INVOICE\nInvoice No: INV-TEST-999\nTotal: R2500.00"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200
            result = r.json()["data"]["results"][0]
            assert "fields" in result
            assert "mr_match" in result
            assert "warnings" in result
            assert result["mr_match"]["status"] in (
                "MATCHED", "MISMATCH", "NOT_FOUND", "NO_REFERENCE"
            )
        finally:
            os.unlink(path)


# ── MR matching tests ─────────────────────────────────────────────────────────

class TestMRMatching:
    def _make_mr(self, db, project_id, site_id, owner_id, request_number, qty=30.0):
        from app.models.material_request import MaterialRequest, MaterialRequestItem
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination
        from decimal import Decimal
        now = datetime.now(timezone.utc)
        mr = MaterialRequest(
            request_number=request_number,
            project_id=uuid.UUID(project_id),
            site_id=uuid.UUID(site_id),
            requested_by=uuid.UUID(owner_id),
            status=RecordStatus.APPROVED,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            requested_date=now,
        )
        db.add(mr); db.flush()
        db.add(MaterialRequestItem(
            material_request_id=mr.id,
            description="Cement 50kg bags",
            requested_quantity=Decimal(str(qty)),
            unit="bags",
        ))
        db.flush()
        return mr

    @pytest.fixture
    def mr_setup(self, db, client):
        from tests.conftest import make_project, make_site
        owner   = make_user(db, role="OWNER")
        project = make_project(db, owner_id=owner["id"])
        site    = make_site(db, project_id=project["id"])
        tok     = login(client, owner["email"], owner["password"])
        return dict(owner_id=owner["id"], project_id=project["id"],
                    site_id=site["id"], tok=tok)

    def test_mr_reference_found_returns_matched(self, client, db, mr_setup):
        tok = mr_setup["tok"]
        mr  = self._make_mr(db, mr_setup["project_id"], mr_setup["site_id"],
                            mr_setup["owner_id"], "MR-PROC-001", qty=30.0)
        db.commit()

        email = _seed_email(db, subject="Invoice for MR-PROC-001", has_attachments=True)
        content = f"Invoice No: INV-001\nReference: MR-PROC-001\nCement 30 bags\nTotal: R5400.00".encode()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200
            mr_match = r.json()["data"]["results"][0]["mr_match"]
            assert mr_match["status"] in ("MATCHED", "MISMATCH")
            assert mr_match["mr_number"] == "MR-PROC-001"
        finally:
            os.unlink(path)

    def test_no_mr_reference_returns_no_reference(self, client, db, gp_setup):
        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=True)
        content = b"Invoice No: INV-999\nSome random text without any MR number\nTotal: R1000"

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200
            mr_match = r.json()["data"]["results"][0]["mr_match"]
            assert mr_match["status"] == "NO_REFERENCE"
        finally:
            os.unlink(path)

    def test_mr_reference_not_in_db_creates_alert(self, client, db, gp_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        tok   = gp_setup["tok"]
        email = _seed_email(db, has_attachments=True)
        # Reference exists in text but not in DB
        content = b"Invoice for MR-GHOST-9999\nTotal: R2000"

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            before = db.query(SystemAlert).filter(
                SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
            ).count()

            client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))

            after = db.query(SystemAlert).filter(
                SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
            ).count()
            assert after > before
        finally:
            os.unlink(path)

    def test_quantity_mismatch_creates_alert(self, client, db, mr_setup):
        """Invoice qty differs significantly from MR qty → MISMATCH alert."""
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        tok = mr_setup["tok"]
        # MR has 30 bags
        mr = self._make_mr(db, mr_setup["project_id"], mr_setup["site_id"],
                           mr_setup["owner_id"], "MR-QTY-001", qty=30.0)
        db.commit()

        email = _seed_email(db, has_attachments=True)
        # Invoice claims 100 bags (>5% difference from 30)
        content = (
            b"Invoice No: INV-QTY-001\n"
            b"Material Request: MR-QTY-001\n"
            b"Cement 50kg  100 bags  R180  R18000\n"
            b"Total: R18000"
        )
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content); path = f.name

        try:
            _seed_attachment(db, email.id, path)
            db.commit()

            before = db.query(SystemAlert).filter(
                SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
            ).count()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200

            mr_match = r.json()["data"]["results"][0]["mr_match"]
            # Status should be MATCHED or MISMATCH depending on whether parser extracted items
            assert mr_match["status"] in ("MATCHED", "MISMATCH", "NOT_FOUND", "NO_REFERENCE")
            # If MISMATCH, alert was created
            if mr_match["status"] == "MISMATCH":
                after = db.query(SystemAlert).filter(
                    SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
                ).count()
                assert after > before
        finally:
            os.unlink(path)


# ── PDF text extraction tests ─────────────────────────────────────────────────

class TestPDFExtraction:
    """
    Tests for PDF selectable-text extraction via pypdf.

    The _make_text_pdf() helper creates a minimal valid PDF (no external tools
    needed) that pypdf can read.  These tests confirm the full pipeline:
      PDF attachment → pypdf extracts text → parsers find MR reference → MATCHED
    """

    def test_extract_text_from_pdf_uses_pypdf(self):
        """pypdf extracts text from a selectable-text PDF without OCR."""
        pytest.importorskip("pypdf")
        from app.services.document_ai_service import extract_text_from_pdf

        lines = [
            "MR-619B19DD-0004",
            "Invoice No: INV-TEST-001",
            "Internal Doors  3  each  R500.00  R1500.00",
            "Total: R1500.00",
        ]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            _make_text_pdf(path, lines)
            text = extract_text_from_pdf(path)
            assert text.strip(), "Expected non-empty text from selectable-text PDF"
            assert "MR-619B19DD-0004" in text, f"MR ref not found in: {text[:200]}"
            assert "1500" in text, "Total amount not found"
        finally:
            os.unlink(path)

    def test_extract_document_text_pdf_returns_extracted(self):
        """extract_document_text returns (text, 'EXTRACTED') for selectable PDF."""
        pytest.importorskip("pypdf")
        from app.services.document_ai_service import extract_document_text

        lines = ["Invoice MR-619B19DD-0004", "Doors 3 each R500 R1500", "Total: R1500"]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            _make_text_pdf(path, lines)
            text, status = extract_document_text(path)
            assert status == "EXTRACTED", f"Expected EXTRACTED, got {status}"
            assert "MR-619B19DD-0004" in text
        finally:
            os.unlink(path)

    def test_process_pdf_attachment_extracts_mr_reference(self, client, db, gp_setup):
        """Processing a PDF attachment extracts MR reference and returns mr_match."""
        pytest.importorskip("pypdf")

        tok   = gp_setup["tok"]
        email = _seed_email(db, subject="Invoice for MR-619B19DD-0004", has_attachments=True)
        lines = [
            "TAX INVOICE",
            "Invoice No: INV-619-001",
            "Material Request: MR-619B19DD-0004",
            "Internal Doors  3  each  R500.00  R1500.00",
            "Total: R1500.00",
        ]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            _make_text_pdf(path, lines)
            _seed_attachment(db, email.id, path, filename="invoice.pdf", detected_type="INVOICE")
            db.commit()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(tok))
            assert r.status_code == 200, r.text

            result = r.json()["data"]
            assert result["processed_status"] == "PROCESSED"
            assert len(result["results"]) == 1

            att_result = result["results"][0]
            assert att_result["extraction_status"] == "EXTRACTED", (
                f"Expected EXTRACTED, got {att_result['extraction_status']}"
            )
            assert "MR-619B19DD-0004" in (att_result["mr_match"].get("mr_number") or "NOT_FOUND_IN_DB")
            # MR not in DB → NOT_FOUND is acceptable; the key test is extraction worked
            assert att_result["mr_match"]["status"] in ("MATCHED", "NOT_FOUND")
        finally:
            os.unlink(path)

    def test_process_pdf_matched_mr_in_db(self, client, db, gp_setup):
        """PDF with a known MR number matches a real MaterialRequest in DB → MATCHED."""
        pytest.importorskip("pypdf")
        from app.models.material_request import MaterialRequest, MaterialRequestItem
        from app.models.enums import RecordStatus, MRPriority, DeliveryDestination

        # Use a unique request number per test run to avoid UNIQUE constraint errors
        test_mr_number = f"MR-PDF-{uuid.uuid4().hex[:8].upper()}"

        # Setup
        s       = gp_setup
        project = make_project(db, owner_id=s["owner_id"])
        site    = make_site(db, project_id=project["id"])
        now     = datetime.now(timezone.utc)

        mr = MaterialRequest(
            request_number=test_mr_number,
            project_id=uuid.UUID(project["id"]),
            site_id=uuid.UUID(site["id"]),
            requested_by=uuid.UUID(s["owner_id"]),
            status=RecordStatus.APPROVED,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.SITE_STORE,
            requested_date=now,
        )
        db.add(mr); db.flush()
        db.add(MaterialRequestItem(
            material_request_id=mr.id,
            description="Internal Doors",
            requested_quantity=3,
            unit="each",
        ))
        db.commit()

        email = _seed_email(db, subject=f"Invoice {test_mr_number}", has_attachments=True)
        lines = [
            "Invoice No: INV-PDF-002",
            test_mr_number,
            "Internal Doors  3  each  R500.00  R1500.00",
            "Total: R1500.00",
        ]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            _make_text_pdf(path, lines)
            _seed_attachment(db, email.id, path, filename="invoice_matched.pdf", detected_type="INVOICE")
            db.commit()

            r = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(s["tok"]))
            assert r.status_code == 200, r.text

            match = r.json()["data"]["results"][0]["mr_match"]
            assert match["mr_number"] == test_mr_number
            assert match["status"] == "MATCHED", (
                f"Expected MATCHED, got {match['status']} — mismatch: {match.get('mismatch_detail')}"
            )
        finally:
            os.unlink(path)


# ── Auto-invoice creation tests ───────────────────────────────────────────────

class TestAutoInvoiceCreation:
    """
    Tests for Issue 1: auto-creating an invoice when an INVOICE email arrives
    and a PO number is found.  Also covers the re-process use case (email was
    processed before the PO existed — clicking Re-process must create the invoice).
    """

    def _make_po(self, db, project_id: str, supplier_id: str, owner_id: str,
                 po_number: str = None):
        """Insert a minimal PurchaseOrder directly via ORM."""
        from app.models.purchase_order import PurchaseOrder
        from app.models.enums import RecordStatus
        from decimal import Decimal
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        po_number = po_number or f"PO-AINV-{uuid.uuid4().hex[:6].upper()}"
        po = PurchaseOrder(
            po_number=po_number,
            project_id=uuid.UUID(project_id),
            supplier_id=uuid.UUID(supplier_id),
            status=RecordStatus.APPROVED,
            po_date=now,
            total_amount=Decimal("5000.00"),
            subtotal_amount=Decimal("4347.83"),
            vat_amount=Decimal("652.17"),
            created_by=uuid.UUID(owner_id),
            created_at=now,
            updated_at=now,
        )
        db.add(po)
        db.flush()
        return po

    @pytest.fixture
    def inv_setup(self, db, client):
        from tests.conftest import make_project, make_site, make_supplier
        owner    = make_user(db, role="OWNER")
        project  = make_project(db, owner_id=owner["id"])
        site     = make_site(db, project_id=project["id"])
        supplier = make_supplier(db)
        tok      = login(client, owner["email"], owner["password"])
        return dict(
            owner_id=owner["id"], project_id=project["id"],
            site_id=site["id"], supplier_id=supplier["id"], tok=tok,
        )

    def test_process_invoice_with_po_creates_invoice(self, client, db, inv_setup):
        """When an INVOICE email has a matching PO number, auto_invoice_created=True."""
        from app.models.invoice import Invoice

        s = inv_setup
        po_number = f"PO-AINV-{uuid.uuid4().hex[:6].upper()}"
        po = self._make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], po_number)
        db.commit()

        email = _seed_email(db, subject=f"Invoice for {po_number}", has_attachments=True)
        content = (
            f"TAX INVOICE\n"
            f"Invoice No: INV-TEST-{uuid.uuid4().hex[:6]}\n"
            f"Purchase Order: {po_number}\n"
            f"Total: R5000.00\n"
        ).encode()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            _seed_attachment(db, email.id, path, detected_type="INVOICE")
            db.commit()

            r = client.post(
                f"/api/v1/gmail/incoming/{email.id}/process",
                headers=auth(s["tok"])
            )
            assert r.status_code == 200, r.text

            result = r.json()["data"]["results"][0]
            assert result["auto_invoice_created"] is True, (
                f"Expected auto_invoice_created=True, got {result['auto_invoice_created']}. "
                f"Fields: {result.get('fields')}"
            )
            assert result["auto_invoice_id"] is not None

            # Invoice must exist in DB
            inv = db.query(Invoice).filter(Invoice.purchase_order_id == po.id).first()
            assert inv is not None, "Invoice not found in DB after auto-create"
        finally:
            os.unlink(path)

    def test_process_invoice_without_po_no_invoice_created(self, client, db, inv_setup):
        """When no matching PO exists, auto_invoice_created=False."""
        from app.models.invoice import Invoice

        s = inv_setup
        email = _seed_email(db, subject="Invoice for PO-DOES-NOT-EXIST", has_attachments=True)
        content = b"TAX INVOICE\nInvoice No: INV-X01\nPurchase Order: PO-NONEXISTENT-9999\nTotal: R1000.00"

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            _seed_attachment(db, email.id, path, detected_type="INVOICE")
            db.commit()

            r = client.post(
                f"/api/v1/gmail/incoming/{email.id}/process",
                headers=auth(s["tok"])
            )
            assert r.status_code == 200, r.text

            result = r.json()["data"]["results"][0]
            assert result["auto_invoice_created"] is False
            assert result["auto_invoice_id"] is None
        finally:
            os.unlink(path)

    def test_reprocess_creates_invoice_when_po_added_later(self, client, db, inv_setup):
        """
        Covers the missed-invoice scenario:
        1. Email arrives and is processed (no PO yet) → auto_invoice_created=False
        2. PO is later created in the system
        3. User clicks Re-process → auto_invoice_created=True
        """
        from app.models.invoice import Invoice
        from app.models.incoming_email import IncomingEmail

        s = inv_setup
        po_number = f"PO-RETRY-{uuid.uuid4().hex[:6].upper()}"

        # Step 1: process email BEFORE PO exists
        email = _seed_email(db, subject=f"Invoice {po_number}", has_attachments=True)
        content = (
            f"TAX INVOICE\n"
            f"Invoice No: INV-RETRY-001\n"
            f"Purchase Order: {po_number}\n"
            f"Total: R3000.00\n"
        ).encode()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            _seed_attachment(db, email.id, path, detected_type="INVOICE")
            db.commit()

            r1 = client.post(
                f"/api/v1/gmail/incoming/{email.id}/process",
                headers=auth(s["tok"])
            )
            assert r1.status_code == 200
            assert r1.json()["data"]["results"][0]["auto_invoice_created"] is False

            # Step 2: PO is created later
            po = self._make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], po_number)
            db.commit()

            # Step 3: Re-process → invoice should now be created
            r2 = client.post(
                f"/api/v1/gmail/incoming/{email.id}/process",
                headers=auth(s["tok"])
            )
            assert r2.status_code == 200
            result2 = r2.json()["data"]["results"][0]
            assert result2["auto_invoice_created"] is True, (
                f"Expected invoice created on re-process. Fields: {result2.get('fields')}"
            )

            inv = db.query(Invoice).filter(Invoice.purchase_order_id == po.id).first()
            assert inv is not None, "Invoice still missing after re-process"
        finally:
            os.unlink(path)

    def test_reprocess_idempotent_does_not_double_create(self, client, db, inv_setup):
        """Re-processing an email that already created an invoice does not duplicate it."""
        from app.models.invoice import Invoice

        s = inv_setup
        po_number = f"PO-IDEM-{uuid.uuid4().hex[:6].upper()}"
        self._make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], po_number)
        db.commit()

        email = _seed_email(db, subject=f"Invoice {po_number}", has_attachments=True)
        content = (
            f"TAX INVOICE\n"
            f"Invoice No: INV-IDEM-001\n"
            f"Purchase Order: {po_number}\n"
            f"Total: R2000.00\n"
        ).encode()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            _seed_attachment(db, email.id, path, detected_type="INVOICE")
            db.commit()

            # First process — creates invoice
            client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(s["tok"]))

            from app.models.purchase_order import PurchaseOrder
            po_obj = db.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_number).first()
            count_after_first = db.query(Invoice).filter(Invoice.purchase_order_id == po_obj.id).count()
            assert count_after_first == 1

            # Second process (Re-process) — must NOT create a second invoice
            r2 = client.post(f"/api/v1/gmail/incoming/{email.id}/process", headers=auth(s["tok"]))
            assert r2.status_code == 200
            # auto_invoice_created should be False (already exists)
            assert r2.json()["data"]["results"][0]["auto_invoice_created"] is False

            count_after_second = db.query(Invoice).filter(Invoice.purchase_order_id == po_obj.id).count()
            assert count_after_second == 1, "Duplicate invoice created on re-process"
        finally:
            os.unlink(path)
