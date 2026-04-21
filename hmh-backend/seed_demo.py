"""
HMH Construction System — Demo Seed Script
============================================
Populates the database with realistic, relational demo data covering every module.

Run:
    cd hmh-backend
    python seed_demo.py

Idempotent: re-running skips seeding if Project HMH-CORN-01 already exists.
"""

import sys
import uuid
from datetime import datetime, date, timezone, timedelta

from sqlalchemy import insert as _sa_insert
from app.db.session import db_session
from app.models.enums import (
    UserRole, ProjectStatus, RecordStatus, StageStatus, LotStatus,
    ItemType, MovementType, AlertStatus, AlertSeverity, AlertType,
    PaymentType, PaymentStatus, BoqStatus, AttachmentEntity, AttachmentType,
    VatMode, FuelType, FuelUsageType, InvoiceMatchStatus,
)
from app.models.user import User
from app.models.project import Project
from app.models.site import Site
from app.models.lot import Lot
from app.models.stage import StageMaster, ProjectStageStatus
from app.models.item import ItemCategory, Item
from app.models.supplier import Supplier
from app.models.boq import BOQHeader, BOQSection, BOQItem
from app.models.material_request import MaterialRequest, MaterialRequestItem
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.delivery import Delivery, DeliveryItem
from app.models.stock import StockLedger, UsageLog
from app.models.fuel import FuelLog
from app.models.invoice import Invoice, InvoiceMatchingResult
from app.models.payment import Payment
from app.models.alert import SystemAlert
from app.models.attachment import Attachment
from app.core.security import hash_password

# ─────────────────────────────────────────────────────────────────
# FIXED UUIDs (for idempotency — never change these)
# ─────────────────────────────────────────────────────────────────

# Users
U_ADMIN        = uuid.UUID("00000000-0000-0000-0000-000000000001")
U_MANAGER      = uuid.UUID("00000000-0000-0000-0000-000000000002")
U_PROCUREMENT  = uuid.UUID("00000000-0000-0000-0000-000000000003")
U_SITE_MGR     = uuid.UUID("00000000-0000-0000-0000-000000000004")
U_SITE_STAFF   = uuid.UUID("00000000-0000-0000-0000-000000000005")

# Projects
P_CORN  = uuid.UUID("10000000-0000-0000-0000-000000000001")
P_RIV   = uuid.UUID("10000000-0000-0000-0000-000000000002")

# Sites (under CORN)
S_CORN_A = uuid.UUID("20000000-0000-0000-0000-000000000001")
S_CORN_B = uuid.UUID("20000000-0000-0000-0000-000000000002")

# Lots
LOTS_A = [uuid.UUID(f"30000000-0000-0000-0000-{i:012d}") for i in range(1, 6)]
LOTS_B = [uuid.UUID(f"30000000-0000-0000-0000-{i:012d}") for i in range(6, 11)]

# Stage master
STAGES = {
    "Foundations":     uuid.UUID("40000000-0000-0000-0000-000000000001"),
    "Slab":            uuid.UUID("40000000-0000-0000-0000-000000000002"),
    "Brickwork":       uuid.UUID("40000000-0000-0000-0000-000000000003"),
    "Roof":            uuid.UUID("40000000-0000-0000-0000-000000000004"),
    "Plumbing Rough":  uuid.UUID("40000000-0000-0000-0000-000000000005"),
    "Electrical Rough":uuid.UUID("40000000-0000-0000-0000-000000000006"),
    "Plastering":      uuid.UUID("40000000-0000-0000-0000-000000000007"),
    "Finishing":       uuid.UUID("40000000-0000-0000-0000-000000000008"),
}

# Item categories
CAT_CONCRETE  = uuid.UUID("50000000-0000-0000-0000-000000000001")
CAT_MASONRY   = uuid.UUID("50000000-0000-0000-0000-000000000002")
CAT_ROOFING   = uuid.UUID("50000000-0000-0000-0000-000000000003")
CAT_PLUMBING  = uuid.UUID("50000000-0000-0000-0000-000000000004")
CAT_ELECTRICAL= uuid.UUID("50000000-0000-0000-0000-000000000005")
CAT_FINISHING = uuid.UUID("50000000-0000-0000-0000-000000000006")
CAT_FUEL      = uuid.UUID("50000000-0000-0000-0000-000000000007")

# Items
I_CEMENT    = uuid.UUID("60000000-0000-0000-0000-000000000001")
I_SAND      = uuid.UUID("60000000-0000-0000-0000-000000000002")
I_STONE     = uuid.UUID("60000000-0000-0000-0000-000000000003")
I_STOCK_BRK = uuid.UUID("60000000-0000-0000-0000-000000000004")
I_MAXI_BRK  = uuid.UUID("60000000-0000-0000-0000-000000000005")
I_ROOF_TIMB = uuid.UUID("60000000-0000-0000-0000-000000000006")
I_CORR_SHEETM = uuid.UUID("60000000-0000-0000-0000-000000000007")
I_PVC_PIPE  = uuid.UUID("60000000-0000-0000-0000-000000000008")
I_ELEC_CABLE= uuid.UUID("60000000-0000-0000-0000-000000000009")
I_PLASTER_SAND = uuid.UUID("60000000-0000-0000-0000-000000000010")
I_PAINT     = uuid.UUID("60000000-0000-0000-0000-000000000011")
I_DIESEL    = uuid.UUID("60000000-0000-0000-0000-000000000012")

# Suppliers
SUP_AFRI    = uuid.UUID("70000000-0000-0000-0000-000000000001")
SUP_DBN     = uuid.UUID("70000000-0000-0000-0000-000000000002")
SUP_COASTAL = uuid.UUID("70000000-0000-0000-0000-000000000003")
SUP_KZN     = uuid.UUID("70000000-0000-0000-0000-000000000004")
SUP_PRO     = uuid.UUID("70000000-0000-0000-0000-000000000005")
SUP_MEGA    = uuid.UUID("70000000-0000-0000-0000-000000000006")

# BOQ
BOQ_HEAD    = uuid.UUID("80000000-0000-0000-0000-000000000001")
BOQ_SEC = {
    "Foundations":  uuid.UUID("81000000-0000-0000-0000-000000000001"),
    "Slab":         uuid.UUID("81000000-0000-0000-0000-000000000002"),
    "Brickwork":    uuid.UUID("81000000-0000-0000-0000-000000000003"),
    "Roof":         uuid.UUID("81000000-0000-0000-0000-000000000004"),
    "Plumbing":     uuid.UUID("81000000-0000-0000-0000-000000000005"),
    "Electrical":   uuid.UUID("81000000-0000-0000-0000-000000000006"),
    "Finishing":    uuid.UUID("81000000-0000-0000-0000-000000000007"),
}

# Material Requests
MR1 = uuid.UUID("90000000-0000-0000-0000-000000000001")
MR2 = uuid.UUID("90000000-0000-0000-0000-000000000002")
MR3 = uuid.UUID("90000000-0000-0000-0000-000000000003")
MR4 = uuid.UUID("90000000-0000-0000-0000-000000000004")

# Purchase Orders
PO1 = uuid.UUID("A0000000-0000-0000-0000-000000000001")
PO2 = uuid.UUID("A0000000-0000-0000-0000-000000000002")
PO3 = uuid.UUID("A0000000-0000-0000-0000-000000000003")

# Deliveries
DEL1 = uuid.UUID("B0000000-0000-0000-0000-000000000001")
DEL2 = uuid.UUID("B0000000-0000-0000-0000-000000000002")
DEL3 = uuid.UUID("B0000000-0000-0000-0000-000000000003")

# Invoices
INV1 = uuid.UUID("C0000000-0000-0000-0000-000000000001")
INV2 = uuid.UUID("C0000000-0000-0000-0000-000000000002")
INV3 = uuid.UUID("C0000000-0000-0000-0000-000000000003")

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def now() -> datetime:
    return datetime.now(tz=timezone.utc)

