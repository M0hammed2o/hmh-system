"""
Import all models here so Alembic's env.py only needs to import this module
and all tables are registered on Base.metadata.
"""

from app.models.enums import *  # noqa: F401, F403 — re-export all enum types
from app.models.user import User
from app.models.project import Project
from app.models.site import Site
from app.models.lot import Lot
from app.models.stage import StageMaster, ProjectStageStatus
from app.models.access import UserProjectAccess, UserSiteAccess
from app.models.supplier import Supplier
from app.models.item import ItemCategory, Item, ItemAlias
from app.models.boq import BOQHeader, BOQSection, BOQItem
from app.models.material_request import MaterialRequest, MaterialRequestItem
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, PoEmailLog
from app.models.delivery import Delivery, DeliveryItem
from app.models.stock import StockLedger, UsageLog
from app.models.invoice import Invoice, InvoiceMatchingResult
from app.models.payment import Payment
from app.models.attachment import Attachment, UsageRemainingProof
from app.models.alert import SystemAlert
from app.models.fuel import FuelLog

__all__ = [
    "User",
    "Project",
    "Site",
    "Lot",
    "StageMaster",
    "ProjectStageStatus",
    "UserProjectAccess",
    "UserSiteAccess",
    "Supplier",
    "ItemCategory",
    "Item",
    "ItemAlias",
    "BOQHeader",
    "BOQSection",
    "BOQItem",
    "MaterialRequest",
    "MaterialRequestItem",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PoEmailLog",
    "Delivery",
    "DeliveryItem",
    "StockLedger",
    "UsageLog",
    "Invoice",
    "InvoiceMatchingResult",
    "Payment",
    "Attachment",
    "UsageRemainingProof",
    "SystemAlert",
    "FuelLog",
]
