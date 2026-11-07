"""Focused Fuel Management workflow, stock, permission, and reporting tests."""

import uuid
import base64
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.models.attachment import Attachment
from app.models.audit import AuditEvent
from app.models.fuel_management import (
    FuelEmailLog, FuelEquipmentProfile, FuelIssue, FuelIssueEvidence, FuelOrder, FuelReconciliation,
    FuelStockAdjustment, FuelStorageLocation, FuelTypeDefinition,
)
from app.models.vehicle import FuelDelivery, Vehicle
from app.models.fuel import FuelLog
from app.models.enums import VehicleStatus, VehicleType
from app.models.alert import SystemAlert
from app.models.enums import AlertSeverity, AlertStatus, AlertType, FuelType, FuelUsageType
from tests.conftest import (
    auth, login, make_project, make_site, make_supplier, make_user,
    make_user_project_access,
)


@pytest.fixture()
def fuel_ctx(db, client):
    owner = make_user(db, role="OWNER")
    admin = make_user(db, role="OFFICE_ADMIN")
    site_user = make_user(db, role="SITE_STAFF")
    outsider = make_user(db, role="SITE_STAFF")
    project = make_project(db, owner["id"])
    other_project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db)
    make_user_project_access(db, admin["id"], project["id"])
    make_user_project_access(db, site_user["id"], project["id"])
    db.commit()
    headers = {
        "owner": auth(login(client, owner["email"], owner["password"])),
        "admin": auth(login(client, admin["email"], admin["password"])),
        "site": auth(login(client, site_user["email"], site_user["password"])),
        "outsider": auth(login(client, outsider["email"], outsider["password"])),
    }
    diesel = db.query(FuelTypeDefinition).filter_by(code="DIESEL").first()
    petrol = db.query(FuelTypeDefinition).filter_by(code="PETROL_95").first()
    if not diesel:
        diesel = FuelTypeDefinition(code="DIESEL", name="Diesel", is_active=True); db.add(diesel)
    if not petrol:
        petrol = FuelTypeDefinition(code="PETROL_95", name="Petrol 95", is_active=True); db.add(petrol)
    db.flush()
    storage_body = {
        "site_id": site["id"], "fuel_type_id": str(diesel.id), "name": "Main Diesel Tank",
        "capacity_litres": 5000, "low_stock_threshold_litres": 100, "opening_stock_litres": 1000,
    }
    r = client.post(f"/api/v1/projects/{project['id']}/fuel-management/storage", json=storage_body, headers=headers["owner"])
    assert r.status_code == 201, r.text
    return {
        "owner": owner, "admin": admin, "site_user": site_user, "project": project,
        "other_project": other_project, "site": site, "supplier": supplier, "headers": headers,
        "diesel_id": str(diesel.id), "petrol_id": str(petrol.id), "storage_id": r.json()["data"]["id"],
    }


def create_order(client, c, headers="site", litres=500):
    body = {
        "site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"],
        "supplier_id": c["supplier"]["id"], "storage_location_id": c["storage_id"],
        "requested_litres": litres, "delivery_location": "Main site tank",
    }
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/orders",
                    json=body, headers=c["headers"][headers])
    assert r.status_code == 201, r.text
    return r.json()["data"]


def order_to_ordered(client, c, litres=500):
    order = create_order(client, c, litres=litres)
    oid = order["id"]
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/submit", headers=c["headers"]["site"]).status_code == 200
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/approve", headers=c["headers"]["admin"]).status_code == 200
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/mark-ordered",
                    json={"supplier_reference": "SUP-REF-1"}, headers=c["headers"]["admin"])
    assert r.status_code == 200, r.text
    return oid


def record_and_verify(client, c, order_id, litres, note):
    body = {
        "delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": litres,
        "confirmed_litres": litres, "delivery_note_number": note,
        "storage_location_id": c["storage_id"],
    }
    r = client.post(f"/api/v1/fuel-management/orders/{order_id}/deliveries", json=body, headers=c["headers"]["site"])
    assert r.status_code == 201, r.text
    delivery = r.json()["data"]
    v = client.post(f"/api/v1/fuel-management/deliveries/{delivery['id']}/verify", headers=c["headers"]["site"])
    assert v.status_code == 200, v.text
    return delivery


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def issue_with_evidence(client, c, body, *, vehicle=False, hour=False, headers="site"):
    files = {
        "asset_photo": ("asset.png", PNG, "image/png"),
        "pump_photo": ("pump.png", PNG, "image/png"),
    }
    if vehicle: files["odometer_photo"] = ("odo.png", PNG, "image/png")
    if hour: files["hour_meter_photo"] = ("hour.png", PNG, "image/png")
    return client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues-with-evidence",
                       data={"payload": json.dumps(body)}, files=files, headers=c["headers"][headers])


def assert_audit(db, *, actor_id, entity_type, entity_id, action, reason=None):
    db.expire_all()
    event = db.query(AuditEvent).filter(
        AuditEvent.actor_id == uuid.UUID(str(actor_id)), AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == uuid.UUID(str(entity_id)), AuditEvent.action == action,
    ).order_by(AuditEvent.created_at.desc()).first()
    assert event is not None
    assert event.created_at is not None
    if reason is not None:
        assert event.notes == reason
    return event


def test_order_workflow_and_self_approval_guard(client, fuel_ctx):
    c = fuel_ctx; order = create_order(client, c, headers="site")
    oid = order["id"]
    assert order["status"] == "DRAFT"
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/submit", headers=c["headers"]["site"]).status_code == 200
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/approve", headers=c["headers"]["site"]).status_code == 403
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/approve", headers=c["headers"]["admin"]).json()["data"]["status"] == "APPROVED"
    own = create_order(client, c, headers="admin")
    assert client.post(f"/api/v1/fuel-management/orders/{own['id']}/submit", headers=c["headers"]["admin"]).status_code == 200
    assert client.post(f"/api/v1/fuel-management/orders/{own['id']}/approve", headers=c["headers"]["admin"]).status_code == 409


def test_every_order_transition_returns_enriched_current_history(client, fuel_ctx):
    c = fuel_ctx

    def assert_transition(response, status, next_approver, history_statuses):
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == status
        assert data["requester_name"]
        assert data["next_approver"] == next_approver
        assert [entry["to_status"] for entry in data["history"]] == history_statuses
        assert data["history"][-1]["actor_name"]
        return data

    order = create_order(client, c)
    submitted = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{order['id']}/submit", headers=c["headers"]["site"]),
        "SUBMITTED", "Fuel approver", ["DRAFT", "SUBMITTED"],
    )
    approved = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{order['id']}/approve", headers=c["headers"]["admin"]),
        "APPROVED", "Procurement ordering", ["DRAFT", "SUBMITTED", "APPROVED"],
    )
    ordered = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{order['id']}/mark-ordered",
                    json={"supplier_reference": "ENRICHED-PO"}, headers=c["headers"]["admin"]),
        "ORDERED", "Delivery receiver", ["DRAFT", "SUBMITTED", "APPROVED", "ORDERED"],
    )
    assert submitted["id"] == approved["id"] == ordered["id"]
    record_and_verify(client, c, order["id"], 500, "ENRICHED-DN")
    closed = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{order['id']}/close", headers=c["headers"]["admin"]),
        "CLOSED", None, ["DRAFT", "SUBMITTED", "APPROVED", "ORDERED", "DELIVERED", "CLOSED"],
    )
    assert closed["history"][-1]["from_status"] == "DELIVERED"

    rejected_order = create_order(client, c)
    client.post(f"/api/v1/fuel-management/orders/{rejected_order['id']}/submit", headers=c["headers"]["site"])
    rejected = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{rejected_order['id']}/reject",
                    json={"reason": "Request no longer feasible"}, headers=c["headers"]["admin"]),
        "REJECTED", None, ["DRAFT", "SUBMITTED", "REJECTED"],
    )
    assert rejected["history"][-1]["reason"] == "Request no longer feasible"

    cancelled_order = create_order(client, c)
    cancelled = assert_transition(
        client.post(f"/api/v1/fuel-management/orders/{cancelled_order['id']}/cancel",
                    json={"reason": "Operational plan changed"}, headers=c["headers"]["site"]),
        "CANCELLED", None, ["DRAFT", "CANCELLED"],
    )
    assert cancelled["history"][-1]["reason"] == "Operational plan changed"


def test_invalid_transition_and_rejection_reason(client, fuel_ctx):
    c = fuel_ctx; oid = create_order(client, c)["id"]
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/approve", headers=c["headers"]["admin"]).status_code == 422
    client.post(f"/api/v1/fuel-management/orders/{oid}/submit", headers=c["headers"]["site"])
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/reject", json={}, headers=c["headers"]["admin"]).status_code == 422
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/reject", json={"reason": "Budget deferred"}, headers=c["headers"]["admin"])
    assert r.json()["data"]["status"] == "REJECTED"


def test_cancel_and_project_access(client, fuel_ctx):
    c = fuel_ctx; oid = create_order(client, c)["id"]
    assert client.get(f"/api/v1/fuel-management/orders/{oid}", headers=c["headers"]["outsider"]).status_code == 403
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/cancel", json={"reason": "No longer required"}, headers=c["headers"]["site"])
    assert r.json()["data"]["status"] == "CANCELLED"


def test_order_number_unique_constraint(db, fuel_ctx):
    c = fuel_ctx
    base = dict(order_number="FUR-DUPLICATE", project_id=uuid.UUID(c["project"]["id"]),
                site_id=uuid.UUID(c["site"]["id"]), fuel_type_id=uuid.UUID(c["diesel_id"]),
                requested_by=uuid.UUID(c["owner"]["id"]), request_date=datetime.now().date(),
                requested_litres=1, delivery_location="Tank", status="DRAFT")
    db.add(FuelOrder(**base)); db.flush()
    with pytest.raises(Exception):
        with db.begin_nested():
            db.add(FuelOrder(**base)); db.flush()


def test_partial_and_multiple_deliveries_update_status(client, fuel_ctx):
    c = fuel_ctx; oid = order_to_ordered(client, c, 500)
    record_and_verify(client, c, oid, 200, "DN-1")
    assert client.get(f"/api/v1/fuel-management/orders/{oid}", headers=c["headers"]["owner"]).json()["data"]["status"] == "PARTIALLY_DELIVERED"
    record_and_verify(client, c, oid, 300, "DN-2")
    order = client.get(f"/api/v1/fuel-management/orders/{oid}", headers=c["headers"]["owner"]).json()["data"]
    assert order["status"] == "DELIVERED" and order["delivered_litres"] == 500


def test_excess_delivery_rejected_and_admin_override(client, db, fuel_ctx):
    c = fuel_ctx; oid = order_to_ordered(client, c, 100)
    body = {"delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 110,
            "delivery_note_number": "DN-X", "storage_location_id": c["storage_id"]}
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["site"]).status_code == 409
    body.update({"allow_excess": True, "excess_reason": "Supplier meter calibration variance"})
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["owner"])
    assert r.status_code == 201 and r.json()["data"]["excess_override"] is True
    event = assert_audit(db, actor_id=c["owner"]["id"],
                         entity_type="FUEL_DELIVERY", entity_id=r.json()["data"]["id"],
                         action="OVERRUN_ACCEPTED", reason=body["excess_reason"])
    assert event.before_value == {"recorded_litres": 0.0, "ordered_litres": 100.0}
    assert event.after_value["recorded_litres"] == 110
    assert event.after_value["excess_litres"] == 10