def dt(days_ago: int = 0, hour: int = 8) -> datetime:
    return datetime.now(tz=timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0) \
           - timedelta(days=days_ago)

def d(days_ago: int = 0) -> date:
    return (date.today() - timedelta(days=days_ago))

def log(msg: str):
    print(f"  + {msg}")


# ─────────────────────────────────────────────────────────────────
# SEED SECTIONS
# ─────────────────────────────────────────────────────────────────

def seed_users(db):
    """
    Create demo users. If an email already exists (from a previous partial run
    or manual setup), keep the existing user and return their real UUID so all
    FK references in subsequent sections stay consistent.

    Returns a dict: email -> UUID (actual UUID in the DB).
    """
    print("\n[1] Users")
    existing_by_email = {u.email: u for u in db.query(User).all()}

    users_data = [
        dict(id=U_ADMIN, full_name="Admin User", email="admin@hmhgroup.com",
             role=UserRole.OWNER, must_reset_password=False),
        dict(id=U_MANAGER, full_name="Office Manager", email="office.manager@hmhgroup.com",
             role=UserRole.OFFICE_ADMIN, must_reset_password=False),
        dict(id=U_PROCUREMENT, full_name="Procurement Officer", email="procurement@hmhgroup.com",
             role=UserRole.OFFICE_USER, must_reset_password=False),
        dict(id=U_SITE_MGR, full_name="Site Manager A", email="sitemanager.a@hmhgroup.com",
             role=UserRole.SITE_MANAGER, must_reset_password=False),
        dict(id=U_SITE_STAFF, full_name="Site Staff B", email="sitestaff.b@hmhgroup.com",
             role=UserRole.SITE_STAFF, must_reset_password=False),
    ]

    ph = hash_password("Demo@1234")
    uuid_map = {}
    for d_u in users_data:
        email = d_u["email"]
        if email in existing_by_email:
            # Email already in DB — use the real UUID (do not try to change it)
            real_uuid = existing_by_email[email].id
            uuid_map[email] = real_uuid
            log(f"Skipped (exists, using UUID {real_uuid}): {email}")
        else:
            db.add(User(password_hash=ph, is_active=True, **d_u))
            uuid_map[email] = d_u["id"]
            log(f"Created user: {email}")

    return uuid_map


def seed_projects(db):
    print("\n[2] Projects")
    existing = {str(p.id) for p in db.query(Project).all()}

    projects = [
        Project(id=P_CORN, name="Cornubia Residential Phase 1", code="HMH-CORN-01",
                description="76-unit residential development in Cornubia, Phase 1",
                location="Cornubia, KwaZulu-Natal", client_name="Cornubia Developments (Pty) Ltd",
                start_date=d(120), estimated_end_date=d(-365), go_live_date=d(-300),
                status=ProjectStatus.ACTIVE, created_by=U_ADMIN),
        Project(id=P_RIV, name="Riverstone Mixed Use Block A", code="HMH-RIV-02",
                description="Mixed-use commercial + residential block in Riverhorse",
                location="Riverhorse Valley, Durban", client_name="Riverstone Properties Ltd",
                start_date=d(-30), estimated_end_date=d(-545),
                status=ProjectStatus.PLANNED, created_by=U_ADMIN),
    ]
    for p in projects:
        if str(p.id) not in existing:
            db.add(p)
            log(f"Created project: {p.code}")
        else:
            log(f"Skipped (exists): {p.code}")


def seed_sites(db):
    print("\n[3] Sites")
    existing = {str(s.id) for s in db.query(Site).all()}

    sites = [
        Site(id=S_CORN_A, project_id=P_CORN, name="Site A — Block 1-5",
             code="CORN-A", site_type="construction_site",
             location_description="Northern cluster, Lots 1–38", is_active=True),
        Site(id=S_CORN_B, project_id=P_CORN, name="Site B — Block 6-10",
             code="CORN-B", site_type="construction_site",
             location_description="Southern cluster, Lots 39–76", is_active=True),
    ]
    for s in sites:
        if str(s.id) not in existing:
            db.add(s)
            log(f"Created site: {s.code}")
        else:
            log(f"Skipped (exists): {s.code}")


def seed_lots(db):
    print("\n[4] Lots")
    existing = {str(l.id) for l in db.query(Lot).all()}

    lot_statuses_a = [LotStatus.COMPLETED, LotStatus.IN_PROGRESS, LotStatus.IN_PROGRESS,
                      LotStatus.AVAILABLE, LotStatus.AVAILABLE]
    lot_statuses_b = [LotStatus.IN_PROGRESS, LotStatus.AVAILABLE, LotStatus.AVAILABLE,
                      LotStatus.ON_HOLD, LotStatus.AVAILABLE]

    lots = []
    for i, (lot_id, status) in enumerate(zip(LOTS_A, lot_statuses_a), 1):
        lots.append(Lot(id=lot_id, project_id=P_CORN, site_id=S_CORN_A,
                        lot_number=f"LOT-A{i:02d}", unit_type="3-bedroom",
                        block_number="Block 1", status=status))
    for i, (lot_id, status) in enumerate(zip(LOTS_B, lot_statuses_b), 1):
        lots.append(Lot(id=lot_id, project_id=P_CORN, site_id=S_CORN_B,
                        lot_number=f"LOT-B{i:02d}", unit_type="2-bedroom",
                        block_number="Block 2", status=status))

    for lot in lots:
        if str(lot.id) not in existing:
            db.add(lot)
    log(f"Created {len(lots)} lots")


def seed_stages(db):
    print("\n[5] Stage Master")
    existing_stages = db.query(StageMaster).all()
    existing_names  = {s.name            for s in existing_stages}
    existing_seqs   = {s.sequence_order  for s in existing_stages}
    # Also patch STAGES dict if name already exists with a different UUID
    for s in existing_stages:
        if s.name in STAGES:
            STAGES[s.name] = s.id  # use real DB UUID

    stage_list = list(STAGES.items())
    next_seq = max(existing_seqs, default=0) + 1

    for seq, (name, stage_id) in enumerate(stage_list, 1):
        if name in existing_names:
            log(f"Skipped stage: {name}")
            continue
        # Find a free sequence_order
        while seq in existing_seqs or seq < next_seq:
            seq += 1
        existing_seqs.add(seq)
        db.add(StageMaster(id=stage_id, name=name, sequence_order=seq,
                           description=f"{name} construction phase",
                           created_at=now()))
        log(f"Created stage: {name} (seq={seq})")

    # Flush so we can reference stage IDs in ProjectStageStatus
    db.flush()

    print("\n[5b] Project Stage Statuses (sample per lot)")
    existing_pss = {(str(r.project_id), str(r.site_id), str(r.lot_id), str(r.stage_id))
                    for r in db.query(ProjectStageStatus).all()}

    stage_ids = list(STAGES.values())

    # Lot A1: Completed → Foundations + Slab + Brickwork done
    lot_stage_data = [
        # (lot_id, site_id, stage_idx, status, started_at, completed_at)
        (LOTS_A[0], S_CORN_A, 0, StageStatus.CERTIFIED, dt(90), dt(75)),
        (LOTS_A[0], S_CORN_A, 1, StageStatus.CERTIFIED, dt(74), dt(60)),
        (LOTS_A[0], S_CORN_A, 2, StageStatus.CERTIFIED, dt(59), dt(40)),
        (LOTS_A[0], S_CORN_A, 3, StageStatus.CERTIFIED, dt(39), dt(20)),
        (LOTS_A[0], S_CORN_A, 4, StageStatus.CERTIFIED, dt(19), dt(10)),
        (LOTS_A[0], S_CORN_A, 5, StageStatus.CERTIFIED, dt(9), dt(5)),
        (LOTS_A[0], S_CORN_A, 6, StageStatus.CERTIFIED, dt(4), dt(2)),
        (LOTS_A[0], S_CORN_A, 7, StageStatus.CERTIFIED, dt(1), dt(0)),
        # Lot A2: In Progress → Foundations done, Slab in progress
        (LOTS_A[1], S_CORN_A, 0, StageStatus.CERTIFIED, dt(50), dt(40)),
        (LOTS_A[1], S_CORN_A, 1, StageStatus.IN_PROGRESS, dt(39), None),
        (LOTS_A[1], S_CORN_A, 2, StageStatus.NOT_STARTED, None, None),
        # Lot A3: In Progress → Foundations in progress
        (LOTS_A[2], S_CORN_A, 0, StageStatus.IN_PROGRESS, dt(15), None),
        # Lot B1: In Progress → Foundations done, Slab awaiting inspection
        (LOTS_B[0], S_CORN_B, 0, StageStatus.CERTIFIED, dt(30), dt(20)),
        (LOTS_B[0], S_CORN_B, 1, StageStatus.AWAITING_INSPECTION, dt(19), None),
    ]

    for (lot_id, site_id, stage_idx, status, started, completed) in lot_stage_data:
        key = (str(P_CORN), str(site_id), str(lot_id), str(stage_ids[stage_idx]))
        if key not in existing_pss:
            db.add(ProjectStageStatus(
                id=uuid.uuid4(),
                project_id=P_CORN, site_id=site_id, lot_id=lot_id,
                stage_id=stage_ids[stage_idx], status=status,
                started_at=started, completed_at=completed,
                inspection_required=(status == StageStatus.AWAITING_INSPECTION),
                updated_by=U_SITE_MGR,
            ))
    log("Created project stage statuses")


