"""
HMH Connected Demo Seed — Cornubia Residential Phase 1

Creates one complete, linked story across every module.
Every record chains to the next so the full procurement flow is testable.

Idempotent: runs safely on top of existing data; uses unique codes/names
to detect and skip existing records.

Run from hmh-backend directory:
    python scripts/seed_hmh_connected_demo.py

Demo flow to test after seeding:
  1. Login → Dashboard shows active project + alerts
  2. Projects → Cornubia → Lots → see Lot 1–6 each with BOQ
  3. Lot 1 → BOQ summary → 8/10 bags cement (normal)
  4. Lot 2 → BOQ summary → 20/10 bags → OVER BOQ alert shown
  5. Procurement → MR-001 (approved, converted to PO)
  6. Procurement → MR-002 (pending approval, over BOQ flagged)
  7. Procurement → PO-001 → email log (mock sent to buildzone@demo.com)
  8. Deliveries → DEL-001 (full delivery, signed)
  9. Deliveries → DEL-002 (partial, 150/200 bags)
  10. Payments/Reconciliation → INV-BZ-001 (MATCHED)
  11. Payments/Reconciliation → INV-BZ-002 (QUANTITY_MISMATCH)
  12. Alerts → BOQ overrun alert for Lot 2 + WhatsApp queue entry
  13. Vehicles → Hilux VEH-001 → tyre R2800 + fuel R1200
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import insert as _sa_insert
from sqlalchemy.orm import Session

from app.db.session import db_session
from app.core.security import hash_password
from app.models.enums import (
    AlertSeverity, AlertStatus, AlertType,
    BoqStatus, DeliveryDestination, EmailStatus, InvoiceMatchStatus,
    ItemType, JobCardStatus, JobCardWorkType,
    LotStatus, MRPriority, MovementType,
    NotificationChannel, NotificationStatus,
    PaymentStatus, PaymentType, ProjectStatus, RecordStatus,
    VehicleCostType, VehicleStatus, VehicleType,
)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


# ── Deterministic UUIDs ───────────────────────────────────────────────────────
# Using uuid5 with a fixed namespace so IDs are stable across runs.
_NS = uuid.UUID("00000000-0000-0000-0000-c0rnub1ade00")

def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(_NS, name)


# ── Idempotent helpers ────────────────────────────────────────────────────────

def _get_or_none(db: Session, model, **kwargs):
    return db.query(model).filter_by(**kwargs).first()


def _skip(label: str) -> None:
    print(f"  skip  {label}")


def _done(label: str) -> None:
    print(f"  ok    {label}")


# ═════════════════════════════════════════════════════════════════════════════
# SEED FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def seed_users(db: Session) -> dict:
    from app.models.user import User
    from app.models.enums import UserRole

    users = {}

    specs = [
        ("owner",       "Mohammed Moosa",    "admin@hmhgroup.com",          UserRole.OWNER,        "Mohammed@1",   False),
        ("office_user", "Aisha Kader",       "office@hmhgroup.com",         UserRole.OFFICE_USER,  "Office@1234",  False),
        ("site_manager","Yusuf Petersen",    "site@hmhgroup.com",           UserRole.SITE_MANAGER, "Site@1234",    False),
    ]

    for key, full_name, email, role, pwd, must_reset in specs:
        u = _get_or_none(db, User, email=email)
        if u:
            users[key] = u
            _skip(f"user {email}")
        else:
            u = User(
                full_name=full_name,
                email=email,
                phone="+27831234567" if key == "owner" else None,
                role=role,
                password_hash=hash_password(pwd),
                is_active=True,
                must_reset_password=must_reset,
                created_at=NOW, updated_at=NOW,
            )
            db.add(u)
            db.flush()
            users[key] = u
            _done(f"user {email}")

    return users


def seed_project(db: Session, owner_id: uuid.UUID):
    from app.models.project import Project

    p = _get_or_none(db, Project, code="CORN-PH1")
    if p:
        _skip("project Cornubia Residential Phase 1")
        return p

    p = Project(
        id=_id("project:corn-ph1"),
        name="Cornubia Residential Phase 1",
        code="CORN-PH1",
        description="76-unit residential development — Phase 1 demo",
        location="Cornubia, KwaZulu-Natal",
        client_name="HMH Group (Proprietary) Limited",
        start_date=date(2025, 3, 1),
        estimated_end_date=date(2025, 12, 31),
        budget=8_500_000.00,
        status=ProjectStatus.ACTIVE,
        created_by=owner_id,
        created_at=NOW, updated_at=NOW,
    )
    db.add(p)
    db.flush()
    _done(f"project {p.code}")
    return p


def seed_sites(db: Session, project_id: uuid.UUID):
    from app.models.site import Site

    sites = {}
    specs = [
        ("site_a", "Site A", "construction_site",  "Block A — Cornubia North"),
        ("site_b", "Site B", "main_warehouse",      "Block B — Cornubia South / Warehouse"),
    ]

    for key, name, site_type, desc in specs:
        s = _get_or_none(db, Site, project_id=project_id, name=name)
        if s:
            sites[key] = s
            _skip(f"site {name}")
        else:
            s = Site(
                id=_id(f"site:{name.lower().replace(' ', '_')}"),
                project_id=project_id,
                name=name,
                site_type=site_type,
                location_description=desc,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            db.add(s)
            db.flush()
            sites[key] = s
            _done(f"site {name}")

    return sites


def seed_lots(db: Session, project_id: uuid.UUID, sites: dict):
    from app.models.lot import Lot

    lots = {}
    specs = [
        ("lot1", "1", sites["site_a"].id, "2-Bed Unit",  LotStatus.IN_PROGRESS),
        ("lot2", "2", sites["site_a"].id, "2-Bed Unit",  LotStatus.IN_PROGRESS),
        ("lot3", "3", sites["site_a"].id, "3-Bed Unit",  LotStatus.IN_PROGRESS),
        ("lot4", "4", sites["site_b"].id, "Warehouse",   LotStatus.AVAILABLE),
        ("lot5", "5", sites["site_b"].id, "2-Bed Unit",  LotStatus.AVAILABLE),
        ("lot6", "6", sites["site_b"].id, "3-Bed Unit",  LotStatus.AVAILABLE),
    ]

    for key, lot_number, site_id, unit_type, status in specs:
        l = _get_or_none(db, Lot, project_id=project_id, lot_number=lot_number)
        if l:
            lots[key] = l
            _skip(f"lot {lot_number}")
        else:
            l = Lot(
                id=_id(f"lot:{lot_number}"),
                project_id=project_id,
                site_id=site_id,
                lot_number=lot_number,
                unit_type=unit_type,
                status=status,
                start_date=date(2025, 3, 15),
                expected_completion_date=date(2025, 9, 30),
                budgeted_cost=180_000.00,
                created_at=NOW, updated_at=NOW,
            )
            db.add(l)
            db.flush()
            lots[key] = l
            _done(f"lot {lot_number}")

    return lots


def seed_items(db: Session):
    from app.models.item import Item, ItemCategory

    # Category
    cat = _get_or_none(db, ItemCategory, name="Construction Materials")
    if not cat:
        cat = ItemCategory(
            id=_id("cat:construction"),
            name="Construction Materials",
            is_active=True,
            created_at=NOW, updated_at=NOW,
        )
        db.add(cat)
        db.flush()
        _done("category: Construction Materials")
    else:
        _skip("category: Construction Materials")

    items = {}
    specs = [
        ("cement",   "Cement 50kg Bag",   "bag",  ItemType.MATERIAL,  300.00),
        ("sand",     "Building Sand",      "m3",   ItemType.MATERIAL,  850.00),
        ("bricks",   "Stock Brick",        "each", ItemType.MATERIAL,  1.85),
        ("f_labour", "Foundation Labour",  "job",  ItemType.LABOUR,    2500.00),
        ("b_labour", "Brickwork Labour",   "job",  ItemType.LABOUR,    6500.00),
    ]

    for key, name, unit, itype, rate in specs:
        normalized = name.lower().replace(" ", "_")
        it = _get_or_none(db, Item, normalized_name=normalized)
        if it:
            items[key] = it
            _skip(f"item {name}")
        else:
            it = Item(
                id=_id(f"item:{normalized}"),
                name=name,
                normalized_name=normalized,
                category_id=cat.id,
                default_unit=unit,
                item_type=itype,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            db.add(it)
            db.flush()
            items[key] = it
            _done(f"item {name}")

    return items


def seed_supplier(db: Session):
    from app.models.supplier import Supplier

    s = _get_or_none(db, Supplier, name="BuildZone Cement Supplies")
    if s:
        _skip("supplier BuildZone")
        return s

    s = Supplier(
        id=_id("supplier:buildzone"),
        name="BuildZone Cement Supplies",
        code="BZ-001",
        email="buildzone@demo.com",
        phone="+27312345678",
        whatsapp_number="+27312345678",
        contact_person="Thabo Nkosi",
        vat_number="4510234567",
        address="12 Industrial Road, Pinetown, KZN",
        payment_terms="30 days",
        is_active=True,
        created_at=NOW, updated_at=NOW,
    )
    db.add(s)
    db.flush()
    _done("supplier BuildZone Cement Supplies")
    return s


def seed_sa_suppliers(db: Session) -> dict:
    """Seed real South African building suppliers for demo realism."""
    from app.models.supplier import Supplier

    suppliers = {}
    specs = [
        ("cashbuild", "Cashbuild Trade", "CB-001",
         "accounts@cashbuild.co.za", "+27119239300", "+27119239300",
         "Sipho Dlamini", "4390123456", "Cashbuild Cornubia, King Cetshwayo Hwy",
         "30 days"),
        ("buco", "BUCO Durban", "BUCO-DBN",
         "durban@buco.co.za", "+27317000100", "+27317000100",
         "Ravi Pillay", "4120987654", "BUCO Trade, 45 Bluff Rd, Durban, KZN",
         "30 days"),
        ("plumblink", "Plumblink Pinetown", "PL-001",
         "pinetown@plumblink.co.za", "+27315361234", None,
         "Fatima Essop", "4670345678", "Plumblink, 3 Bamboo Lane, Pinetown, KZN",
         "30 days"),
        ("voltex", "Voltex Durban North", "VX-DBN",
         "durbannorth@voltex.co.za", "+27315712000", None,
         "Brendan Naidoo", "4780654321", "Voltex, 78 Umhlanga Rocks Drive, Durban",
         "30 days"),
    ]

    for key, name, code, email, phone, wa, contact, vat, address, terms in specs:
        s = _get_or_none(db, Supplier, name=name)
        if s:
            suppliers[key] = s
            _skip(f"supplier {name}")
        else:
            s = Supplier(
                id=_id(f"supplier:{key}"),
                name=name,
                code=code,
                email=email,
                phone=phone,
                whatsapp_number=wa,
                contact_person=contact,
                vat_number=vat,
                address=address,
                payment_terms=terms,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            db.add(s)
            db.flush()
            suppliers[key] = s
            _done(f"supplier {name}")

    return suppliers


def seed_boq_template_and_lot_boqs(
    db: Session,
    project_id: uuid.UUID,
    lots: dict,
    items: dict,
    owner_id: uuid.UUID,
) -> dict:
    """
    Create the Standard Residential Unit BOQ template and clone it to each lot.
    Each lot gets its own independent BOQHeader + sections + items.
    Items are linked to catalog item_ids so allocation tracking works.
    """
    from app.models.boq import BOQHeader, BOQSection, BOQItem

    # ── Template header ───────────────────────────────────────────────────────
    tmpl = _get_or_none(db, BOQHeader, id=_id("boq:template:std_residential"))
    if not tmpl:
        tmpl = BOQHeader(
            id=_id("boq:template:std_residential"),
            project_id=project_id,
            version_name="Standard Residential Unit BOQ",
            source_type="system_template",
            status=BoqStatus.ACTIVE,
            is_active_version=True,
            is_template=True,
            template_name="Standard Residential Unit BOQ",
            uploaded_by=owner_id,
            uploaded_at=NOW,
            notes="Demo template — 5 line items with catalog links",
        )
        db.add(tmpl)
        db.flush()
        _done("BOQ template: Standard Residential Unit BOQ")
    else:
        _skip("BOQ template: Standard Residential Unit BOQ")

    # Template section
    tmpl_sec = _get_or_none(db, BOQSection, boq_header_id=tmpl.id, section_name="Materials & Labour")
    if not tmpl_sec:
        tmpl_sec = BOQSection(
            id=_id("boq:template:section1"),
            boq_header_id=tmpl.id,
            section_name="Materials & Labour",
            sequence_order=1,
            created_at=NOW, updated_at=NOW,
        )
        db.add(tmpl_sec)
        db.flush()

    # Template items — define the 5 demo BOQ lines
    # (description, item_key, qty, rate, type, unit)
    tmpl_lines = [
        ("Cement 50kg",       "cement",   10.0,   300.00, "MATERIAL", "bag"),
        ("Building Sand",     "sand",      2.0,   850.00, "MATERIAL", "m3"),
        ("Stock Bricks",      "bricks",  3000.0,   1.85, "MATERIAL", "each"),
        ("Foundation Labour", "f_labour",  1.0,  2500.00, "LABOUR",   "job"),
        ("Brickwork Labour",  "b_labour",  1.0,  6500.00, "LABOUR",   "job"),
    ]

    # ── Clone to each lot ─────────────────────────────────────────────────────
    lot_headers = {}

    for lot_key, lot in lots.items():
        header_id = _id(f"boq:lot{lot.lot_number}:header")

        # Check if already exists
        existing_header = _get_or_none(db, BOQHeader, id=header_id)
        if existing_header:
            lot_headers[lot_key] = existing_header
            _skip(f"BOQ header for Lot {lot.lot_number}")
            continue

        # Create lot-specific header
        header = BOQHeader(
            id=header_id,
            project_id=project_id,
            version_name=f"Standard Residential Unit BOQ — Lot {lot.lot_number}",
            source_type="template_clone",
            status=BoqStatus.ACTIVE,
            is_active_version=True,
            is_template=False,
            template_name=None,
            uploaded_by=owner_id,
            uploaded_at=NOW,
            notes=f"Cloned from Standard Residential template for Lot {lot.lot_number}",
        )
        db.add(header)
        db.flush()

        # Create section
        section = BOQSection(
            id=_id(f"boq:lot{lot.lot_number}:section1"),
            boq_header_id=header.id,
            section_name="Materials & Labour",
            sequence_order=1,
            created_at=NOW, updated_at=NOW,
        )
        db.add(section)
        db.flush()

        # Mark the lot as having a template applied
        lot.boq_template_id = tmpl.id

        # Clone items using Core INSERT to avoid GENERATED ALWAYS planned_total
        for sort_idx, (desc, item_key, qty, rate, itype, unit) in enumerate(tmpl_lines, 1):
            item_id = items[item_key].id
            db.execute(
                _sa_insert(BOQItem).values(
                    id=_id(f"boq:lot{lot.lot_number}:{item_key}"),
                    boq_section_id=section.id,
                    project_id=project_id,
                    site_id=lot.site_id,
                    lot_id=lot.id,
                    item_id=item_id,
                    raw_description=desc,
                    item_type=itype,
                    unit=unit,
                    planned_quantity=qty,
                    planned_rate=rate,
                    sort_order=sort_idx,
                    is_active=True,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        lot_headers[lot_key] = header
        _done(f"BOQ Lot {lot.lot_number} ({len(tmpl_lines)} items)")

    return lot_headers


def seed_scenario_1_normal_flow(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    lots: dict,
    items: dict,
    supplier,
    owner_id: uuid.UUID,
    site_manager_id: uuid.UUID,
    office_user_id: uuid.UUID,
):
    """
    Scenario 1 — Lot 1 normal flow.
    MR-001 → Approved → PO-001 → Email sent → DEL-001 received →
    Stock issued to Lot 1 → INV-BZ-001 MATCHED.
    """
    from app.models.material_request import MaterialRequest, MaterialRequestItem
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, PoEmailLog
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.stock import StockLedger

    site_a = sites["site_a"]
    lot1 = lots["lot1"]
    cement = items["cement"]

    # MR-001
    mr = _get_or_none(db, MaterialRequest, request_number="MR-001")
    if not mr:
        mr = MaterialRequest(
            id=_id("mr:001"),
            request_number="MR-001",
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot1.id,
            requested_by=site_manager_id,
            preferred_supplier_id=supplier.id,
            priority=MRPriority.NORMAL,
            delivery_destination=DeliveryDestination.LOT,
            status=RecordStatus.CONVERTED_TO_PO,
            over_boq=False,
            approved_by=office_user_id,
            approved_at=NOW - timedelta(days=3),
            requested_date=NOW - timedelta(days=5),
            needed_by_date=TODAY - timedelta(days=2),
            notes="Regular cement request for Lot 1 foundation slab.",
            converted_to_po_at=NOW - timedelta(days=3),
            created_at=NOW - timedelta(days=5), updated_at=NOW - timedelta(days=3),
        )
        db.add(mr)
        db.flush()
        db.add(MaterialRequestItem(
            id=_id("mr:001:item1"),
            material_request_id=mr.id,
            item_id=cement.id,
            description="Cement 50kg",
            requested_quantity=8.0,
            approved_quantity=8.0,
            unit="bag",
            over_boq_quantity=None,
        ))
        db.flush()
        _done("MR-001 (cement, Lot 1, approved)")
    else:
        _skip("MR-001")

    # PO-001
    po = _get_or_none(db, PurchaseOrder, po_number="PO-001")
    if not po:
        po = PurchaseOrder(
            id=_id("po:001"),
            po_number="PO-001",
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot1.id,
            supplier_id=supplier.id,
            material_request_id=mr.id,
            delivery_destination=DeliveryDestination.LOT,
            status=RecordStatus.RECEIVED,
            po_date=NOW - timedelta(days=3),
            expected_delivery_date=TODAY - timedelta(days=1),
            subtotal_amount=2400.00,
            vat_amount=313.04,
            total_amount=2400.00,
            created_by=office_user_id,
            approved_by=office_user_id,
            sent_at=NOW - timedelta(days=3),
            notes="8 bags cement for Lot 1 foundation.",
            created_at=NOW - timedelta(days=3), updated_at=NOW - timedelta(days=1),
        )
        db.add(po)
        db.flush()

        db.add(PurchaseOrderItem(
            id=_id("po:001:item1"),
            purchase_order_id=po.id,
            item_id=cement.id,
            lot_id=lot1.id,
            description="Cement 50kg Bag",
            quantity_ordered=8.0,
            quantity_received=8.0,
            unit="bag",
            rate=300.00,
            line_total=2400.00,
            created_at=NOW - timedelta(days=3),
        ))
        db.flush()
        _done("PO-001 (received)")

        # Email log
        db.add(PoEmailLog(
            id=_id("email:po001:1"),
            purchase_order_id=po.id,
            material_request_id=mr.id,
            sent_to_email="buildzone@demo.com",
            email_subject="Purchase Order PO-001 — HMH Group",
            email_body="<p>Please supply 8 × Cement 50kg bags for Lot 1.</p>",
            status=EmailStatus.sent,
            sent_at=NOW - timedelta(days=3),
            created_at=NOW - timedelta(days=3),
        ))
        _done("Email log: PO-001 → buildzone@demo.com (mock sent)")
    else:
        po = _get_or_none(db, PurchaseOrder, po_number="PO-001")
        _skip("PO-001")

    # DEL-001
    delivery = _get_or_none(db, Delivery, delivery_number="DEL-001")
    if not delivery:
        from app.models.delivery import Delivery, DeliveryItem
        delivery = Delivery(
            id=_id("delivery:001"),
            delivery_number="DEL-001",
            purchase_order_id=po.id,
            supplier_id=supplier.id,
            project_id=project_id,
            site_id=site_a.id,
            received_by_user_id=site_manager_id,
            delivery_date=NOW - timedelta(days=1),
            supplier_delivery_note_number="BZ-DN-20250415",
            delivery_status=RecordStatus.RECEIVED,
            receiver_name="Yusuf Petersen",
            delivery_note_image_url="/uploads/demo/delivery_note_del001.jpg",
            signature_image_url="/uploads/demo/signature_del001.jpg",
            comments="All 8 bags received in good condition.",
            created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(days=1),
        )
        db.add(delivery)
        db.flush()

        poi = _get_or_none(db, PurchaseOrderItem, purchase_order_id=po.id)
        db.add(DeliveryItem(
            id=_id("delivery:001:item1"),
            delivery_id=delivery.id,
            purchase_order_item_id=poi.id if poi else None,
            item_id=cement.id,
            description="Cement 50kg Bag",
            quantity_expected=8.0,
            quantity_received=8.0,
            unit="bag",
            created_at=NOW - timedelta(days=1),
        ))
        db.flush()
        _done("DEL-001 (full delivery, signed)")
    else:
        _skip("DEL-001")

    # Stock ledger — 8 bags issued to Lot 1
    existing_sl = db.query(StockLedger).filter(
        StockLedger.reference_id == _id("delivery:001"),
        StockLedger.item_id == cement.id,
    ).first()
    if not existing_sl:
        db.add(StockLedger(
            id=_id("stock:del001:cement"),
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot1.id,
            item_id=cement.id,
            movement_type=MovementType.DELIVERY_RECEIVED,
            reference_type="delivery",
            reference_id=_id("delivery:001"),
            quantity_in=8.0,
            quantity_out=0.0,
            unit="bag",
            unit_cost=300.00,
            movement_date=NOW - timedelta(days=1),
            entered_by=site_manager_id,
            notes="DEL-001 — 8 bags to Lot 1",
            created_at=NOW - timedelta(days=1),
        ))
        _done("Stock ledger: 8 bags cement → Lot 1")
    else:
        _skip("Stock ledger DEL-001")

    # INV-BZ-001
    invoice = _get_or_none(db, Invoice, invoice_number="INV-BZ-001")
    if not invoice:
        invoice = Invoice(
            id=_id("invoice:bz001"),
            invoice_number="INV-BZ-001",
            supplier_id=supplier.id,
            project_id=project_id,
            site_id=site_a.id,
            purchase_order_id=po.id,
            invoice_date=TODAY - timedelta(days=1),
            due_date=TODAY + timedelta(days=29),
            subtotal_amount=2400.00,
            vat_amount=313.04,
            total_amount=2400.00,
            status=RecordStatus.MATCHED,
            captured_by=office_user_id,
            captured_at=NOW - timedelta(hours=12),
            notes="Invoice matches PO-001 and DEL-001.",
            created_at=NOW - timedelta(hours=12), updated_at=NOW - timedelta(hours=12),
        )
        db.add(invoice)
        db.flush()

        db.add(InvoiceMatchingResult(
            id=_id("match:bz001"),
            invoice_id=invoice.id,
            purchase_order_id=po.id,
            delivery_id=_id("delivery:001"),
            match_status=InvoiceMatchStatus.MATCHED,
            quantity_match=True,
            amount_match=True,
            supplier_match=True,
            notes="Full match — 8 bags × R300 = R2,400. Signed by Yusuf Petersen.",
            checked_by=office_user_id,
            checked_at=NOW - timedelta(hours=6),
            created_at=NOW - timedelta(hours=12),
        ))
        _done("INV-BZ-001 → MATCHED")
    else:
        _skip("INV-BZ-001")

    db.flush()


def seed_scenario_2_over_boq(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    lots: dict,
    items: dict,
    supplier,
    owner_id: uuid.UUID,
    site_manager_id: uuid.UUID,
):
    """
    Scenario 2 — Lot 2 over BOQ.
    MR-002 requests 20 bags; BOQ allocation is only 10.
    System creates PENDING_APPROVAL MR + HIGH alert + mock WhatsApp message.
    """
    from app.models.material_request import MaterialRequest, MaterialRequestItem
    from app.models.alert import SystemAlert
    from app.models.notification_queue import NotificationQueue
    from app.models.alert_recipient import AlertRecipient

    site_a = sites["site_a"]
    lot2 = lots["lot2"]
    cement = items["cement"]

    # MR-002
    mr = _get_or_none(db, MaterialRequest, request_number="MR-002")
    if not mr:
        mr = MaterialRequest(
            id=_id("mr:002"),
            request_number="MR-002",
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot2.id,
            requested_by=site_manager_id,
            preferred_supplier_id=supplier.id,
            priority=MRPriority.HIGH,
            delivery_destination=DeliveryDestination.LOT,
            status=RecordStatus.PENDING_APPROVAL,
            over_boq=True,
            over_boq_reason="Extra foundation correction required. Soil instability detected.",
            requested_date=NOW - timedelta(hours=4),
            needed_by_date=TODAY + timedelta(days=1),
            notes="URGENT: Lot 2 slab correction — need extra cement.",
            created_at=NOW - timedelta(hours=4), updated_at=NOW - timedelta(hours=4),
        )
        db.add(mr)
        db.flush()
        db.add(MaterialRequestItem(
            id=_id("mr:002:item1"),
            material_request_id=mr.id,
            item_id=cement.id,
            description="Cement 50kg",
            requested_quantity=20.0,
            unit="bag",
            over_boq_quantity=10.0,
        ))
        db.flush()
        _done("MR-002 (20 bags, 10 OVER BOQ, pending approval)")
    else:
        _skip("MR-002")

    # ALERT-001
    alert = db.query(SystemAlert).filter(
        SystemAlert.id == _id("alert:001:overboq:lot2")
    ).first()
    if not alert:
        alert = SystemAlert(
            id=_id("alert:001:overboq:lot2"),
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot2.id,
            reference_type="material_request",
            reference_id=_id("mr:002"),
            alert_type=AlertType.BOQ_ALLOCATION_EXCEEDED,
            severity=AlertSeverity.HIGH,
            title="Lot 2: Cement over BOQ allocation (20 bags vs 10 allowed)",
            message=(
                "Material request MR-002 exceeds BOQ allocation for Lot 2.\n"
                "Planned: 10 bags\n"
                "Requested: 20 bags\n"
                "Over by: 10 bags\n"
                "Reason: Extra foundation correction required. Soil instability detected.\n"
                "Action: Owner approval required before PO can be raised."
            ),
            status=AlertStatus.OPEN,
            notification_channel="whatsapp",
            created_at=NOW - timedelta(hours=4),
        )
        db.add(alert)
        db.flush()
        _done("ALERT-001: BOQ overrun Lot 2 (OPEN)")
    else:
        _skip("ALERT-001")

    # WhatsApp recipient (owner)
    recipient = db.query(AlertRecipient).filter(
        AlertRecipient.phone_number == "+27831234567"
    ).first()
    if not recipient:
        recipient = AlertRecipient(
            id=_id("recipient:owner"),
            name="Mohammed Moosa",
            phone_number="+27831234567",
            label="Owner",
            receives_critical_alerts=True,
            receives_daily_summary=True,
            receives_material_alerts=True,
            receives_delivery_alerts=True,
            receives_invoice_alerts=True,
            receives_vehicle_alerts=True,
            is_active=True,
            created_at=NOW, updated_at=NOW,
        )
        db.add(recipient)
        db.flush()
        _done("WhatsApp recipient: Mohammed Moosa (+27831234567)")
    else:
        _skip("WhatsApp recipient: owner")

    # Mock WhatsApp notification
    notif = db.query(NotificationQueue).filter(
        NotificationQueue.id == _id("notif:alert001:whatsapp")
    ).first()
    if not notif:
        db.add(NotificationQueue(
            id=_id("notif:alert001:whatsapp"),
            alert_id=alert.id,
            recipient_id=recipient.id,
            channel=NotificationChannel.WHATSAPP,
            phone_number="+27831234567",
            message_body=(
                "⚠️ *HIGH* — Lot 2: Cement over BOQ allocation (20 bags vs 10 allowed)\n\n"
                "Material request MR-002 exceeds BOQ allocation for Lot 2.\n"
                "Planned: 10 bags\n"
                "Requested: 20 bags\n"
                "Over by: 10 bags\n"
                "Reason: Extra foundation correction required. Soil instability detected.\n\n"
                "Time: " + NOW.strftime("%d %b %Y %H:%M") + "\n\nReply ACK to acknowledge."
            ),
            status=NotificationStatus.MOCK_SENT,
            attempt_count=1,
            last_attempt_at=NOW - timedelta(hours=4),
            next_attempt_at=None,
            requires_acknowledgement=True,
            created_at=NOW - timedelta(hours=4),
        ))
        _done("WhatsApp MOCK_SENT: overrun alert → owner")
    else:
        _skip("WhatsApp notification: alert001")

    db.flush()


def seed_scenario_3_warehouse_partial(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    items: dict,
    supplier,
    owner_id: uuid.UUID,
    office_user_id: uuid.UUID,
):
    """
    Scenario 3 — Bulk warehouse partial delivery.
    PO-002 orders 200 bags; DEL-002 receives only 150.
    INV-BZ-002 is for 200 bags → QUANTITY_MISMATCH.
    """
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, PoEmailLog
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.stock import StockLedger
    from app.models.alert import SystemAlert

    site_b = sites["site_b"]
    cement = items["cement"]

    # PO-002
    po = _get_or_none(db, PurchaseOrder, po_number="PO-002")
    if not po:
        po = PurchaseOrder(
            id=_id("po:002"),
            po_number="PO-002",
            project_id=project_id,
            site_id=site_b.id,
            supplier_id=supplier.id,
            delivery_destination=DeliveryDestination.MAIN_WAREHOUSE,
            status=RecordStatus.PARTIALLY_RECEIVED,
            po_date=NOW - timedelta(days=7),
            expected_delivery_date=TODAY - timedelta(days=3),
            subtotal_amount=60_000.00,
            vat_amount=7_826.09,
            total_amount=60_000.00,
            created_by=office_user_id,
            approved_by=office_user_id,
            sent_at=NOW - timedelta(days=7),
            notes="Bulk cement order for main warehouse. 200 bags.",
            created_at=NOW - timedelta(days=7), updated_at=NOW - timedelta(days=3),
        )
        db.add(po)
        db.flush()

        poi = PurchaseOrderItem(
            id=_id("po:002:item1"),
            purchase_order_id=po.id,
            item_id=cement.id,
            description="Cement 50kg Bag — Bulk",
            quantity_ordered=200.0,
            quantity_received=150.0,
            unit="bag",
            rate=300.00,
            line_total=60_000.00,
            created_at=NOW - timedelta(days=7),
        )
        db.add(poi)
        db.flush()
        _done("PO-002 (200 bags bulk order, partially received)")

        db.add(PoEmailLog(
            id=_id("email:po002:1"),
            purchase_order_id=po.id,
            sent_to_email="buildzone@demo.com",
            email_subject="Purchase Order PO-002 — HMH Group",
            email_body="<p>Please supply 200 × Cement 50kg bags to Main Warehouse.</p>",
            status=EmailStatus.sent,
            sent_at=NOW - timedelta(days=7),
            created_at=NOW - timedelta(days=7),
        ))
        _done("Email log: PO-002 → buildzone@demo.com")
    else:
        po = _get_or_none(db, PurchaseOrder, po_number="PO-002")
        poi = db.query(PurchaseOrderItem).filter_by(purchase_order_id=po.id).first()
        _skip("PO-002")

    # DEL-002 — 150 of 200 bags
    delivery = _get_or_none(db, Delivery, delivery_number="DEL-002")
    if not delivery:
        delivery = Delivery(
            id=_id("delivery:002"),
            delivery_number="DEL-002",
            purchase_order_id=po.id,
            supplier_id=supplier.id,
            project_id=project_id,
            site_id=site_b.id,
            received_by_user_id=office_user_id,
            delivery_date=NOW - timedelta(days=3),
            supplier_delivery_note_number="BZ-DN-20250412",
            delivery_status=RecordStatus.PARTIALLY_RECEIVED,
            receiver_name="Aisha Kader",
            delivery_note_image_url="/uploads/demo/delivery_note_del002.jpg",
            signature_image_url="/uploads/demo/signature_del002.jpg",
            comments="Only 150 bags delivered. Supplier says remaining 50 bags out of stock. ETA 5 days.",
            created_at=NOW - timedelta(days=3), updated_at=NOW - timedelta(days=3),
        )
        db.add(delivery)
        db.flush()

        db.add(DeliveryItem(
            id=_id("delivery:002:item1"),
            delivery_id=delivery.id,
            purchase_order_item_id=poi.id if poi else None,
            item_id=cement.id,
            description="Cement 50kg Bag",
            quantity_expected=200.0,
            quantity_received=150.0,
            unit="bag",
            discrepancy_reason="50 bags out of stock at supplier. Back-order confirmed.",
            created_at=NOW - timedelta(days=3),
        ))
        db.flush()
        _done("DEL-002 (150/200 bags — PARTIAL, 50 outstanding)")
    else:
        _skip("DEL-002")

    # Stock ledger — 150 bags to main warehouse
    existing_sl = db.query(StockLedger).filter(
        StockLedger.reference_id == _id("delivery:002"),
        StockLedger.item_id == cement.id,
    ).first()
    if not existing_sl:
        db.add(StockLedger(
            id=_id("stock:del002:cement"),
            project_id=project_id,
            site_id=site_b.id,
            lot_id=None,
            item_id=cement.id,
            movement_type=MovementType.DELIVERY_RECEIVED,
            reference_type="delivery",
            reference_id=_id("delivery:002"),
            quantity_in=150.0,
            quantity_out=0.0,
            unit="bag",
            unit_cost=300.00,
            movement_date=NOW - timedelta(days=3),
            entered_by=office_user_id,
            notes="DEL-002 partial — 150 of 200 bags to main warehouse (Site B)",
            created_at=NOW - timedelta(days=3),
        ))
        _done("Stock ledger: 150 bags cement → Main Warehouse (Site B)")
    else:
        _skip("Stock ledger DEL-002")

    # INV-BZ-002 — for 200 bags (quantity mismatch with delivery)
    invoice = _get_or_none(db, Invoice, invoice_number="INV-BZ-002")
    if not invoice:
        invoice = Invoice(
            id=_id("invoice:bz002"),
            invoice_number="INV-BZ-002",
            supplier_id=supplier.id,
            project_id=project_id,
            site_id=site_b.id,
            purchase_order_id=po.id,
            invoice_date=TODAY - timedelta(days=3),
            due_date=TODAY + timedelta(days=27),
            subtotal_amount=60_000.00,
            vat_amount=7_826.09,
            total_amount=60_000.00,
            status=RecordStatus.SUBMITTED,
            captured_by=office_user_id,
            captured_at=NOW - timedelta(days=2),
            notes="Invoice is for 200 bags but only 150 were delivered. DO NOT PAY until delivery is complete.",
            created_at=NOW - timedelta(days=2), updated_at=NOW - timedelta(days=2),
        )
        db.add(invoice)
        db.flush()

        db.add(InvoiceMatchingResult(
            id=_id("match:bz002"),
            invoice_id=invoice.id,
            purchase_order_id=po.id,
            delivery_id=_id("delivery:002"),
            match_status=InvoiceMatchStatus.QUANTITY_MISMATCH,
            quantity_match=False,
            amount_match=False,
            supplier_match=True,
            notes="Invoice claims 200 bags (R60,000) but delivery DEL-002 confirms only 150 received. Outstanding: 50 bags = R15,000 over-invoiced.",
            checked_by=office_user_id,
            checked_at=NOW - timedelta(hours=18),
            created_at=NOW - timedelta(days=2),
        ))
        _done("INV-BZ-002 → QUANTITY_MISMATCH (invoice 200, received 150)")
    else:
        _skip("INV-BZ-002")

    # Partial delivery alert
    alert_id = _id("alert:002:partial:del002")
    if not db.query(SystemAlert).filter_by(id=alert_id).first():
        db.add(SystemAlert(
            id=alert_id,
            project_id=project_id,
            site_id=site_b.id,
            reference_type="delivery",
            reference_id=_id("delivery:002"),
            alert_type=AlertType.DELIVERY_DISCREPANCY,
            severity=AlertSeverity.MEDIUM,
            title="Partial delivery: DEL-002 (150 of 200 bags received)",
            message="PO-002 ordered 200 bags cement. DEL-002 delivered only 150. Outstanding: 50 bags. Supplier back-order noted.",
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=NOW - timedelta(days=3),
        ))
        _done("ALERT-002: Partial delivery DEL-002")
    else:
        _skip("ALERT-002")

    db.flush()


def seed_scenario_4_labour_pending(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    lots: dict,
    items: dict,
    owner_id: uuid.UUID,
    site_manager_id: uuid.UUID,
    office_user_id: uuid.UUID,
):
    """
    Scenario 4 — Labour approval pending for Lot 3.
    JC-LAB-001 is a JobCard at SITE_APPROVED stage, awaiting office approval.
    Labour is handled via JobCards, NOT MaterialRequest.
    Payment shows NOT PAYABLE until office+owner approval complete.
    """
    from app.models.job_card import JobCard
    from app.models.enums import JobCardStatus, JobCardWorkType

    site_a = sites["site_a"]
    lot3 = lots["lot3"]

    jc = _get_or_none(db, JobCard, job_card_number="JC-LAB-001")
    if not jc:
        jc = JobCard(
            id=_id("jc:lab001"),
            job_card_number="JC-LAB-001",
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot3.id,
            work_description="Brickwork Labour — Lot 3. 3 bricklayers × 5 days. Wall plate height achieved.",
            work_type=JobCardWorkType.DAILY_LABOUR,
            worker_name="Thulani Mthembu and team",
            quantity=5.0,
            unit="days",
            rate=1300.00,
            total_amount=6500.00,
            owner_approval_required=False,
            status=JobCardStatus.SITE_APPROVED,
            submitted_by=site_manager_id,
            submitted_at=NOW - timedelta(days=2),
            site_approved_by=site_manager_id,
            site_approved_at=NOW - timedelta(days=1),
            work_date=TODAY - timedelta(days=3),
            notes="Site manager confirmed wall plate height achieved. Awaiting office approval before payment.",
            created_by=site_manager_id,
            created_at=NOW - timedelta(days=2), updated_at=NOW - timedelta(days=1),
        )
        db.add(jc)
        db.flush()
        _done("JC-LAB-001 (brickwork labour R6,500 — Lot 3 — SITE_APPROVED, awaiting office)")
    else:
        _skip("JC-LAB-001")


def seed_job_cards(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    lots: dict,
    owner_id: uuid.UUID,
    site_manager_id: uuid.UUID,
    office_user_id: uuid.UUID,
):
    """
    Seed 3 job cards showing the full approval chain at different stages.
    JC-001: SITE_APPROVED  (Lot 1 brickwork — waiting office)
    JC-002: OFFICE_APPROVED (Lot 2 foundation labour — waiting payment approval)
    JC-003: DRAFT          (Lot 3 plastering — just created by site manager)
    """
    from app.models.enums import JobCardStatus, JobCardWorkType
    from app.models.job_card import JobCard

    site_a = sites["site_a"]
    cards = [
        (
            "JC-001",
            lot_id := lots["lot1"].id,
            "Brickwork — Lot 1. 3 bricklayers × 5 days completed.",
            JobCardWorkType.DAILY_LABOUR, "Thulani Mthembu", 5.0, "days", 600.00,
            JobCardStatus.SITE_APPROVED,
            site_manager_id, NOW - timedelta(days=4),
            site_manager_id, NOW - timedelta(days=3),
            None, None, None, None,
            "Wall plate height achieved. Ready for roof.",
        ),
        (
            "JC-002",
            lots["lot2"].id,
            "Foundation Labour — Lot 2. Concrete team correction pour.",
            JobCardWorkType.CONTRACT, None, 1.0, "job", 4500.00,
            JobCardStatus.OFFICE_APPROVED,
            site_manager_id, NOW - timedelta(days=6),
            site_manager_id, NOW - timedelta(days=5),
            office_user_id, NOW - timedelta(days=4),
            None, None,
            "Extra pour required after soil correction.",
        ),
        (
            "JC-003",
            lots["lot3"].id,
            "Plastering — Lot 3 internal walls. 2 plasterers × 3 days.",
            JobCardWorkType.DAILY_LABOUR, "Vusi Khoza", 6.0, "days", 550.00,
            JobCardStatus.DRAFT,
            None, None, None, None, None, None, None, None,
            "Ready to submit once plastering is complete.",
        ),
    ]

    for (
        number, lot_id, desc, wtype, worker, qty, unit, rate,
        status, sub_by, sub_at, site_by, site_at,
        off_by, off_at, own_by, own_at, notes
    ) in cards:
        existing = _get_or_none(db, JobCard, job_card_number=number)
        if existing:
            _skip(f"Job card {number}")
            continue

        total = round(qty * rate, 2)
        jc = JobCard(
            id=_id(f"jc:{number.lower()}"),
            job_card_number=number,
            project_id=project_id,
            site_id=site_a.id,
            lot_id=lot_id,
            work_description=desc,
            work_type=wtype,
            worker_name=worker,
            quantity=qty,
            unit=unit,
            rate=rate,
            total_amount=total,
            owner_approval_required=total >= 10_000,
            status=status,
            submitted_by=sub_by,
            submitted_at=sub_at,
            site_approved_by=site_by,
            site_approved_at=site_at,
            office_approved_by=off_by,
            office_approved_at=off_at,
            owner_approved_by=own_by,
            owner_approved_at=own_at,
            work_date=TODAY - timedelta(days=4),
            notes=notes,
            created_by=site_manager_id,
            created_at=NOW - timedelta(days=6), updated_at=NOW - timedelta(days=2),
        )
        db.add(jc)
        db.flush()
        _done(f"Job card {number}: {status.value} — R{total:,.0f}")

    db.flush()


def seed_scenario_5_vehicle(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    owner_id: uuid.UUID,
    office_user_id: uuid.UUID,
):
    """
    Scenario 6 — Toyota Hilux VEH-001 assigned to Site A.
    Tyre replacement R2800, Fuel R1200.
    Both visible on owner dashboard under Site A costs.
    """
    from app.models.vehicle import Vehicle, VehicleCost

    site_a = sites["site_a"]

    vehicle = _get_or_none(db, Vehicle, registration="CA 123-456")
    if not vehicle:
        vehicle = Vehicle(
            id=_id("vehicle:001"),
            registration="CA 123-456",
            name="Toyota Hilux — VEH-001",
            vehicle_type=VehicleType.BAKKIE,
            status=VehicleStatus.ACTIVE,
            assigned_project_id=project_id,
            assigned_site_id=site_a.id,
            last_service_date=date(2025, 1, 15),
            next_service_date=date(2025, 7, 15),
            notes="Main site bakkie for Site A material runs.",
            created_by=owner_id,
            created_at=NOW - timedelta(days=30), updated_at=NOW,
        )
        db.add(vehicle)
        db.flush()
        _done("VEH-001: Toyota Hilux CA 123-456 → Site A")

        db.add(VehicleCost(
            id=_id("vcost:001:tyre"),
            vehicle_id=vehicle.id,
            cost_type=VehicleCostType.TYRE,
            amount=2800.00,
            description="Front left tyre burst on site. Replaced with new 265/65 R17.",
            project_id=project_id,
            site_id=site_a.id,
            cost_date=TODAY - timedelta(days=2),
            recorded_by=office_user_id,
            notes="Burst tyre during material delivery run.",
            created_at=NOW - timedelta(days=2),
        ))
        _done("VehicleCost: Tyre replacement R2,800 → Site A")

        db.add(VehicleCost(
            id=_id("vcost:001:fuel"),
            vehicle_id=vehicle.id,
            cost_type=VehicleCostType.FUEL,
            amount=1200.00,
            description="Diesel — weekly fuel fill-up. 80L × R15/L.",
            project_id=project_id,
            site_id=site_a.id,
            cost_date=TODAY - timedelta(days=1),
            recorded_by=office_user_id,
            notes="Regular weekly diesel.",
            created_at=NOW - timedelta(days=1),
        ))
        _done("VehicleCost: Fuel R1,200 → Site A")
        db.flush()
    else:
        _skip("VEH-001 Toyota Hilux")


def seed_initial_warehouse_stock(
    db: Session,
    project_id: uuid.UUID,
    sites: dict,
    items: dict,
    office_user_id: uuid.UUID,
):
    """
    Add opening stock balances so the stock page shows real numbers.
    Site B acts as the main warehouse.
    """
    from app.models.stock import StockLedger

    site_b = sites["site_b"]

    stock_items = [
        (items["cement"], 150.0, "bag",    300.00, "Opening: 150 bags in warehouse (from DEL-002)"),
        (items["sand"],     12.0, "m3",    850.00, "Opening: 12m3 building sand in warehouse"),
        (items["bricks"], 8000.0, "each",    1.85, "Opening: 8000 bricks in warehouse"),
    ]

    for item, qty, unit, cost, notes in stock_items:
        ref_id = _id(f"stock:opening:{item.normalized_name}")
        existing = db.query(StockLedger).filter_by(id=ref_id).first()
        if existing:
            _skip(f"Opening stock: {item.name}")
            continue

        # Skip cement — already added by DEL-002 above
        if item.normalized_name == "cement_50kg_bag":
            continue

        db.add(StockLedger(
            id=ref_id,
            project_id=project_id,
            site_id=site_b.id,
            lot_id=None,
            item_id=item.id,
            movement_type=MovementType.OPENING_BALANCE,
            reference_type="opening_balance",
            reference_id=None,
            quantity_in=qty,
            quantity_out=0.0,
            unit=unit,
            unit_cost=cost,
            movement_date=NOW - timedelta(days=30),
            entered_by=office_user_id,
            notes=notes,
            created_at=NOW - timedelta(days=30),
        ))
        _done(f"Opening stock: {qty} {unit} {item.name}")

    db.flush()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def seed() -> None:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  HMH Connected Demo Seed — Cornubia Residential Phase 1")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    with db_session() as db:

        print("[ Users ]")
        users = seed_users(db)
        db.flush()

        print("\n[ Project ]")
        project = seed_project(db, users["owner"].id)
        db.flush()

        print("\n[ Sites ]")
        sites = seed_sites(db, project.id)
        db.flush()

        print("\n[ Lots ]")
        lots = seed_lots(db, project.id, sites)
        db.flush()

        print("\n[ Item Catalogue ]")
        items = seed_items(db)
        db.flush()

        print("\n[ Suppliers ]")
        supplier = seed_supplier(db)
        sa_suppliers = seed_sa_suppliers(db)
        db.flush()

        print("\n[ BOQ Template + Per-Lot BOQ Clone ]")
        lot_headers = seed_boq_template_and_lot_boqs(
            db, project.id, lots, items, users["owner"].id
        )
        db.flush()

        print("\n[ Opening Warehouse Stock ]")
        seed_initial_warehouse_stock(
            db, project.id, sites, items, users["office_user"].id
        )

        print("\n[ Scenario 1 — Lot 1 Normal Flow (MR-001 → PO-001 → DEL-001 → INV-BZ-001) ]")
        seed_scenario_1_normal_flow(
            db, project.id, sites, lots, items, supplier,
            users["owner"].id, users["site_manager"].id, users["office_user"].id,
        )

        print("\n[ Scenario 2 — Lot 2 Over BOQ (MR-002 → ALERT-001 → WhatsApp MOCK) ]")
        seed_scenario_2_over_boq(
            db, project.id, sites, lots, items, supplier,
            users["owner"].id, users["site_manager"].id,
        )

        print("\n[ Scenario 3 — Warehouse Partial Delivery (PO-002 → DEL-002 → INV-BZ-002 MISMATCH) ]")
        seed_scenario_3_warehouse_partial(
            db, project.id, sites, items, supplier,
            users["owner"].id, users["office_user"].id,
        )

        print("\n[ Scenario 4 — Labour Approval Pending (LAB-001, Lot 3) ]")
        seed_scenario_4_labour_pending(
            db, project.id, sites, lots, items,
            users["owner"].id, users["site_manager"].id, users["office_user"].id,
        )

        print("\n[ Job Cards — Labour Approval Chain ]")
        seed_job_cards(
            db, project.id, sites, lots,
            users["owner"].id, users["site_manager"].id, users["office_user"].id,
        )

        print("\n[ Scenario 5 — Vehicle Costs (VEH-001 Toyota Hilux, Site A) ]")
        seed_scenario_5_vehicle(
            db, project.id, sites, users["owner"].id, users["office_user"].id,
        )

        db.commit()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SEED COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("  LOGIN DETAILS")
    print("  ─────────────────────────────────────────────────────────")
    print("  Owner:        admin@hmhgroup.com   / Mohammed@1")
    print("  Office:       office@hmhgroup.com  / Office@1234")
    print("  Site:         site@hmhgroup.com    / Site@1234")
    print()
    print("  DEMO FLOW TO TEST")
    print("  ─────────────────────────────────────────────────────────")
    print("  Dashboard  → active project, open alerts, pending approvals")
    print("  Projects   → Cornubia → Lots tab (6 lots, each with BOQ icon)")
    print("  Lot 1      → BOQ: 8/10 bags used — on track")
    print("  Lot 2      → BOQ: 20/10 bags — OVER BOQ (red bar)")
    print("  Lot 3      → BOQ allocated, JC-LAB-001 site approved → awaiting office")
    print("  Procurement → MR-001 (CONVERTED_TO_PO) + MR-002 (PENDING_APPROVAL)")
    print("  Procurement → PO-001 (RECEIVED) → email log (mock sent)")
    print("  Procurement → PO-002 (PARTIALLY_RECEIVED) → 50 bags outstanding")
    print("  Deliveries  → DEL-001 (8/8 full, signed)")
    print("  Deliveries  → DEL-002 (150/200 partial, discrepancy noted)")
    print("  Reconciliation → INV-BZ-001 (MATCHED ✓)")
    print("  Reconciliation → INV-BZ-002 (QUANTITY_MISMATCH ✗)")
    print("  Alerts     → BOQ overrun Lot 2 + partial delivery alert")
    print("  Alerts → WhatsApp Queue → 1 MOCK_SENT to owner")
    print("  Vehicles   → CA 123-456 Hilux → tyre R2,800 + fuel R1,200")
    print("  Suppliers  → Cashbuild, BUCO Durban, Plumblink, Voltex also seeded")
    print("  Labour     → /labour → JC-001 site approved, JC-002 awaiting office")
    print("  WhatsApp   → /whatsapp-queue → MOCK_SENT messages visible")
    print("  Owner Dash → /owner → today spend, alerts, approvals, vehicles")
    print()


if __name__ == "__main__":
    seed()