def test_wrong_fuel_storage_rejected(client, fuel_ctx):
    c = fuel_ctx; oid = order_to_ordered(client, c)
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage",
                    json={"site_id": c["site"]["id"], "fuel_type_id": c["petrol_id"], "name": "Petrol Tank"},
                    headers=c["headers"]["owner"])
    petrol_storage = r.json()["data"]["id"]
    body = {"delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 10,
            "delivery_note_number": "DN-WRONG", "storage_location_id": petrol_storage}
    assert client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["site"]).status_code == 422


def test_uncut_over_storage_blocks_issues_until_opening_balance_or_delivery(client, db, fuel_ctx):
    """Phase 8: a freshly-created storage location with no evidence behind
    its stock (no opening balance, no verified delivery) must refuse
    FuelIssue — the calculated balance is untrustworthy zero, not a real
    empty tank. Cutover is set automatically by real evidence, not a
    manual toggle."""
    c = fuel_ctx
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage", json={
        "site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"], "name": "New Uncut-Over Tank",
    }, headers=c["headers"]["owner"])
    assert r.status_code == 201, r.text
    storage = r.json()["data"]
    assert storage["cutover_confirmed_at"] is None

    body = {"storage_location_id": storage["id"], "fuel_type_id": c["diesel_id"],
            "destination_type": "GENERATOR", "equipment_reference": "GEN-CUTOVER", "litres": 5}
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues", json=body, headers=c["headers"]["site"])
    assert r.status_code == 422, r.text
    assert "cutover" in r.text.lower()

    # A controlled opening-balance adjustment is real evidence — cutover confirms automatically.
    adj = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/adjustments", json={
        "storage_location_id": storage["id"], "adjustment_type": "OPENING",
        "litres_delta": 200, "reason": "Physical dip count at cutover",
    }, headers=c["headers"]["owner"])
    assert adj.status_code == 201, adj.text

    storages = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage", headers=c["headers"]["owner"]).json()["data"]
    confirmed = next(s for s in storages if s["id"] == storage["id"])
    assert confirmed["cutover_confirmed_at"] is not None

    r2 = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues", json=body, headers=c["headers"]["site"])
    assert r2.status_code == 422 and "Mandatory fuel evidence" in r2.text  # cutover no longer the blocker


def test_manual_emergency_delivery_requires_fuel_admin_and_reason(client, db, fuel_ctx):
    """Phase 7: emergency receipts bypass the procurement chain entirely, so
    they must be locked to fuel.admin, always carry a mandatory reason, and
    leave an explicit, structurally-distinct audit trail."""
    c = fuel_ctx
    url = f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/manual-emergency"
    body = {"storage_location_id": c["storage_id"], "delivered_litres": 50, "reason": "Emergency cash purchase — site ran dry, no time to raise an MR"}

    # SITE_STAFF has fuel.receive but not fuel.admin — must be rejected.
    assert client.post(url, json=body, headers=c["headers"]["site"]).status_code == 403

    # Missing reason — rejected before touching the DB.
    bad = dict(body); del bad["reason"]
    assert client.post(url, json=bad, headers=c["headers"]["admin"]).status_code == 422

    r = client.post(url, json=body, headers=c["headers"]["admin"])
    assert r.status_code == 201, r.text
    fd = r.json()["data"]
    assert fd["is_manual_emergency"] is True
    assert fd["emergency_reason"] == body["reason"]
    assert fd["order_id"] is None
    assert fd["procurement_delivery_item_id"] is None
    assert fd["verification_status"] == "VERIFIED"

    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 1050.0

    event = assert_audit(db, actor_id=c["admin"]["id"], entity_type="FUEL_DELIVERY",
                         entity_id=fd["id"], action="CREATE", reason=body["reason"])
    assert event.after_value["manual_emergency"] is True


def test_legacy_order_delivery_supplier_and_meter_variance_are_independent(client, fuel_ctx):
    """Phase 6: the legacy FuelOrder-based delivery path must use the same
    corrected variance model as the procurement hand-off — two independent
    figures, never a silent fallback from meter to supplier quantity."""
    c = fuel_ctx; oid = order_to_ordered(client, c, 500)
    body = {
        "delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 400,
        "confirmed_litres": 395, "delivery_note_number": "DN-VAR",
        "storage_location_id": c["storage_id"], "opening_reading": 1000, "closing_reading": 1390,
    }
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["site"])
    assert r.status_code == 201, r.text
    fd = r.json()["data"]
    assert fd["calculated_received_litres"] == 390.0
    assert fd["supplier_variance_litres"] == -5.0
    assert fd["meter_variance_litres"] == 5.0

    # No readings captured at all — meter variance must be NULL, never fall back to supplier variance.
    body2 = {"delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 90,
             "confirmed_litres": 85, "delivery_note_number": "DN-NOREAD", "storage_location_id": c["storage_id"]}
    r2 = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body2, headers=c["headers"]["site"])
    assert r2.status_code == 201, r2.text
    fd2 = r2.json()["data"]
    assert fd2["supplier_variance_litres"] == -5.0
    assert fd2["meter_variance_litres"] is None


def test_vehicle_issue_reduces_stock_and_reverse_restores(client, db, fuel_ctx):
    c = fuel_ctx
    vehicle = Vehicle(registration=f"TEST-{uuid.uuid4().hex[:5]}", name="Test Bakkie",
                      vehicle_type=VehicleType.BAKKIE, status=VehicleStatus.ACTIVE,
                      assigned_project_id=uuid.UUID(c["project"]["id"]), fuel_consumption_per_100km=12)
    db.add(vehicle); db.commit()
    body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "vehicle_id": str(vehicle.id), "destination_type": "VEHICLE", "litres": 50,
            "odometer_reading": 1000, "received_by": "Driver"}
    r = issue_with_evidence(client, c, body, vehicle=True)
    assert r.status_code == 201, r.text
    issue = r.json()["data"]
    # Phase 14: the anomaly-review drill-down needs to resolve "who issued this"
    # and "which vehicle" without a separate lookup.
    assert issue["vehicle_registration"] == vehicle.registration
    assert issue["issued_by_name"] == "Test User"
    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 950
    assert client.post(f"/api/v1/fuel-management/issues/{issue['id']}/reverse", json={"reason": "Entry duplicated"}, headers=c["headers"]["owner"]).status_code == 200
    reversal = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_ISSUE",
                            entity_id=issue["id"], action="UPDATE", reason="Entry duplicated")
    assert reversal.before_value == {"is_reversed": False}
    assert reversal.after_value == {"is_reversed": True}
    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 1000


def test_issue_destination_and_insufficient_stock(client, fuel_ctx):
    c = fuel_ctx
    base = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "destination_type": "GENERATOR", "litres": 20}
    assert client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues", json=base, headers=c["headers"]["site"]).status_code == 422
    base.update({"equipment_reference": "GEN-WRONG-FUEL", "fuel_type_id": c["petrol_id"]})
    assert client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues", json=base, headers=c["headers"]["site"]).status_code == 422
    base["fuel_type_id"] = c["diesel_id"]
    base.update({"equipment_reference": "GEN-01", "litres": 2000, "hour_meter_reading": 10})
    assert issue_with_evidence(client, c, base).status_code == 409


def test_decreasing_hour_meter_rejected(client, fuel_ctx):
    c = fuel_ctx
    body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "destination_type": "GENERATOR", "equipment_reference": "GEN-02", "litres": 20,
            "hour_meter_reading": 100}
    assert issue_with_evidence(client, c, body).status_code == 201
    body["hour_meter_reading"] = 99
    assert issue_with_evidence(client, c, body).status_code == 422


def test_reconciliation_threshold_and_approval_separation(client, db, fuel_ctx):
    c = fuel_ctx
    body = {"storage_location_id": c["storage_id"], "physical_balance_litres": 800,
            "explanation": "Physical dip reading"}
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/reconciliations", json=body, headers=c["headers"]["admin"])
    assert r.status_code == 201, r.text
    rec = r.json()["data"]
    assert rec["variance_litres"] == -200 and rec["status"] == "PENDING_APPROVAL"
    assert client.post(f"/api/v1/fuel-management/reconciliations/{rec['id']}/approve", json={}, headers=c["headers"]["admin"]).status_code == 409
    approved = client.post(f"/api/v1/fuel-management/reconciliations/{rec['id']}/approve", json={"reason": "Reviewed"}, headers=c["headers"]["owner"])
    assert approved.status_code == 200
    event = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_RECONCILIATION",
                         entity_id=rec["id"], action="APPROVE", reason="Reviewed")
    assert event.before_value["status"] == "PENDING_APPROVAL"
    assert event.before_value["variance_litres"] == -200
    assert event.after_value["status"] == "APPROVED"
    assert event.after_value["approved_by"] == c["owner"]["id"]


def test_adjustment_permissions_and_immutable_history(client, db, fuel_ctx):
    c = fuel_ctx
    body = {"storage_location_id": c["storage_id"], "adjustment_type": "LOSS",
            "litres_delta": -10, "reason": "Approved spill correction"}
    assert client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/adjustments", json=body, headers=c["headers"]["site"]).status_code == 403
    response = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/adjustments", json=body, headers=c["headers"]["owner"])
    assert response.status_code == 201
    event = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_ADJUSTMENT",
                         entity_id=response.json()["data"]["id"], action="UPDATE", reason=body["reason"])
    assert event.before_value["calculated_balance_litres"] == 1000
    assert event.after_value["calculated_balance_litres"] == 990
    assert event.after_value["litres_delta"] == -10
    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 990


def test_reports_and_legacy_delete_protection(client, db, fuel_ctx):
    c = fuel_ctx; create_order(client, c)
    r = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/reports/orders.csv", headers=c["headers"]["owner"])
    assert r.status_code == 200 and "Order number" in r.text
    usage = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/reports/usage.csv", headers=c["headers"]["owner"])
    assert usage.status_code == 200 and "Issue number" in usage.text
    assert client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/reports/orders.csv", headers=c["headers"]["site"]).status_code == 403

    # Phase 9: fuel_ctx's storage already completed cutover (opening stock at creation) —
    # the legacy Fuel Log must refuse new writes once Fuel Management is live for the project.
    frozen = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel/",
        json={"fuel_type": "DIESEL", "usage_type": "EQUIPMENT", "equipment_ref": "GEN-NEW", "litres": 5},
        headers=c["headers"]["owner"],
    )
    assert frozen.status_code == 422, frozen.text
    assert "Fuel Management" in frozen.text

    # A pre-existing historical FuelLog row (as if written before cutover) stays
    # intact and readable, but is still immutable — corrections go through
    # Fuel Management reversals/adjustments, never a delete.
    legacy = FuelLog(
        project_id=uuid.UUID(c["project"]["id"]), fuel_type=FuelType.DIESEL, usage_type=FuelUsageType.EQUIPMENT,
        equipment_ref="GEN-OLD", litres=5, recorded_by=uuid.UUID(c["owner"]["id"]),
        fuel_date=datetime.now(timezone.utc), log_date=datetime.now(timezone.utc).date(),
    )
    db.add(legacy); db.commit()
    deleted = client.delete(f"/api/v1/fuel/{legacy.id}", headers=c["headers"]["owner"])
    assert deleted.status_code == 409