def seed_item_catalogue(db):
    print("\n[6] Item Categories & Items")
    existing_cats = {c.name for c in db.query(ItemCategory).all()}
    existing_items = {str(i.id) for i in db.query(Item).all()}

    cats = [
        ItemCategory(id=CAT_CONCRETE,   name="Concrete & Aggregates",   is_active=True),
        ItemCategory(id=CAT_MASONRY,    name="Masonry & Brickwork",      is_active=True),
        ItemCategory(id=CAT_ROOFING,    name="Roofing",                  is_active=True),
        ItemCategory(id=CAT_PLUMBING,   name="Plumbing",                 is_active=True),
        ItemCategory(id=CAT_ELECTRICAL, name="Electrical",               is_active=True),
        ItemCategory(id=CAT_FINISHING,  name="Finishing & Paintwork",    is_active=True),
        ItemCategory(id=CAT_FUEL,       name="Fuel & Consumables",       is_active=True),
    ]
    for cat in cats:
        if cat.name not in existing_cats:
            db.add(cat)

    items = [
        Item(id=I_CEMENT,     name="Cement 50kg Bag",         normalized_name="cement 50kg bag",
             category_id=CAT_CONCRETE,   default_unit="bag",  item_type=ItemType.MATERIAL),
        Item(id=I_SAND,       name="Building Sand (m³)",       normalized_name="building sand",
             category_id=CAT_CONCRETE,   default_unit="m³",   item_type=ItemType.MATERIAL),
        Item(id=I_STONE,      name="Crushed Stone 13mm (m³)",  normalized_name="crushed stone 13mm",
             category_id=CAT_CONCRETE,   default_unit="m³",   item_type=ItemType.MATERIAL),
        Item(id=I_STOCK_BRK,  name="Stock Brick (each)",       normalized_name="stock brick",
             category_id=CAT_MASONRY,    default_unit="each", item_type=ItemType.MATERIAL),
        Item(id=I_MAXI_BRK,   name="Maxi Brick (each)",        normalized_name="maxi brick",
             category_id=CAT_MASONRY,    default_unit="each", item_type=ItemType.MATERIAL),
        Item(id=I_ROOF_TIMB,  name="Roof Timber 38x114 (m)",   normalized_name="roof timber 38x114",
             category_id=CAT_ROOFING,    default_unit="m",    item_type=ItemType.MATERIAL),
        Item(id=I_CORR_SHEETM,name="Corrugated Iron Sheet 3m", normalized_name="corrugated iron sheet 3m",
             category_id=CAT_ROOFING,    default_unit="sheet",item_type=ItemType.MATERIAL),
        Item(id=I_PVC_PIPE,   name="PVC Pipe 110mm (m)",        normalized_name="pvc pipe 110mm",
             category_id=CAT_PLUMBING,   default_unit="m",    item_type=ItemType.MATERIAL),
        Item(id=I_ELEC_CABLE, name="Electrical Cable 2.5mm²",  normalized_name="electrical cable 2.5mm",
             category_id=CAT_ELECTRICAL, default_unit="m",    item_type=ItemType.MATERIAL),
        Item(id=I_PLASTER_SAND,name="Plaster Sand (m³)",         normalized_name="plaster sand",
             category_id=CAT_FINISHING,  default_unit="m³",   item_type=ItemType.MATERIAL),
        Item(id=I_PAINT,      name="PVA Paint 20L White",       normalized_name="pva paint 20l white",
             category_id=CAT_FINISHING,  default_unit="tin",  item_type=ItemType.MATERIAL),
        Item(id=I_DIESEL,     name="Diesel (litres)",           normalized_name="diesel litres",
             category_id=CAT_FUEL,       default_unit="L",    item_type=ItemType.MATERIAL,
             is_high_risk=True),
    ]
    for item in items:
        if str(item.id) not in existing_items:
            db.add(item)
    log(f"Created {len(items)} items in {len(cats)} categories")


def seed_suppliers(db):
    print("\n[7] Suppliers")
    existing = {str(s.id) for s in db.query(Supplier).all()}

    suppliers = [
        Supplier(id=SUP_AFRI,    name="AfriBuild Supplies",       code="AFR-001",
                 email="orders@afribuild.co.za",  phone="031 555 0101",
                 contact_person="Kevin Dlamini",  payment_terms="30 days",
                 address="14 Industrial Rd, Pinetown, KZN", is_active=True),
        Supplier(id=SUP_DBN,     name="Durban Brick & Block",     code="DBB-002",
                 email="sales@durbanbrick.co.za", phone="031 555 0202",
                 contact_person="Priya Naidoo",   payment_terms="EFT on delivery",
                 address="22 Clay Road, Pinetown, KZN", is_active=True),
        Supplier(id=SUP_COASTAL, name="Coastal Cement Traders",   code="CCT-003",
                 email="admin@coastalcement.co.za", phone="031 555 0303",
                 contact_person="Brian Gounden",  payment_terms="30 days",
                 address="7 Harbour View, Bayhead, Durban", is_active=True),
        Supplier(id=SUP_KZN,     name="KZN Roofing Solutions",    code="KZN-004",
                 email="info@kznroofing.co.za",   phone="031 555 0404",
                 contact_person="Thabo Mthembu",  payment_terms="50% upfront",
                 address="88 Roofline Estate, Hammarsdale", is_active=True),
        Supplier(id=SUP_PRO,     name="ProPlumb KZN",             code="PPL-005",
                 email="orders@proplumb.co.za",   phone="031 555 0505",
                 contact_person="Sandra Reddy",   payment_terms="30 days",
                 address="3 Plumber Close, Springfield, Durban", is_active=True),
        Supplier(id=SUP_MEGA,    name="Mega Hardware Warehouse",  code="MHW-006",
                 email="trade@megahardware.co.za",phone="031 555 0606",
                 contact_person="James van der Berg", payment_terms="30 days",
                 address="1 Warehouse Drive, Westmead, KZN", is_active=True),
    ]
    for s in suppliers:
        if str(s.id) not in existing:
            db.add(s)
    log(f"Created {len(suppliers)} suppliers")


