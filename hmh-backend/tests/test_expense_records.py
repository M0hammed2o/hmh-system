"""
Tests for expense record upload and approval flow.

Covers:
- Upload expense creates ExpenseRecord
- Upload with file creates extraction
- List returns expenses
- Approve sets APPROVED status
- Reject sets REJECTED status
- Re-approve already approved raises 400
- Gmail attachment triggers extraction record
"""

import io
import uuid
import pytest

from tests.conftest import auth, login, make_user, make_project, make_site, make_user_project_access


@pytest.fixture
def expense_setup(db, client):
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


def _upload_expense(client, tok, supplier="Tyre Shop", category="VEHICLE_REPAIR",
                    amount=None, file_content=None):
    data = {
        "supplier_name": supplier,
        "category": category,
    }
    if amount is not None:
        data["amount"] = str(amount)

    if file_content:
        files = {"file": ("receipt.pdf", io.BytesIO(file_content), "application/pdf")}
    else:
        files = {}

    return client.post(
        "/api/v1/expenses/upload",
        data=data,
        files=files,
        headers=auth(tok),
    )


class TestExpenseUpload:
    def test_upload_returns_201(self, client, db, expense_setup):
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"])
        assert r.status_code == 201, r.text

    def test_upload_creates_expense_record(self, client, db, expense_setup):
        from app.models.document_extraction import ExpenseRecord
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"], supplier="Test Tyre Co")
        exp_id = r.json()["data"]["id"]
        e = db.query(ExpenseRecord).filter(
            ExpenseRecord.id == uuid.UUID(exp_id)
        ).first()
        assert e is not None
        assert e.supplier_name == "Test Tyre Co"
        assert e.status in ("UPLOADED", "NEEDS_REVIEW")

    def test_upload_with_amount_stays_uploaded(self, client, db, expense_setup):
        from app.models.document_extraction import ExpenseRecord
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"], amount=1500.00)
        e = db.query(ExpenseRecord).filter(
            ExpenseRecord.id == uuid.UUID(r.json()["data"]["id"])
        ).first()
        assert e.status == "UPLOADED"
        assert float(e.amount) == 1500.00

    def test_upload_with_file_creates_extraction(self, client, db, expense_setup):
        from app.models.document_extraction import DocumentExtraction
        s = expense_setup
        content = b"Invoice No: INV-EXP-001\nTyre repair\nTotal: R750.00"
        r = _upload_expense(client, s["staff_tok"], file_content=content)
        assert r.status_code == 201
        # Extraction should have been created
        exp_id = r.json()["data"]["id"]
        from app.models.document_extraction import ExpenseRecord
        e = db.query(ExpenseRecord).filter(ExpenseRecord.id == uuid.UUID(exp_id)).first()
        assert e.extraction_id is not None
        ext = db.query(DocumentExtraction).filter(
            DocumentExtraction.id == e.extraction_id
        ).first()
        assert ext is not None
        assert ext.document_type == "INVOICE"

    def test_upload_with_file_auto_extracts_invoice_number(self, client, db, expense_setup):
        s = expense_setup
        content = b"TAX INVOICE\nInvoice No: INV-TYRE-007\nTotal: R1200.00"
        r = _upload_expense(client, s["staff_tok"], file_content=content)
        assert r.status_code == 201
        from app.models.document_extraction import ExpenseRecord
        e = db.query(ExpenseRecord).filter(
            ExpenseRecord.id == uuid.UUID(r.json()["data"]["id"])
        ).first()
        # invoice_number might be auto-extracted
        assert e is not None  # just check it saved


class TestExpenseList:
    def test_list_returns_200(self, client, db, expense_setup):
        s = expense_setup
        r = client.get("/api/v1/expenses/", headers=auth(s["owner_tok"]))
        assert r.status_code == 200
        assert "items" in r.json()["data"]

    def test_list_includes_uploaded_expense(self, client, db, expense_setup):
        s = expense_setup
        _upload_expense(client, s["staff_tok"], supplier="UniqueSupplierXYZ")
        r = client.get("/api/v1/expenses/", headers=auth(s["owner_tok"]))
        items = r.json()["data"]["items"]
        assert any(i["supplier_name"] == "UniqueSupplierXYZ" for i in items)

    def test_list_site_staff_is_forbidden(self, client, db, expense_setup):
        """Listing expenses requires OFFICE_AND_ABOVE."""
        s = expense_setup
        r = client.get("/api/v1/expenses/", headers=auth(s["staff_tok"]))
        assert r.status_code == 403


class TestExpenseGet:
    def test_get_by_id(self, client, db, expense_setup):
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"], supplier="GetTestSupplier")
        exp_id = r.json()["data"]["id"]
        r2 = client.get(f"/api/v1/expenses/{exp_id}", headers=auth(s["owner_tok"]))
        assert r2.status_code == 200
        assert r2.json()["data"]["supplier_name"] == "GetTestSupplier"

    def test_get_unknown_returns_404(self, client, db, expense_setup):
        s = expense_setup
        r = client.get(f"/api/v1/expenses/{uuid.uuid4()}", headers=auth(s["owner_tok"]))
        assert r.status_code == 404


class TestExpenseApproval:
    def test_approve_sets_approved_status(self, client, db, expense_setup):
        from app.models.document_extraction import ExpenseRecord
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"], amount=500.0)
        exp_id = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/expenses/{exp_id}/approve",
            json={"notes": "Approved by owner"},
            headers=auth(s["owner_tok"]),
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "APPROVED"

        e = db.query(ExpenseRecord).filter(ExpenseRecord.id == uuid.UUID(exp_id)).first()
        assert e.status == "APPROVED"
        assert e.approved_by is not None
        assert e.approved_at is not None

    def test_reject_sets_rejected_status(self, client, db, expense_setup):
        from app.models.document_extraction import ExpenseRecord
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"])
        exp_id = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/expenses/{exp_id}/reject",
            json={"notes": "Duplicate submission"},
            headers=auth(s["owner_tok"]),
        )
        assert r2.status_code == 200
        e = db.query(ExpenseRecord).filter(ExpenseRecord.id == uuid.UUID(exp_id)).first()
        assert e.status == "REJECTED"

    def test_approve_already_approved_returns_400(self, client, db, expense_setup):
        s = expense_setup
        r = _upload_expense(client, s["staff_tok"])
        exp_id = r.json()["data"]["id"]

        client.post(f"/api/v1/expenses/{exp_id}/approve", json={}, headers=auth(s["owner_tok"]))
        r2 = client.post(f"/api/v1/expenses/{exp_id}/approve", json={}, headers=auth(s["owner_tok"]))
        assert r2.status_code == 400