def test_fuel_issue_computes_weighted_average_delivery_cost(client, db, fuel_ctx):
    """Phase 10: FuelIssue carries its own cost, derived from the real
    delivery price (never fabricated) — fuel_ctx's opening 1000 L balance
    recorded no price, so those litres are excluded from both sides of the
    weighted average and only the costed delivery below feeds it.

    The exclusion follows from the missing price, not from the adjustment's
    OPENING type: since 0082 an opening balance can carry a price of its own.
    The premise is asserted rather than assumed, because adding a price to the
    fixture would blend the numbers and quietly destroy this guard."""
    c = fuel_ctx; oid = order_to_ordered(client, c, 500)
    opening = db.query(FuelStockAdjustment).filter_by(
        storage_location_id=uuid.UUID(c["storage_id"]), adjustment_type="OPENING").one()
    assert opening.cost_per_litre is None
    body = {
        "delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 500,
        "confirmed_litres": 500, "delivery_note_number": "DN-COST",
        "storage_location_id": c["storage_id"], "cost_per_litre": 22.5,
    }
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["site"])
    assert r.status_code == 201, r.text
    fd = r.json()["data"]
    assert fd["cost_per_litre"] == 22.5
    assert client.post(f"/api/v1/fuel-management/deliveries/{fd['id']}/verify", headers=c["headers"]["site"]).status_code == 200

    issue_body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-COST", "litres": 100}
    r2 = issue_with_evidence(client, c, issue_body)
    assert r2.status_code == 201, r2.text
    issue = r2.json()["data"]
    assert issue["unit_cost"] == 22.5
    assert issue["total_cost"] == 2250.0


def test_cost_summary_and_dashboard_combine_fuel_log_and_fuel_issue(client, db, fuel_ctx):
    """Phase 10: project cost reporting must not silently under-report once
    a project moves to Fuel Management — fuel_ctx already has cutover, so
    all its fuel cost/litres now come from FuelIssue, not the frozen
    FuelLog. Combined only at this reporting layer, never in stock calcs."""
    c = fuel_ctx; oid = order_to_ordered(client, c, 500)
    body = {
        "delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 500,
        "confirmed_litres": 500, "delivery_note_number": "DN-COST2",
        "storage_location_id": c["storage_id"], "cost_per_litre": 20.0,
    }
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=body, headers=c["headers"]["site"])
    fd = r.json()["data"]
    client.post(f"/api/v1/fuel-management/deliveries/{fd['id']}/verify", headers=c["headers"]["site"])

    issue_body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-COST2", "litres": 50}
    r2 = issue_with_evidence(client, c, issue_body)
    assert r2.status_code == 201, r2.text

    summary = client.get(f"/api/v1/projects/{c['project']['id']}/cost-summary", headers=c["headers"]["owner"])
    assert summary.status_code == 200, summary.text
    data = summary.json()["data"]
    assert data["fuel_cost"] == 1000.0  # 50L * 20.0, entirely from FuelIssue — FuelLog is frozen here
    assert data["fuel_litres"] == 50.0

    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"])
    assert dash.status_code == 200


def test_legacy_vehicle_fuel_delivery_flow_frozen_after_cutover(client, fuel_ctx):
    """Phase 10: vehicles.py's own bulk fuel-delivery/fill flow writes
    FuelLog directly, bypassing fuel_service.create_fuel_log() — it must be
    frozen independently once Fuel Management is live for the project, or
    Phase 9's freeze could be silently bypassed through this second path."""
    c = fuel_ctx
    r = client.post("/api/v1/vehicles/fuel-deliveries/", data={
        "site_id": c["site"]["id"], "project_id": c["project"]["id"],
        "delivery_date": date.today().isoformat(), "fuel_type": "DIESEL", "litres_delivered": "100",
    }, headers=c["headers"]["owner"])
    assert r.status_code == 422, r.text
    assert "Fuel Management" in r.text


def test_legacy_fuel_log_still_works_before_fuel_management_cutover(client, db):
    """Phase 9: the freeze is scoped to projects where Fuel Management has
    actually gone live. A project with no cut-over storage location at all
    must be completely unaffected — legacy FuelLog keeps working exactly as
    before for teams who haven't adopted Fuel Management yet."""
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    db.commit()
    tok = auth(login(client, owner["email"], owner["password"]))
    r = client.post(
        f"/api/v1/projects/{project['id']}/fuel/",
        json={"fuel_type": "DIESEL", "usage_type": "EQUIPMENT", "equipment_ref": "GEN-01", "litres": 5},
        headers=tok,
    )
    assert r.status_code == 201, r.text


