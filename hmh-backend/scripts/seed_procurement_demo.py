"""
Seed realistic procurement demo data.

Run from hmh-backend/:
    python scripts/seed_procurement_demo.py

Creates (idempotent — safe to run multiple times):
  - 3 suppliers
  - 1 test project + site + 3 lots
  - Item category + Cement item
  - BOQ with 50 bags/lot cement allocation
  - MR-DEMO-001  Approved, 30 bags (within BOQ) → converted to PO
  - MR-DEMO-002  Submitted, 65 bags (15 OVER BOQ) → BOQ alert created
  - PO-DEMO-001  Sent to Cement Direct SA, email log stored
  - DN-DEMO-001  Partial delivery: 20/30 bags received, 10 back-ordered → alert
  - INV-DEMO-001 Invoice for full 30 bags despite only 20 received → mismatch alert
"""

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.alert import SystemAlert
from app.models.boq import BOQHeader, BOQSection
from app.models.delivery import Delivery, DeliveryItem
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    BoqStatus,
    DeliveryDestination,
    EmailStatus,
    InvoiceMatchStatus,
    ItemType,
    LotStatus,
    MRPriority,
    NotificationChannel,
    NotificationStatus,
    RecordStatus,
    VatMode,
)
from app.models.invoice import Invoice, InvoiceMatchingResult
from app.models.item import Item, ItemCategory
from app.models.lot import Lot
from app.models.material_request import MaterialRequest, MaterialRequestItem
from app.models.notification_queue import NotificationQueue
from app.models.project import Project
from app.models.purchase_order import PoEmailLog, PurchaseOrder, PurchaseOrderItem
from app.models.site import Site
from app.models.supplier import Supplier
from app.models.user import User


def _find_or_create(db, model, filter_kwargs, create_kwargs):
    obj = db.query(model).filter_by(**filter_kwargs).first()
    if obj:
        return obj, False
    obj = model(**{**filter_kwargs, **create_kwargs})
    db.add(obj)
    db.flush()
    return obj, True


