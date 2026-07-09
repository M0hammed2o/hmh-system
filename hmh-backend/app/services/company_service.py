"""Company CRUD + supplier-link service."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.company import Company, CompanySupplierLink
from app.models.supplier import Supplier
from app.schemas.company import CompanyCreate, CompanyUpdate


def _get_or_404(db: Session, company_id: uuid.UUID) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def list_companies(db: Session) -> list[Company]:
    return db.query(Company).order_by(Company.name).all()


def get_company(db: Session, company_id: uuid.UUID) -> Company:
    return _get_or_404(db, company_id)


def get_company_suppliers(db: Session, company_id: uuid.UUID) -> list[Supplier]:
    _get_or_404(db, company_id)
    links = (
        db.query(CompanySupplierLink)
        .filter(CompanySupplierLink.company_id == company_id)
        .all()
    )
    return [link.supplier for link in links if link.supplier]


def create_company(db: Session, data: CompanyCreate) -> Company:
    existing = db.query(Company).filter(Company.name == data.name.strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A company with this name already exists")

    company = Company(
        name=data.name.strip(),
        registration_number=data.registration_number,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        address=data.address,
        notes=data.notes,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def update_company(db: Session, company_id: uuid.UUID, data: CompanyUpdate) -> Company:
    company = _get_or_404(db, company_id)
    fields = data.model_fields_set

    if "name" in fields and data.name is not None:
        company.name = data.name.strip()
    if "registration_number" in fields:
        company.registration_number = data.registration_number
    if "contact_email" in fields:
        company.contact_email = data.contact_email
    if "contact_phone" in fields:
        company.contact_phone = data.contact_phone
    if "address" in fields:
        company.address = data.address
    if "notes" in fields:
        company.notes = data.notes

    db.commit()
    db.refresh(company)
    return company


def delete_company(db: Session, company_id: uuid.UUID) -> dict:
    company = _get_or_404(db, company_id)
    name = company.name
    db.delete(company)
    db.commit()
    return {"deleted_company": name}


def link_supplier(db: Session, company_id: uuid.UUID, supplier_id: uuid.UUID) -> CompanySupplierLink:
    _get_or_404(db, company_id)

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    existing = (
        db.query(CompanySupplierLink)
        .filter(
            CompanySupplierLink.company_id == company_id,
            CompanySupplierLink.supplier_id == supplier_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Supplier already linked to this company")

    link = CompanySupplierLink(company_id=company_id, supplier_id=supplier_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def unlink_supplier(db: Session, company_id: uuid.UUID, supplier_id: uuid.UUID) -> None:
    _get_or_404(db, company_id)

    link = (
        db.query(CompanySupplierLink)
        .filter(
            CompanySupplierLink.company_id == company_id,
            CompanySupplierLink.supplier_id == supplier_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Supplier link not found")

    db.delete(link)
    db.commit()


def get_project_suppliers(db: Session, project_id: uuid.UUID) -> Optional[list[Supplier]]:
    """
    Returns the approved suppliers for a project's linked company,
    or None if the project has no company (meaning all suppliers allowed).
    """
    from app.models.project import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.company_id:
        return None

    links = (
        db.query(CompanySupplierLink)
        .filter(CompanySupplierLink.company_id == project.company_id)
        .all()
    )
    return [link.supplier for link in links if link.supplier]