def test_business_example_1000l_diesel_partial_deliveries_and_two_vehicle_issues(client, db):
    """The exact business scenario approved before implementation began.

    1000L Diesel requested via Request Materials (no BOQ) -> office approval
    -> real PO -> invoice attachable -> two partial deliveries (600L + 400L)
    confirmed as 595L + 400L = 995L total (never 1000, never duplicated,
    idempotent under retry) -> storage cutover confirmed by that real
    evidence -> Vehicle A issued 100L -> Vehicle B issued 100L -> no
    duplicate FuelLog anywhere -> supplier history shows the real PO ->
    procurement DeliveryItem records stay untouched by the Fuel-side
    confirmation -> both variance types auditable -> reconciliation works.
    """
    from app.models.delivery import DeliveryItem
    from app.models.fuel import FuelLog
    from app.models.purchase_order import PurchaseOrder

    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db)
    db.commit()
    hdr = auth(login(client, owner["email"], owner["password"]))
    pid = project["id"]

    diesel = db.query(FuelTypeDefinition).filter_by(code="DIESEL").first()
    if not diesel:
        diesel = FuelTypeDefinition(code="DIESEL", name="Diesel", is_active=True)
        db.add(diesel); db.flush()

    # Storage exists but has no evidence yet — not cut over.
    r = client.post(f"/api/v1/projects/{pid}/fuel-management/storage", json={
        "site_id": site["id"], "fuel_type_id": str(diesel.id), "name": "Site Diesel Tank",
        "capacity_litres": 5000,
    }, headers=hdr)
    assert r.status_code == 201, r.text
    storage_id = r.json()["data"]["id"]
    assert r.json()["data"]["cutover_confirmed_at"] is None

    def storage_balance():
        storages = client.get(f"/api/v1/projects/{pid}/fuel-management/storage", headers=hdr).json()["data"]
        return next(s for s in storages if s["id"] == storage_id)

    # 1. Site clerk requests 1000L Diesel via Request Materials — FUEL category, no BOQ link.
    r = client.post(f"/api/v1/projects/{pid}/material-requests/", json={
        "site_id": site["id"], "procurement_category": "FUEL",
        "items": [{"description": "Diesel", "requested_quantity": 1000.0, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    mr = r.json()["data"]
    assert mr["procurement_category"] == "FUEL"
    assert mr["items"][0]["boq_item_id"] is None
    mr_id = mr["id"]

    # 2. Office approval — the exact same endpoints as a MATERIAL request.
    assert client.post(f"/api/v1/material-requests/{mr_id}/submit", headers=hdr).status_code == 200
    assert client.post(f"/api/v1/material-requests/{mr_id}/approve", json={}, headers=hdr).status_code == 200

    # 3. Office selects the supplier and converts to a real PO.
    r = client.post(f"/api/v1/material-requests/{mr_id}/convert-to-po", json={
        "supplier_id": supplier["id"],
        "items": [{"description": "Diesel", "quantity": 1000, "unit": "L", "rate": 25.0}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    po_id = r.json()["data"]["po_id"]

    # 4. Invoice is attachable against the real PO.
    r_inv = client.post(f"/api/v1/projects/{pid}/invoices/", json={
        "invoice_number": f"INV-DIESEL-{uuid.uuid4().hex[:6].upper()}",
        "supplier_id": supplier["id"], "purchase_order_id": po_id, "total_amount": 25000.0,
    }, headers=hdr)
    assert r_inv.status_code == 201, r_inv.text

    # 5. First delivery: 600L physically delivered, recorded as a real DeliveryItem.
    r = client.post(f"/api/v1/projects/{pid}/deliveries/", json={
        "supplier_id": supplier["id"], "site_id": site["id"], "purchase_order_id": po_id,
        "supplier_delivery_note_number": "DN-DIESEL-1",
        "items": [{"description": "Diesel", "quantity_received": 600.0, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    delivery_item_1 = r.json()["data"]["items"][0]["id"]

    # 6. Fuel receipt confirms 595L (physical dip differs slightly from the documented 600L).
    hand_off_url = f"/api/v1/projects/{pid}/fuel-management/deliveries/from-procurement"
    r = client.post(hand_off_url, json={
        "delivery_item_id": delivery_item_1, "storage_location_id": storage_id, "confirmed_litres": 595.0,
    }, headers=hdr)
    assert r.status_code == 201, r.text
    fd1 = r.json()["data"]
    assert fd1["litres_delivered"] == 600.0
    assert fd1["confirmed_litres"] == 595.0
    assert fd1["supplier_variance_litres"] == -5.0

    storage = storage_balance()
    assert storage["cutover_confirmed_at"] is not None
    assert storage["calculated_balance_litres"] == 595.0

    # Retry the exact same hand-off (double-click) — idempotent, no double stock.
    r_retry = client.post(hand_off_url, json={
        "delivery_item_id": delivery_item_1, "storage_location_id": storage_id, "confirmed_litres": 595.0,
    }, headers=hdr)
    assert r_retry.status_code == 201, r_retry.text
    assert r_retry.json()["data"]["id"] == fd1["id"]
    assert storage_balance()["calculated_balance_litres"] == 595.0

    # 7. Second, partial delivery: 400L, confirmed in full with meter readings this time.
    r = client.post(f"/api/v1/projects/{pid}/deliveries/", json={
        "supplier_id": supplier["id"], "site_id": site["id"], "purchase_order_id": po_id,
        "supplier_delivery_note_number": "DN-DIESEL-2",
        "items": [{"description": "Diesel", "quantity_received": 400.0, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    delivery_item_2 = r.json()["data"]["items"][0]["id"]

    r = client.post(hand_off_url, json={
        "delivery_item_id": delivery_item_2, "storage_location_id": storage_id, "confirmed_litres": 400.0,
        "opening_reading": 1000.0, "closing_reading": 1400.0,
    }, headers=hdr)
    assert r.status_code == 201, r.text
    fd2 = r.json()["data"]
    assert fd2["supplier_variance_litres"] == 0.0
    assert fd2["meter_variance_litres"] == 0.0

    # Total confirmed stock: 595 + 400 = 995L — never 1000, never duplicated.
    assert storage_balance()["calculated_balance_litres"] == 995.0

    # Procurement DeliveryItem records stay exactly as documented, untouched by
    # the Fuel-side confirmation — the two layers never overwrite each other.
    di1 = db.query(DeliveryItem).filter(DeliveryItem.id == uuid.UUID(delivery_item_1)).first()
    assert float(di1.quantity_received) == 600.0

    # 8. Vehicle A receives 100L.
    vehicle_a = Vehicle(
        registration=f"VA-{uuid.uuid4().hex[:5]}", name="Vehicle A", vehicle_type=VehicleType.BAKKIE,
        status=VehicleStatus.ACTIVE, assigned_project_id=uuid.UUID(pid), fuel_consumption_per_100km=10,
    )
    db.add(vehicle_a); db.commit()
    issue_body_a = {
        "storage_location_id": storage_id, "fuel_type_id": str(diesel.id),
        "vehicle_id": str(vehicle_a.id), "destination_type": "VEHICLE", "litres": 100,
        "odometer_reading": 1000, "evidence_override_reason": "business-example scenario test",
    }
    r = client.post(f"/api/v1/projects/{pid}/fuel-management/issues", json=issue_body_a, headers=hdr)
    assert r.status_code == 201, r.text
    issue_a = r.json()["data"]
    assert issue_a["litres"] == 100.0
    assert storage_balance()["calculated_balance_litres"] == 895.0

    # Vehicle A's own fuel history shows the same 100L issue — consumption/anomaly
    # calc ran (first-ever fill has no prior odometer, so distance is None, no
    # false-positive anomaly).
    r_a = client.get(f"/api/v1/projects/{pid}/fuel-management/issues",
                     params={"vehicle_id": str(vehicle_a.id)}, headers=hdr)
    assert r_a.status_code == 200
    assert len(r_a.json()["data"]) == 1
    assert r_a.json()["data"][0]["id"] == issue_a["id"]
    assert r_a.json()["data"][0]["anomaly_flag"] is False

    # 9. Vehicle B receives 100L.
    vehicle_b = Vehicle(
        registration=f"VB-{uuid.uuid4().hex[:5]}", name="Vehicle B", vehicle_type=VehicleType.BAKKIE,
        status=VehicleStatus.ACTIVE, assigned_project_id=uuid.UUID(pid), fuel_consumption_per_100km=10,
    )
    db.add(vehicle_b); db.commit()
    issue_body_b = {**issue_body_a, "vehicle_id": str(vehicle_b.id), "odometer_reading": 500}
    r = client.post(f"/api/v1/projects/{pid}/fuel-management/issues", json=issue_body_b, headers=hdr)
    assert r.status_code == 201, r.text
    assert storage_balance()["calculated_balance_litres"] == 795.0

    # No duplicate FuelLog anywhere — FuelIssue is the sole ledger for these fills.
    assert db.query(FuelLog).filter(FuelLog.vehicle_id.in_([vehicle_a.id, vehicle_b.id])).count() == 0

    # Supplier history naturally shows the real Fuel procurement chain — no
    # parallel Fuel supplier-history engine exists or is needed.
    supplier_pos = db.query(PurchaseOrder).filter(PurchaseOrder.supplier_id == uuid.UUID(supplier["id"])).all()
    assert any(str(p.id) == po_id for p in supplier_pos)

    # Reconciliation still works against the resulting stock.
    r_rec = client.post(f"/api/v1/projects/{pid}/fuel-management/reconciliations", json={
        "storage_location_id": storage_id, "physical_balance_litres": 795.0,
        "explanation": "Physical dip matches calculated stock",
    }, headers=hdr)
    assert r_rec.status_code == 201, r_rec.text
    assert r_rec.json()["data"]["variance_litres"] == 0.0


def test_fuel_schema_has_no_boq_dependency():
    """Fuel quantities remain structurally separate from BOQ/procurement totals."""
    tables = [
        FuelTypeDefinition.__table__, FuelStorageLocation.__table__, FuelOrder.__table__,
        FuelDelivery.__table__, FuelIssue.__table__, FuelStockAdjustment.__table__,
        FuelReconciliation.__table__,
    ]
    targets = {foreign_key.target_fullname for table in tables for foreign_key in table.foreign_keys}
    assert not any(target.startswith("boq_") or ".boq_" in target for target in targets)


def test_site_request_submits_with_history_and_my_filter(client, fuel_ctx):
    c = fuel_ctx
    profile = {"site_id": c["site"]["id"], "equipment_reference": "GEN-MOBILE-1",
               "destination_type": "GENERATOR", "hour_meter_required": True}
    assert client.put(f"/api/v1/projects/{c['project']['id']}/fuel-management/equipment-profiles",
                      json=profile, headers=c["headers"]["owner"]).status_code == 200
    body = {"site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"],
            "requested_litres": 75, "delivery_location": "Main site",
            "intended_use": "Generator shift", "expected_delivery_date": "2026-08-05",
            "destination_type": "GENERATOR", "equipment_reference": "GEN-MOBILE-1", "notes": "Night work"}
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/requests",
                    json=body, headers=c["headers"]["site"])
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["status"] == "SUBMITTED" and data["next_approver"] == "Fuel approver"
    assert [x["to_status"] for x in data["history"]] == ["DRAFT", "SUBMITTED"]
    mine = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/orders?mine=true",
                      headers=c["headers"]["site"]).json()["data"]
    assert [x["id"] for x in mine] == [data["id"]]


def test_site_request_destination_types_and_project_ownership(client, db, fuel_ctx):
    c = fuel_ctx
    vehicle = Vehicle(registration=f"REQ-{uuid.uuid4().hex[:5]}", name="Request Vehicle",
                      vehicle_type=VehicleType.BAKKIE, status=VehicleStatus.ACTIVE,
                      assigned_project_id=uuid.UUID(c["project"]["id"]))
    other_vehicle = Vehicle(registration=f"OTH-{uuid.uuid4().hex[:5]}", name="Other Vehicle",
                            vehicle_type=VehicleType.BAKKIE, status=VehicleStatus.ACTIVE,
                            assigned_project_id=uuid.UUID(c["other_project"]["id"]))
    db.add_all([vehicle, other_vehicle]); db.commit()
    for destination, reference in [
        ("GENERATOR", "GEN-REQUEST"), ("PLANT", "PLANT-REQUEST"),
        ("OTHER_EQUIPMENT", "OTHER-REQUEST"),
    ]:
        profile = {"site_id": c["site"]["id"], "equipment_reference": reference,
                   "destination_type": destination, "hour_meter_required": True}
        response = client.put(
            f"/api/v1/projects/{c['project']['id']}/fuel-management/equipment-profiles",
            json=profile, headers=c["headers"]["owner"],
        )
        assert response.status_code == 200, response.text

    base = {"site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"],
            "requested_litres": 25, "delivery_location": "Authorised site",
            "intended_use": "Scheduled operation", "expected_delivery_date": "2026-08-06"}
    destinations = [
        ("VEHICLE", {"vehicle_id": str(vehicle.id)}),
        ("SITE_STORAGE", {"storage_location_id": c["storage_id"]}),
        ("GENERATOR", {"equipment_reference": "GEN-REQUEST"}),
        ("PLANT", {"equipment_reference": "PLANT-REQUEST"}),
        ("OTHER_EQUIPMENT", {"equipment_reference": "OTHER-REQUEST"}),
    ]
    for destination, selected in destinations:
        response = client.post(
            f"/api/v1/projects/{c['project']['id']}/fuel-management/requests",
            json={**base, "destination_type": destination, **selected}, headers=c["headers"]["site"],
        )
        assert response.status_code == 201, (destination, response.text)
        assert response.json()["data"]["destination_type"] == destination

    wrong_vehicle = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/requests",
        json={**base, "destination_type": "VEHICLE", "vehicle_id": str(other_vehicle.id)},
        headers=c["headers"]["site"],
    )
    assert wrong_vehicle.status_code == 422 and "does not belong" in wrong_vehicle.text

    other_site = make_site(db, c["other_project"]["id"]); db.commit()
    other_storage = client.post(
        f"/api/v1/projects/{c['other_project']['id']}/fuel-management/storage",
        json={"site_id": other_site["id"], "fuel_type_id": c["diesel_id"], "name": "Other Project Tank"},
        headers=c["headers"]["owner"],
    )
    assert other_storage.status_code == 201
    wrong_storage = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/requests",
        json={**base, "destination_type": "SITE_STORAGE",
              "storage_location_id": other_storage.json()["data"]["id"]}, headers=c["headers"]["site"],
    )
    assert wrong_storage.status_code == 422 and "different project" in wrong_storage.text

    db.add(FuelEquipmentProfile(
        project_id=uuid.UUID(c["other_project"]["id"]), site_id=uuid.UUID(other_site["id"]),
        equipment_reference="CROSS-PROJECT-GEN", destination_type="GENERATOR",
        tolerance_pct=20, minimum_issue_interval_hours=0, hour_meter_required=True,
        override_required=False, is_active=True,
    )); db.commit()
    wrong_equipment = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/requests",
        json={**base, "destination_type": "GENERATOR", "equipment_reference": "CROSS-PROJECT-GEN"},
        headers=c["headers"]["site"],
    )
    assert wrong_equipment.status_code == 422 and "does not belong" in wrong_equipment.text


def test_mandatory_evidence_and_authorised_override_audit(client, db, fuel_ctx):
    c = fuel_ctx
    vehicle = Vehicle(registration=f"EVD-{uuid.uuid4().hex[:5]}", name="Evidence Vehicle",
                      vehicle_type=VehicleType.BAKKIE, status=VehicleStatus.ACTIVE,
                      assigned_project_id=uuid.UUID(c["project"]["id"]))
    db.add(vehicle); db.commit()
    body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "vehicle_id": str(vehicle.id), "destination_type": "VEHICLE", "litres": 10,
            "odometer_reading": 10}
    denied = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues",
                         json=body, headers=c["headers"]["site"])
    assert denied.status_code == 422 and "Mandatory fuel evidence" in denied.text
    body["evidence_override_reason"] = "Camera unavailable after site inspection"
    allowed = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/issues",
                          json=body, headers=c["headers"]["owner"])
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["data"]["evidence_override_reason"] == body["evidence_override_reason"]
    event = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_ISSUE",
                         entity_id=allowed.json()["data"]["id"], action="OVERRUN_ACCEPTED",
                         reason=body["evidence_override_reason"])
    assert event.before_value["evidence_complete"] is False
    assert set(event.before_value["missing_evidence"]) == {"ASSET_PHOTO", "PUMP_PHOTO", "ODOMETER_PHOTO"}
    assert event.after_value["evidence_override_accepted"] is True


def test_equipment_profile_drives_feasibility_override(client, db, fuel_ctx):
    c = fuel_ctx
    profile = {"site_id": c["site"]["id"], "equipment_reference": "GEN-PROFILE",
               "destination_type": "GENERATOR", "expected_litres_per_hour": 5,
               "tolerance_pct": 10, "tank_capacity_litres": 100,
               "hour_meter_required": True, "override_required": True}
    assert client.put(f"/api/v1/projects/{c['project']['id']}/fuel-management/equipment-profiles",
                      json=profile, headers=c["headers"]["owner"]).status_code == 200
    base = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "destination_type": "GENERATOR", "equipment_reference": "GEN-PROFILE",
            "litres": 20, "hour_meter_reading": 100}
    assert issue_with_evidence(client, c, base, hour=True).status_code == 201
    base.update({"litres": 50, "hour_meter_reading": 101})
    denied = issue_with_evidence(client, c, base, hour=True)
    assert denied.status_code == 422 and "feasibility limits" in denied.text
    base["feasibility_override_reason"] = "Manager confirmed extended loaded operation"
    allowed = issue_with_evidence(client, c, base, hour=True, headers="owner")
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["data"]["feasibility_status"] == "OVERRIDDEN"
    event = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_ISSUE",
                         entity_id=allowed.json()["data"]["id"], action="OVERRUN_ACCEPTED",
                         reason=base["feasibility_override_reason"])
    assert event.before_value == {"feasibility_status": "OVERRIDE_REQUIRED"}
    assert event.after_value == {"feasibility_status": "OVERRIDDEN"}


def test_hour_based_vehicle_uses_hour_meter_not_odometer(client, db, fuel_ctx):
    """A Vehicle (TLB/excavator/crane) flagged uses_hours=True must be tracked
    by hour meter / L-per-hour even though it's issued via destination_type=
    VEHICLE — not forced through the odometer / L-per-100km path, and without
    needing a separate FuelEquipmentProfile."""
    c = fuel_ctx
    vehicle = Vehicle(
        registration=f"HRS-{uuid.uuid4().hex[:5]}", name="Hour-Based TLB",
        vehicle_type=VehicleType.TLB, status=VehicleStatus.ACTIVE,
        assigned_project_id=uuid.UUID(c["project"]["id"]),
        uses_hours=True, hour_meter_required=True,
        fuel_consumption_per_hour=5, fuel_tolerance_pct=20, tank_capacity_l=100,
    )
    db.add(vehicle); db.commit()
    base = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "vehicle_id": str(vehicle.id), "destination_type": "VEHICLE",
            "litres": 20, "hour_meter_reading": 100}

    first = issue_with_evidence(client, c, base, hour=True)
    assert first.status_code == 201, first.text
    data = first.json()["data"]
    assert data["litres_per_hour"] is None  # no previous reading yet — nothing to compare
    assert data["litres_per_100km"] is None
    assert data["feasibility_status"] == "OK"

    # Second fill: 20 L over 2 hours -> 10 L/hour, exceeds 5 * 1.2 = 6 tolerance -> anomaly.
    base.update({"litres": 20, "hour_meter_reading": 102})
    second = issue_with_evidence(client, c, base, hour=True)
    assert second.status_code == 201, second.text
    data2 = second.json()["data"]
    assert data2["litres_per_hour"] == 10.0
    assert data2["litres_per_100km"] is None
    assert data2["operating_hours_since_previous"] == 2.0
    assert data2["feasibility_status"] == "REVIEW"
    assert "L/hour" in (data2.get("anomaly_reason") or "")


def test_hour_based_vehicle_rejects_non_increasing_hour_meter(client, db, fuel_ctx):
    c = fuel_ctx
    vehicle = Vehicle(
        registration=f"HRS-{uuid.uuid4().hex[:5]}", name="Excavator",
        vehicle_type=VehicleType.EXCAVATOR, status=VehicleStatus.ACTIVE,
        assigned_project_id=uuid.UUID(c["project"]["id"]),
        uses_hours=True, hour_meter_required=True, fuel_consumption_per_hour=5,
    )
    db.add(vehicle); db.commit()
    base = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "vehicle_id": str(vehicle.id), "destination_type": "VEHICLE",
            "litres": 10, "hour_meter_reading": 50}
    assert issue_with_evidence(client, c, base, hour=True).status_code == 201

    base.update({"litres": 10, "hour_meter_reading": 50})  # same reading — must be rejected
    stuck = issue_with_evidence(client, c, base, hour=True)
    assert stuck.status_code == 422 and "greater than the previous reading" in stuck.text