def main() -> None:
    db = SessionLocal()
    try:
        now   = datetime.now(timezone.utc)
        today = date.today()

        print("Starting procurement demo seed...", flush=True)

        # ── Admin user ────────────────────────────────────────────────────────
        admin = db.query(User).filter(User.is_active == True).first()
        if not admin:
            print("ERROR: No active users found. Run seed_owner.py first.", flush=True)
            return
        admin_id = admin.id
        print(f"  Using admin: {admin.email}", flush=True)

        # ── Suppliers ─────────────────────────────────────────────────────────
        suppliers_spec = [
            dict(name="BuildMart Supplies",    email="orders@buildmart.co.za",
                 contact_person="John Smith",   phone="0115559001", payment_terms="30 days"),
            dict(name="Cement Direct SA",       email="sales@cementdirect.co.za",
                 contact_person="Maria Dlamini",phone="0115559002", payment_terms="14 days"),
            dict(name="QuickBuild Materials",   email="procurement@quickbuild.co.za",
                 contact_person="Sipho Nkosi",  phone="0115559003", payment_terms="COD"),
        ]
        suppliers = []
        for spec in suppliers_spec:
            s, created = _find_or_create(db, Supplier, {"name": spec["name"]},
                                         {**spec, "is_active": True})
            print(f"  {'Created' if created else 'Found'} supplier: {s.name}", flush=True)
            suppliers.append(s)

        # ── Project ───────────────────────────────────────────────────────────
        from app.models.enums import ProjectStatus  # noqa: avoid top-level circular risk
        project, created = _find_or_create(
            db, Project, {"code": "DEMO-PROC-001"},
            dict(name="Demo Construction Project", status=ProjectStatus.ACTIVE,
                 location="Johannesburg, Gauteng", client_name="HMH Demo Client",
                 start_date=today, created_by=admin_id),
        )
        print(f"  {'Created' if created else 'Found'} project: {project.name}", flush=True)

        # ── Site ──────────────────────────────────────────────────────────────
        site, created = _find_or_create(
            db, Site, {"project_id": project.id, "name": "Demo Site Alpha"},
            dict(site_type="construction_site", is_active=True),
        )
        print(f"  {'Created' if created else 'Found'} site: {site.name}", flush=True)

        # ── Lots ──────────────────────────────────────────────────────────────
        lots = []
        for i in range(1, 4):
            lot, created = _find_or_create(
                db, Lot, {"project_id": project.id, "lot_number": f"LOT-{i:03d}"},
                dict(site_id=site.id, unit_type="residential",
                     status=LotStatus.IN_PROGRESS),
            )
            print(f"  {'Created' if created else 'Found'} lot: {lot.lot_number}", flush=True)
            lots.append(lot)

        # ── Item category + Cement ─────────────────────────────────────────────
        cat, _ = _find_or_create(db, ItemCategory, {"name": "Building Materials"},
                                 {"is_active": True})

        cement, created = _find_or_create(
            db, Item, {"normalized_name": "cement 50kg bags"},
            dict(name="Cement 50kg bags", item_type=ItemType.MATERIAL,
                 category_id=cat.id, default_unit="bags", is_active=True),
        )
        print(f"  {'Created' if created else 'Found'} item: {cement.name}", flush=True)

        # ── BOQ ───────────────────────────────────────────────────────────────
        boq = (db.query(BOQHeader)
               .filter_by(project_id=project.id, template_name="Demo Procurement BOQ")
               .first())
        if not boq:
            boq = BOQHeader(
                project_id=project.id,
                version_name="Demo Procurement BOQ v1.0",
                template_name="Demo Procurement BOQ",
                source_type="manual",
                status=BoqStatus.ACTIVE,
                is_active_version=True,
                is_template=False,
                uploaded_by=admin_id,
                uploaded_at=now,
            )
            db.add(boq)
            db.flush()

            section = BOQSection(
                boq_header_id=boq.id,
                section_name="Foundation Materials",
                sequence_order=1,
            )
            db.add(section)
            db.flush()

            # 50 bags cement allocation per lot — use raw SQL to skip GENERATED column
            for lot in lots:
                db.execute(text("""
                    INSERT INTO boq_items
                        (id, boq_section_id, project_id, site_id, lot_id, item_id,
                         raw_description, unit, planned_quantity, planned_rate,
                         sort_order, is_active, created_at, updated_at)
                    VALUES
                        (:id, :sec, :proj, :site, :lot, :item,
                         :desc, :unit, :qty, :rate, :sort, true, now(), now())
                    ON CONFLICT DO NOTHING
                """), dict(
                    id=str(uuid.uuid4()), sec=str(section.id),
                    proj=str(project.id), site=str(site.id),
                    lot=str(lot.id),     item=str(cement.id),
                    desc="Cement 50kg bags (Foundation works)",
                    unit="bags", qty=50, rate=180.00, sort=1,
                ))
            print("  Created BOQ: 50 bags cement per lot", flush=True)
        else:
            print(f"  Found BOQ: {boq.version_name}", flush=True)

        # ── MR-DEMO-001 — Approved, within BOQ ────────────────────────────────
        mr1 = db.query(MaterialRequest).filter_by(request_number="MR-DEMO-001").first()
        if not mr1:
            mr1 = MaterialRequest(
                request_number="MR-DEMO-001",
                project_id=project.id, site_id=site.id, lot_id=lots[0].id,
                requested_by=admin_id,
                preferred_supplier_id=suppliers[1].id,
                status=RecordStatus.APPROVED,
                priority=MRPriority.HIGH,
                delivery_destination=DeliveryDestination.SITE_STORE,
                requested_date=now,
                needed_by_date=today + timedelta(days=7),
                notes="Cement required for LOT-001 foundation slab",
                over_boq=False,
                approved_by=admin_id,
                approved_at=now,
            )
            db.add(mr1)
            db.flush()
            db.add(MaterialRequestItem(
                material_request_id=mr1.id, item_id=cement.id,
                description="Cement 50kg bags",
                requested_quantity=Decimal("30"), approved_quantity=Decimal("30"),
                unit="bags",
            ))
            db.flush()
            print("  Created MR-DEMO-001: 30 bags cement, APPROVED (within BOQ)", flush=True)
        else:
            print("  Found MR-DEMO-001", flush=True)

        # ── MR-DEMO-002 — Submitted, OVER BOQ ─────────────────────────────────
        mr2 = db.query(MaterialRequest).filter_by(request_number="MR-DEMO-002").first()
        if not mr2:
            mr2 = MaterialRequest(
                request_number="MR-DEMO-002",
                project_id=project.id, site_id=site.id, lot_id=lots[1].id,
                requested_by=admin_id,
                preferred_supplier_id=suppliers[0].id,
                status=RecordStatus.SUBMITTED,
                priority=MRPriority.URGENT,
                delivery_destination=DeliveryDestination.SITE_STORE,
                requested_date=now,
                needed_by_date=today + timedelta(days=3),
                notes="Urgent — quantity exceeds BOQ due to approved rework",
                over_boq=True,
                over_boq_reason="Site engineer approved additional quantity for rework on LOT-002",
            )
            db.add(mr2)
            db.flush()
            db.add(MaterialRequestItem(
                material_request_id=mr2.id, item_id=cement.id,
                description="Cement 50kg bags",
                requested_quantity=Decimal("65"),
                unit="bags",
                over_boq_quantity=Decimal("15"),
            ))
            db.flush()

            # BOQ overrun alert
            db.add(SystemAlert(
                alert_type=AlertType.BOQ_ALLOCATION_EXCEEDED,
                severity=AlertSeverity.HIGH,
                title="BOQ Overrun — MR-DEMO-002",
                message=(
                    "Material request MR-DEMO-002 for LOT-002 requests 65 bags of cement "
                    "but BOQ allows 50. Over by 15 bags. Site engineer sign-off required."
                ),
                status=AlertStatus.OPEN,
                project_id=project.id, site_id=site.id, lot_id=lots[1].id,
                notification_channel="whatsapp",
                created_at=now, sent_at=now,
            ))
            db.flush()
            print("  Created MR-DEMO-002: 65 bags cement, SUBMITTED, 15 OVER BOQ + alert", flush=True)
        else:
            print("  Found MR-DEMO-002", flush=True)

        # ── PO-DEMO-001 — Sent to Cement Direct SA ────────────────────────────
        po = db.query(PurchaseOrder).filter_by(po_number="PO-DEMO-001").first()
        if not po:
            po = PurchaseOrder(
                po_number="PO-DEMO-001",
                project_id=project.id, site_id=site.id, lot_id=lots[0].id,
                supplier_id=suppliers[1].id,
                material_request_id=mr1.id,
                status=RecordStatus.SENT,
                po_date=now,
                expected_delivery_date=today + timedelta(days=5),
                subtotal_amount=Decimal("4695.65"),
                vat_amount=Decimal("704.35"),
                total_amount=Decimal("5400.00"),
                created_by=admin_id, approved_by=admin_id,
                sent_at=now,
                notes="Deliver to Demo Site Alpha store. Contact site manager on arrival.",
            )
            db.add(po)
            db.flush()

            po_item = PurchaseOrderItem(
                purchase_order_id=po.id, item_id=cement.id,
                description="Cement 50kg bags",
                quantity_ordered=Decimal("30"),
                quantity_received=Decimal("20"),
                unit="bags", rate=Decimal("180.00"),
                vat_mode=VatMode.INCLUSIVE, vat_rate=Decimal("15.00"),
                line_total=Decimal("5400.00"),
                created_at=now,
            )
            db.add(po_item)
            db.flush()

            db.add(PoEmailLog(
                purchase_order_id=po.id, sent_to_email=suppliers[1].email,
                sent_by=admin_id,
                email_subject="Purchase Order PO-DEMO-001 — HMH Group",
                email_body="<html><body>Demo mock email body.</body></html>",
                material_request_id=mr1.id,
                status=EmailStatus.sent, sent_at=now, created_at=now,
            ))

            mr1.status = RecordStatus.CONVERTED_TO_PO
            mr1.converted_to_po_at = now
            db.flush()
            print("  Created PO-DEMO-001: 30 bags @ R180, SENT to Cement Direct SA", flush=True)
        else:
            print("  Found PO-DEMO-001", flush=True)
            po_item = po.order_items[0] if po.order_items else None

        # ── DN-DEMO-001 — Partial delivery (20/30 bags) ────────────────────────
        delivery = db.query(Delivery).filter_by(delivery_number="DN-DEMO-001").first()
        if not delivery:
            delivery = Delivery(
                delivery_number="DN-DEMO-001",
                purchase_order_id=po.id,
                supplier_id=suppliers[1].id,
                project_id=project.id, site_id=site.id,
                received_by_user_id=admin_id,
                delivery_date=now,
                supplier_delivery_note_number="SDN-5002",
                delivery_status=RecordStatus.PARTIALLY_RECEIVED,
                comments=(
                    "20 of 30 bags delivered. Supplier confirmed back-order of 10 bags. "
                    "Expected delivery within 7 days."
                ),
            )
            db.add(delivery)
            db.flush()

            db.add(DeliveryItem(
                delivery_id=delivery.id, item_id=cement.id,
                description="Cement 50kg bags",
                quantity_expected=Decimal("30"),
                quantity_received=Decimal("20"),
                unit="bags",
                discrepancy_reason="Supplier short-shipped. Back-order raised for 10 bags.",
                created_at=now,
            ))
            db.flush()

            db.add(SystemAlert(
                alert_type=AlertType.DELIVERY_DISCREPANCY,
                severity=AlertSeverity.HIGH,
                title="Partial Delivery — PO-DEMO-001",
                message=(
                    "Delivery DN-DEMO-001 received 20 of 30 bags ordered on PO-DEMO-001. "
                    "10 bags outstanding. Back-order confirmed by Cement Direct SA."
                ),
                status=AlertStatus.OPEN,
                project_id=project.id, site_id=site.id,
                notification_channel="whatsapp",
                created_at=now, sent_at=now,
            ))
            db.flush()
            print("  Created DN-DEMO-001: 20/30 bags received, 10 back-ordered + alert", flush=True)
        else:
            print("  Found DN-DEMO-001", flush=True)

        # ── INV-DEMO-001 — Invoice mismatch (invoiced 30, received 20) ─────────
        invoice = db.query(Invoice).filter_by(invoice_number="INV-DEMO-001").first()
        if not invoice:
            invoice = Invoice(
                invoice_number="INV-DEMO-001",
                supplier_id=suppliers[1].id,
                project_id=project.id, site_id=site.id,
                purchase_order_id=po.id,
                invoice_date=today,
                due_date=today + timedelta(days=30),
                subtotal_amount=Decimal("4695.65"),
                vat_amount=Decimal("704.35"),
                total_amount=Decimal("5400.00"),
                status=RecordStatus.SUBMITTED,
                captured_by=admin_id, captured_at=now,
                notes="Supplier invoiced for full PO qty despite partial delivery",
            )
            db.add(invoice)
            db.flush()

            db.add(InvoiceMatchingResult(
                invoice_id=invoice.id,
                purchase_order_id=po.id,
                delivery_id=delivery.id,
                match_status=InvoiceMatchStatus.QUANTITY_MISMATCH,
                quantity_match=False,
                amount_match=False,
                supplier_match=True,
                notes=(
                    "Invoice R5,400 for 30 bags but only 20 bags received. "
                    "Dispute required — invoice should be R3,600 for 20 bags."
                ),
                checked_by=admin_id, checked_at=now,
                created_at=now,
            ))
            db.flush()

            db.add(SystemAlert(
                alert_type=AlertType.INVOICE_MISMATCH,
                severity=AlertSeverity.HIGH,
                title="Invoice Mismatch — INV-DEMO-001",
                message=(
                    "Invoice INV-DEMO-001 from Cement Direct SA does not match delivery. "
                    "Invoiced: 30 bags (R5,400). Received: 20 bags. Dispute required."
                ),
                status=AlertStatus.OPEN,
                project_id=project.id, site_id=site.id,
                notification_channel="whatsapp",
                created_at=now, sent_at=now,
            ))
            db.flush()
            print("  Created INV-DEMO-001: QUANTITY_MISMATCH (invoiced 30, received 20) + alert", flush=True)
        else:
            print("  Found INV-DEMO-001", flush=True)

        db.commit()

        print("\n=== Procurement Demo Seed Complete ===", flush=True)
        print(f"  Project  : {project.name}  [{project.code}]", flush=True)
        print(f"  Site     : {site.name}", flush=True)
        print(f"  Lots     : {', '.join(l.lot_number for l in lots)}", flush=True)
        print(f"  Suppliers: {', '.join(s.name for s in suppliers)}", flush=True)
        print("", flush=True)
        print("  MR-DEMO-001  30 bags cement APPROVED  → PO-DEMO-001 sent", flush=True)
        print("  MR-DEMO-002  65 bags cement SUBMITTED → 15 OVER BOQ, alert raised", flush=True)
        print("  PO-DEMO-001  Sent to Cement Direct SA (30 bags @ R180 incl.)", flush=True)
        print("  DN-DEMO-001  Partial: 20/30 bags received, 10 back-ordered, alert raised", flush=True)
        print("  INV-DEMO-001 QUANTITY_MISMATCH: invoiced 30 bags, received 20, alert raised", flush=True)
        print("", flush=True)
        print("Verify with:", flush=True)
        print("  GET /api/v1/purchase-orders/PO-DEMO-001/outstanding", flush=True)
        print("  GET /api/v1/invoices/INV-DEMO-001/proof", flush=True)

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