def seed_boq(db):
    print("\n[8] BOQ")
    existing_headers = {str(h.id) for h in db.query(BOQHeader).all()}
    if str(BOQ_HEAD) in existing_headers:
        log("Skipped (exists)")
        return

    db.add(BOQHeader(
        id=BOQ_HEAD, project_id=P_CORN,
        version_name="Phase 1 — Rev A", source_type="manual",
        status=BoqStatus.ACTIVE, is_active_version=True,
        uploaded_by=U_MANAGER, uploaded_at=dt(100),
        notes="Initial approved BOQ for Phase 1, 76 units",
    ))
    db.flush()

    section_stage_map = {
        "Foundations":  STAGES["Foundations"],
        "Slab":         STAGES["Slab"],
        "Brickwork":    STAGES["Brickwork"],
        "Roof":         STAGES["Roof"],
        "Plumbing":     STAGES["Plumbing Rough"],
        "Electrical":   STAGES["Electrical Rough"],
        "Finishing":    STAGES["Finishing"],
    }

    for seq, (sec_name, sec_id) in enumerate(BOQ_SEC.items(), 1):
        db.add(BOQSection(
            id=sec_id, boq_header_id=BOQ_HEAD,
            stage_id=section_stage_map.get(sec_name),
            section_name=sec_name, sequence_order=seq,
        ))
    db.flush()

    # BOQ items — planned_total is GENERATED ALWAYS AS STORED in PostgreSQL.
    # The ORM model does NOT use Computed(), so SQLAlchemy would try to send
    # planned_total=None in the INSERT, which PostgreSQL rejects.
    # Fix: use SQLAlchemy Core insert() with an explicit column list that omits
    # planned_total. Core insert() only sends columns that appear in the values dict.
    boq_items_data = [
        # Foundations
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Foundations"], project_id=P_CORN,
             raw_description="Cement 50kg - foundations (76 units)",
             item_id=I_CEMENT, unit="bag", planned_quantity=1520, planned_rate=98.0,
             item_type="MATERIAL", sort_order=1, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Foundations"], project_id=P_CORN,
             raw_description="Building Sand - foundations",
             item_id=I_SAND, unit="m3", planned_quantity=380, planned_rate=220.0,
             item_type="MATERIAL", sort_order=2, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Foundations"], project_id=P_CORN,
             raw_description="Crushed Stone 13mm - foundations",
             item_id=I_STONE, unit="m3", planned_quantity=190, planned_rate=310.0,
             item_type="MATERIAL", sort_order=3, is_active=True),
        # Brickwork
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Brickwork"], project_id=P_CORN,
             raw_description="Stock Brick - external walls",
             item_id=I_STOCK_BRK, unit="each", planned_quantity=228000, planned_rate=3.20,
             item_type="MATERIAL", sort_order=1, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Brickwork"], project_id=P_CORN,
             raw_description="Maxi Brick - internal partition walls",
             item_id=I_MAXI_BRK, unit="each", planned_quantity=114000, planned_rate=4.10,
             item_type="MATERIAL", sort_order=2, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Brickwork"], project_id=P_CORN,
             raw_description="Plaster Sand - brickwork mortar",
             item_id=I_PLASTER_SAND, unit="m3", planned_quantity=285, planned_rate=195.0,
             item_type="MATERIAL", sort_order=3, is_active=True),
        # Roof
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Roof"], project_id=P_CORN,
             raw_description="Roof Timber 38x114 - trusses",
             item_id=I_ROOF_TIMB, unit="m", planned_quantity=9120, planned_rate=28.50,
             item_type="MATERIAL", sort_order=1, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Roof"], project_id=P_CORN,
             raw_description="Corrugated Iron Sheet 3m - roofing",
             item_id=I_CORR_SHEETM, unit="sheet", planned_quantity=3040, planned_rate=185.0,
             item_type="MATERIAL", sort_order=2, is_active=True),
        # Plumbing
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Plumbing"], project_id=P_CORN,
             raw_description="PVC Pipe 110mm - drainage (per unit)",
             item_id=I_PVC_PIPE, unit="m", planned_quantity=1520, planned_rate=42.0,
             item_type="MATERIAL", sort_order=1, is_active=True),
        # Electrical
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Electrical"], project_id=P_CORN,
             raw_description="Electrical Cable 2.5mm2 - lighting circuits",
             item_id=I_ELEC_CABLE, unit="m", planned_quantity=7600, planned_rate=18.50,
             item_type="MATERIAL", sort_order=1, is_active=True),
        # Finishing
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Finishing"], project_id=P_CORN,
             raw_description="Plaster Sand - internal plastering",
             item_id=I_PLASTER_SAND, unit="m3", planned_quantity=456, planned_rate=195.0,
             item_type="MATERIAL", sort_order=1, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Finishing"], project_id=P_CORN,
             raw_description="PVA Paint 20L White - interior walls",
             item_id=I_PAINT, unit="tin", planned_quantity=608, planned_rate=320.0,
             item_type="MATERIAL", sort_order=2, is_active=True),
        # Slab
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Slab"], project_id=P_CORN,
             raw_description="Cement 50kg - slab",
             item_id=I_CEMENT, unit="bag", planned_quantity=760, planned_rate=98.0,
             item_type="MATERIAL", sort_order=1, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Slab"], project_id=P_CORN,
             raw_description="Building Sand - slab mix",
             item_id=I_SAND, unit="m3", planned_quantity=190, planned_rate=220.0,
             item_type="MATERIAL", sort_order=2, is_active=True),
        dict(id=uuid.uuid4(), boq_section_id=BOQ_SEC["Slab"], project_id=P_CORN,
             raw_description="Crushed Stone 13mm - slab",
             item_id=I_STONE, unit="m3", planned_quantity=95, planned_rate=310.0,
             item_type="MATERIAL", sort_order=3, is_active=True),
    ]
    # Insert via Core to avoid sending GENERATED column planned_total
    db.execute(_sa_insert(BOQItem), boq_items_data)
    log(f"Created BOQ: {len(BOQ_SEC)} sections, {len(boq_items_data)} items")


def seed_material_requests(db):
    print("\n[9] Material Requests")
    existing = {str(mr.id) for mr in db.query(MaterialRequest).all()}

    mrs = [
        (MR1, "MR-CORN-001", RecordStatus.APPROVED, LOTS_A[1], STAGES["Slab"],
         dt(45), d(40), [(I_CEMENT, 80, "bag"), (I_SAND, 20, "m³"), (I_STONE, 10, "m³")]),
        (MR2, "MR-CORN-002", RecordStatus.APPROVED, LOTS_A[2], STAGES["Foundations"],
         dt(20), d(15), [(I_CEMENT, 60, "bag"), (I_SAND, 15, "m³")]),
        (MR3, "MR-CORN-003", RecordStatus.SUBMITTED, LOTS_B[0], STAGES["Brickwork"],
         dt(10), d(7),  [(I_STOCK_BRK, 5000, "each"), (I_PLASTER_SAND, 15, "m³")]),
        (MR4, "MR-CORN-004", RecordStatus.DRAFT, LOTS_A[1], STAGES["Roof"],
         dt(3),  d(1),  [(I_ROOF_TIMB, 200, "m"), (I_CORR_SHEETM, 80, "sheet")]),
    ]

    for (mr_id, req_num, status, lot_id, stage_id, req_date, needed_by, items) in mrs:
        if str(mr_id) not in existing:
            db.add(MaterialRequest(
                id=mr_id, request_number=req_num, project_id=P_CORN,
                site_id=S_CORN_A, lot_id=lot_id, stage_id=stage_id,
                requested_by=U_SITE_MGR, status=status,
                requested_date=req_date, needed_by_date=needed_by,
                reviewed_by=U_MANAGER if status == RecordStatus.APPROVED else None,
                reviewed_at=dt(2) if status == RecordStatus.APPROVED else None,
            ))
            db.flush()
            for (item_id, qty, unit) in items:
                db.add(MaterialRequestItem(
                    id=uuid.uuid4(), material_request_id=mr_id,
                    item_id=item_id, requested_quantity=qty, unit=unit,
                ))
    log(f"Created {len(mrs)} material requests")