def test_evidence_upload_failure_rolls_back_issue_metadata_and_stock_then_retry_succeeds(
    client, db, fuel_ctx, monkeypatch,
):
    c = fuel_ctx
    vehicle = Vehicle(registration=f"FAIL-{uuid.uuid4().hex[:5]}", name="Failure Vehicle",
                      vehicle_type=VehicleType.BAKKIE, status=VehicleStatus.ACTIVE,
                      assigned_project_id=uuid.UUID(c["project"]["id"]))
    db.add(vehicle); db.commit()
    body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
            "vehicle_id": str(vehicle.id), "destination_type": "VEHICLE", "litres": 40,
            "odometer_reading": 500}
    from app.services import attachment_service
    original_save = attachment_service.save_attachment
    original_cleanup = attachment_service.cleanup_staged_uploads
    attempts = {"count": 0}; cleaned = []

    def fail_second(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise RuntimeError("simulated second attachment storage failure")
        return original_save(*args, **kwargs)

    def track_cleanup(paths):
        cleaned.extend(paths)
        return original_cleanup(paths)

    issue_count = db.query(FuelIssue).count()
    evidence_count = db.query(FuelIssueEvidence).count()
    attachment_count = db.query(Attachment).count()
    monkeypatch.setattr(attachment_service, "save_attachment", fail_second)
    monkeypatch.setattr(attachment_service, "cleanup_staged_uploads", track_cleanup)
    failed = issue_with_evidence(client, c, body, vehicle=True)
    assert failed.status_code == 503
    assert "No fuel issue was recorded" in failed.text
    db.expire_all()
    assert db.query(FuelIssue).count() == issue_count
    assert db.query(FuelIssueEvidence).count() == evidence_count
    assert db.query(Attachment).count() == attachment_count
    assert cleaned and all(not path.startswith("http") for path in cleaned)
    dashboard = client.get(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard",
        headers=c["headers"]["owner"],
    ).json()["data"]
    assert dashboard["current_calculated_stock"] == 1000

    monkeypatch.setattr(attachment_service, "save_attachment", original_save)
    retry = issue_with_evidence(client, c, body, vehicle=True)
    assert retry.status_code == 201, retry.text
    db.expire_all()
    assert db.query(FuelIssue).count() == issue_count + 1
    assert db.query(FuelIssueEvidence).filter_by(issue_id=uuid.UUID(retry.json()["data"]["id"])).count() == 3
    assert db.query(Attachment).count() == attachment_count + 3
    assert client.get(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard",
        headers=c["headers"]["owner"],
    ).json()["data"]["current_calculated_stock"] == 960


@pytest.mark.parametrize("payload", [
    "{not-json",
    "{}",
    json.dumps({"storage_location_id": "not-a-uuid", "fuel_type_id": str(uuid.uuid4()),
                "destination_type": "GENERATOR", "equipment_reference": "GEN-X", "litres": 10}),
    json.dumps({"storage_location_id": str(uuid.uuid4()), "fuel_type_id": str(uuid.uuid4()),
                "destination_type": "INVALID_DESTINATION", "equipment_reference": "GEN-X", "litres": 10}),
    json.dumps({"storage_location_id": str(uuid.uuid4()), "fuel_type_id": str(uuid.uuid4()),
                "destination_type": "GENERATOR", "equipment_reference": "GEN-X", "litres": "many"}),
])
def test_multipart_issue_payload_errors_are_controlled_422(client, fuel_ctx, payload):
    c = fuel_ctx
    response = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/issues-with-evidence",
        data={"payload": payload}, files={"asset_photo": ("asset.png", PNG, "image/png")},
        headers=c["headers"]["site"],
    )
    assert response.status_code == 422
    assert "Invalid Fuel issue payload" in response.text


def test_frontend_base_url_environment_validation_and_normalization(monkeypatch):
    # Dummy Supabase credentials so these constructions exercise ONLY the
    # FRONTEND_BASE_URL validator, not validate_production_storage (see
    # test_production_storage_validation below for that one).
    _supabase = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_KEY": "dummy-key"}
    test_settings = Settings(_env_file=None, APP_ENV="test", DEBUG=False, FRONTEND_BASE_URL="")
    assert test_settings.FRONTEND_BASE_URL == "http://localhost:5173"
    production = Settings(
        _env_file=None, APP_ENV="production", DEBUG=False,
        FRONTEND_BASE_URL="https://fuel.example.test/", **_supabase,
    )
    assert production.FRONTEND_BASE_URL == "https://fuel.example.test"
    from app.services import fuel_email_service
    monkeypatch.setattr(fuel_email_service.settings, "FRONTEND_BASE_URL", production.FRONTEND_BASE_URL)
    assert fuel_email_service._frontend_url("/notifications/fuel-order/123") == (
        "https://fuel.example.test/notifications/fuel-order/123"
    )
    with pytest.raises(ValueError, match="local absolute paths"):
        fuel_email_service._frontend_url("//unsafe.example/path")
    with pytest.raises(PydanticValidationError, match="must be configured"):
        Settings(_env_file=None, APP_ENV="production", DEBUG=False, FRONTEND_BASE_URL="", **_supabase)
    with pytest.raises(PydanticValidationError, match="cannot point to localhost"):
        Settings(_env_file=None, APP_ENV="staging", DEBUG=False,
                 FRONTEND_BASE_URL="http://localhost:5173", **_supabase)
    with pytest.raises(PydanticValidationError, match="public origin"):
        Settings(_env_file=None, APP_ENV="production", DEBUG=False,
                 FRONTEND_BASE_URL="https://fuel.example.test/unsafe/path", **_supabase)


def test_production_storage_validation():
    """Outside development/test, Fuel evidence/attachment storage must be
    configured (Supabase) — production must never silently fall back to
    local disk, which is ephemeral and served unauthenticated."""
    with pytest.raises(PydanticValidationError, match="SUPABASE_URL and SUPABASE_SERVICE_KEY"):
        Settings(_env_file=None, APP_ENV="production", DEBUG=False,
                 FRONTEND_BASE_URL="https://fuel.example.test",
                 SUPABASE_URL="", SUPABASE_SERVICE_KEY="")
    with pytest.raises(PydanticValidationError, match="SUPABASE_URL and SUPABASE_SERVICE_KEY"):
        Settings(_env_file=None, APP_ENV="production", DEBUG=False,
                 FRONTEND_BASE_URL="https://fuel.example.test",
                 SUPABASE_URL="https://example.supabase.co", SUPABASE_SERVICE_KEY="")
    # Fully configured production settings pass.
    ok = Settings(_env_file=None, APP_ENV="production", DEBUG=False,
                   FRONTEND_BASE_URL="https://fuel.example.test",
                   SUPABASE_URL="https://example.supabase.co", SUPABASE_SERVICE_KEY="dummy-key")
    assert ok.SUPABASE_URL == "https://example.supabase.co"
    # Development/test never requires it.
    dev = Settings(_env_file=None, APP_ENV="development", DEBUG=True)
    assert dev.SUPABASE_URL == ""


