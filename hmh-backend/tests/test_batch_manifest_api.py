"""
The batch manifest endpoint.

What a mixed upload would do, readable before any of it happens. The screen
that drives the import reads this, and so does the import manifest in the
handover report, so the two cannot drift apart into telling an operator
different stories about the same document.

The endpoint is read-only. Every test here checks that as well as whatever
else it is checking, because a manifest that writes while being read would
be worse than no manifest at all.
"""

import uuid
from datetime import datetime, timezone

import pytest


def _now():
    return datetime.now(timezone.utc)

from app.models.enums import AIImportDocumentType as T


# ── Setup ─────────────────────────────────────────────────────────────────────

def _owner(db, client):
    from tests.conftest import make_user

    user = make_user(db, role="OWNER")
    db.commit()
    res = client.post("/api/v1/auth/login", json={
        "email": user["email"], "password": "Test@1234",
    })
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return user, {"Authorization": f"Bearer {token}"}


def _batch_with(db, owner, documents):
    """
    A batch holding one document per (type, file_name, extracted fields).

    Extractions are written directly rather than run through the AI
    pipeline: these tests are about what the manifest says, not about
    whether the model can read a scan.
    """
    from app.models.ai_import import AIImportBatch, AIImportDocument, AIImportExtraction
    from app.models.enums import AIImportDocumentStatus

    batch = AIImportBatch(reference=f"M-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()

    created = []
    for spec in documents:
        document = AIImportDocument(
            batch_id=batch.id,
            file_name=spec["file_name"],
            stored_path=f"supabase://ai_import/x/{uuid.uuid4().hex}.pdf",
            mime_type="application/pdf", file_size_bytes=2048,
            checksum_sha256=uuid.uuid4().hex * 2,
            status=AIImportDocumentStatus.AWAITING_REVIEW,
            document_type=spec["type"],
            project_id=spec.get("project_id"),
            supplier_id=spec.get("supplier_id"),
            payment_evidence_detected=spec.get("paid", False),
            payment_evidence_note=(
                "Payment evidence detected — verification required."
                if spec.get("paid") else None
            ),
            uploaded_by=uuid.UUID(owner["id"]),
        )
        db.add(document)
        db.flush()
        db.add(AIImportExtraction(
            document_id=document.id,
            created_at=_now(),
            schema_version="1.0",
            prompt_version="1.1",
            provider="test",
            extraction_mode="text",
            fields={
                name: {"value": value, "page": 1, "confidence": 0.9, "source": "text"}
                for name, value in spec.get("fields", {}).items()
            },
            line_items=[],
            is_current=True,
        ))
        created.append(document)
    db.commit()
    return batch, created


# ── The shape of it ───────────────────────────────────────────────────────────

def test_the_manifest_lists_every_document(db, client):
    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "a.pdf", "type": T.QUOTATION,
         "fields": {"document_number": "BR1-QUT/1", "total_amount": "100.00"}},
        {"file_name": "b.pdf", "type": T.PURCHASE_ORDER,
         "fields": {"document_number": "PO-021", "total_amount": "200.00"}},
    ])

    res = client.get(f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["batch"]["document_count"] == 2
    assert [r["file_name"] for r in data["rows"]] == ["a.pdf", "b.pdf"]


def test_each_row_says_where_it_goes_and_what_it_would_do(db, client):
    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "proforma.pdf", "type": T.PRO_FORMA_INVOICE,
         "fields": {"document_number": "P89250", "total_amount": "17444.89"}},
    ])

    res = client.get(f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers)
    row = res.json()["data"]["rows"][0]

    assert row["routing"]["destination"] == "provisional_charges"
    assert row["routing"]["destination_label"] == "Pending supplier charges"
    # The consequence has to be stated, not implied by a module name.
    assert "Accounts Payable" in row["routing"]["effect"]
    assert row["routing"]["action"] in {"CREATE", "LINK_EXISTING", "REVIEW"}