def _po_totals(items_data):
    """Compute PO totals from item list: (desc, item_id, qty, rate, vat_mode, vat_rate)."""
    subtotal = 0.0
    vat_total = 0.0
    for _, _, qty, rate, vat_mode, vat_rate in items_data:
        if vat_mode == VatMode.EXCLUSIVE:
            excl = qty * rate
            vat = excl * (vat_rate / 100)
            subtotal += excl
            vat_total += vat
        else:  # INCLUSIVE
            incl = qty * rate
            excl = incl / (1 + vat_rate / 100)
            vat = incl - excl
            subtotal += excl
            vat_total += vat
    return round(subtotal, 2), round(vat_total, 2), round(subtotal + vat_total, 2)


def seed_purchase_orders(db):
    print("\n[10] Purchase Orders")
    existing = {str(po.id) for po in db.query(PurchaseOrder).all()}

    # (desc, item_id, qty, rate, vat_mode, vat_rate)
    po1_items = [
        ("Cement 50kg Bag",        I_CEMENT, 80,  98.00,  VatMode.INCLUSIVE, 15.0),
        ("Building Sand (m³)",     I_SAND,   20, 220.00,  VatMode.INCLUSIVE, 15.0),
        ("Crushed Stone 13mm (m³)",I_STONE,  10, 310.00,  VatMode.INCLUSIVE, 15.0),
    ]
    po2_items = [
        ("Stock Brick (each)",     I_STOCK_BRK, 5000, 3.20, VatMode.EXCLUSIVE, 15.0),
        ("Maxi Brick (each)",      I_MAXI_BRK,  2000, 4.10, VatMode.EXCLUSIVE, 15.0),
        ("Plaster Sand (m³)",      I_PLASTER_SAND, 15, 195.0, VatMode.EXCLUSIVE, 15.0),
    ]
    po3_items = [
        ("Roof Timber 38x114 (m)", I_ROOF_TIMB,    200, 28.50, VatMode.EXCLUSIVE, 15.0),
        ("Corrugated Iron Sheet",  I_CORR_SHEETM,  80,  185.0, VatMode.INCLUSIVE, 15.0),
    ]

    po_defs = [
        (PO1, "PO-CORN-001", SUP_COASTAL, RecordStatus.SENT,     MR1, dt(42), po1_items),
        (PO2, "PO-CORN-002", SUP_DBN,     RecordStatus.APPROVED, MR2, dt(18), po2_items),
        (PO3, "PO-CORN-003", SUP_KZN,     RecordStatus.DRAFT,    MR4, dt(2),  po3_items),
    ]

    for (po_id, po_num, sup_id, status, mr_id, po_date, items) in po_defs:
        if str(po_id) not in existing:
            sub, vat, total = _po_totals(items)
            db.add(PurchaseOrder(
                id=po_id, po_number=po_num, project_id=P_CORN, site_id=S_CORN_A,
                supplier_id=sup_id, material_request_id=mr_id,
                status=status, po_date=po_date,
                expected_delivery_date=d(10),
                subtotal_amount=sub, vat_amount=vat, total_amount=total,
                created_by=U_PROCUREMENT,
                approved_by=U_MANAGER if status in (RecordStatus.APPROVED, RecordStatus.SENT) else None,
                sent_at=po_date if status == RecordStatus.SENT else None,
            ))
            db.flush()
            for (desc, item_id, qty, rate, vat_mode, vat_rate) in items:
                if vat_mode == VatMode.EXCLUSIVE:
                    line_total = qty * rate * (1 + vat_rate / 100)
                else:
                    line_total = qty * rate
                db.add(PurchaseOrderItem(
                    id=uuid.uuid4(), purchase_order_id=po_id,
                    item_id=item_id, description=desc,
                    quantity_ordered=qty, unit=None,
                    rate=rate, vat_mode=vat_mode, vat_rate=vat_rate,
                    line_total=round(line_total, 2),
                    created_at=po_date,
                ))
    log("Created 3 purchase orders with line items")


def seed_deliveries(db):
    print("\n[11] Deliveries")
    existing = {str(d.id) for d in db.query(Delivery).all()}

    deliveries = [
        # DEL1: Full delivery against PO1 — cement, sand, stone
        dict(id=DEL1, delivery_number="DN-AfriBuild-1042",
             purchase_order_id=PO1, supplier_id=SUP_COASTAL, project_id=P_CORN,
             site_id=S_CORN_A, received_by_user_id=U_SITE_MGR,
             delivery_date=dt(38), delivery_status=RecordStatus.RECEIVED,
             supplier_delivery_note_number="CCT-DN-1042",
             comments="Full delivery, all items accounted for",
             items=[
                 dict(item_id=I_CEMENT,  description="Cement 50kg Bag",
                      quantity_expected=80.0, quantity_received=80.0, unit="bag"),
                 dict(item_id=I_SAND,    description="Building Sand (m³)",
                      quantity_expected=20.0, quantity_received=20.0, unit="m³"),
                 dict(item_id=I_STONE,   description="Crushed Stone 13mm (m³)",
                      quantity_expected=10.0, quantity_received=10.0, unit="m³"),
             ]),
        # DEL2: Short delivery — only 3800 bricks of 5000 ordered (discrepancy)
        dict(id=DEL2, delivery_number="DN-DBN-Brick-0871",
             purchase_order_id=PO2, supplier_id=SUP_DBN, project_id=P_CORN,
             site_id=S_CORN_A, received_by_user_id=U_SITE_MGR,
             delivery_date=dt(15), delivery_status=RecordStatus.RECEIVED,
             supplier_delivery_note_number="DBB-DN-0871",
             comments="Partial delivery — driver said remainder tomorrow",
             items=[
                 dict(item_id=I_STOCK_BRK, description="Stock Brick (each)",
                      quantity_expected=5000.0, quantity_received=3800.0, unit="each",
                      discrepancy_reason="Supplier loaded short — 1200 bricks outstanding"),
                 dict(item_id=I_PLASTER_SAND, description="Plaster Sand (m³)",
                      quantity_expected=15.0, quantity_received=15.0, unit="m³"),
             ]),
        # DEL3: Ad-hoc delivery — paint & cable, no linked PO
        dict(id=DEL3, delivery_number="DN-Mega-0234",
             purchase_order_id=None, supplier_id=SUP_MEGA, project_id=P_CORN,
             site_id=S_CORN_B, received_by_user_id=U_SITE_STAFF,
             delivery_date=dt(5), delivery_status=RecordStatus.RECEIVED,
             supplier_delivery_note_number="MHW-DN-0234",
             comments="Emergency top-up — paint and cable for Site B finishing",
             items=[
                 dict(item_id=I_PAINT,     description="PVA Paint 20L White",
                      quantity_expected=None, quantity_received=30.0, unit="tin"),
                 dict(item_id=I_ELEC_CABLE,description="Electrical Cable 2.5mm²",
                      quantity_expected=None, quantity_received=500.0, unit="m"),
             ]),
    ]

    for d_d in deliveries:
        if str(d_d["id"]) not in existing:
            items = d_d.pop("items")
            db.add(Delivery(**d_d))
            db.flush()
            for di in items:
                db.add(DeliveryItem(
                    id=uuid.uuid4(), delivery_id=d_d["id"], created_at=d_d["delivery_date"], **di
                ))
    log("Created 3 deliveries (1 with discrepancy)")