def test_fuel_email_logs_nonblocking_and_retryable(client, db, fuel_ctx, monkeypatch):
    c = fuel_ctx; order = create_order(client, c); oid = order["id"]
    from app.services import email_service
    monkeypatch.setattr(email_service, "send_email", lambda *a, **k: {"status": "FAILED", "error": "mailbox offline"})
    submitted = client.post(f"/api/v1/fuel-management/orders/{oid}/submit", headers=c["headers"]["site"])
    assert submitted.status_code == 200 and submitted.json()["data"]["status"] == "SUBMITTED"
    assert db.query(FuelEmailLog).filter_by(order_id=uuid.UUID(oid), status="FAILED").count() >= 1
    sent_bodies = []
    monkeypatch.setattr(email_service, "send_email", lambda to, subject, body, **k: (
        sent_bodies.append(body) or {"status": "MOCK_SENT", "error": None}
    ))
    retry = client.post("/api/v1/fuel-management/email-queue/retry", headers=c["headers"]["owner"])
    assert retry.status_code == 200 and retry.json()["data"]["processed"] >= 1
    assert sent_bodies and 'href="http://localhost:5173/notifications/fuel-order/' in sent_bodies[0]


def test_notification_deep_link_access_and_read_history(client, db, fuel_ctx):
    c = fuel_ctx
    order = create_order(client, c)
    alert = SystemAlert(project_id=uuid.UUID(c["project"]["id"]), target_user_id=uuid.UUID(c["admin"]["id"]),
        reference_type="FUEL_ORDER", reference_id=uuid.UUID(order["id"]), alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
        severity=AlertSeverity.MEDIUM, title="Fuel request", message="Review", status=AlertStatus.OPEN,
        notification_channel="in_app", created_at=datetime.now(timezone.utc))
    db.add(alert); db.commit()
    opened = client.get(f"/api/v1/alerts/{alert.id}/open", headers=c["headers"]["admin"])
    assert opened.status_code == 200
    assert opened.json()["data"]["action_url"] == f"/fuel-management/orders?order={order['id']}"
    assert opened.json()["data"]["read_at"]
    assert client.get(f"/api/v1/alerts/{alert.id}/open", headers=c["headers"]["site"]).status_code == 403
    read = client.post(f"/api/v1/alerts/{alert.id}/read", headers=c["headers"]["admin"])
    assert read.status_code == 200 and read.json()["data"]["status"] == "OPEN" and read.json()["data"]["read_at"]
    history = client.get("/api/v1/alerts/", headers=c["headers"]["admin"])
    assert history.status_code == 200
    assert any(row["id"] == str(alert.id) and row["read_at"] for row in history.json()["data"])

    missing = SystemAlert(
        project_id=uuid.UUID(c["project"]["id"]), target_user_id=uuid.UUID(c["admin"]["id"]),
        reference_type="FUEL_ORDER", reference_id=uuid.uuid4(), alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
        severity=AlertSeverity.MEDIUM, title="Missing Fuel request", message="Review",
        status=AlertStatus.OPEN, notification_channel="in_app", created_at=datetime.now(timezone.utc),
    )
    other_order = FuelOrder(
        order_number=f"FUR-CROSS-{uuid.uuid4().hex[:8]}", project_id=uuid.UUID(c["other_project"]["id"]),
        fuel_type_id=uuid.UUID(c["diesel_id"]), requested_by=uuid.UUID(c["owner"]["id"]),
        request_date=datetime.now().date(), requested_litres=5, delivery_location="Other project",
        status="DRAFT",
    )
    db.add(other_order); db.flush()
    cross_project = SystemAlert(
        project_id=uuid.UUID(c["project"]["id"]), target_user_id=uuid.UUID(c["admin"]["id"]),
        reference_type="FUEL_ORDER", reference_id=other_order.id, alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
        severity=AlertSeverity.MEDIUM, title="Cross-project Fuel request", message="Review",
        status=AlertStatus.OPEN, notification_channel="in_app", created_at=datetime.now(timezone.utc),
    )
    db.add_all([missing, cross_project]); db.commit()
    not_found = client.get(f"/api/v1/alerts/{missing.id}/open", headers=c["headers"]["admin"])
    assert not_found.status_code == 404 and "Referenced Fuel request not found" in not_found.text
    denied = client.get(f"/api/v1/alerts/{cross_project.id}/open", headers=c["headers"]["admin"])
    assert denied.status_code == 403 and "different projects" in denied.text


# ── Phase 5: procurement DeliveryItem -> FuelDelivery hand-off ────────────────