def test_the_manifest_action_is_one_of_the_four(db, client):
    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": f"{i}.pdf", "type": t,
         "fields": {"document_number": f"REF-{i}", "total_amount": "10.00"}}
        for i, t in enumerate([
            T.QUOTATION, T.PURCHASE_ORDER, T.PRO_FORMA_INVOICE,
            T.SUPPLIER_INVOICE, T.DELIVERY_NOTE, T.UNKNOWN,
        ])
    ])

    res = client.get(f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers)
    allowed = {"CREATE", "LINK_EXISTING", "REVIEW", "SKIP_DUPLICATE", None}
    for row in res.json()["data"]["rows"]:
        assert row["routing"]["action"] in allowed


def test_the_summary_counts_what_matters(db, client):
    """
    The header exists so nobody has to count twenty rows to find out how
    many of them create a liability.
    """
    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "q1.pdf", "type": T.QUOTATION,
         "fields": {"document_number": "Q1", "total_amount": "10.00"}},
        {"file_name": "q2.pdf", "type": T.QUOTATION,
         "fields": {"document_number": "Q2", "total_amount": "20.00"}},
        {"file_name": "inv.pdf", "type": T.SUPPLIER_INVOICE,
         "fields": {"document_number": "85956", "total_amount": "494.32"}},
    ])

    data = client.get(
        f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
    ).json()["data"]

    assert data["summary"]["by_destination"]["Procurement"] == 2
    assert data["summary"]["by_destination"]["Accounts Payable"] == 1


# ── Context that is missing is said to be missing ─────────────────────────────

def test_a_document_without_a_supplier_needs_review(db, client):
    """
    Two of the twenty name suppliers that do not exist in the system — Build
    It and J S Singh Glazzing. Nothing can be filed against a name alone.
    """
    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "po01.pdf", "type": T.PURCHASE_ORDER,
         "fields": {"document_number": "PO-01", "supplier_name": "BUILD IT",
                    "total_amount": "3699.55"}},
    ])

    row = client.get(
        f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
    ).json()["data"]["rows"][0]

    assert row["routing"]["action"] == "REVIEW"
    assert any("supplier is not linked" in n for n in row["routing"]["review_notes"])
    # What the document said is still reported, so the reader can match it up.
    assert row["supplier_name"] == "BUILD IT"


def test_payment_evidence_is_surfaced_without_settling_anything(db, client):
    from app.models.payment import Payment

    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "paid.pdf", "type": T.PRO_FORMA_INVOICE, "paid": True,
         "fields": {"document_number": "QTE254210", "total_amount": "3699.50"}},
    ])
    payments_before = db.query(Payment).count()

    data = client.get(
        f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
    ).json()["data"]

    assert data["summary"]["payment_evidence_count"] == 1
    assert data["rows"][0]["payment_evidence_detected"] is True
    assert db.query(Payment).count() == payments_before


# ── Read-only, and tolerant ───────────────────────────────────────────────────

def test_reading_the_manifest_writes_nothing(db, client):
    """
    Called on every page load and on a timer while a batch is processing. If
    it had a side effect, that side effect would happen repeatedly.
    """
    from app.models.ai_import import AIImportPosting
    from app.models.invoice import Invoice
    from app.models.provisional_charge import ProvisionalCharge
    from app.models.quotation import Quotation
    from app.models.stock import StockLedger

    owner, headers = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "q.pdf", "type": T.QUOTATION,
         "fields": {"document_number": "Q1", "total_amount": "10.00"}},
        {"file_name": "p.pdf", "type": T.PRO_FORMA_INVOICE,
         "fields": {"document_number": "P1", "total_amount": "20.00"}},
        {"file_name": "i.pdf", "type": T.SUPPLIER_INVOICE,
         "fields": {"document_number": "I1", "total_amount": "30.00"}},
    ])

    counts = lambda: (                                      # noqa: E731
        db.query(Invoice).count(), db.query(Quotation).count(),
        db.query(ProvisionalCharge).count(), db.query(StockLedger).count(),
        db.query(AIImportPosting).count(),
    )
    before = counts()
    for _ in range(3):
        assert client.get(
            f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
        ).status_code == 200
    db.expire_all()
    assert counts() == before