def seed_stock(db):
    print("\n[12] Stock Ledger & Usage Logs")
    existing_ledger = db.query(StockLedger).count()
    if existing_ledger > 0:
        log("Skipped (stock ledger already populated)")
        return

    entries_a = now()

    # Opening balances for Site A
    opening = [
        (I_CEMENT,     "bag",   50.0,   92.0),
        (I_SAND,       "m³",    12.0,   200.0),
        (I_STONE,      "m³",    5.0,    280.0),
        (I_STOCK_BRK,  "each",  2000.0, 2.95),
        (I_PLASTER_SAND,"m³",   8.0,    180.0),
    ]
    for (item_id, unit, qty, cost) in opening:
        db.add(StockLedger(
            id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A, item_id=item_id,
            movement_type=MovementType.OPENING_BALANCE, reference_type="SEED",
            quantity_in=qty, quantity_out=0, unit=unit, unit_cost=cost,
            movement_date=dt(50), entered_by=U_MANAGER,
            notes="Opening balance from previous period", created_at=dt(50),
        ))

    # DEL1 stock receipts
    del1_receipts = [
        (I_CEMENT, "bag",  80.0, 98.00),
        (I_SAND,   "m³",   20.0, 220.0),
        (I_STONE,  "m³",   10.0, 310.0),
    ]
    for (item_id, unit, qty, cost) in del1_receipts:
        db.add(StockLedger(
            id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A, item_id=item_id,
            movement_type=MovementType.DELIVERY_RECEIVED, reference_type="DELIVERY",
            reference_id=DEL1, quantity_in=qty, quantity_out=0,
            unit=unit, unit_cost=cost, movement_date=dt(38),
            entered_by=U_SITE_MGR, created_at=dt(38),
        ))

    # DEL2 stock receipts
    db.add(StockLedger(
        id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A, item_id=I_STOCK_BRK,
        movement_type=MovementType.DELIVERY_RECEIVED, reference_type="DELIVERY",
        reference_id=DEL2, quantity_in=3800.0, quantity_out=0,
        unit="each", unit_cost=2.95, movement_date=dt(15),
        entered_by=U_SITE_MGR, created_at=dt(15),
    ))
    db.add(StockLedger(
        id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A, item_id=I_PLASTER_SAND,
        movement_type=MovementType.DELIVERY_RECEIVED, reference_type="DELIVERY",
        reference_id=DEL2, quantity_in=15.0, quantity_out=0,
        unit="m³", unit_cost=190.0, movement_date=dt(15),
        entered_by=U_SITE_MGR, created_at=dt(15),
    ))

    # DEL3 receipts for Site B
    db.add(StockLedger(
        id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_B, item_id=I_PAINT,
        movement_type=MovementType.DELIVERY_RECEIVED, reference_type="DELIVERY",
        reference_id=DEL3, quantity_in=30.0, quantity_out=0,
        unit="tin", unit_cost=320.0, movement_date=dt(5),
        entered_by=U_SITE_STAFF, created_at=dt(5),
    ))
    db.add(StockLedger(
        id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_B, item_id=I_ELEC_CABLE,
        movement_type=MovementType.DELIVERY_RECEIVED, reference_type="DELIVERY",
        reference_id=DEL3, quantity_in=500.0, quantity_out=0,
        unit="m", unit_cost=18.50, movement_date=dt(5),
        entered_by=U_SITE_STAFF, created_at=dt(5),
    ))

    # Usage logs (Site A)
    usage_records = [
        (I_CEMENT,     S_CORN_A, LOTS_A[0], 30.0, "bag",   "Masonry team 1", dt(35)),
        (I_CEMENT,     S_CORN_A, LOTS_A[1], 40.0, "bag",   "Masonry team 2", dt(25)),
        (I_SAND,       S_CORN_A, LOTS_A[0], 8.0,  "m³",    "Masonry team 1", dt(35)),
        (I_STONE,      S_CORN_A, LOTS_A[0], 5.0,  "m³",    "Slab crew",      dt(30)),
        (I_STOCK_BRK,  S_CORN_A, LOTS_A[1], 1200.0,"each", "Brickwork crew", dt(12)),
        (I_PLASTER_SAND,S_CORN_A,LOTS_A[1], 5.0,  "m³",    "Plaster team",   dt(8)),
        (I_PAINT,      S_CORN_B, LOTS_B[0], 12.0, "tin",   "Finishing crew", dt(3)),
        (I_ELEC_CABLE, S_CORN_B, LOTS_B[0], 150.0,"m",     "Electrician",    dt(3)),
    ]

    usage_ids = []
    for (item_id, site_id, lot_id, qty, unit, person, usage_dt) in usage_records:
        u_id = uuid.uuid4()
        usage_ids.append(u_id)
        db.add(UsageLog(
            id=u_id, project_id=P_CORN, site_id=site_id, lot_id=lot_id,
            item_id=item_id, quantity_used=qty,
            used_by_person_name=person, recorded_by_user_id=U_SITE_MGR,
            usage_date=usage_dt, created_at=usage_dt,
        ))
        db.add(StockLedger(
            id=uuid.uuid4(), project_id=P_CORN, site_id=site_id, item_id=item_id,
            movement_type=MovementType.USAGE, reference_type="USAGE_LOG",
            reference_id=u_id, quantity_in=0, quantity_out=qty,
            unit=unit, movement_date=usage_dt, entered_by=U_SITE_MGR,
            created_at=usage_dt,
        ))

    log(f"Created stock ledger entries + {len(usage_records)} usage logs")


def seed_fuel(db):
    print("\n[13] Fuel Logs")
    existing = db.query(FuelLog).count()
    if existing > 0:
        log("Skipped (fuel logs already exist)")
        return

    # total_cost is GENERATED ALWAYS AS STORED — SQLAlchemy Computed(persisted=True)
    # automatically excludes it from INSERT
    logs = [
        FuelLog(id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
                fuel_type=FuelType.DIESEL, usage_type=FuelUsageType.EQUIPMENT,
                equipment_ref="Excavator EX-001", litres=120.0, cost_per_litre=22.50,
                fuelled_by="Thabo Mokoena", recorded_by=U_SITE_MGR,
                fuel_date=dt(30), notes="Morning fill-up for foundations"),
        FuelLog(id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
                fuel_type=FuelType.DIESEL, usage_type=FuelUsageType.GENERATOR,
                equipment_ref="Gen GEN-A1", litres=45.0, cost_per_litre=22.80,
                fuelled_by="Sipho Cele", recorded_by=U_SITE_MGR,
                fuel_date=dt(20), notes="Site A generator top-up"),
        FuelLog(id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_B,
                fuel_type=FuelType.DIESEL, usage_type=FuelUsageType.DELIVERY_VEHICLE,
                equipment_ref="Truck KZN 456 GP", litres=80.0, cost_per_litre=22.60,
                fuelled_by="Driver", recorded_by=U_SITE_STAFF,
                fuel_date=dt(10), notes="Delivery vehicle refuel"),
        FuelLog(id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
                fuel_type=FuelType.DIESEL, usage_type=FuelUsageType.EQUIPMENT,
                equipment_ref="Mixer MX-003", litres=30.0, cost_per_litre=23.10,
                fuelled_by="Bongani Zulu", recorded_by=U_SITE_MGR,
                fuel_date=dt(3), notes=None),
    ]
    for fl in logs:
        db.add(fl)
    log(f"Created {len(logs)} fuel logs")