def _create_fuel_delivery_item(client, c, litres=600.0, rate=25.0):
    """Real MR (FUEL) -> submit -> approve -> convert-to-po -> Delivery/DeliveryItem.
    Returns (delivery_item_id, po_id) using the exact same procurement
    endpoints as a MATERIAL request — no Fuel-specific procurement engine."""
    pid, hdr = c["project"]["id"], c["headers"]["owner"]
    r = client.post(f"/api/v1/projects/{pid}/material-requests/", json={
        "site_id": c["site"]["id"], "procurement_category": "FUEL",
        "items": [{"description": "Diesel", "requested_quantity": litres, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    mr_id = r.json()["data"]["id"]
    assert client.post(f"/api/v1/material-requests/{mr_id}/submit", headers=hdr).status_code == 200
    assert client.post(f"/api/v1/material-requests/{mr_id}/approve", json={}, headers=hdr).status_code == 200
    r = client.post(f"/api/v1/material-requests/{mr_id}/convert-to-po", json={
        "supplier_id": c["supplier"]["id"],
        "items": [{"description": "Diesel", "quantity": litres, "unit": "L", "rate": rate}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    po_id = r.json()["data"]["po_id"]
    r = client.post(f"/api/v1/projects/{pid}/deliveries/", json={
        "supplier_id": c["supplier"]["id"], "site_id": c["site"]["id"], "purchase_order_id": po_id,
        "supplier_delivery_note_number": f"DN-{uuid.uuid4().hex[:6]}",
        "items": [{"description": "Diesel", "quantity_received": litres, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    return r.json()["data"]["items"][0]["id"], po_id


def test_pending_procurement_confirmations_lists_and_clears_on_confirm(client, fuel_ctx):
    """The office Fuel Deliveries screen needs to know which real
    procurement DeliveryItems (FUEL MR -> PO -> Delivery) are still
    waiting to be confirmed into stock — and stop listing one the moment
    it's confirmed."""
    c = fuel_ctx
    pending_url = f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/pending-confirmation"
    assert client.get(pending_url, headers=c["headers"]["admin"]).json()["data"] == []

    delivery_item_id, po_id = _create_fuel_delivery_item(client, c, litres=300.0)
    r = client.get(pending_url, headers=c["headers"]["admin"])
    assert r.status_code == 200, r.text
    pending = r.json()["data"]
    assert len(pending) == 1
    assert pending[0]["delivery_item_id"] == delivery_item_id
    assert pending[0]["quantity_received"] == 300.0
    assert pending[0]["po_id"] == po_id

    hand_off = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/from-procurement",
        json={"delivery_item_id": delivery_item_id, "storage_location_id": c["storage_id"], "confirmed_litres": 298.0},
        headers=c["headers"]["admin"],
    )
    assert hand_off.status_code == 201, hand_off.text

    assert client.get(pending_url, headers=c["headers"]["admin"]).json()["data"] == []


def test_procurement_delivery_item_hand_off_confirms_stock_and_is_idempotent(client, db, fuel_ctx):
    c = fuel_ctx
    delivery_item_id, _po_id = _create_fuel_delivery_item(client, c, litres=600.0)
    body = {"delivery_item_id": delivery_item_id, "storage_location_id": c["storage_id"], "confirmed_litres": 595.0}
    url = f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/from-procurement"

    r = client.post(url, json=body, headers=c["headers"]["admin"])
    assert r.status_code == 201, r.text
    fd = r.json()["data"]
    assert fd["verification_status"] == "VERIFIED"
    assert fd["litres_delivered"] == 600.0
    assert fd["confirmed_litres"] == 595.0
    assert fd["supplier_variance_litres"] == -5.0
    assert fd["meter_variance_litres"] is None
    assert fd["procurement_delivery_item_id"] == delivery_item_id
    assert fd["order_id"] is None

    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 1000 + 595.0

    # Retry / double-click on the exact same delivery_item_id — idempotent, no double stock.
    r2 = client.post(url, json=body, headers=c["headers"]["admin"])
    assert r2.status_code == 201, r2.text
    assert r2.json()["data"]["id"] == fd["id"]
    dash2 = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash2["current_calculated_stock"] == 1000 + 595.0
    assert db.query(FuelDelivery).filter(
        FuelDelivery.procurement_delivery_item_id == uuid.UUID(delivery_item_id)
    ).count() == 1


def test_procurement_delivery_item_meter_variance_is_independent_of_supplier_variance(client, fuel_ctx):
    c = fuel_ctx
    delivery_item_id, _ = _create_fuel_delivery_item(client, c, litres=400.0)
    body = {
        "delivery_item_id": delivery_item_id, "storage_location_id": c["storage_id"],
        "confirmed_litres": 400.0, "opening_reading": 1000, "closing_reading": 1390,
    }
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/from-procurement",
                     json=body, headers=c["headers"]["admin"])
    assert r.status_code == 201, r.text
    fd = r.json()["data"]
    assert fd["calculated_received_litres"] == 390.0
    assert fd["supplier_variance_litres"] == 0.0
    assert fd["meter_variance_litres"] == 10.0


def test_partial_fuel_deliveries_accumulate_without_duplication(client, fuel_ctx):
    """Business-example partial-delivery pattern: 600L + 400L confirmed as
    595L + 400L = 995L total, each DeliveryItem confirmed exactly once."""
    c = fuel_ctx
    url = f"/api/v1/projects/{c['project']['id']}/fuel-management/deliveries/from-procurement"
    item_1, _ = _create_fuel_delivery_item(client, c, litres=600.0)
    r1 = client.post(url, json={"delivery_item_id": item_1, "storage_location_id": c["storage_id"],
                                 "confirmed_litres": 595.0}, headers=c["headers"]["admin"])
    assert r1.status_code == 201, r1.text

    item_2, _ = _create_fuel_delivery_item(client, c, litres=400.0)
    r2 = client.post(url, json={"delivery_item_id": item_2, "storage_location_id": c["storage_id"],
                                 "confirmed_litres": 400.0}, headers=c["headers"]["admin"])
    assert r2.status_code == 201, r2.text

    dash = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/dashboard", headers=c["headers"]["owner"]).json()["data"]
    assert dash["current_calculated_stock"] == 1000 + 595.0 + 400.0


def test_delivery_item_without_purchase_order_is_rejected(client, fuel_ctx):
    c = fuel_ctx
    pid, hdr = c["project"]["id"], c["headers"]["owner"]
    r = client.post(f"/api/v1/projects/{pid}/deliveries/", json={
        "supplier_id": c["supplier"]["id"], "site_id": c["site"]["id"],
        "items": [{"description": "Diesel", "quantity_received": 100, "unit": "L"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    delivery_item_id = r.json()["data"]["items"][0]["id"]

    body = {"delivery_item_id": delivery_item_id, "storage_location_id": c["storage_id"], "confirmed_litres": 100}
    r = client.post(f"/api/v1/projects/{pid}/fuel-management/deliveries/from-procurement", json=body, headers=c["headers"]["admin"])
    assert r.status_code == 422, r.text
    assert "purchase order" in r.text


def test_delivery_item_not_from_fuel_material_request_is_rejected(client, fuel_ctx):
    """A DeliveryItem sourced from an ordinary MATERIAL MR/PO must never be
    confirmable into Fuel stock — Fuel stays isolated from general
    materials procurement even though both share the same pipeline."""
    c = fuel_ctx
    pid, hdr = c["project"]["id"], c["headers"]["owner"]
    r = client.post(f"/api/v1/projects/{pid}/material-requests/", json={
        "site_id": c["site"]["id"],
        "items": [{"description": "Cement", "requested_quantity": 10.0, "unit": "bag"}],
    }, headers=hdr)
    mr_id = r.json()["data"]["id"]
    client.post(f"/api/v1/material-requests/{mr_id}/submit", headers=hdr)
    client.post(f"/api/v1/material-requests/{mr_id}/approve", json={}, headers=hdr)
    r = client.post(f"/api/v1/material-requests/{mr_id}/convert-to-po", json={
        "supplier_id": c["supplier"]["id"],
        "items": [{"description": "Cement", "quantity": 10, "unit": "bag", "rate": 100.0}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    po_id = r.json()["data"]["po_id"]
    r = client.post(f"/api/v1/projects/{pid}/deliveries/", json={
        "supplier_id": c["supplier"]["id"], "site_id": c["site"]["id"], "purchase_order_id": po_id,
        "items": [{"description": "Cement", "quantity_received": 10, "unit": "bag"}],
    }, headers=hdr)
    assert r.status_code == 201, r.text
    delivery_item_id = r.json()["data"]["items"][0]["id"]

    body = {"delivery_item_id": delivery_item_id, "storage_location_id": c["storage_id"], "confirmed_litres": 10}
    r = client.post(f"/api/v1/projects/{pid}/fuel-management/deliveries/from-procurement", json=body, headers=c["headers"]["admin"])
    assert r.status_code == 422, r.text
    assert "Fuel material request" in r.text


# ───────────────────────────────────────────────────────────────────────────────
# Phase: storage edit, removal, and price per litre (migration 0082)
#
# Before this, a storage location could only be created and listed: a wrong
# name meant a second tank beside the first, a test tank stayed forever, and
# nothing in the fuel UI could record what the fuel cost — so a tank stocked by
# an opening balance produced NULL-cost issues and under-reported project spend
# by exactly that fuel.
# ───────────────────────────────────────────────────────────────────────────────


def make_storage(client, c, *, name, headers="owner", **extra):
    """A second storage location in the same project, for tests that must not
    disturb fuel_ctx's main tank."""
    body = {"site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"], "name": name,
            "capacity_litres": 5000, "low_stock_threshold_litres": 100}
    body.update(extra)
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage",
                    json=body, headers=c["headers"][headers])
    assert r.status_code == 201, r.text
    return r.json()["data"]


def patch_storage(client, c, storage_id, body, headers="owner"):
    return client.patch(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage/{storage_id}",
                        json=body, headers=c["headers"][headers])


def retire_storage(client, c, storage_id, body=None, headers="owner"):
    return client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage/{storage_id}/retire",
                       json=body if body is not None else {}, headers=c["headers"][headers])


def list_storage(client, c, headers="owner", include_inactive=False):
    r = client.get(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage",
                   params={"include_inactive": include_inactive}, headers=c["headers"][headers])
    assert r.status_code == 200, r.text
    return r.json()["data"]


def adjust(client, c, storage_id, **body):
    body.setdefault("storage_location_id", storage_id)
    return client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/adjustments",
                       json=body, headers=c["headers"]["owner"])


# ── Edit ──────────────────────────────────────────────────────────────────────


def test_storage_edit_updates_in_place_and_audits_only_changed_fields(client, db, fuel_ctx):
    """A correction must change the tank that exists, not mint a second one,
    and the audit row must say what actually moved — a snapshot of every field
    makes a renamed tank indistinguishable from a re-capacitied one."""
    c = fuel_ctx
    before_count = len(list_storage(client, c))
    r = patch_storage(client, c, c["storage_id"], {"name": "  Main Diesel Tank A  ",
                                                   "low_stock_threshold_litres": 250})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Main Diesel Tank A"  # stripped, as on create
    assert r.json()["data"]["low_stock_threshold_litres"] == 250
    assert r.json()["data"]["capacity_litres"] == 5000  # untouched field survives
    assert len(list_storage(client, c)) == before_count

    event = assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_STORAGE",
                         entity_id=c["storage_id"], action="UPDATE")
    assert set(event.before_value) == {"name", "low_stock_threshold_litres"}
    assert event.before_value["name"] == "Main Diesel Tank"
    # The trail records what was saved, not what was typed.
    assert event.after_value["name"] == "Main Diesel Tank A"


def test_storage_edit_requires_fuel_admin(client, db, fuel_ctx):
    """SITE_STAFF can receive and issue fuel but must not be able to restate a
    tank's capacity, which is what every variance is measured against."""
    c = fuel_ctx
    r = patch_storage(client, c, c["storage_id"], {"capacity_litres": 99000}, headers="site")
    assert r.status_code == 403, r.text


def test_storage_edit_rejects_empty_body_and_foreign_project(client, db, fuel_ctx):
    c = fuel_ctx
    assert patch_storage(client, c, c["storage_id"], {}).status_code == 422
    r = client.patch(
        f"/api/v1/projects/{c['other_project']['id']}/fuel-management/storage/{c['storage_id']}",
        json={"name": "Stolen Tank"}, headers=c["headers"]["owner"])
    assert r.status_code == 422, r.text
    assert patch_storage(client, c, str(uuid.uuid4()), {"name": "Ghost Tank"}).status_code == 404


def test_storage_edit_refuses_duplicate_name(client, db, fuel_ctx):
    """Renaming onto an existing name must fail as a conflict, not blow up as a
    500. The site_id is pinned deliberately: production's constraint is
    UNIQUE NULLS NOT DISTINCT, but the test schema comes from create_all(), so
    a NULL-site version of this test would pass here and fail in production."""
    c = fuel_ctx
    second = make_storage(client, c, name="Reserve Diesel Tank")
    r = patch_storage(client, c, second["id"], {"name": "Main Diesel Tank"})
    assert r.status_code == 409, r.text
    # The failed flush must not have left the session poisoned.
    assert patch_storage(client, c, second["id"], {"name": "Reserve Diesel Tank B"}).status_code == 200


def test_storage_fuel_type_change_allowed_while_unused_and_locked_once_used(client, db, fuel_ctx):
    """Diesel litres do not become petrol because somebody changed a dropdown.
    The lock keys on movements, not on the balance: a tank drained back to zero
    still has diesel history behind it."""
    c = fuel_ctx
    unused = make_storage(client, c, name="Spare Tank")
    assert unused["has_movements"] is False
    r = patch_storage(client, c, unused["id"], {"fuel_type_id": c["petrol_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["fuel_type_id"] == c["petrol_id"]

    # fuel_ctx's main tank has an OPENING adjustment, so it is spoken for.
    used = next(s for s in list_storage(client, c) if s["id"] == c["storage_id"])
    assert used["has_movements"] is True
    r2 = patch_storage(client, c, c["storage_id"], {"fuel_type_id": c["petrol_id"]})
    assert r2.status_code == 409, r2.text
    assert "fuel type" in r2.json()["message"].lower()
    # Sending the unchanged value is not a change, so it is not refused.
    assert patch_storage(client, c, c["storage_id"], {"fuel_type_id": c["diesel_id"],
                                                     "notes": "unchanged type"}).status_code == 200


def test_storage_capacity_cannot_drop_below_current_balance(client, db, fuel_ctx):
    """A capacity under the balance would make every later feasibility check
    and variance read off a tank that cannot hold what it already holds."""
    c = fuel_ctx  # opening balance is 1000 L
    assert patch_storage(client, c, c["storage_id"], {"capacity_litres": 999}).status_code == 422
    assert patch_storage(client, c, c["storage_id"], {"capacity_litres": 1000}).status_code == 200
    assert patch_storage(client, c, c["storage_id"], {"capacity_litres": None}).status_code == 200


def test_storage_edit_refused_once_deactivated(client, db, fuel_ctx):
    c = fuel_ctx
    tank = make_storage(client, c, name="Decommissioned Tank", opening_stock_litres=50)
    assert retire_storage(client, c, tank["id"],
                          {"write_off_reason": "Tank scrapped"}).json()["data"]["action"] == "DEACTIVATED"
    r = patch_storage(client, c, tank["id"], {"name": "Back From The Dead"})
    assert r.status_code == 422, r.text
    assert "reactivate" in r.json()["message"].lower()


# ── Remove ────────────────────────────────────────────────────────────────────


def test_unused_storage_is_deleted_outright_and_the_audit_row_survives(client, db, fuel_ctx):
    """A tank created by mistake should not have to be lived with. The audit
    event has no FK to the row, so the trail outlives the delete."""
    c = fuel_ctx
    tank = make_storage(client, c, name="Typo Tank")
    r = retire_storage(client, c, tank["id"])
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"storage_id": tank["id"], "name": "Typo Tank",
                                "action": "DELETED", "blocked_by": [], "litres_written_off": 0.0}
    db.expire_all()
    assert db.query(FuelStorageLocation).filter_by(id=uuid.UUID(tank["id"])).first() is None
    assert_audit(db, actor_id=c["owner"]["id"], entity_type="FUEL_STORAGE",
                 entity_id=tank["id"], action="DELETE")


def test_storage_with_history_is_deactivated_and_hidden_not_deleted(client, db, fuel_ctx):
    """Its deliveries, issues and adjustments have to survive it, so the row
    stays and is hidden instead. include_inactive is the only way back."""
    c = fuel_ctx
    r = retire_storage(client, c, c["storage_id"], {"write_off_reason": "Tank taken out of service"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["action"] == "DEACTIVATED"
    assert "stock adjustments" in r.json()["data"]["blocked_by"]

    assert [s["id"] for s in list_storage(client, c)] == []
    hidden = list_storage(client, c, include_inactive=True)
    assert [s["id"] for s in hidden] == [c["storage_id"]]
    assert hidden[0]["is_active"] is False

    assert retire_storage(client, c, c["storage_id"]).status_code == 409


def test_removing_a_tank_holding_stock_demands_a_reason_then_writes_it_off(client, db, fuel_ctx):
    """The reported case: a tank with fuel in it. Both the storage list and the
    dashboard read active tanks only, so deactivating it would drop those
    litres out of every stock figure while the deliveries and issues behind
    them stayed on record. The write-off makes the disappearance an entry with
    a reason on it rather than a silence."""
    c = fuel_ctx
    tank = make_storage(client, c, name="Test", capacity_litres=1000, opening_stock_litres=800)
    before = next(s for s in list_storage(client, c) if s["id"] == tank["id"])
    assert before["calculated_balance_litres"] == 800

    refused = retire_storage(client, c, tank["id"])
    assert refused.status_code == 422, refused.text
    assert "800" in refused.json()["message"]
    db.expire_all()
    assert db.query(FuelStorageLocation).filter_by(id=uuid.UUID(tank["id"])).one().is_active is True

    r = retire_storage(client, c, tank["id"], {"write_off_reason": "Tank removed from site"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["action"] == "DEACTIVATED"
    assert r.json()["data"]["litres_written_off"] == 800.0

    db.expire_all()
    loss = db.query(FuelStockAdjustment).filter_by(
        storage_location_id=uuid.UUID(tank["id"]), adjustment_type="LOSS").one()
    assert float(loss.litres_delta) == -800.0
    assert loss.reason == "Tank removed from site"
    assert loss.cost_per_litre is None  # a price belongs on litres coming in
    assert next(s for s in list_storage(client, c, include_inactive=True)
                if s["id"] == tank["id"])["calculated_balance_litres"] == 0


def test_storage_removal_requires_fuel_admin(client, db, fuel_ctx):
    c = fuel_ctx
    tank = make_storage(client, c, name="Not Yours Tank")
    assert retire_storage(client, c, tank["id"], headers="site").status_code == 403
    db.expire_all()
    assert db.query(FuelStorageLocation).filter_by(id=uuid.UUID(tank["id"])).first() is not None


def test_deactivated_storage_can_be_reactivated(client, db, fuel_ctx):
    """Without this a mistaken removal is recoverable only by SQL, because the
    list hides the row."""
    c = fuel_ctx
    assert retire_storage(client, c, c["storage_id"],
                          {"write_off_reason": "Removed in error"}).status_code == 200
    r = client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/storage/{c['storage_id']}/reactivate",
        headers=c["headers"]["owner"])
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is True
    assert [s["id"] for s in list_storage(client, c)] == [c["storage_id"]]
    # Already active: a second reactivate is a conflict, not a silent no-op.
    assert client.post(
        f"/api/v1/projects/{c['project']['id']}/fuel-management/storage/{c['storage_id']}/reactivate",
        headers=c["headers"]["owner"]).status_code == 409


def test_deactivated_storage_refuses_further_fuel_movements(client, db, fuel_ctx):
    """Deactivation was cosmetic before this: nothing checked is_active on any
    write path, so a hidden tank could still accumulate stock that neither the
    storage list nor the dashboard could show."""
    c = fuel_ctx
    oid = order_to_ordered(client, c, 200)  # ordered while the tank is still live
    assert retire_storage(client, c, c["storage_id"],
                          {"write_off_reason": "Out of service"}).status_code == 200

    issue_body = {"storage_location_id": c["storage_id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-DEAD", "litres": 10}
    assert issue_with_evidence(client, c, issue_body).status_code == 422

    assert adjust(client, c, c["storage_id"], adjustment_type="GAIN", litres_delta=5,
                  reason="Should be refused").status_code == 422

    delivery_body = {"delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_litres": 200,
                     "confirmed_litres": 200, "delivery_note_number": "DN-DEAD",
                     "storage_location_id": c["storage_id"]}
    r = client.post(f"/api/v1/fuel-management/orders/{oid}/deliveries", json=delivery_body,
                    headers=c["headers"]["site"])
    assert r.status_code == 422, r.text

    assert client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/reconciliations",
                       json={"storage_location_id": c["storage_id"], "physical_balance_litres": 0,
                             "explanation": "Should be refused",
                             "reconciliation_date": datetime.now(timezone.utc).isoformat()},
                       headers=c["headers"]["owner"]).status_code == 422


# ── Price per litre ───────────────────────────────────────────────────────────


def test_costed_opening_stock_prices_the_fuel_it_put_in(client, db, fuel_ctx):
    """The gap this closes: a tank stocked by an opening balance had nowhere to
    hold a price, so every issue off it carried a NULL cost forever and project
    fuel spend under-reported by exactly that fuel."""
    c = fuel_ctx
    tank = make_storage(client, c, name="Priced Opening Tank",
                        opening_stock_litres=1000, opening_cost_per_litre=18)
    assert tank["average_cost_per_litre"] == 18.0
    db.expire_all()
    opening = db.query(FuelStockAdjustment).filter_by(
        storage_location_id=uuid.UUID(tank["id"]), adjustment_type="OPENING").one()
    assert float(opening.cost_per_litre) == 18.0

    issue_body = {"storage_location_id": tank["id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-OPEN", "litres": 100}
    r = issue_with_evidence(client, c, issue_body)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["unit_cost"] == 18.0
    assert r.json()["data"]["total_cost"] == 1800.0


def test_average_blends_costed_opening_stock_with_a_costed_gain(client, db, fuel_ctx):
    """(1000 x 18 + 500 x 24) / 1500 = 20.00. Worth asserting, because an
    average computed over litres on hand rather than litres that entered would
    give a different answer the moment anything is issued."""
    c = fuel_ctx
    tank = make_storage(client, c, name="Blended Tank",
                        opening_stock_litres=1000, opening_cost_per_litre=18)
    r = adjust(client, c, tank["id"], adjustment_type="GAIN", litres_delta=500,
               reason="Transferred in from the depot", cost_per_litre=24)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["cost_per_litre"] == 24.0

    fresh = next(s for s in list_storage(client, c) if s["id"] == tank["id"])
    assert fresh["average_cost_per_litre"] == 20.0

    issue_body = {"storage_location_id": tank["id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-BLEND", "litres": 100}
    r2 = issue_with_evidence(client, c, issue_body)
    assert r2.status_code == 201, r2.text
    assert r2.json()["data"]["unit_cost"] == 20.0
    # The average is over litres that entered, so issuing does not restate it.
    assert next(s for s in list_storage(client, c)
                if s["id"] == tank["id"])["average_cost_per_litre"] == 20.0


def test_uncosted_litres_are_excluded_from_the_average_not_valued_at_zero(client, db, fuel_ctx):
    """The single most important case. 1000 uncosted litres plus 500 @ 24 is
    24.00, not 8.00: litres with no recorded price are left out of BOTH the
    numerator and the denominator. Counting them at zero would value real fuel
    at nothing and drag every tank's average toward it."""
    c = fuel_ctx
    tank = make_storage(client, c, name="Partly Priced Tank", opening_stock_litres=1000)
    assert tank["average_cost_per_litre"] is None  # never a fabricated number

    assert adjust(client, c, tank["id"], adjustment_type="GAIN", litres_delta=500,
                  reason="Transferred in at a known price", cost_per_litre=24).status_code == 201
    fresh = next(s for s in list_storage(client, c) if s["id"] == tank["id"])
    assert fresh["average_cost_per_litre"] == 24.0
    assert fresh["average_cost_per_litre"] != 8.0

    issue_body = {"storage_location_id": tank["id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-PART", "litres": 100}
    r = issue_with_evidence(client, c, issue_body)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["unit_cost"] == 24.0


def test_issue_cost_is_the_average_as_at_the_issue_date(client, db, fuel_ctx):
    """unit_cost is frozen onto the issue row at issue time, so a price
    recorded today must not retro-value yesterday's fuel."""
    c = fuel_ctx
    tank = make_storage(client, c, name="As At Tank",
                        opening_stock_litres=1000, opening_cost_per_litre=18)
    issue_body = {"storage_location_id": tank["id"], "fuel_type_id": c["diesel_id"],
                  "destination_type": "GENERATOR", "equipment_reference": "GEN-ASAT", "litres": 100}
    first = issue_with_evidence(client, c, issue_body)
    assert first.status_code == 201, first.text
    assert first.json()["data"]["unit_cost"] == 18.0

    assert adjust(client, c, tank["id"], adjustment_type="GAIN", litres_delta=1000,
                  reason="Later load at a higher price", cost_per_litre=30).status_code == 201
    db.expire_all()
    frozen = db.query(FuelIssue).filter_by(id=uuid.UUID(first.json()["data"]["id"])).one()
    assert float(frozen.unit_cost) == 18.0

    second = issue_with_evidence(client, c, issue_body)
    assert second.status_code == 201, second.text
    assert second.json()["data"]["unit_cost"] == 24.0  # (18000 + 30000) / 2000


def test_price_is_refused_on_an_adjustment_that_takes_stock_away(client, db, fuel_ctx):
    """A cost per litre prices the litres coming in. On a LOSS it would be
    read into the weighted average as an inbound price it is not."""
    c = fuel_ctx
    r = adjust(client, c, c["storage_id"], adjustment_type="LOSS", litres_delta=-10,
               reason="Spillage", cost_per_litre=20)
    assert r.status_code == 422, r.text
    assert "adds stock" in r.json()["message"]
    assert adjust(client, c, c["storage_id"], adjustment_type="LOSS", litres_delta=-10,
                  reason="Spillage").status_code == 201


def test_non_positive_prices_are_rejected_by_the_schema(client, db, fuel_ctx):
    """Zero is not a price, it is a missing one — and NULL, not 0, is how a
    missing price is recorded, so the litres stay out of the average."""
    c = fuel_ctx
    for price in (0, -5):
        assert adjust(client, c, c["storage_id"], adjustment_type="GAIN", litres_delta=10,
                      reason="Bad price", cost_per_litre=price).status_code == 422
        body = {"site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"],
                "name": f"Bad Price Tank {price}", "opening_stock_litres": 100,
                "opening_cost_per_litre": price}
        assert client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage",
                           json=body, headers=c["headers"]["owner"]).status_code == 422


def test_opening_price_without_opening_litres_is_rejected(client, db, fuel_ctx):
    """A price with nothing to price would be accepted and then silently
    dropped, leaving the user believing a rate had been recorded."""
    c = fuel_ctx
    body = {"site_id": c["site"]["id"], "fuel_type_id": c["diesel_id"],
            "name": "Priceless Tank", "opening_cost_per_litre": 20}
    r = client.post(f"/api/v1/projects/{c['project']['id']}/fuel-management/storage",
                    json=body, headers=c["headers"]["owner"])
    assert r.status_code == 422, r.text


def test_storage_read_exposes_movement_and_cost_fields(client, db, fuel_ctx):
    """The screen decides what the Delete button will do, and whether the fuel
    type is still editable, from these two fields alone."""
    c = fuel_ctx
    unused = make_storage(client, c, name="Fields Tank")
    assert unused["has_movements"] is False
    assert unused["average_cost_per_litre"] is None
    assert unused["is_active"] is True

    rows = {s["id"]: s for s in list_storage(client, c)}
    assert rows[c["storage_id"]]["has_movements"] is True
    assert rows[unused["id"]]["has_movements"] is False
