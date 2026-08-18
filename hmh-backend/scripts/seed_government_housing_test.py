"""Repeatable South African government-housing TEST dataset.

This script is intentionally tied to a dedicated Supabase TEST project.  It
refuses to run unless all safety gates pass, clears only the guarded TEST
database, and then recreates a deterministic synthetic portfolio.

Required environment variables::

    APP_ENV=test
    DATABASE_URL=<TEST Supabase Postgres/Supavisor URL>
    HMH_TEST_SUPABASE_REF=ekipedffcywxlabchznq
    HMH_TEST_SEED_CONFIRM=government_housing_test_v1

For local verification only, set HMH_ALLOW_LOCAL_TEST_SEED=true and use a
loopback DATABASE_URL.  Never put database credentials in this file.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401,E402 - registers every ORM table
import app.models.municipality_invoice  # noqa: F401,E402 - omitted from app.models.__init__
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402


SEED_BATCH = "government_housing_test_v1"
DEFAULT_TEST_PROJECT_REF = "ekipedffcywxlabchznq"
UUID_NAMESPACE = uuid.UUID("71b156de-5fe2-4d77-a24c-fad8ab6d4c6e")
TODAY = date.today()
NOW = datetime.now(timezone.utc)
RNG = random.Random(20260817)


def sid(*parts: object) -> uuid.UUID:
    """Stable UUID for idempotent, reproducible records."""
    return uuid.uuid5(UUID_NAMESPACE, ":".join(str(part) for part in parts))


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stamp(day: date, hour: int = 9, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def table(name: str):
    return Base.metadata.tables[name]


def insert_rows(db: Session, name: str, rows: Iterable[dict[str, Any]]) -> int:
    payload = list(rows)
    if payload:
        db.execute(table(name).insert(), payload)
    return len(payload)


def assert_test_target(database_url: str) -> None:
    """Fail closed unless the URL is the named TEST project or loopback."""
    app_env = os.getenv("APP_ENV", "").strip().lower()
    node_env = os.getenv("NODE_ENV", "").strip().lower()
    confirmation = os.getenv("HMH_TEST_SEED_CONFIRM", "")
    expected_ref = os.getenv("HMH_TEST_SUPABASE_REF", DEFAULT_TEST_PROJECT_REF).strip()

    if app_env not in {"test", "testing"}:
        raise SystemExit("REFUSED: APP_ENV must be exactly 'test' or 'testing'.")
    if node_env == "production":
        raise SystemExit("REFUSED: NODE_ENV=production.")
    if confirmation != SEED_BATCH:
        raise SystemExit(f"REFUSED: HMH_TEST_SEED_CONFIRM must equal {SEED_BATCH!r}.")
    if not expected_ref or len(expected_ref) < 12:
        raise SystemExit("REFUSED: HMH_TEST_SUPABASE_REF is missing or invalid.")

    url = make_url(database_url)
    host = (url.host or "").lower()
    username = (url.username or "").lower()
    local_allowed = os.getenv("HMH_ALLOW_LOCAL_TEST_SEED", "").lower() == "true"
    is_loopback = host in {"localhost", "127.0.0.1", "::1"}
    is_named_test = expected_ref.lower() in host or expected_ref.lower() in username

    if is_loopback and not local_allowed:
        raise SystemExit("REFUSED: loopback seeding requires HMH_ALLOW_LOCAL_TEST_SEED=true.")
    if not is_named_test and not (is_loopback and local_allowed):
        raise SystemExit(
            "REFUSED: DATABASE_URL does not identify the configured TEST Supabase project."
        )


def clear_business_data(db: Session) -> None:
    """Clear application rows only after assert_test_target has succeeded."""
    names = list(
        db.execute(
            text(
                """
                select tablename
                from pg_tables
                where schemaname = 'public'
                  and tablename <> 'alembic_version'
                order by tablename
                """
            )
        ).scalars()
    )
    # project_stage_statuses is a retained legacy table from the initial schema;
    # it is empty and intentionally not mapped by the current application.
    known = set(Base.metadata.tables) | {"project_stage_statuses"}
    unexpected = sorted(set(names) - known)
    if unexpected:
        raise RuntimeError(
            "REFUSED: unexpected public tables exist; review before clearing: "
            + ", ".join(unexpected)
        )
    quoted = ", ".join(f'public."{name}"' for name in names)
    if quoted:
        db.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


PROJECTS = [
    {
        "code": "TEST-KZN-BNG-04",
        "name": "KwaMashu BNG Housing Phase 4",
        "province": "KwaZulu-Natal",
        "municipality": "Fictional eThekwini North Housing Directorate",
        "location": "KwaMashu Extension 12, KwaZulu-Natal",
        "units": 96,
        "progress": 82,
        "budget": 43_200_000,
        "contract": 48_500_000,
        "forecast": 42_850_000,
        "start_days": 315,
        "finish_days": 50,
        "status": "ACTIVE",
        "health": "GREEN",
        "scenario": "Healthy project: on programme, procurement stable, unit completions accelerating.",
    },
    {
        "code": "TEST-GP-TEM-34",
        "name": "Tembisa Extension 34 Social Housing",
        "province": "Gauteng",
        "municipality": "Fictional Ekurhuleni Housing Delivery Unit",
        "location": "Tembisa Extension 34, Gauteng",
        "units": 84,
        "progress": 58,
        "budget": 39_750_000,
        "contract": 44_900_000,
        "forecast": 40_100_000,
        "start_days": 285,
        "finish_days": 105,
        "status": "ACTIVE",
        "health": "YELLOW",
        "scenario": "Procurement delay: roof timber and window packages await final approval.",
    },
    {
        "code": "TEST-EC-LUS-02",
        "name": "Lusikisiki Rural Housing Programme 02",
        "province": "Eastern Cape",
        "municipality": "Fictional OR Tambo Rural Settlements Agency",
        "location": "Lusikisiki Cluster 7, Eastern Cape",
        "units": 72,
        "progress": 29,
        "budget": 34_600_000,
        "contract": 39_200_000,
        "forecast": 35_300_000,
        "start_days": 230,
        "finish_days": 190,
        "status": "ACTIVE",
        "health": "RED",
        "scenario": "Fuel concern: excavator and water tanker consumption exceed expected norms.",
    },
    {
        "code": "TEST-MP-EMA-11",
        "name": "Emalahleni Integrated Housing Development 11",
        "province": "Mpumalanga",
        "municipality": "Fictional Nkangala Human Settlements Programme Office",
        "location": "Emalahleni South, Mpumalanga",
        "units": 100,
        "progress": 46,
        "budget": 46_800_000,
        "contract": 52_900_000,
        "forecast": 49_900_000,
        "start_days": 300,
        "finish_days": 145,
        "status": "ACTIVE",
        "health": "RED",
        "scenario": "Cost overrun risk: reinforcement, roads and stormwater packages are under pressure.",
    },
    {
        "code": "TEST-LP-POL-08",
        "name": "Polokwane Serviced Stands and Top Structures 08",
        "province": "Limpopo",
        "municipality": "Fictional Capricorn Housing Implementation Office",
        "location": "Polokwane Extension 106, Limpopo",
        "units": 64,
        "progress": 92,
        "budget": 31_500_000,
        "contract": 36_400_000,
        "forecast": 31_100_000,
        "start_days": 340,
        "finish_days": 30,
        "status": "ACTIVE",
        "health": "YELLOW",
        "scenario": "Near completion: snagging is active and close-out certificates remain outstanding.",
    },
    {
        "code": "TEST-FS-BOT-03",
        "name": "Botshabelo Community Housing Phase 3",
        "province": "Free State",
        "municipality": "Fictional Mangaung Community Housing Directorate",
        "location": "Botshabelo Section H, Free State",
        "units": 58,
        "progress": 100,
        "budget": 27_900_000,
        "contract": 32_200_000,
        "forecast": 27_650_000,
        "start_days": 390,
        "finish_days": -35,
        "status": "COMPLETED",
        "health": "GREEN",
        "scenario": "Completed works: defects-liability inspections and final account close-out remain.",
    },
    {
        "code": "TEST-NW-RUS-06",
        "name": "Rustenburg Affordable Housing Package 06",
        "province": "North West",
        "municipality": "Fictional Bojanala Housing Development Unit",
        "location": "Rustenburg East, North West",
        "units": 88,
        "progress": 18,
        "budget": 40_900_000,
        "contract": 46_300_000,
        "forecast": 41_200_000,
        "start_days": 145,
        "finish_days": 275,
        "status": "ACTIVE",
        "health": "YELLOW",
        "scenario": "Recently started: bulk earthworks and early foundations are in progress.",
    },
]


STAGES = [
    ("SITE_CLEAR", "Site Clearing", 1),
    ("EXCAVATION", "Excavation", 2),
    ("FOUNDATIONS", "Foundations", 3),
    ("SLAB", "Surface Bed and Slab", 4),
    ("BRICKWORK", "Brickwork", 5),
    ("ROOF", "Roof Structure and Covering", 6),
    ("PLASTER", "Internal and External Plaster", 7),
    ("PLUMBING", "Plumbing Installation", 8),
    ("ELECTRICAL", "Electrical Installation", 9),
    ("CEILINGS", "Ceilings and Flooring", 10),
    ("FINISHES", "Painting and Final Finishes", 11),
    ("SNAG", "Snagging and Quality Inspection", 12),
    ("HANDOVER", "Handover and Close-out", 13),
]


BOQ_ITEMS = [
    ("Preliminaries", "Site establishment and temporary services", "item", 1.0, 24_500),
    ("Earthworks", "Excavate foundation trenches", "m3", 32.0, 310),
    ("Earthworks", "Imported G7 fill compacted in layers", "m3", 24.0, 420),
    ("Concrete", "20 MPa concrete to strip footings", "m3", 9.5, 1_780),
    ("Concrete", "25 MPa concrete surface bed", "m3", 7.0, 1_960),
    ("Reinforcing", "High-tensile reinforcing steel", "kg", 620.0, 24.50),
    ("Reinforcing", "Ref 193 welded mesh", "m2", 52.0, 96),
    ("Brickwork", "140 mm concrete block walling", "m2", 145.0, 285),
    ("Brickwork", "Stock brick external skin", "number", 4_800.0, 2.35),
    ("Roofing", "Prefabricated timber roof trusses", "item", 1.0, 15_800),
    ("Roofing", "0.47 mm IBR roof sheeting and accessories", "m2", 78.0, 245),
    ("Doors and Windows", "Powder-coated aluminium windows", "number", 7.0, 1_850),
    ("Doors and Windows", "External and internal door set", "number", 6.0, 1_420),
    ("Plastering", "Internal plaster to walls", "m2", 210.0, 92),
    ("Plastering", "External plaster to walls", "m2", 118.0, 105),
    ("Painting", "Three-coat acrylic wall paint system", "m2", 328.0, 58),
    ("Plumbing", "Hot and cold water installation", "item", 1.0, 12_900),
    ("Sanitaryware", "Sanitaryware suite complete", "item", 1.0, 8_750),
    ("Electrical", "Domestic electrical installation and COC", "item", 1.0, 18_600),
    ("Flooring", "Ceramic floor tiles including adhesive", "m2", 46.0, 235),
    ("Ceilings", "6.4 mm gypsum ceiling and insulation", "m2", 52.0, 225),
    ("External Works", "House connection to sewer reticulation", "item", 1.0, 11_800),
    ("External Works", "House connection to water reticulation", "item", 1.0, 8_600),
    ("Roads and Stormwater", "Share of roads, kerbs and stormwater works", "item", 1.0, 31_500),
]


SUPPLIERS = [
    ("TST-AGG", "Ubuntu Aggregates Test Supplies", "Aggregates and sand"),
    ("TST-CEM", "Sisonke Cement Distribution Test", "Cement"),
    ("TST-BRK", "Mzanzi Block and Brick Test Works", "Bricks and blocks"),
    ("TST-STL", "Imbokodo Reinforcing Test Steel", "Reinforcing steel and mesh"),
    ("TST-ROF", "Khanyisa Roofing Test Systems", "Roof trusses and sheeting"),
    ("TST-PLB", "Amanzi Plumbing Test Merchants", "Plumbing and sanitaryware"),
    ("TST-ELC", "Lethabo Electrical Test Wholesalers", "Electrical material"),
    ("TST-HDW", "Vuka Hardware Test Depot", "General hardware"),
    ("TST-PNT", "Spectrum Coatings Test SA", "Paint and coatings"),
    ("TST-TIL", "Ndlovu Tile and Floor Test Centre", "Tiles and flooring"),
    ("TST-FUL", "Masakhane Fuel Test Logistics", "Bulk diesel"),
    ("TST-PLT", "Siyakhula Plant Hire Test Services", "Plant hire"),
    ("TST-TRN", "Bophelo Transport Test Solutions", "Transport"),
    ("TST-PPE", "SafeSite PPE Test Distributors", "PPE"),
    ("TST-SEC", "Qapha Test Site Security", "Security"),
    ("TST-SUB", "Thuthukani Building Teams Test", "Building subcontractor"),
    ("TST-CIV", "Ikusasa Civils Test Contractors", "Civil subcontractor"),
    ("TST-WIN", "Amandla Window and Door Test Fabricators", "Windows and doors"),
]


STAFF = [
    ("Lerato Mokoena", "executive.test@ubuntu-housing.invalid", "OWNER", "Executive Director"),
    ("Thabo Dlamini", "admin.test@ubuntu-housing.invalid", "OFFICE_ADMIN", "Contract Manager"),
    ("Naledi Khumalo", "finance.test@ubuntu-housing.invalid", "OFFICE_ADMIN", "Finance Manager"),
    ("Zanele Mthembu", "procurement.test@ubuntu-housing.invalid", "PROCUREMENT_LEAD", "Procurement Lead"),
    ("Kabelo Ndlovu", "qs.test@ubuntu-housing.invalid", "OFFICE_USER", "Quantity Surveyor"),
    ("Ayesha Naidoo", "accounts.test@ubuntu-housing.invalid", "OFFICE_USER", "Accountant"),
    ("Sipho Cele", "pm.kzn.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Refilwe Molefe", "pm.gp.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Bulelwa Gqoboka", "pm.ec.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Mandla Nkosi", "pm.mp.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Tshepo Maseko", "pm.lp.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Palesa Mofokeng", "pm.fs.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Onkgopotse Modise", "pm.nw.test@ubuntu-housing.invalid", "OFFICE_USER", "Project Manager"),
    ("Sibusiso Zulu", "site.kzn.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Neo Masina", "site.gp.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Lwazi Mpondo", "site.ec.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Themba Mahlangu", "site.mp.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Mpho Mathiba", "site.lp.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Karabo Lephoi", "site.fs.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Boitumelo Seane", "site.nw.test@ubuntu-housing.invalid", "SITE_MANAGER", "Site Manager"),
    ("Nokuthula Ngcobo", "clerk.kzn.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Itumeleng Radebe", "clerk.gp.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Andisiwe Faku", "clerk.ec.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Precious Mabuza", "clerk.mp.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Rendani Netshifhefhe", "clerk.lp.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Kamohelo Tsolo", "clerk.fs.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Lesego Pilane", "clerk.nw.test@ubuntu-housing.invalid", "SITE_STAFF", "Site Clerk"),
    ("Nomsa Vilakazi", "readonly.test@ubuntu-housing.invalid", "READ_ONLY", "Client Observer"),
]


def seed_foundations(db: Session, counts: Counter) -> dict[str, Any]:
    password_hash = hash_password("HMH-Test-2026!")
    pin_hash = hash_password("2468")
    owner_id = sid("user", STAFF[0][1])
    user_rows = []
    for idx, (name, email, role, title) in enumerate(STAFF):
        created = NOW - timedelta(days=330 - min(idx, 20))
        user_rows.append(
            {
                "id": sid("user", email),
                "full_name": name,
                "email": email,
                "phone": f"+2700001{idx:04d}",
                "password_hash": password_hash,
                "role": role,
                "is_active": True,
                "must_reset_password": False,
                "pin_hash": pin_hash if role in {"SITE_MANAGER", "SITE_STAFF"} else None,
                "failed_login_attempts": 0,
                "created_by": None if idx == 0 else owner_id,
                "created_at": created,
                "updated_at": created,
            }
        )
    counts["users"] += insert_rows(db, "users", user_rows)

    company_id = sid("company", SEED_BATCH)
    counts["companies"] += insert_rows(
        db,
        "companies",
        [
            {
                "id": company_id,
                "name": "Ubuntu Housing & Infrastructure Contractors (Pty) Ltd — TEST DATA",
                "registration_number": "TEST/2018/123456/07",
                "contact_email": "office@ubuntu-housing.invalid",
                "contact_phone": "+27000000000",
                "address": "100 Test Avenue, Johannesburg, 2001",
                "notes": f"Synthetic contractor | seed_batch={SEED_BATCH}",
                "created_at": NOW - timedelta(days=365),
                "updated_at": NOW,
            }
        ],
    )

    supplier_rows = []
    for idx, (code, name, category) in enumerate(SUPPLIERS):
        supplier_rows.append(
            {
                "id": sid("supplier", code),
                "name": name,
                "code": code,
                "contact_name": f"Test Contact {idx + 1}",
                "contact_person": f"Test Contact {idx + 1}",
                "email": f"orders.{code.lower()}@suppliers.invalid",
                "phone": f"+2700002{idx:04d}",
                "whatsapp_number": None,
                "address": f"{20 + idx} Synthetic Industrial Road, South Africa",
                "vat_number": f"4{idx + 10:09d}",
                "bank_name": None,
                "bank_account": None,
                "bank_branch_code": None,
                "payment_terms": "30 days from statement",
                "payment_due_days": 30,
                "vat_registered": True,
                "pricing_method": "EX_VAT",
                "default_vat_rate": money(15),
                "is_active": True,
                "notes": f"TEST DATA | {category} | No real banking or contact details",
                "created_at": NOW - timedelta(days=350 - idx),
                "updated_at": NOW,
            }
        )
    counts["suppliers"] += insert_rows(db, "suppliers", supplier_rows)
    counts["company_supplier_links"] += insert_rows(
        db,
        "company_supplier_links",
        [
            {
                "id": sid("company-supplier", code),
                "company_id": company_id,
                "supplier_id": sid("supplier", code),
            }
            for code, _, _ in SUPPLIERS
        ],
    )

    stage_rows = [
        {
            "id": sid("stage", code),
            "name": name,
            "code": code,
            "sequence_order": sequence,
            "description": f"South African housing construction stage — {name}",
            "is_active": True,
            "created_at": NOW - timedelta(days=400),
            "updated_at": NOW,
        }
        for code, name, sequence in STAGES
    ]
    counts["stages"] += insert_rows(db, "stage_master", stage_rows)

    categories = sorted({category for category, *_ in BOQ_ITEMS})
    counts["item_categories"] += insert_rows(
        db,
        "item_categories",
        [
            {
                "id": sid("item-category", name),
                "name": name,
                "description": f"TEST DATA | {name}",
                "is_active": True,
                "created_at": NOW - timedelta(days=360),
                "updated_at": NOW,
            }
            for name in categories
        ],
    )
    item_rows = []
    for idx, (category, description, unit, _, rate) in enumerate(BOQ_ITEMS):
        item_rows.append(
            {
                "id": sid("item", idx),
                "name": description,
                "normalized_name": "".join(ch.lower() if ch.isalnum() else "_" for ch in description).strip("_"),
                "category_id": sid("item-category", category),
                "default_unit": unit,
                "item_type": "MATERIAL" if category != "Preliminaries" else "SERVICE",
                "is_active": True,
                "requires_remaining_photo": category in {"Concrete", "Reinforcing"},
                "is_high_risk": category in {"Reinforcing", "Roads and Stormwater"},
                "notes": f"TEST DATA | benchmark rate R{rate:,.2f}",
                "created_at": NOW - timedelta(days=360),
                "updated_at": NOW,
            }
        )
    counts["items"] += insert_rows(db, "items", item_rows)
    return {"owner_id": owner_id, "company_id": company_id}


def unit_progress(project_progress: int, lot_index: int, project_index: int) -> int:
    offset = ((lot_index * 17 + project_index * 11) % 23) - 11
    value = int(clamp(project_progress + offset, 0, 100))
    if project_progress == 100:
        return 100 if lot_index % 9 else 96
    return value


def seed_projects_and_progress(db: Session, ctx: dict[str, Any], counts: Counter) -> None:
    owner_id = ctx["owner_id"]
    company_id = ctx["company_id"]
    project_rows: list[dict[str, Any]] = []
    site_rows: list[dict[str, Any]] = []
    lot_rows: list[dict[str, Any]] = []
    stage_status_rows: list[dict[str, Any]] = []
    access_rows: list[dict[str, Any]] = []
    site_access_rows: list[dict[str, Any]] = []

    for pidx, spec in enumerate(PROJECTS):
        project_id = sid("project", spec["code"])
        start = TODAY - timedelta(days=spec["start_days"])
        finish = TODAY + timedelta(days=spec["finish_days"])
        description = (
            f"TEST DATA — Synthetic public-sector housing contract. {spec['scenario']} "
            f"Synthetic contract value R{spec['contract']:,.0f}; approved delivery budget "
            f"R{spec['budget']:,.0f}; forecast final cost R{spec['forecast']:,.0f}. "
            f"No real tender award is represented. seed_batch={SEED_BATCH}"
        )
        project_rows.append(
            {
                "id": project_id,
                "name": spec["name"],
                "code": spec["code"],
                "description": description,
                "location": spec["location"],
                "client_name": spec["municipality"] + " — SYNTHETIC",
                "company_id": company_id,
                "start_date": start,
                "estimated_end_date": finish,
                "go_live_date": start + timedelta(days=14),
                "budget": money(spec["budget"]),
                "status": spec["status"],
                "created_by": owner_id,
                "created_at": stamp(start - timedelta(days=21)),
                "updated_at": NOW - timedelta(days=pidx),
            }
        )

        main_site_id = sid("site", spec["code"], "main")
        store_site_id = sid("site", spec["code"], "store")
        site_rows.extend(
            [
                {
                    "id": main_site_id,
                    "project_id": project_id,
                    "name": f"{spec['province']} Housing Site",
                    "code": f"{spec['code']}-SITE",
                    "site_type": "construction_site",
                    "location_description": spec["location"],
                    "is_active": True,
                    "created_at": stamp(start),
                    "updated_at": NOW,
                },
                {
                    "id": store_site_id,
                    "project_id": project_id,
                    "name": "Site Store and Fuel Yard",
                    "code": f"{spec['code']}-STORE",
                    "site_type": "main_warehouse",
                    "location_description": f"Secure store within {spec['location']}",
                    "is_active": True,
                    "created_at": stamp(start),
                    "updated_at": NOW,
                },
            ]
        )

        pm_id = sid("user", STAFF[6 + pidx][1])
        site_manager_id = sid("user", STAFF[13 + pidx][1])
        site_clerk_id = sid("user", STAFF[20 + pidx][1])
        for user_id, edit, approve in [(site_manager_id, True, False), (site_clerk_id, True, False)]:
            access_rows.append(
                {
                    "id": sid("project-access", user_id, project_id),
                    "user_id": user_id,
                    "project_id": project_id,
                    "can_view": True,
                    "can_edit": edit,
                    "can_approve": approve,
                    "created_at": stamp(start),
                    "updated_at": NOW,
                }
            )
        for user_id in (site_manager_id, site_clerk_id):
            site_access_rows.append(
                {
                    "id": sid("site-access", user_id, main_site_id),
                    "user_id": user_id,
                    "site_id": main_site_id,
                    "can_receive_delivery": True,
                    "can_record_usage": True,
                    "can_request_stock": True,
                    "can_update_stage": user_id == site_manager_id,
                    "created_at": stamp(start),
                    "updated_at": NOW,
                }
            )

        for lidx in range(spec["units"]):
            lot_number = f"{(lidx // 25) + 1:02d}-{(lidx % 25) + 1:03d}"
            lot_id = sid("lot", spec["code"], lot_number)
            progress = unit_progress(spec["progress"], lidx, pidx)
            on_hold = spec["health"] == "RED" and lidx % 31 == 0 and progress < 75
            if on_hold:
                lot_status = "ON_HOLD"
            elif progress >= 95:
                lot_status = "COMPLETED"
            elif progress >= 5:
                lot_status = "IN_PROGRESS"
            else:
                lot_status = "AVAILABLE"
            current_stage_idx = min(len(STAGES) - 1, int(progress / 100 * len(STAGES)))
            current_stage = STAGES[current_stage_idx][1]
            lot_start = start + timedelta(days=(lidx % 8) * 7)
            completed_date = TODAY - timedelta(days=(lidx % 35) + 3) if lot_status == "COMPLETED" else None
            lot_rows.append(
                {
                    "id": lot_id,
                    "project_id": project_id,
                    "site_id": main_site_id,
                    "lot_number": lot_number,
                    "unit_type": "40 m² BNG Two-Bedroom Unit" if lidx % 5 else "45 m² Accessible BNG Unit",
                    "block_number": f"Block {(lidx // 25) + 1}",
                    "status": lot_status,
                    "buyer_name": None,
                    "manager_user_id": site_manager_id,
                    "start_date": lot_start,
                    "expected_completion_date": finish - timedelta(days=lidx % 20),
                    "actual_completion_date": completed_date,
                    "budgeted_cost": money(spec["budget"] / spec["units"] * 0.82),
                    "notes": f"TEST DATA | {progress}% | Current stage: {current_stage} | Synthetic Record",
                    "created_at": stamp(lot_start),
                    "updated_at": NOW - timedelta(days=lidx % 11),
                }
            )

            for sidx, (stage_code, stage_name, sequence) in enumerate(STAGES):
                stage_start_pct = sidx / len(STAGES) * 100
                stage_end_pct = (sidx + 1) / len(STAGES) * 100
                blocked = on_hold and sidx == current_stage_idx
                if progress >= stage_end_pct:
                    stage_status = "CERTIFIED" if sequence in {3, 4, 9, 13} else "COMPLETED"
                    stage_progress = 100
                elif progress > stage_start_pct:
                    stage_status = "BLOCKED" if blocked else "IN_PROGRESS"
                    stage_progress = int((progress - stage_start_pct) / (stage_end_pct - stage_start_pct) * 100)
                else:
                    stage_status = "NOT_STARTED"
                    stage_progress = 0
                planned = lot_start + timedelta(days=sequence * max(7, int((finish - start).days / 15)))
                started_at = stamp(planned - timedelta(days=6)) if stage_progress else None
                completed_at = stamp(planned - timedelta(days=2)) if stage_progress == 100 else None
                stage_status_rows.append(
                    {
                        "id": sid("stage-status", lot_id, stage_code),
                        "project_id": project_id,
                        "site_id": main_site_id,
                        "lot_id": lot_id,
                        "stage_id": sid("stage", stage_code),
                        "status": stage_status,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "certified_at": completed_at if stage_status == "CERTIFIED" else None,
                        "inspection_required": sequence in {3, 4, 9, 12, 13},
                        "certification_required": sequence in {3, 4, 9, 13},
                        "ready_for_labour_payment": stage_progress == 100,
                        "notes": "TEST DATA — synthetic milestone history",
                        "completion_notes": "Quality check passed against synthetic inspection checklist" if completed_at else None,
                        "completed_by_name": "Synthetic Site Quality Team" if completed_at else None,
                        "progress_pct": stage_progress,
                        "blocked_reason": "Material approval or weather delay under review" if blocked else None,
                        "planned_completion_date": planned,
                        "updated_by": pm_id,
                        "created_at": stamp(lot_start),
                        "updated_at": NOW - timedelta(days=lidx % 9),
                    }
                )

    counts["projects"] += insert_rows(db, "projects", project_rows)
    counts["sites"] += insert_rows(db, "sites", site_rows)
    counts["user_project_access"] += insert_rows(db, "user_project_access", access_rows)
    counts["user_site_access"] += insert_rows(db, "user_site_access", site_access_rows)
    counts["lots"] += insert_rows(db, "lots", lot_rows)
    counts["stage_statuses"] += insert_rows(db, "project_stage_status", stage_status_rows)


def seed_boq(db: Session, ctx: dict[str, Any], counts: Counter) -> None:
    """Create a substantial, project-level BOQ with realistic rates and quantities."""
    owner_id = ctx["owner_id"]
    header_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    boq_rows: list[dict[str, Any]] = []
    for pidx, spec in enumerate(PROJECTS):
        project_id = sid("project", spec["code"])
        header_id = sid("boq-header", spec["code"])
        imported_at = stamp(TODAY - timedelta(days=spec["start_days"] + 14))
        header_rows.append(
            {
                "id": header_id,
                "project_id": project_id,
                "version_name": "Approved Contract BOQ — TEST v1",
                "source_file_name": f"{spec['code']}_synthetic_boq.xlsx",
                "source_type": "EXCEL_IMPORT",
                "status": "ACTIVE",
                "is_active_version": True,
                "is_template": False,
                "uploaded_by": owner_id,
                "uploaded_at": imported_at,
                "notes": f"TEST DATA | Synthetic BOQ | seed_batch={SEED_BATCH}",
            }
        )
        categories: dict[str, uuid.UUID] = {}
        for sequence, category in enumerate(sorted({row[0] for row in BOQ_ITEMS}), start=1):
            section_id = sid("boq-section", spec["code"], category)
            categories[category] = section_id
            stage_index = min(sequence - 1, len(STAGES) - 1)
            section_rows.append(
                {
                    "id": section_id,
                    "boq_header_id": header_id,
                    "stage_id": sid("stage", STAGES[stage_index][0]),
                    "section_name": category,
                    "sequence_order": sequence,
                    "notes": "TEST DATA — synthetic tender section",
                    "created_at": imported_at,
                    "updated_at": imported_at,
                }
            )
        for iidx, (category, description, unit, per_unit_qty, rate) in enumerate(BOQ_ITEMS):
            regional_factor = Decimal(str(1 + (pidx - 3) * 0.012))
            planned_rate = money(Decimal(str(rate)) * regional_factor)
            planned_qty = Decimal(str(per_unit_qty * spec["units"])).quantize(Decimal("0.001"))
            boq_rows.append(
                {
                    "id": sid("boq-item", spec["code"], iidx),
                    "boq_section_id": categories[category],
                    "project_id": project_id,
                    "site_id": sid("site", spec["code"], "main"),
                    "lot_id": None,
                    "stage_id": sid("stage", STAGES[min(iidx // 2, len(STAGES) - 1)][0]),
                    "item_id": sid("item", iidx),
                    "supplier_id": None,
                    "raw_description": description,
                    "normalized_description": description.lower(),
                    "specification": "Synthetic BNG housing specification for presentation use only",
                    "item_type": "SERVICE" if category == "Preliminaries" else "MATERIAL",
                    "unit": unit,
                    "planned_quantity": planned_qty,
                    "planned_rate": planned_rate,
                    "sort_order": iidx + 1,
                    "is_active": True,
                    "notes": "TEST DATA",
                    "created_at": imported_at,
                    "updated_at": NOW,
                }
            )
    counts["boq_headers"] += insert_rows(db, "boq_headers", header_rows)
    counts["boq_sections"] += insert_rows(db, "boq_sections", section_rows)
    counts["boq_items"] += insert_rows(db, "boq_items", boq_rows)


def procurement_status(spec: dict[str, Any], index: int) -> str:
    if index < 8:
        return "CONVERTED_TO_PO"
    if index < 10:
        return "APPROVED"
    if spec["code"] == "TEST-GP-TEM-34" and index < 15:
        return "PENDING_APPROVAL"
    if index in {10, 11, 12}:
        return "PENDING_APPROVAL"
    if index == 13:
        return "SUBMITTED"
    if index == 14:
        return "REJECTED"
    if index == 15:
        return "APPROVED"
    return "DRAFT"


def seed_procurement(db: Session, ctx: dict[str, Any], counts: Counter) -> None:
    """Create chronological MR → quote → PO → delivery → invoice → payment chains."""
    owner_id = ctx["owner_id"]
    admin_id = sid("user", STAFF[1][1])
    finance_id = sid("user", STAFF[2][1])
    procurement_id = sid("user", STAFF[3][1])
    qs_id = sid("user", STAFF[4][1])

    mr_rows: list[dict[str, Any]] = []
    mr_item_rows: list[dict[str, Any]] = []
    approval_rows: list[dict[str, Any]] = []
    quotation_rows: list[dict[str, Any]] = []
    mr_quote_rows: list[dict[str, Any]] = []
    quote_vote_rows: list[dict[str, Any]] = []
    po_rows: list[dict[str, Any]] = []
    po_item_rows: list[dict[str, Any]] = []
    delivery_rows: list[dict[str, Any]] = []
    delivery_item_rows: list[dict[str, Any]] = []
    invoice_rows: list[dict[str, Any]] = []
    matching_rows: list[dict[str, Any]] = []
    payment_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for pidx, spec in enumerate(PROJECTS):
        project_id = sid("project", spec["code"])
        site_id = sid("site", spec["code"], "main")
        store_id = sid("site", spec["code"], "store")
        requester_id = sid("user", STAFF[20 + pidx][1])
        start = TODAY - timedelta(days=spec["start_days"])
        for midx in range(18):
            item_a = (midx * 2 + pidx) % len(BOQ_ITEMS)
            item_b = (item_a + 1) % len(BOQ_ITEMS)
            first_possible = start + timedelta(days=24)
            proposed = TODAY - timedelta(days=max(8, 252 - midx * 14 - pidx * 2))
            request_day = max(first_possible, proposed)
            status = procurement_status(spec, midx)
            mr_id = sid("mr", spec["code"], midx)
            over_boq = spec["code"] == "TEST-MP-EMA-11" and midx in {5, 9, 15}
            rejected = status == "REJECTED"
            approved = status in {"APPROVED", "CONVERTED_TO_PO"}
            needed_by = request_day + timedelta(days=18)
            if spec["code"] == "TEST-GP-TEM-34" and status == "PENDING_APPROVAL":
                needed_by = TODAY - timedelta(days=4 + midx % 3)
            supplier_idx = (midx + pidx * 3) % len(SUPPLIERS)
            mr_rows.append(
                {
                    "id": mr_id,
                    "request_number": f"MR-{spec['code'][-5:]}-{midx + 1:03d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "lot_id": None,
                    "requested_by": requester_id,
                    "status": status,
                    "notes": f"TEST DATA | {BOQ_ITEMS[item_a][0]} procurement batch | Synthetic Record",
                    "is_active": True,
                    "stage_id": sid("stage", STAGES[min(midx // 2, len(STAGES) - 1)][0]),
                    "preferred_supplier_id": sid("supplier", SUPPLIERS[supplier_idx][0]),
                    "requested_date": stamp(request_day, 8),
                    "needed_by_date": needed_by,
                    "reviewed_by": admin_id if approved or rejected else None,
                    "reviewed_at": stamp(request_day + timedelta(days=1), 13) if approved or rejected else None,
                    "rejection_reason": "Quantity and specification require correction before resubmission" if rejected else None,
                    "priority": "HIGH" if needed_by <= TODAY else ("URGENT" if midx == 15 else "NORMAL"),
                    "delivery_destination": "SITE_STORE",
                    "over_boq": over_boq,
                    "over_boq_reason": "Roads and reinforcement quantity exceeds current allowance" if over_boq else None,
                    "approved_by": procurement_id if approved else None,
                    "approved_at": stamp(request_day + timedelta(days=3), 10) if approved else None,
                    "converted_to_po_at": stamp(request_day + timedelta(days=7), 11) if status == "CONVERTED_TO_PO" else None,
                    "issuing_company": "HMH_GROUP",
                    "procurement_category": "MATERIAL",
                    "created_at": stamp(request_day, 8),
                    "updated_at": stamp(request_day + timedelta(days=3 if approved else 1), 11),
                }
            )

            item_payload: list[tuple[int, Decimal, Decimal]] = []
            for line, item_idx in enumerate((item_a, item_b), start=1):
                _, description, unit, per_unit_qty, rate = BOQ_ITEMS[item_idx]
                share = Decimal(str(0.045 + (midx % 4) * 0.012))
                qty = Decimal(str(per_unit_qty * spec["units"])) * share
                qty = max(qty, Decimal("1" if unit in {"item", "number"} else "5"))
                qty = qty.quantize(Decimal("0.001"))
                approved_qty = qty if approved else None
                mr_item_id = sid("mr-item", spec["code"], midx, line)
                mr_item_rows.append(
                    {
                        "id": mr_item_id,
                        "request_id": mr_id,
                        "material_request_id": mr_id,
                        "item_id": sid("item", item_idx),
                        "boq_item_id": sid("boq-item", spec["code"], item_idx),
                        "description": description,
                        "quantity_requested": qty,
                        "quantity_approved": approved_qty,
                        "requested_quantity": qty,
                        "approved_quantity": approved_qty,
                        "over_boq_quantity": qty * Decimal("0.12") if over_boq else Decimal("0"),
                        "unit": unit,
                        "remarks": "TEST DATA — synthetic quantity",
                        "preferred_supplier_id": sid("supplier", SUPPLIERS[supplier_idx][0]),
                        "extra_reason_type": "BREAKAGE" if over_boq and line == 1 else None,
                        "extra_reason_notes": "Additional reinforcement due to revised synthetic civil detail" if over_boq and line == 1 else None,
                        "created_at": stamp(request_day, 8),
                    }
                )
                item_payload.append((item_idx, qty, Decimal(str(rate))))

            if approved:
                for aidx, approver in enumerate((admin_id, qs_id, procurement_id)):
                    approval_rows.append(
                        {
                            "id": sid("mr-approval", mr_id, aidx),
                            "mr_id": mr_id,
                            "approved_by": approver,
                            "approved_at": stamp(request_day + timedelta(days=aidx + 1), 9 + aidx),
                            "is_override": False,
                            "notes": ["Quantity checked against programme", "Budget availability confirmed", "Supplier documents verified"][aidx],
                        }
                    )

            if status not in {"CONVERTED_TO_PO", "APPROVED"}:
                continue

            # Three competing supplier quotations; the winner rotates.
            quote_ids: list[uuid.UUID] = []
            quote_totals: list[Decimal] = []
            winner = (midx + pidx) % 3
            cost_risk_factor = Decimal("2.35") if spec["code"] == "TEST-MP-EMA-11" and midx in {5, 9} else Decimal("1")
            for qidx in range(3):
                candidate_idx = (supplier_idx + qidx) % len(SUPPLIERS)
                factor = [Decimal("1.045"), Decimal("0.982"), Decimal("1.018")][(qidx - winner) % 3]
                total = sum(qty * rate for _, qty, rate in item_payload) * factor * cost_risk_factor
                net = money(total)
                vat = money(net * Decimal("0.15"))
                quote_id = sid("quotation", spec["code"], midx, qidx)
                quote_ids.append(quote_id)
                quote_totals.append(net + vat)
                quotation_rows.append(
                    {
                        "id": quote_id,
                        "quote_number": f"QT-{spec['code'][-5:]}-{midx + 1:03d}-{qidx + 1}",
                        "supplier_id": sid("supplier", SUPPLIERS[candidate_idx][0]),
                        "project_id": project_id,
                        "material_request_id": mr_id,
                        "status": "APPROVED" if qidx == winner else "REJECTED",
                        "quote_date": request_day + timedelta(days=4),
                        "expiry_date": request_day + timedelta(days=34),
                        "net_amount": net,
                        "vat_amount": vat,
                        "gross_amount": net + vat,
                        "vat_rate_used": money(15),
                        "notes": "TEST DATA | Synthetic supplier quotation comparison",
                        "created_by": procurement_id,
                        "created_at": stamp(request_day + timedelta(days=4)),
                        "updated_at": stamp(request_day + timedelta(days=6)),
                    }
                )

            if status != "CONVERTED_TO_PO":
                continue

            po_id = sid("po", spec["code"], midx)
            po_day = request_day + timedelta(days=8)
            selected_supplier_idx = (supplier_idx + winner) % len(SUPPLIERS)
            selected_total = quote_totals[winner]
            po_status = "RECEIVED" if midx < 7 else "SENT"
            po_rows.append(
                {
                    "id": po_id,
                    "po_number": f"PO-{spec['code'][-5:]}-{midx + 1:03d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "supplier_id": sid("supplier", SUPPLIERS[selected_supplier_idx][0]),
                    "material_request_id": mr_id,
                    "status": po_status,
                    "vat_mode": "EXCLUSIVE",
                    "subtotal_amount": money(selected_total / Decimal("1.15")),
                    "vat_amount": money(selected_total - selected_total / Decimal("1.15")),
                    "total_amount": selected_total,
                    "expected_delivery_date": po_day + timedelta(days=12),
                    "delivery_address": spec["location"],
                    "notes": "TEST DATA — synthetic purchase order; no external dispatch",
                    "created_by": procurement_id,
                    "po_date": stamp(po_day),
                    "approved_by": admin_id,
                    "sent_at": stamp(po_day + timedelta(days=1)) if po_status == "SENT" else stamp(po_day),
                    "delivery_destination": "SITE_STORE",
                    "quotation_id": quote_ids[winner],
                    "issuing_company": "HMH_GROUP",
                    "is_active": True,
                    "created_at": stamp(po_day),
                    "updated_at": stamp(po_day + timedelta(days=1)),
                }
            )
            for qidx in range(3):
                candidate_idx = (supplier_idx + qidx) % len(SUPPLIERS)
                for line, (item_idx, qty, rate) in enumerate(item_payload, start=1):
                    unit_price = money(rate * ([Decimal("1.045"), Decimal("0.982"), Decimal("1.018")][(qidx - winner) % 3]) * cost_risk_factor)
                    mr_quote_id = sid("mr-quote", spec["code"], midx, qidx, line)
                    mr_quote_rows.append(
                        {
                            "id": mr_quote_id,
                            "material_request_id": mr_id,
                            "supplier_id": sid("supplier", SUPPLIERS[candidate_idx][0]),
                            "item_id": sid("item", item_idx),
                            "description": BOQ_ITEMS[item_idx][1],
                            "quoted_quantity": qty,
                            "unit": BOQ_ITEMS[item_idx][2],
                            "unit_price": unit_price,
                            "total_price": money(qty * unit_price),
                            "delivery_date": po_day + timedelta(days=10 + qidx * 2),
                            "validity_date": po_day + timedelta(days=28),
                            "notes": "TEST DATA | selected on balanced price and delivery" if qidx == winner else "TEST DATA | alternate quote",
                            "is_selected": qidx == winner,
                            "created_by": procurement_id,
                            "source": "MANUAL",
                            "status": "APPROVED" if qidx == winner else "REJECTED",
                            "boq_unit_price": money(rate),
                            "rejection_reason": None if qidx == winner else "Not the best evaluated combination of price and delivery",
                            "rejected_at": None if qidx == winner else stamp(po_day - timedelta(days=1)),
                            "approved_at": stamp(po_day - timedelta(days=1)) if qidx == winner else None,
                            "purchase_order_id": po_id if qidx == winner else None,
                            "created_at": stamp(request_day + timedelta(days=4)),
                        }
                    )
                    if qidx == winner:
                        for vidx, voter in enumerate((admin_id, qs_id, procurement_id)):
                            quote_vote_rows.append(
                                {
                                    "id": sid("mr-quote-vote", mr_quote_id, vidx),
                                    "quote_id": mr_quote_id,
                                    "voted_by": voter,
                                    "voted_at": stamp(request_day + timedelta(days=5 + vidx), 9 + vidx),
                                    "is_override": False,
                                    "notes": "Commercial and technical review complete",
                                }
                            )

            for line, (item_idx, qty, rate) in enumerate(item_payload, start=1):
                adjusted_rate = money(rate * cost_risk_factor * Decimal("0.982"))
                po_item_rows.append(
                    {
                        "id": sid("po-item", spec["code"], midx, line),
                        "purchase_order_id": po_id,
                        "item_id": sid("item", item_idx),
                        "boq_item_id": sid("boq-item", spec["code"], item_idx),
                        "description": BOQ_ITEMS[item_idx][1],
                        "quantity": qty,
                        "quantity_ordered": qty,
                        "quantity_received": qty if midx < 7 else Decimal("0"),
                        "unit": BOQ_ITEMS[item_idx][2],
                        "unit_price": adjusted_rate,
                        "rate": adjusted_rate,
                        "vat_rate": money(15),
                        "vat_mode": "EXCLUSIVE",
                        "line_total": money(qty * adjusted_rate),
                        "stage_id": sid("stage", STAGES[min(midx // 2, len(STAGES) - 1)][0]),
                        "created_at": stamp(po_day),
                    }
                )

            if midx >= 7:
                continue
            delivery_id = sid("delivery", spec["code"], midx)
            delivery_day = po_day + timedelta(days=9 + midx % 4)
            discrepancy = midx == 6 and spec["health"] != "GREEN"
            delivery_rows.append(
                {
                    "id": delivery_id,
                    "delivery_number": f"DEL-{spec['code'][-5:]}-{midx + 1:03d}",
                    "purchase_order_id": po_id,
                    "supplier_id": sid("supplier", SUPPLIERS[selected_supplier_idx][0]),
                    "project_id": project_id,
                    "site_id": site_id,
                    "received_by_user_id": requester_id,
                    "delivery_date": stamp(delivery_day, 11),
                    "supplier_delivery_note_number": f"SDN-TEST-{pidx + 1}{midx + 1:03d}",
                    "delivery_status": "PARTIALLY_RECEIVED" if discrepancy else "RECEIVED",
                    "comments": "Short delivery recorded; balance requested" if discrepancy else "Quantity and condition verified — TEST DATA",
                    "receiver_name": STAFF[20 + pidx][0],
                    "driver_name": f"Synthetic Driver {pidx + 1}-{midx + 1}",
                    "is_active": True,
                    "created_at": stamp(delivery_day, 11),
                    "updated_at": stamp(delivery_day, 12),
                }
            )
            for line, (item_idx, qty, rate) in enumerate(item_payload, start=1):
                received = qty * Decimal("0.82") if discrepancy and line == 1 else qty
                delivery_item_rows.append(
                    {
                        "id": sid("delivery-item", spec["code"], midx, line),
                        "delivery_id": delivery_id,
                        "purchase_order_item_id": sid("po-item", spec["code"], midx, line),
                        "item_id": sid("item", item_idx),
                        "boq_item_id": sid("boq-item", spec["code"], item_idx),
                        "description": BOQ_ITEMS[item_idx][1],
                        "quantity_expected": qty,
                        "quantity_received": received,
                        "unit": BOQ_ITEMS[item_idx][2],
                        "discrepancy_reason": "Short quantity on supplier delivery note" if received != qty else None,
                        "created_at": stamp(delivery_day, 11),
                    }
                )
                stock_rows.append(
                    {
                        "id": sid("stock-delivery", spec["code"], midx, line),
                        "project_id": project_id,
                        "site_id": store_id,
                        "lot_id": None,
                        "item_id": sid("item", item_idx),
                        "boq_item_id": sid("boq-item", spec["code"], item_idx),
                        "movement_type": "DELIVERY_RECEIVED",
                        "reference_type": "delivery",
                        "reference_id": delivery_id,
                        "quantity_in": received,
                        "quantity_out": Decimal("0"),
                        "unit": BOQ_ITEMS[item_idx][2],
                        "unit_cost": money(rate),
                        "movement_date": stamp(delivery_day, 12),
                        "entered_by": requester_id,
                        "notes": "TEST DATA — verified receipt",
                        "created_at": stamp(delivery_day, 12),
                    }
                )

            if midx >= 6:
                continue
            invoice_id = sid("invoice", spec["code"], midx)
            invoice_day = delivery_day + timedelta(days=3)
            invoice_status = "PAID" if midx < 4 else ("PARTIALLY_PAID" if midx == 4 else "MATCHED")
            invoice_rows.append(
                {
                    "id": invoice_id,
                    "invoice_number": f"INV-{spec['code'][-5:]}-{midx + 1:03d}",
                    "supplier_id": sid("supplier", SUPPLIERS[selected_supplier_idx][0]),
                    "project_id": project_id,
                    "site_id": site_id,
                    "purchase_order_id": po_id,
                    "invoice_date": invoice_day,
                    "due_date": invoice_day + timedelta(days=30),
                    "subtotal_amount": money(selected_total / Decimal("1.15")),
                    "vat_amount": money(selected_total - selected_total / Decimal("1.15")),
                    "total_amount": selected_total,
                    "status": invoice_status,
                    "captured_by": finance_id,
                    "captured_at": stamp(invoice_day),
                    "notes": "TEST DATA — synthetic tax invoice; no real supplier liability",
                    "vat_rate_used": money(15),
                    "is_active": True,
                    "created_at": stamp(invoice_day),
                    "updated_at": stamp(invoice_day + timedelta(days=1)),
                }
            )
            matching_rows.append(
                {
                    "id": sid("invoice-match", spec["code"], midx),
                    "invoice_id": invoice_id,
                    "purchase_order_id": po_id,
                    "delivery_id": delivery_id,
                    "match_status": "MATCHED",
                    "quantity_match": True,
                    "amount_match": True,
                    "supplier_match": True,
                    "notes": "Four-way match passed on synthetic documents",
                    "checked_by": finance_id,
                    "checked_at": stamp(invoice_day + timedelta(days=1)),
                    "created_at": stamp(invoice_day + timedelta(days=1)),
                }
            )
            reconciliation_rows.append(
                {
                    "id": sid("proc-recon", spec["code"], midx),
                    "reconciliation_number": f"REC-{spec['code'][-5:]}-{midx + 1:03d}",
                    "status": "MATCHED",
                    "purchase_order_id": po_id,
                    "invoice_id": invoice_id,
                    "delivery_id": delivery_id,
                    "quotation_id": quote_ids[winner],
                    "material_request_id": mr_id,
                    "variance_data": {"quantity_variance": 0, "amount_variance": 0, "synthetic": True},
                    "notes": "TEST DATA — reconciled",
                    "reviewed_by": finance_id,
                    "reviewed_at": stamp(invoice_day + timedelta(days=1)),
                    "created_by": finance_id,
                    "created_at": stamp(invoice_day + timedelta(days=1)),
                    "updated_at": stamp(invoice_day + timedelta(days=1)),
                }
            )
            if invoice_status in {"PAID", "PARTIALLY_PAID"}:
                paid_amount = selected_total if invoice_status == "PAID" else money(selected_total * Decimal("0.55"))
                payment_day = invoice_day + timedelta(days=24)
                payment_rows.append(
                    {
                        "id": sid("payment", spec["code"], midx),
                        "project_id": project_id,
                        "supplier_id": sid("supplier", SUPPLIERS[selected_supplier_idx][0]),
                        "invoice_id": invoice_id,
                        "payment_type": "SUPPLIER",
                        "amount": paid_amount,
                        "amount_paid": paid_amount,
                        "payment_date": payment_day,
                        "reference": f"TEST-EFT-{pidx + 1}{midx + 1:04d}",
                        "payment_reference": f"TEST-EFT-{pidx + 1}{midx + 1:04d}",
                        "payment_method": "TEST EFT",
                        "status": "PAID",
                        "notes": "TEST DATA — no real payment was made",
                        "created_by": finance_id,
                        "approved_by": owner_id,
                        "captured_by": finance_id,
                        "is_active": True,
                        "created_at": stamp(payment_day),
                        "updated_at": stamp(payment_day),
                    }
                )
            audit_rows.append(
                {
                    "id": sid("audit-procurement", spec["code"], midx),
                    "actor_id": procurement_id,
                    "action": "CREATE",
                    "entity_type": "PURCHASE_ORDER",
                    "entity_id": po_id,
                    "before_value": None,
                    "after_value": {"status": po_status, "seed_batch": SEED_BATCH},
                    "notes": "TEST DATA — synthetic procurement audit event",
                    "ip_address": "192.0.2.10",
                    "created_at": stamp(po_day),
                }
            )

    for name, rows in [
        ("material_requests", mr_rows),
        ("material_request_items", mr_item_rows),
        ("mr_approvals", approval_rows),
        ("quotations", quotation_rows),
        ("purchase_orders", po_rows),
        ("mr_quotes", mr_quote_rows),
        ("mr_quote_votes", quote_vote_rows),
        ("purchase_order_items", po_item_rows),
        ("deliveries", delivery_rows),
        ("delivery_items", delivery_item_rows),
        ("invoices", invoice_rows),
        ("invoice_matching_results", matching_rows),
        ("payments", payment_rows),
        ("procurement_reconciliations", reconciliation_rows),
        ("stock_ledger", stock_rows),
        ("audit_events", audit_rows),
    ]:
        counts[name] += insert_rows(db, name, rows)


VEHICLE_TYPES = [
    ("Toyota", "Hilux 2.4 GD-6", "BAKKIE", 80, 9.2, False, None),
    ("Isuzu", "FTR 850 Dropside", "TRUCK", 200, 24.0, False, None),
    ("Bell", "315SL TLB", "TLB", 145, None, True, 11.5),
    ("Caterpillar", "320 Excavator", "EXCAVATOR", 410, None, True, 18.0),
]


def synthetic_registration(project_index: int, vehicle_index: int) -> str:
    province_suffix = ["ZN", "GP", "EC", "MP", "L", "FS", "NW"][project_index]
    return f"T{project_index + 1}{vehicle_index + 2:02d} ST {province_suffix}"


def seed_fleet_and_fuel(db: Session, ctx: dict[str, Any], counts: Counter) -> None:
    owner_id = ctx["owner_id"]
    admin_id = sid("user", STAFF[1][1])
    procurement_id = sid("user", STAFF[3][1])
    fuel_supplier_id = sid("supplier", "TST-FUL")
    diesel_id = sid("fuel-type", "DIESEL")
    counts["fuel_types"] += insert_rows(
        db,
        "fuel_types",
        [
            {
                "id": diesel_id,
                "code": "DIESEL",
                "name": "50 ppm Diesel",
                "is_active": True,
                "created_at": NOW - timedelta(days=400),
                "updated_at": NOW,
            },
            {
                "id": sid("fuel-type", "PETROL"),
                "code": "PETROL",
                "name": "Unleaded Petrol 95",
                "is_active": True,
                "created_at": NOW - timedelta(days=400),
                "updated_at": NOW,
            },
        ],
    )

    vehicle_rows: list[dict[str, Any]] = []
    vehicle_cost_rows: list[dict[str, Any]] = []
    storage_rows: list[dict[str, Any]] = []
    profile_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    order_history_rows: list[dict[str, Any]] = []
    delivery_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    adjustment_rows: list[dict[str, Any]] = []
    legacy_log_rows: list[dict[str, Any]] = []

    for pidx, spec in enumerate(PROJECTS):
        project_id = sid("project", spec["code"])
        site_id = sid("site", spec["code"], "main")
        store_id = sid("site", spec["code"], "store")
        site_manager_id = sid("user", STAFF[13 + pidx][1])
        storage_id = sid("fuel-storage", spec["code"])
        storage_rows.append(
            {
                "id": storage_id,
                "project_id": project_id,
                "site_id": store_id,
                "fuel_type_id": diesel_id,
                "name": "Bundled Site Diesel Tank — TEST",
                "location_type": "FIXED_TANK",
                "capacity_litres": money(10_000),
                "low_stock_threshold_litres": money(1_200),
                "is_active": True,
                "notes": f"TEST DATA | Synthetic storage for {spec['code']}",
                "cutover_confirmed_at": stamp(TODAY - timedelta(days=280)),
                "cutover_confirmed_by": owner_id,
                "created_at": stamp(TODAY - timedelta(days=300)),
                "updated_at": NOW,
            }
        )

        vehicle_ids: list[uuid.UUID] = []
        for vidx, (make, model, vehicle_type, tank, per_100, uses_hours, per_hour) in enumerate(VEHICLE_TYPES):
            vehicle_id = sid("vehicle", spec["code"], vidx)
            vehicle_ids.append(vehicle_id)
            registration = synthetic_registration(pidx, vidx)
            current_odometer = None if uses_hours else Decimal(str(42_000 + pidx * 6_100 + vidx * 8_300))
            current_hours = Decimal(str(2_100 + pidx * 180 + vidx * 95)) if uses_hours else None
            vehicle_rows.append(
                {
                    "id": vehicle_id,
                    "registration": registration,
                    "name": f"{make} {model} — {spec['province']} TEST",
                    "vehicle_type": vehicle_type,
                    "status": "MAINTENANCE" if pidx == 2 and vidx == 3 else "ACTIVE",
                    "assigned_project_id": project_id,
                    "assigned_site_id": site_id,
                    "last_service_date": TODAY - timedelta(days=35 + vidx * 12),
                    "next_service_date": TODAY + timedelta(days=55 - vidx * 8),
                    "notes": "TEST DATA | Synthetic registration; not linked to a real vehicle",
                    "created_by": owner_id,
                    "make": make,
                    "model": model,
                    "year": 2019 + ((pidx + vidx) % 6),
                    "fuel_type": "DIESEL",
                    "tank_capacity_l": money(tank),
                    "fuel_consumption_per_100km": money(per_100) if per_100 else None,
                    "current_odometer_km": current_odometer,
                    "service_interval_km": 10_000 if not uses_hours else None,
                    "vin_number": f"TESTVIN{pidx + 1:02d}{vidx + 1:02d}000000000",
                    "uses_hours": uses_hours,
                    "current_hours_reading": current_hours,
                    "fuel_consumption_per_hour": money(per_hour) if per_hour else None,
                    "fuel_tolerance_pct": money(18),
                    "fuel_minimum_issue_interval_hours": money(6),
                    "fuel_override_required": True,
                    "hour_meter_required": uses_hours,
                    "created_at": NOW - timedelta(days=350),
                    "updated_at": NOW,
                }
            )
            profile_rows.append(
                {
                    "id": sid("fuel-profile", spec["code"], vidx),
                    "project_id": project_id,
                    "site_id": site_id,
                    "equipment_reference": registration if not uses_hours else f"{vehicle_type}-{pidx + 1:02d}-{vidx + 1:02d}",
                    "destination_type": "VEHICLE" if not uses_hours else "PLANT",
                    "expected_litres_per_hour": money(per_hour) if per_hour else None,
                    "tolerance_pct": money(18),
                    "tank_capacity_litres": money(tank),
                    "minimum_issue_interval_hours": money(6),
                    "hour_meter_required": uses_hours,
                    "override_required": True,
                    "is_active": True,
                    "created_at": NOW - timedelta(days=300),
                    "updated_at": NOW,
                }
            )
            for cidx in range(3):
                cost_day = TODAY - timedelta(days=210 - cidx * 70 + vidx * 3)
                vehicle_cost_rows.append(
                    {
                        "id": sid("vehicle-cost", spec["code"], vidx, cidx),
                        "vehicle_id": vehicle_id,
                        "cost_type": ["SERVICE", "TYRE", "REPAIR"][cidx],
                        "amount": money([4_800, 7_600, 3_950][cidx] * (1 + pidx * 0.03)),
                        "description": ["Scheduled service", "Tyre replacement", "Minor hydraulic or suspension repair"][cidx],
                        "project_id": project_id,
                        "site_id": site_id,
                        "cost_date": cost_day,
                        "recorded_by": site_manager_id,
                        "notes": "TEST DATA — synthetic fleet cost",
                        "created_at": stamp(cost_day),
                    }
                )

        calculated_balance = Decimal("0")
        start_month = TODAY.replace(day=1) - timedelta(days=300)
        start_month = start_month.replace(day=1)
        previous_odometer = defaultdict(lambda: Decimal("15000"))
        previous_hours = defaultdict(lambda: Decimal("900"))
        for month_idx in range(10):
            month_day = (start_month + timedelta(days=month_idx * 30)).replace(day=1)
            if month_day > TODAY:
                break
            order_id = sid("fuel-order", spec["code"], month_idx)
            delivery_id = sid("fuel-delivery", spec["code"], month_idx)
            delivery_litres = Decimal(str(4_200 + ((month_idx + pidx) % 3) * 300))
            litre_rate = money(21.10 + month_idx * 0.18 + pidx * 0.05)
            order_rows.append(
                {
                    "id": order_id,
                    "order_number": f"FO-{spec['code'][-5:]}-{month_idx + 1:03d}",
                    "project_id": project_id,
                    "site_id": store_id,
                    "fuel_type_id": diesel_id,
                    "supplier_id": fuel_supplier_id,
                    "storage_location_id": storage_id,
                    "requested_by": site_manager_id,
                    "request_date": month_day + timedelta(days=2),
                    "requested_litres": delivery_litres,
                    "expected_delivery_date": month_day + timedelta(days=6),
                    "delivery_location": spec["location"],
                    "purpose": "Plant, fleet and generator operations — TEST DATA",
                    "status": "CLOSED",
                    "approved_by": procurement_id,
                    "approved_at": stamp(month_day + timedelta(days=3)),
                    "supplier_reference": f"TEST-FUEL-{pidx + 1}-{month_idx + 1}",
                    "purchase_order_reference": f"TEST-FPO-{pidx + 1}-{month_idx + 1:03d}",
                    "submitted_at": stamp(month_day + timedelta(days=2)),
                    "ordered_at": stamp(month_day + timedelta(days=4)),
                    "closed_at": stamp(month_day + timedelta(days=7)),
                    "intended_use": "SITE_OPERATIONS",
                    "destination_type": "STORAGE",
                    "notes": "TEST DATA — synthetic bulk diesel order",
                    "feasibility_status": "FEASIBLE",
                    "created_at": stamp(month_day + timedelta(days=2)),
                    "updated_at": stamp(month_day + timedelta(days=7)),
                }
            )
            history_steps = [
                (None, "REQUESTED", site_manager_id, 2),
                ("REQUESTED", "APPROVED", procurement_id, 3),
                ("APPROVED", "ORDERED", procurement_id, 4),
                ("ORDERED", "CLOSED", site_manager_id, 7),
            ]
            for hidx, (from_status, to_status, actor, day_offset) in enumerate(history_steps):
                order_history_rows.append(
                    {
                        "id": sid("fuel-order-history", spec["code"], month_idx, hidx),
                        "order_id": order_id,
                        "from_status": from_status,
                        "to_status": to_status,
                        "actor_id": actor,
                        "reason": "Synthetic approval workflow completed",
                        "created_at": stamp(month_day + timedelta(days=day_offset)),
                    }
                )
            delivered_at = stamp(month_day + timedelta(days=7), 10)
            delivery_rows.append(
                {
                    "id": delivery_id,
                    "site_id": store_id,
                    "project_id": project_id,
                    "delivery_date": delivered_at.date(),
                    "fuel_type": "DIESEL",
                    "litres_delivered": delivery_litres,
                    "cost_per_litre": litre_rate,
                    "supplier_name": "Masakhane Fuel Test Logistics",
                    "invoice_number": f"FUEL-INV-TEST-{pidx + 1}-{month_idx + 1:03d}",
                    "notes": "TEST DATA — meter readings checked",
                    "recorded_by": site_manager_id,
                    "order_id": order_id,
                    "supplier_id": fuel_supplier_id,
                    "fuel_type_id": diesel_id,
                    "storage_location_id": storage_id,
                    "delivered_at": delivered_at,
                    "delivery_note_number": f"FDN-TEST-{pidx + 1}-{month_idx + 1:03d}",
                    "opening_reading": money(month_idx * 10_000),
                    "closing_reading": money(month_idx * 10_000 + delivery_litres),
                    "calculated_received_litres": delivery_litres,
                    "confirmed_litres": delivery_litres,
                    "variance_litres": money(0),
                    "tanker_registration": f"TEST TK {pidx + 1:02d}-{month_idx + 10:02d}",
                    "driver_details": f"Synthetic Fuel Driver {month_idx + 1}",
                    "received_by": site_manager_id,
                    "verification_status": "VERIFIED",
                    "verified_by": site_manager_id,
                    "verified_at": delivered_at + timedelta(hours=1),
                    "excess_override": False,
                    "supplier_variance_litres": money(0),
                    "meter_variance_litres": money(0),
                    "is_manual_emergency": False,
                    "created_at": delivered_at,
                    "updated_at": delivered_at + timedelta(hours=1),
                }
            )
            calculated_balance += delivery_litres

            month_issue_total = Decimal("0")
            for issue_idx in range(12):
                vehicle_idx = (issue_idx + month_idx + pidx) % len(vehicle_ids)
                vehicle_id = vehicle_ids[vehicle_idx]
                make, model, vehicle_type, _, per_100, uses_hours, per_hour = VEHICLE_TYPES[vehicle_idx]
                issue_day = month_day + timedelta(days=9 + issue_idx)
                if issue_day > TODAY:
                    continue
                anomaly = ((issue_idx + month_idx * 3 + pidx * 5) % 13 == 0)
                litres = Decimal(str(245 + (issue_idx % 4) * 22))
                if anomaly:
                    litres += Decimal("85")
                distance = Decimal(str(720 + issue_idx * 18)) if not uses_hours else None
                operating_hours = Decimal(str(18 + issue_idx % 5)) if uses_hours else None
                l_per_100 = money(litres / distance * 100) if distance else None
                l_per_hour = money(litres / operating_hours) if operating_hours else None
                previous_odometer[vehicle_id] += distance or Decimal("0")
                previous_hours[vehicle_id] += operating_hours or Decimal("0")
                issue_id = sid("fuel-issue", spec["code"], month_idx, issue_idx)
                destination_reference = synthetic_registration(pidx, vehicle_idx)
                reason = None
                if anomaly:
                    reason = (
                        "Consumption above configured tolerance; investigate repeated refuelling and reading evidence"
                        if spec["code"] == "TEST-EC-LUS-02"
                        else "Consumption above expected synthetic operating range"
                    )
                issue_rows.append(
                    {
                        "id": issue_id,
                        "issue_number": f"FI-{spec['code'][-5:]}-{month_idx + 1:02d}{issue_idx + 1:02d}",
                        "project_id": project_id,
                        "site_id": site_id,
                        "storage_location_id": storage_id,
                        "fuel_type_id": diesel_id,
                        "vehicle_id": vehicle_id,
                        "destination_type": "PLANT" if uses_hours else "VEHICLE",
                        "equipment_reference": destination_reference,
                        "issued_at": stamp(issue_day, 7 + issue_idx % 5),
                        "litres": litres,
                        "odometer_reading": previous_odometer[vehicle_id] if not uses_hours else None,
                        "hour_meter_reading": previous_hours[vehicle_id] if uses_hours else None,
                        "issued_by": site_manager_id,
                        "received_by": f"Synthetic Operator {vehicle_idx + 1}",
                        "purpose": "Construction operations",
                        "notes": "TEST DATA — synthetic fuel issue",
                        "distance_since_previous_km": distance,
                        "litres_per_100km": l_per_100,
                        "operating_hours_since_previous": operating_hours,
                        "litres_per_hour": l_per_hour,
                        "anomaly_flag": anomaly,
                        "anomaly_reason": reason,
                        "is_reversed": False,
                        "reading_source": "MANUAL_VERIFIED",
                        "estimated_remaining_litres": money(calculated_balance - month_issue_total - litres),
                        "feasibility_status": "OVERRIDE_REVIEW" if anomaly else "FEASIBLE",
                        "unit_cost": litre_rate,
                        "total_cost": money(litres * litre_rate),
                        "created_at": stamp(issue_day),
                        "updated_at": stamp(issue_day),
                    }
                )
                legacy_log_rows.append(
                    {
                        "id": sid("legacy-fuel-log", spec["code"], month_idx, issue_idx),
                        "project_id": project_id,
                        "site_id": site_id,
                        "fuel_type": "DIESEL",
                        "usage_type": "EQUIPMENT" if uses_hours else "TRANSPORT",
                        "litres": money(0),
                        "cost_per_litre": litre_rate,
                        "total_cost": money(0),
                        "vehicle_registration": destination_reference,
                        "equipment_name": f"{make} {model}",
                        "odometer_reading": previous_odometer[vehicle_id] if not uses_hours else None,
                        "log_date": issue_day,
                        "recorded_by": site_manager_id,
                        "notes": "Migrated reference only — canonical cost held in FuelIssue" + (" ⚠ ANOMALY" if anomaly else ""),
                        "vehicle_id": vehicle_id,
                        "equipment_ref": destination_reference,
                        "fuelled_by": STAFF[13 + pidx][0],
                        "fuel_date": stamp(issue_day),
                        "distance_km": distance,
                        "l_per_100km": l_per_100,
                        "hours_reading": previous_hours[vehicle_id] if uses_hours else None,
                        "fuel_delivery_id": delivery_id,
                        "hours_operated": operating_hours,
                        "fuel_per_hour": l_per_hour,
                        "created_at": stamp(issue_day),
                        "updated_at": stamp(issue_day),
                    }
                )
                month_issue_total += litres
            calculated_balance -= month_issue_total

            variance = Decimal(str(((month_idx + pidx) % 5) * 7 - 10))
            physical = calculated_balance + variance
            reconciliation_rows.append(
                {
                    "id": sid("fuel-reconciliation", spec["code"], month_idx),
                    "reconciliation_number": f"FR-{spec['code'][-5:]}-{month_idx + 1:03d}",
                    "project_id": project_id,
                    "site_id": store_id,
                    "storage_location_id": storage_id,
                    "fuel_type_id": diesel_id,
                    "reconciliation_date": stamp(month_day + timedelta(days=27), 16),
                    "calculated_balance_litres": money(calculated_balance),
                    "physical_balance_litres": money(physical),
                    "variance_litres": money(variance),
                    "variance_pct": money(abs(variance) / calculated_balance * 100) if calculated_balance else money(0),
                    "explanation": "Minor gauge and temperature variance — TEST DATA",
                    "status": "APPROVED" if abs(variance) <= 20 else "PENDING_APPROVAL",
                    "requires_approval": abs(variance) > 20,
                    "reconciled_by": site_manager_id,
                    "approved_by": admin_id if abs(variance) > 20 else site_manager_id,
                    "approved_at": stamp(month_day + timedelta(days=28), 9),
                    "approval_notes": "Synthetic variance reviewed",
                    "created_at": stamp(month_day + timedelta(days=27), 16),
                    "updated_at": stamp(month_day + timedelta(days=28), 9),
                }
            )
        adjustment = Decimal("-18") if pidx in {2, 3} else Decimal("9")
        adjustment_rows.append(
            {
                "id": sid("fuel-adjustment", spec["code"]),
                "project_id": project_id,
                "site_id": store_id,
                "storage_location_id": storage_id,
                "fuel_type_id": diesel_id,
                "adjustment_type": "LOSS" if adjustment < 0 else "CORRECTION",
                "litres_delta": adjustment,
                "reason": "Approved synthetic reconciliation correction",
                "authorised_by": admin_id,
                "created_at": NOW - timedelta(days=18 + pidx),
            }
        )

    for name, rows in [
        ("vehicles", vehicle_rows),
        ("vehicle_costs", vehicle_cost_rows),
        ("fuel_storage_locations", storage_rows),
        ("fuel_equipment_profiles", profile_rows),
        ("fuel_orders", order_rows),
        ("fuel_order_history", order_history_rows),
        ("fuel_deliveries", delivery_rows),
        ("fuel_issues", issue_rows),
        ("fuel_reconciliations", reconciliation_rows),
        ("fuel_stock_adjustments", adjustment_rows),
        ("fuel_logs", legacy_log_rows),
    ]:
        counts[name] += insert_rows(db, name, rows)


def seed_operations_finance_and_documents(db: Session, ctx: dict[str, Any], counts: Counter) -> None:
    owner_id = ctx["owner_id"]
    admin_id = sid("user", STAFF[1][1])
    finance_id = sid("user", STAFF[2][1])
    qs_id = sid("user", STAFF[4][1])
    subcontractor_id = sid("supplier", "TST-SUB")
    civil_supplier_id = sid("supplier", "TST-CIV")

    programme_rows: list[dict[str, Any]] = []
    weekly_rows: list[dict[str, Any]] = []
    weekly_item_rows: list[dict[str, Any]] = []
    job_rows: list[dict[str, Any]] = []
    work_done_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    claim_line_rows: list[dict[str, Any]] = []
    muni_invoice_rows: list[dict[str, Any]] = []
    muni_item_rows: list[dict[str, Any]] = []
    attachment_rows: list[dict[str, Any]] = []
    alert_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for pidx, spec in enumerate(PROJECTS):
        project_id = sid("project", spec["code"])
        site_id = sid("site", spec["code"], "main")
        pm_id = sid("user", STAFF[6 + pidx][1])
        site_manager_id = sid("user", STAFF[13 + pidx][1])
        site_clerk_id = sid("user", STAFF[20 + pidx][1])
        start = TODAY - timedelta(days=spec["start_days"])
        finish = TODAY + timedelta(days=spec["finish_days"])
        duration = max(180, (finish - start).days)

        predecessor = None
        for sidx, (stage_code, stage_name, _) in enumerate(STAGES):
            activity_id = sid("programme", spec["code"], stage_code)
            planned_start = start + timedelta(days=int(duration * sidx / len(STAGES)))
            planned_finish = start + timedelta(days=int(duration * (sidx + 1) / len(STAGES)) - 1)
            stage_start_pct = sidx / len(STAGES) * 100
            stage_end_pct = (sidx + 1) / len(STAGES) * 100
            if spec["progress"] >= stage_end_pct:
                status = "COMPLETED"
                progress = 100
                actual_finish = min(planned_finish + timedelta(days=(pidx + sidx) % 5 - 2), TODAY)
            elif spec["progress"] > stage_start_pct:
                status = "IN_PROGRESS"
                progress = int((spec["progress"] - stage_start_pct) / (stage_end_pct - stage_start_pct) * 100)
                actual_finish = None
            else:
                status = "NOT_STARTED"
                progress = 0
                actual_finish = None
            programme_rows.append(
                {
                    "id": activity_id,
                    "activity_number": f"PRG-{spec['code'][-5:]}-{sidx + 1:02d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "title": stage_name,
                    "description": f"TEST DATA — portfolio programme activity for {stage_name}",
                    "activity_type": "CONSTRUCTION",
                    "planned_start_date": planned_start,
                    "planned_finish_date": planned_finish,
                    "actual_start_date": planned_start + timedelta(days=(pidx + sidx) % 4) if progress else None,
                    "actual_finish_date": actual_finish,
                    "baseline_start_date": planned_start,
                    "baseline_finish_date": planned_finish,
                    "duration_days": (planned_finish - planned_start).days + 1,
                    "progress_pct": progress,
                    "status": status,
                    "predecessor_id": predecessor,
                    "lag_days": 0,
                    "is_critical_path": sidx in {2, 3, 4, 5, 11, 12},
                    "is_milestone": sidx in {3, 5, 8, 12},
                    "responsible_team": f"{STAFF[6 + pidx][0]} / {STAFF[13 + pidx][0]}",
                    "notes": "Synthetic baseline and actual dates",
                    "created_by": pm_id,
                    "created_at": stamp(start - timedelta(days=10)),
                    "updated_at": NOW,
                }
            )
            predecessor = activity_id

        # Twelve weeks of plans show an active operating cadence.
        current_monday = TODAY - timedelta(days=TODAY.weekday())
        for widx in range(12):
            week_start = current_monday - timedelta(weeks=11 - widx)
            week_end = week_start + timedelta(days=6)
            plan_id = sid("weekly-plan", spec["code"], week_start.isoformat())
            status = "APPROVED" if week_start < current_monday else "SUBMITTED"
            weekly_rows.append(
                {
                    "id": plan_id,
                    "plan_number": f"WP-{spec['code'][-5:]}-{week_start.strftime('%y%W')}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "week_start_date": week_start,
                    "week_end_date": week_end,
                    "status": status,
                    "notes": "TEST DATA — weekly production plan and constraints review",
                    "submitted_by": site_manager_id,
                    "approved_by": pm_id if status == "APPROVED" else None,
                    "submitted_at": stamp(week_start - timedelta(days=2), 15),
                    "approved_at": stamp(week_start - timedelta(days=1), 10) if status == "APPROVED" else None,
                    "created_at": stamp(week_start - timedelta(days=2), 15),
                    "updated_at": stamp(week_start - timedelta(days=1), 10),
                }
            )
            for line in range(3):
                stage_idx = min(len(STAGES) - 1, int(spec["progress"] / 100 * len(STAGES)) + line - 1)
                actual = max(0, min(100, 78 + ((widx + line + pidx) % 5) * 5)) if week_start < current_monday else None
                weekly_item_rows.append(
                    {
                        "id": sid("weekly-item", spec["code"], week_start.isoformat(), line),
                        "plan_id": plan_id,
                        "programme_activity_id": sid("programme", spec["code"], STAGES[stage_idx][0]),
                        "description": f"Advance {STAGES[stage_idx][1].lower()} on planned unit batch",
                        "planned_progress_pct": 100,
                        "actual_progress_pct": actual,
                        "carry_forward": actual is not None and actual < 90,
                        "completion_notes": "Completed with minor carry-over" if actual is not None else None,
                        "completed_at": stamp(week_end, 14) if actual is not None else None,
                        "sort_order": line + 1,
                    }
                )

        # Labour and subcontractor records contribute to project cost summaries.
        for jidx in range(10):
            work_day = max(start + timedelta(days=45), TODAY - timedelta(days=245 - jidx * 22))
            amount = money((85_000 + jidx * 7_500) * (1.22 if spec["code"] == "TEST-MP-EMA-11" else 1))
            job_rows.append(
                {
                    "id": sid("job-card", spec["code"], jidx),
                    "job_card_number": f"JC-{spec['code'][-5:]}-{jidx + 1:03d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "lot_id": sid("lot", spec["code"], f"{(jidx // 25) + 1:02d}-{(jidx % 25) + 1:03d}"),
                    "stage_id": sid("stage", STAGES[min(jidx, len(STAGES) - 1)][0]),
                    "work_description": f"Labour team for {STAGES[min(jidx, len(STAGES) - 1)][1]}",
                    "work_type": "SUBCONTRACTOR",
                    "worker_name": None,
                    "team_name": f"Synthetic Building Team {jidx % 4 + 1}",
                    "quantity": money(1),
                    "unit": "item",
                    "rate": amount,
                    "total_amount": amount,
                    "owner_approval_required": amount > 100_000,
                    "status": "PAID" if jidx < 7 else ("OFFICE_APPROVED" if jidx < 9 else "SUBMITTED"),
                    "is_active": True,
                    "submitted_by": site_manager_id,
                    "submitted_at": stamp(work_day),
                    "site_approved_by": site_manager_id if jidx < 9 else None,
                    "site_approved_at": stamp(work_day + timedelta(days=1)) if jidx < 9 else None,
                    "office_approved_by": admin_id if jidx < 9 else None,
                    "office_approved_at": stamp(work_day + timedelta(days=2)) if jidx < 9 else None,
                    "owner_approved_by": owner_id if amount > 100_000 and jidx < 7 else None,
                    "owner_approved_at": stamp(work_day + timedelta(days=3)) if amount > 100_000 and jidx < 7 else None,
                    "payment_approved_by": finance_id if jidx < 7 else None,
                    "payment_approved_at": stamp(work_day + timedelta(days=5)) if jidx < 7 else None,
                    "work_date": work_day,
                    "notes": "TEST DATA — synthetic labour record",
                    "created_by": site_clerk_id,
                    "created_at": stamp(work_day),
                    "updated_at": stamp(work_day + timedelta(days=5)),
                }
            )
            work_amount = money((310_000 + jidx * 22_000) * (1.55 if spec["code"] == "TEST-MP-EMA-11" else 1))
            work_done_rows.append(
                {
                    "id": sid("work-done", spec["code"], jidx),
                    "work_done_number": f"WD-{spec['code'][-5:]}-{jidx + 1:03d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "lot_id": None,
                    "supplier_id": civil_supplier_id if jidx % 3 == 0 else subcontractor_id,
                    "job_card_id": sid("job-card", spec["code"], jidx),
                    "work_description": f"Measured {STAGES[min(jidx, len(STAGES) - 1)][1].lower()} work package",
                    "quantity": money(1),
                    "unit": "item",
                    "rate": work_amount,
                    "amount": work_amount,
                    "month": work_day.replace(day=1),
                    "comments": "TEST DATA — measured against synthetic site records",
                    "status": "PAID" if jidx < 7 else ("OFFICE_APPROVED" if jidx < 9 else "SUBMITTED"),
                    "submitted_by": site_manager_id,
                    "submitted_at": stamp(work_day),
                    "site_approved_by": site_manager_id if jidx < 9 else None,
                    "site_approved_at": stamp(work_day + timedelta(days=1)) if jidx < 9 else None,
                    "office_approved_by": qs_id if jidx < 9 else None,
                    "office_approved_at": stamp(work_day + timedelta(days=3)) if jidx < 9 else None,
                    "paid_by": finance_id if jidx < 7 else None,
                    "paid_at": stamp(work_day + timedelta(days=28)) if jidx < 7 else None,
                    "created_by": site_clerk_id,
                    "created_at": stamp(work_day),
                    "updated_at": stamp(work_day + timedelta(days=3)),
                }
            )

        claim_count = 4 if spec["progress"] >= 40 else 2
        for cidx in range(claim_count):
            period_end = TODAY - timedelta(days=(claim_count - cidx) * 45)
            period_start = period_end - timedelta(days=29)
            claim_id = sid("progress-claim", spec["code"], cidx)
            claim_status = "APPROVED" if cidx < claim_count - 1 else "READY_FOR_PRICING"
            claim_rows.append(
                {
                    "id": claim_id,
                    "claim_number": f"PC-{spec['code'][-5:]}-{cidx + 1:02d}",
                    "project_id": project_id,
                    "site_id": site_id,
                    "claim_title": f"Monthly Physical Progress Claim {cidx + 1}",
                    "municipality_name": spec["municipality"] + " — SYNTHETIC",
                    "cert_number": f"CERT-TEST-{pidx + 1}-{cidx + 1:02d}",
                    "period_start": period_start,
                    "period_end": period_end,
                    "reporting_cutoff_date": period_end,
                    "status": claim_status,
                    "notes": "TEST DATA — physical evidence only; commercial pricing reviewed separately",
                    "generation_summary": {"synthetic": True, "included_lines": 8, "seed_batch": SEED_BATCH},
                    "snapshot_json": {"portfolio_progress": spec["progress"], "health": spec["health"]},
                    "generated_at": stamp(period_end + timedelta(days=1)),
                    "approved_at": stamp(period_end + timedelta(days=5)) if claim_status == "APPROVED" else None,
                    "exported_at": stamp(period_end + timedelta(days=6)) if claim_status == "APPROVED" else None,
                    "created_by": qs_id,
                    "created_at": stamp(period_end + timedelta(days=1)),
                    "updated_at": stamp(period_end + timedelta(days=5)),
                }
            )
            for line in range(8):
                lot_index = (cidx * 8 + line) % spec["units"]
                lot_number = f"{(lot_index // 25) + 1:02d}-{(lot_index % 25) + 1:03d}"
                stage_idx = min(len(STAGES) - 1, int(spec["progress"] / 100 * len(STAGES)))
                claim_line_rows.append(
                    {
                        "id": sid("claim-line", spec["code"], cidx, line),
                        "claim_id": claim_id,
                        "source_type": "STAGE_STATUS",
                        "lot_id": sid("lot", spec["code"], lot_number),
                        "stage_status_id": sid("stage-status", sid("lot", spec["code"], lot_number), STAGES[stage_idx][0]),
                        "description": f"{STAGES[stage_idx][1]} — Lot {lot_number}",
                        "stage_name": STAGES[stage_idx][1],
                        "lot_number": lot_number,
                        "work_date": period_end - timedelta(days=line),
                        "quantity": "1",
                        "unit": "unit",
                        "progress_pct": min(100, spec["progress"] + line % 6),
                        "is_included": True,
                        "is_system_generated": True,
                        "reviewer_notes": "Synthetic evidence reviewed",
                        "sort_order": line + 1,
                    }
                )

            invoice_id = sid("municipality-invoice", spec["code"], cidx)
            progress_value = money(Decimal(str(spec["contract"])) * Decimal(str(0.045 + cidx * 0.012)))
            vat = money(progress_value * Decimal("0.15"))
            muni_invoice_rows.append(
                {
                    "id": invoice_id,
                    "invoice_number": f"MINV-{spec['code'][-5:]}-{cidx + 1:02d}",
                    "cert_number": f"CERT-TEST-{pidx + 1}-{cidx + 1:02d}",
                    "project_id": project_id,
                    "invoice_date": period_end + timedelta(days=6),
                    "due_date": period_end + timedelta(days=36),
                    "client_name": spec["municipality"] + " — SYNTHETIC",
                    "client_vat_no": "TEST-VAT-NOT-REAL",
                    "client_address": f"Synthetic Civic Centre, {spec['province']}",
                    "company_email": "accounts@ubuntu-housing.invalid",
                    "project_description": spec["name"],
                    "contract_reference": f"TEST-CONTRACT-{spec['code']}",
                    "subtotal": progress_value,
                    "previously_paid": money(progress_value * cidx),
                    "vat_rate": money(15),
                    "vat_amount": vat,
                    "total_due": progress_value + vat,
                    "notes": "TEST DATA — not a real municipal invoice or tender award",
                    "bank_name": None,
                    "account_number": None,
                    "branch_name": None,
                    "branch_code": None,
                    "status": "PAID" if cidx < claim_count - 1 else "ISSUED",
                    "created_by": finance_id,
                    "created_at": stamp(period_end + timedelta(days=6)),
                    "updated_at": stamp(period_end + timedelta(days=6)),
                }
            )
            muni_item_rows.append(
                {
                    "id": sid("municipality-invoice-item", spec["code"], cidx),
                    "invoice_id": invoice_id,
                    "sort_order": 1,
                    "line_number": "1",
                    "description": f"Certified synthetic housing works for period ending {period_end.isoformat()}",
                    "quantity": money(1),
                    "unit_price": progress_value,
                    "total": progress_value,
                    "disc_pct": money(0),
                    "comments": "TEST DATA",
                    "created_at": stamp(period_end + timedelta(days=6)),
                }
            )

        doc_specs = [
            ("PROJECT", project_id, "PDF", "Synthetic monthly progress report"),
            ("BOQ_HEADER", sid("boq-header", spec["code"]), "PDF", "Synthetic approved BOQ extract"),
            ("PROJECT", project_id, "CERTIFICATE", "Synthetic health and safety file index"),
            ("PROJECT", project_id, "PHOTO", "Synthetic site progress photo placeholder"),
        ]
        for didx, (entity_type, entity_id, attachment_type, caption) in enumerate(doc_specs):
            suffix = "jpg" if attachment_type == "PHOTO" else "pdf"
            stored = f"test-data/{spec['code'].lower()}/{didx + 1:02d}-{caption.lower().replace(' ', '-')}.{suffix}"
            attachment_rows.append(
                {
                    "id": sid("attachment", spec["code"], didx),
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "attachment_type": attachment_type,
                    "file_name": f"TEST_{spec['code']}_{didx + 1:02d}.{suffix}",
                    "stored_path": stored,
                    "file_url": stored,
                    "file_size_bytes": 0,
                    "mime_type": "image/jpeg" if suffix == "jpg" else "application/pdf",
                    "uploaded_by": site_clerk_id,
                    "uploaded_at": NOW - timedelta(days=40 - didx),
                    "is_active": True,
                    "caption": caption + " — TEST PLACEHOLDER",
                    "uploaded_role": "SITE_STAFF",
                }
            )

        # A balanced mixture of open and resolved management alerts.
        scenario_alerts = [
            ("LOW_STOCK", "MEDIUM", "Low cement stock forecast", "Reorder point will be reached within 8 working days."),
            ("REQUEST_PENDING_TOO_LONG", "HIGH", "Approval ageing requires attention", "A material request is approaching its required-on-site date."),
        ]
        if spec["code"] == "TEST-EC-LUS-02":
            scenario_alerts.extend(
                [
                    ("FUEL_USAGE_HIGH", "CRITICAL", "Excavator diesel consumption above tolerance", "EXCAVATOR-03 is 24% above the configured litres/hour benchmark."),
                    ("FUEL_USAGE_HIGH", "HIGH", "Repeated water tanker refuelling", "Refuelling interval and odometer evidence should be reviewed."),
                ]
            )
        if spec["code"] == "TEST-GP-TEM-34":
            scenario_alerts.append(("REQUEST_PENDING_TOO_LONG", "CRITICAL", "Roofing package approval overdue", "Roof timber and window approvals are now on the critical path."))
        if spec["code"] == "TEST-MP-EMA-11":
            scenario_alerts.extend(
                [
                    ("PROJECT_OVER_BUDGET", "CRITICAL", "Forecast final cost exceeds approved budget", "Reinforcement, roads and stormwater packages require commercial intervention."),
                    ("BOQ_VARIANCE_OVERUSE", "HIGH", "Reinforcement quantity variance", "Revised civil details are consuming contingency faster than planned."),
                ]
            )
        if spec["code"] == "TEST-LP-POL-08":
            scenario_alerts.append(("STAGE_DELAYED", "MEDIUM", "Close-out documentation incomplete", "Electrical COCs and final snag sheets remain outstanding on 7 units."))

        for aidx, (alert_type, severity, title, message) in enumerate(scenario_alerts):
            created = NOW - timedelta(days=2 + aidx * 4 + pidx)
            alert_rows.append(
                {
                    "id": sid("alert", spec["code"], aidx),
                    "project_id": project_id,
                    "site_id": site_id,
                    "reference_type": "PROJECT",
                    "reference_id": project_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "title": title + " — TEST DATA",
                    "message": message,
                    "status": "OPEN" if aidx < 2 or severity == "CRITICAL" else "RESOLVED",
                    "target_role": "OWNER",
                    "target_user_id": owner_id,
                    "notification_channel": "in_app",
                    "created_at": created,
                    "resolved_at": None if aidx < 2 or severity == "CRITICAL" else created + timedelta(days=2),
                    "resolved_by": None if aidx < 2 or severity == "CRITICAL" else admin_id,
                }
            )
        audit_rows.append(
            {
                "id": sid("audit-project", spec["code"]),
                "actor_id": pm_id,
                "action": "UPDATE",
                "entity_type": "PROJECT",
                "entity_id": project_id,
                "before_value": {"progress": max(0, spec["progress"] - 7)},
                "after_value": {"progress": spec["progress"], "health": spec["health"], "synthetic": True},
                "notes": "TEST DATA — monthly progress update",
                "ip_address": "198.51.100.20",
                "created_at": NOW - timedelta(days=7 + pidx),
            }
        )

    for name, rows in [
        ("programme_activities", programme_rows),
        ("weekly_plans", weekly_rows),
        ("weekly_plan_items", weekly_item_rows),
        ("job_cards", job_rows),
        ("subcontractor_work_done", work_done_rows),
        ("municipality_progress_claims", claim_rows),
        ("progress_claim_lines", claim_line_rows),
        ("municipality_invoices", muni_invoice_rows),
        ("municipality_invoice_items", muni_item_rows),
        ("attachments", attachment_rows),
        ("system_alerts", alert_rows),
        ("audit_events", audit_rows),
    ]:
        counts[name] += insert_rows(db, name, rows)


def validate_seed(db: Session) -> dict[str, Any]:
    summary = dict(
        db.execute(
            text(
                """
                select
                  (select count(*) from projects) as projects,
                  (select count(*) from lots) as lots,
                  (select count(*) from users) as users,
                  (select count(*) from suppliers) as suppliers,
                  (select count(*) from vehicles) as vehicles,
                  (select count(*) from material_requests) as material_requests,
                  (select count(*) from quotations) as quotations,
                  (select count(*) from purchase_orders) as purchase_orders,
                  (select count(*) from fuel_deliveries) as fuel_deliveries,
                  (select count(*) from fuel_issues) as fuel_issues,
                  (select count(*) from fuel_issues where anomaly_flag) as fuel_anomalies,
                  (select min(created_at)::date from audit_events) as earliest_activity,
                  (select max(created_at)::date from audit_events) as latest_activity
                """
            )
        ).mappings().one()
    )
    if summary["projects"] < 5 or summary["lots"] < 300:
        raise RuntimeError(f"Seed volume validation failed: {summary}")
    negative_fuel = db.execute(
        text(
            """
            with balances as (
              select p.id,
                coalesce((select sum(confirmed_litres) from fuel_deliveries d where d.project_id=p.id and d.verification_status='VERIFIED'),0)
                - coalesce((select sum(litres) from fuel_issues i where i.project_id=p.id and not i.is_reversed),0)
                + coalesce((select sum(litres_delta) from fuel_stock_adjustments a where a.project_id=p.id),0) as balance
              from projects p
            )
            select count(*) from balances where balance < 0
            """
        )
    ).scalar_one()
    if negative_fuel:
        raise RuntimeError(f"Fuel validation failed: {negative_fuel} project(s) have negative stock")
    overpaid = db.execute(
        text(
            """
            select count(*)
            from payments p join invoices i on i.id=p.invoice_id
            where coalesce(p.amount_paid,0) > i.total_amount
            """
        )
    ).scalar_one()
    if overpaid:
        raise RuntimeError(f"Financial validation failed: {overpaid} payment(s) exceed invoice totals")
    summary["negative_fuel_balances"] = negative_fuel
    summary["payments_over_invoice_total"] = overpaid
    return summary


def harden_test_database(db: Session) -> None:
    """Keep the dedicated TEST database off the Supabase Data API surface."""
    db.execute(
        text(
            """
            insert into public.alembic_version (version_num)
            values ('0075')
            on conflict (version_num) do nothing
            """
        )
    )
    names = list(
        db.execute(
            text("select tablename from pg_tables where schemaname='public' order by tablename")
        ).scalars()
    )
    api_roles_exist = db.execute(
        text("select count(*) = 2 from pg_roles where rolname in ('anon','authenticated')")
    ).scalar_one()
    for name in names:
        safe_name = name.replace('"', '""')
        db.execute(text(f'alter table public."{safe_name}" enable row level security'))
        if api_roles_exist:
            db.execute(text(f'revoke all privileges on table public."{safe_name}" from anon, authenticated'))
    if api_roles_exist:
        materialized_views = list(
            db.execute(
                text(
                    "select matviewname from pg_matviews "
                    "where schemaname = 'public' order by matviewname"
                )
            ).scalars()
        )
        for name in materialized_views:
            safe_name = name.replace('"', '""')
            db.execute(
                text(
                    f'revoke all privileges on table public."{safe_name}" '
                    "from anon, authenticated"
                )
            )
        db.execute(
            text(
                "alter default privileges for role postgres in schema public "
                "revoke all on tables from anon, authenticated"
            )
        )
    has_storage = db.execute(text("select to_regclass('storage.buckets') is not null")).scalar_one()
    if has_storage:
        db.execute(
            text(
                """
                insert into storage.buckets (id, name, public)
                values
                  ('hmh-uploads', 'hmh-uploads', true),
                  ('hmh-evidence-private', 'hmh-evidence-private', false)
                on conflict (id) do update set public = excluded.public
                """
            )
        )


def seed(database_url: str) -> dict[str, Any]:
    assert_test_target(database_url)
    engine = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    inspector = inspect(engine)
    if "projects" not in inspector.get_table_names(schema="public"):
        raise SystemExit("REFUSED: application schema is missing; run Alembic migrations first.")
    counts: Counter = Counter()
    with Session(engine) as db:
        with db.begin():
            clear_business_data(db)
            ctx = seed_foundations(db, counts)
            seed_projects_and_progress(db, ctx, counts)
            seed_boq(db, ctx, counts)
            seed_procurement(db, ctx, counts)
            seed_fleet_and_fuel(db, ctx, counts)
            seed_operations_finance_and_documents(db, ctx, counts)
            summary = validate_seed(db)
            harden_test_database(db)
    engine.dispose()
    print(json.dumps({"seed_batch": SEED_BATCH, "inserted": counts, "summary": summary}, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Defaults to DATABASE_URL. Credentials are never printed.",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required.")
    seed(args.database_url)


if __name__ == "__main__":
    main()