def seed_invoices_payments(db):
    print("\n[14] Invoices & Payments")
    existing_inv = {str(i.id) for i in db.query(Invoice).all()}
    existing_pay = db.query(Payment).count()

    # Invoice 1: matched to PO1 delivery, approved
    if str(INV1) not in existing_inv:
        db.add(Invoice(
            id=INV1, invoice_number="CCT-INV-2024-0421",
            supplier_id=SUP_COASTAL, project_id=P_CORN, site_id=S_CORN_A,
            purchase_order_id=PO1,
            invoice_date=d(35), due_date=d(5),
            subtotal_amount=17730.43, vat_amount=2659.57, total_amount=20390.00,
            status=RecordStatus.APPROVED,
            captured_by=U_PROCUREMENT, captured_at=dt(33),
            notes="Full invoice for PO-CORN-001",
        ))
        db.flush()
        db.add(InvoiceMatchingResult(
            id=uuid.uuid4(), invoice_id=INV1, purchase_order_id=PO1, delivery_id=DEL1,
            match_status=InvoiceMatchStatus.MATCHED,
            quantity_match=True, amount_match=True, supplier_match=True,
            notes="Auto-matched: all lines confirmed", created_at=dt(33),
        ))

    # Invoice 2: partial delivery, partially matched
    if str(INV2) not in existing_inv:
        db.add(Invoice(
            id=INV2, invoice_number="DBB-INV-2024-1187",
            supplier_id=SUP_DBN, project_id=P_CORN, site_id=S_CORN_A,
            purchase_order_id=PO2,
            invoice_date=d(12), due_date=d(18),
            subtotal_amount=16825.00, vat_amount=2523.75, total_amount=19348.75,
            status=RecordStatus.SUBMITTED,
            captured_by=U_PROCUREMENT, captured_at=dt(12),
            notes="Supplier invoiced full PO but only partial delivery received",
        ))
        db.flush()
        db.add(InvoiceMatchingResult(
            id=uuid.uuid4(), invoice_id=INV2, purchase_order_id=PO2, delivery_id=DEL2,
            match_status=InvoiceMatchStatus.PARTIALLY_MATCHED,
            quantity_match=False, amount_match=False, supplier_match=True,
            notes="1200 bricks outstanding — do not approve until delivery complete",
            created_at=dt(12),
        ))

    # Invoice 3: ad-hoc, no PO
    if str(INV3) not in existing_inv:
        db.add(Invoice(
            id=INV3, invoice_number="MHW-INV-2024-3308",
            supplier_id=SUP_MEGA, project_id=P_CORN, site_id=S_CORN_B,
            invoice_date=d(4), due_date=d(26),
            subtotal_amount=23739.13, vat_amount=3560.87, total_amount=27300.00,
            status=RecordStatus.DRAFT,
            captured_by=U_PROCUREMENT, captured_at=dt(4),
        ))

    # Payments
    if existing_pay == 0:
        db.flush()
        payments = [
            Payment(id=uuid.uuid4(), invoice_id=INV1, supplier_id=SUP_COASTAL,
                    project_id=P_CORN, payment_type=PaymentType.SUPPLIER,
                    payment_reference="EFT-20240385-001",
                    payment_date=d(2), amount_paid=20390.00,
                    status=PaymentStatus.PAID,
                    approved_by=U_MANAGER, captured_by=U_PROCUREMENT,
                    notes="Full settlement of CCT-INV-2024-0421"),
            Payment(id=uuid.uuid4(), invoice_id=None, supplier_id=None,
                    project_id=P_CORN, payment_type=PaymentType.LABOUR,
                    payment_reference="LABOUR-MAY-W2",
                    payment_date=d(7), amount_paid=38500.00,
                    status=PaymentStatus.PAID,
                    approved_by=U_MANAGER, captured_by=U_PROCUREMENT,
                    notes="Weekly labour payment — brickwork and slab crews"),
            Payment(id=uuid.uuid4(), invoice_id=INV2, supplier_id=SUP_DBN,
                    project_id=P_CORN, payment_type=PaymentType.SUPPLIER,
                    payment_reference="EFT-20240401-007",
                    payment_date=None, amount_paid=19348.75,
                    status=PaymentStatus.PENDING,
                    captured_by=U_PROCUREMENT,
                    notes="Awaiting approval — partial delivery dispute unresolved"),
        ]
        for p in payments:
            db.add(p)
    log("Created 3 invoices, 3 payments")


def seed_alerts(db):
    print("\n[15] System Alerts")
    existing = db.query(SystemAlert).count()
    if existing > 0:
        log("Skipped (alerts already exist)")
        return

    alerts = [
        SystemAlert(
            id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
            alert_type=AlertType.DELIVERY_DISCREPANCY, severity=AlertSeverity.HIGH,
            title="Delivery Discrepancy — DN-DBN-Brick-0871",
            message="1200 Stock Bricks were ordered (PO-CORN-002) but only 3800 of 5000 were received. "
                    "Supplier has been contacted. Outstanding delivery should arrive within 48 hours.",
            status=AlertStatus.ACKNOWLEDGED,
            reference_type="DELIVERY", reference_id=DEL2,
            target_role=UserRole.OFFICE_ADMIN,
            notification_channel="in_app", created_at=dt(15),
        ),
        SystemAlert(
            id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
            alert_type=AlertType.LOW_STOCK, severity=AlertSeverity.MEDIUM,
            title="Low Stock — Cement (Site A)",
            message="Current cement stock at Site A is below the minimum threshold. "
                    "Current balance: ~60 bags. Minimum recommended: 100 bags. "
                    "Material Request MR-CORN-002 has been submitted.",
            status=AlertStatus.OPEN,
            reference_type="ITEM", reference_id=I_CEMENT,
            target_role=UserRole.OFFICE_ADMIN,
            notification_channel="in_app", created_at=dt(5),
        ),
        SystemAlert(
            id=uuid.uuid4(), project_id=P_CORN,
            alert_type=AlertType.INVOICE_MISMATCH, severity=AlertSeverity.HIGH,
            title="Invoice Mismatch — DBB-INV-2024-1187",
            message="Invoice from Durban Brick & Block (DBB-INV-2024-1187) claims full delivery of 5000 "
                    "bricks, but goods received note records only 3800. Do not approve payment until "
                    "discrepancy is resolved.",
            status=AlertStatus.OPEN,
            reference_type="INVOICE", reference_id=INV2,
            target_role=UserRole.OWNER,
            notification_channel="in_app", created_at=dt(12),
        ),
        SystemAlert(
            id=uuid.uuid4(), project_id=P_CORN,
            alert_type=AlertType.OVERDUE_PAYMENT, severity=AlertSeverity.CRITICAL,
            title="Payment Overdue — CCT-INV-2024-0421 (Past Due)",
            message="Invoice CCT-INV-2024-0421 from Coastal Cement Traders was due 5 days ago. "
                    "Payment of R20,390.00 is outstanding. Supplier has been notified.",
            status=AlertStatus.RESOLVED,
            reference_type="INVOICE", reference_id=INV1,
            target_role=UserRole.OWNER,
            notification_channel="in_app", created_at=dt(7),
            resolved_at=dt(2), resolved_by=U_MANAGER,
        ),
        SystemAlert(
            id=uuid.uuid4(), project_id=P_CORN, site_id=S_CORN_A,
            alert_type=AlertType.REQUEST_PENDING_TOO_LONG, severity=AlertSeverity.MEDIUM,
            title="Material Request Pending — MR-CORN-003",
            message="Material Request MR-CORN-003 for brickwork materials has been in SUBMITTED "
                    "status for 10 days without review. Required on-site by the end of this week.",
            status=AlertStatus.OPEN,
            reference_type="MATERIAL_REQUEST", reference_id=MR3,
            target_role=UserRole.OFFICE_ADMIN,
            notification_channel="in_app", created_at=dt(1),
        ),
    ]
    for a in alerts:
        db.add(a)
    log(f"Created {len(alerts)} alerts")