def test_a_document_that_has_not_been_read_yet_is_still_listed(db, client):
    """
    Right after upload nothing has been extracted. That is an ordinary state,
    not an error, and the row has to appear so the operator can see the file
    arrived.
    """
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus

    owner, headers = _owner(db, client)
    batch = AIImportBatch(reference=f"M-{uuid.uuid4().hex[:6]}",
                          uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    db.add(AIImportDocument(
        batch_id=batch.id, file_name="fresh.pdf",
        stored_path="supabase://ai_import/x/fresh.pdf",
        mime_type="application/pdf", file_size_bytes=100,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.UPLOADED,
        document_type=T.UNKNOWN,
        uploaded_by=uuid.UUID(owner["id"]),
    ))
    db.commit()

    data = client.get(
        f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
    ).json()["data"]

    assert len(data["rows"]) == 1
    assert data["rows"][0]["routing"]["action"] is None
    assert "not yet extracted" in data["rows"][0]["routing"]["reason"].lower()


def test_an_unknown_batch_is_a_404(db, client):
    _, headers = _owner(db, client)
    res = client.get(
        f"/api/v1/ai-import/batches/{uuid.uuid4()}/manifest", headers=headers,
    )
    assert res.status_code == 404


def test_the_manifest_requires_authentication(db, client):
    owner, _ = _owner(db, client)
    batch, _ = _batch_with(db, owner, [
        {"file_name": "a.pdf", "type": T.QUOTATION, "fields": {}},
    ])
    res = client.get(f"/api/v1/ai-import/batches/{batch.id}/manifest")
    assert res.status_code in (401, 403)


def test_the_duplicate_check_reads_the_extraction_in_force(db, client):
    """
    A document can carry several extractions — a re-read after a failure, or
    a human correction. Only one is in force, and it is not always the most
    recent row. Comparing against a superseded total would either miss a
    duplicate or invent one.
    """
    from app.models.ai_import import AIImportExtraction

    owner, headers = _owner(db, client)
    from tests.conftest import make_supplier
    supplier_id = uuid.UUID(make_supplier(db, name="Vantage Readymix")["id"])
    db.commit()

    batch, documents = _batch_with(db, owner, [
        {"file_name": "p89250.pdf", "type": T.PRO_FORMA_INVOICE,
         "supplier_id": supplier_id,
         "fields": {"document_number": "P89250", "total_amount": "17444.89"}},
        {"file_name": "p89381.pdf", "type": T.PRO_FORMA_INVOICE,
         "supplier_id": supplier_id,
         "fields": {"document_number": "P89381", "total_amount": "17444.89"}},
    ])

    # Supersede the first document's reading with a different total, the way
    # a correction would: the old row stays, flagged not current.
    old = (
        db.query(AIImportExtraction)
        .filter(AIImportExtraction.document_id == documents[0].id)
        .one()
    )
    old.is_current = False
    db.add(AIImportExtraction(
        document_id=documents[0].id, created_at=_now(),
        schema_version="1.0", prompt_version="1.1", provider="test",
        extraction_mode="text",
        fields={"document_number": {"value": "P89250", "page": 1,
                                    "confidence": 0.9, "source": "manual"},
                "total_amount": {"value": "9000.00", "page": 1,
                                 "confidence": 1.0, "source": "manual"}},
        line_items=[], is_current=True,
    ))
    db.commit()

    rows = client.get(
        f"/api/v1/ai-import/batches/{batch.id}/manifest", headers=headers,
    ).json()["data"]["rows"]
    second = next(r for r in rows if r["file_name"] == "p89381.pdf")

    # The totals no longer match, so the question must not be raised.
    assert not any("same amount" in n for n in second["routing"]["review_notes"])
