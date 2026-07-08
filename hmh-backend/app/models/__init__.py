"""
Import all models here so Alembic's env.py only needs to import this module
and all tables are registered on Base.metadata.
"""

from app.models.enums import *  # noqa: F401, F403 — re-export all enum types
from app.models.user import User
from app.models.project import Project
from app.models.site import Site
from app.models.lot_type import LotType
from app.models.lot import Lot
from app.models.stage import StageMaster, ProjectStageStatus
from app.models.access import UserProjectAccess, UserSiteAccess
from app.models.supplier import Supplier
from app.models.item import ItemCategory, Item, ItemAlias
from app.models.boq import BOQHeader, BOQSection, BOQItem
from app.models.material_request import MaterialRequest, MaterialRequestItem, MRApproval
from app.models.mr_quote import MRQuote
from app.models.mr_quote_vote import MRQuoteVote
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, PoEmailLog
from app.models.delivery import Delivery, DeliveryItem
from app.models.stock import StockLedger, UsageLog
from app.models.invoice import Invoice, InvoiceMatchingResult
from app.models.payment import Payment
from app.models.attachment import Attachment, UsageRemainingProof
from app.models.alert import SystemAlert
from app.models.fuel import FuelLog
from app.models.vehicle import Vehicle, VehicleCost
from app.models.audit import AuditEvent
from app.models.alert_recipient import AlertRecipient
from app.models.notification_queue import NotificationQueue
from app.models.job_card import JobCard
from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment
from app.models.document_extraction import (
    DocumentExtraction, DeliveryVerification,
    DeliveryVerificationItem, ExpenseRecord,
)
from app.models.boq_adjustment import BOQAdjustment
from app.models.mr_email_log import MREmailLog
from app.models.quotation import Quotation
from app.models.procurement_reconciliation import ProcurementReconciliation
from app.models.work_done import SubcontractorWorkDone
from app.models.workshop import (
    WorkshopCategory,
    WorkshopItem,
    WorkshopStock,
    WorkshopSupplierLink,
    WorkshopMR,
    WorkshopMRLine,
    WorkshopMRApproval,
    WorkshopMREmailLog,
    WorkshopIssuance,
)

__all__ = [
    "User",
    "Project",
    "Site",
    "LotType",
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
    "MRApproval",
    "MRQuote",
    "MRQuoteVote",
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
    "Vehicle",
    "VehicleCost",
    "AuditEvent",
    "AlertRecipient",
    "NotificationQueue",
    "JobCard",
    "IncomingEmail",
    "IncomingEmailAttachment",
    "DocumentExtraction",
    "DeliveryVerification",
    "DeliveryVerificationItem",
    "ExpenseRecord",
    "BOQAdjustment",
    "MREmailLog",
    "Quotation",
    "ProcurementReconciliation",
    "SubcontractorWorkDone",
    "WorkshopCategory",
    "WorkshopItem",
    "WorkshopStock",
    "WorkshopSupplierLink",
    "WorkshopMR",
    "WorkshopMRLine",
    "WorkshopMRApproval",
    "WorkshopMREmailLog",
    "WorkshopIssuance",
]