def seed_attachments(db):
    print("\n[16] Attachment Metadata")
    existing = db.query(Attachment).count()
    if existing > 0:
        log("Skipped (attachments already exist)")
        return

    attachments = [
        Attachment(
            id=uuid.uuid4(), entity_type=AttachmentEntity.DELIVERY, entity_id=DEL1,
            file_name="delivery_note_CCT_1042.jpg",
            stored_path="uploads/deliveries/DEL1_CCT_delivery_note.jpg",
            mime_type="image/jpeg", file_size_bytes=284712,
            attachment_type=AttachmentType.DELIVERY_NOTE,
            uploaded_by=U_SITE_MGR, uploaded_at=dt(38), is_active=True,
        ),
        Attachment(
            id=uuid.uuid4(), entity_type=AttachmentEntity.DELIVERY, entity_id=DEL2,
            file_name="delivery_note_DBB_0871_partial.jpg",
            stored_path="uploads/deliveries/DEL2_DBB_partial_delivery.jpg",
            mime_type="image/jpeg", file_size_bytes=195340,
            attachment_type=AttachmentType.DELIVERY_NOTE,
            uploaded_by=U_SITE_MGR, uploaded_at=dt(15), is_active=True,
        ),
        Attachment(
            id=uuid.uuid4(), entity_type=AttachmentEntity.INVOICE, entity_id=INV1,
            file_name="invoice_CCT_2024_0421.pdf",
            stored_path="uploads/invoices/INV1_CCT_2024_0421.pdf",
            mime_type="application/pdf", file_size_bytes=87420,
            attachment_type=AttachmentType.INVOICE_COPY,
            uploaded_by=U_PROCUREMENT, uploaded_at=dt(33), is_active=True,
        ),
        Attachment(
            id=uuid.uuid4(), entity_type=AttachmentEntity.PURCHASE_ORDER, entity_id=PO1,
            file_name="po_CORN_001_signed.pdf",
            stored_path="uploads/purchase_orders/PO1_signed.pdf",
            mime_type="application/pdf", file_size_bytes=142800,
            attachment_type=AttachmentType.PDF,
            uploaded_by=U_MANAGER, uploaded_at=dt(42), is_active=True,
        ),
        Attachment(
            id=uuid.uuid4(), entity_type=AttachmentEntity.DELIVERY, entity_id=DEL3,
            file_name="site_b_delivery_photo.jpg",
            stored_path="uploads/deliveries/DEL3_MEGA_site_b.jpg",
            mime_type="image/jpeg", file_size_bytes=312450,
            attachment_type=AttachmentType.PHOTO,
            uploaded_by=U_SITE_STAFF, uploaded_at=dt(5), is_active=True,
        ),
    ]
    for att in attachments:
        db.add(att)
    log(f"Created {len(attachments)} attachment records")


# ─────────────────────────────────────────────────────────────────
# GLOBAL PATCHER
# ─────────────────────────────────────────────────────────────────

def _patch_user_globals(uuid_map: dict):
    """Update module-level UUID constants to match real DB UUIDs."""
    global U_ADMIN, U_MANAGER, U_PROCUREMENT, U_SITE_MGR, U_SITE_STAFF
    U_ADMIN       = uuid_map["admin@hmhgroup.com"]
    U_MANAGER     = uuid_map["office.manager@hmhgroup.com"]
    U_PROCUREMENT = uuid_map["procurement@hmhgroup.com"]
    U_SITE_MGR    = uuid_map["sitemanager.a@hmhgroup.com"]
    U_SITE_STAFF  = uuid_map["sitestaff.b@hmhgroup.com"]


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def _migrate_schema(db):
    """Apply any missing schema changes that create_all can't handle (ALTER TABLE etc.)."""
    from sqlalchemy import text, inspect
    insp = inspect(db.bind)

    # Add vat_mode / vat_rate to purchase_order_items if missing
    poi_cols = {c["name"] for c in insp.get_columns("purchase_order_items")}
    if "vat_mode" not in poi_cols:
        print("  [migrate] Adding vat_mode to purchase_order_items")
        db.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vat_mode_enum') THEN
                    CREATE TYPE vat_mode_enum AS ENUM ('INCLUSIVE', 'EXCLUSIVE');
                END IF;
            END $$;
        """))
        db.execute(text("""
            ALTER TABLE purchase_order_items
                ADD COLUMN vat_mode vat_mode_enum NOT NULL DEFAULT 'INCLUSIVE',
                ADD COLUMN vat_rate NUMERIC(5,2) NOT NULL DEFAULT 15.00;
        """))
        db.execute(text("COMMIT"))
        print("  [migrate] Done")


def main():
    print("=" * 60)
    print("HMH Construction System - Demo Seed")
    print("=" * 60)

    # Ensure all tables exist (create_all is safe to re-run)
    from sqlalchemy import inspect as _inspect
    from app.db.session import engine
    from app.db.base import Base
    import app.models.user, app.models.project, app.models.site, app.models.lot
    import app.models.stage, app.models.item, app.models.supplier
    import app.models.boq, app.models.material_request, app.models.purchase_order
    import app.models.delivery, app.models.stock, app.models.fuel
    import app.models.invoice, app.models.payment, app.models.alert, app.models.attachment
    import app.models.access
    Base.metadata.create_all(engine, checkfirst=True)
    print("  [schema] Tables verified/created")

    with db_session() as db:
        _migrate_schema(db)
        # Idempotency guard
        existing = db.query(Project).filter_by(code="HMH-CORN-01").first()
        if existing is not None:
            print("\n[!] Project HMH-CORN-01 already exists.")
            print("   Skipping full seed. To re-seed, delete the project first.")
            print("   (Or run individual sections by commenting out the guard.)\n")
            # Still run users in case they were missed
            uuid_map = seed_users(db)
            db.flush()
            _patch_user_globals(uuid_map)
            return

        uuid_map = seed_users(db)
        db.flush()
        _patch_user_globals(uuid_map)
        seed_projects(db)
        db.flush()
        seed_sites(db)
        db.flush()
        seed_lots(db)
        db.flush()
        seed_stages(db)
        db.flush()
        seed_item_catalogue(db)
        db.flush()
        seed_suppliers(db)
        db.flush()
        seed_boq(db)
        db.flush()
        seed_material_requests(db)
        db.flush()
        seed_purchase_orders(db)
        db.flush()
        seed_deliveries(db)
        db.flush()
        seed_stock(db)
        db.flush()
        seed_fuel(db)
        db.flush()
        seed_invoices_payments(db)
        db.flush()
        seed_alerts(db)
        db.flush()
        seed_attachments(db)

    print("\n" + "=" * 60)
    print("Seed complete!")
    print("=" * 60)
    print()
    print("Demo credentials (password: Demo@1234)")
    print("-" * 55)
    print("Role           Email                          Login at")
    print("-" * 55)
    print("OWNER          admin@hmhgroup.com             /login")
    print("OFFICE_ADMIN   office.manager@hmhgroup.com    /login")
    print("OFFICE_USER    procurement@hmhgroup.com       /login")
    print("SITE_MANAGER   sitemanager.a@hmhgroup.com     /site-login")
    print("SITE_STAFF     sitestaff.b@hmhgroup.com       /site-login")
    print()
    print("Pages with visible data:")
    print("  /             Dashboard (project stats, fuel cost card)")
    print("  /projects     HMH-CORN-01 (ACTIVE) + HMH-RIV-02 (PLANNED)")
    print("  /boq          Phase 1 BOQ Rev A, 7 sections, 15 items")
    print("  /procurement  3 POs (SENT, APPROVED, DRAFT) with VAT line items")
    print("  /deliveries   3 deliveries (1 full, 1 discrepancy, 1 ad-hoc)")
    print("  /stock        Opening balances + receipts + 8 usage logs")
    print("  /fuel         4 fuel logs with cost totals")
    print("  /suppliers    6 active suppliers")
    print("  /payments     3 invoices + 3 payments (PAID, PAID, PENDING)")
    print("  /alerts       5 alerts (OPEN, ACKNOWLEDGED, RESOLVED)")
    print("  /site         Site dashboard (SITE_MANAGER/SITE_STAFF only)")
    print()
    print("Note: attachment records are metadata only (placeholder paths).")
    print("      Upload real files via UI or place in hmh-backend/uploads/")
    print()


if __name__ == "__main__":
    main()
