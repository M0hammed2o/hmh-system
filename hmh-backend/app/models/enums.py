"""
Python enums that mirror the PostgreSQL enum types in the schema.
SQLAlchemy maps these to the native DB enum types.
"""

import enum


class UserRole(str, enum.Enum):
    OWNER = "OWNER"
    OFFICE_ADMIN = "OFFICE_ADMIN"
    OFFICE_USER = "OFFICE_USER"
    SITE_MANAGER = "SITE_MANAGER"
    SITE_STAFF = "SITE_STAFF"


class ProjectStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class RecordStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    RECEIVED = "RECEIVED"
    MATCHED = "MATCHED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class StageStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    AWAITING_INSPECTION = "AWAITING_INSPECTION"
    CERTIFIED = "CERTIFIED"


class LotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"


class ItemType(str, enum.Enum):
    MATERIAL = "MATERIAL"
    SERVICE = "SERVICE"
    PACKAGE = "PACKAGE"


class MovementType(str, enum.Enum):
    OPENING_BALANCE = "OPENING_BALANCE"
    DELIVERY_RECEIVED = "DELIVERY_RECEIVED"
    USAGE = "USAGE"
    ADJUSTMENT_ADD = "ADJUSTMENT_ADD"
    ADJUSTMENT_SUBTRACT = "ADJUSTMENT_SUBTRACT"
    RETURN_TO_STORE = "RETURN_TO_STORE"
    TRANSFER_IN = "TRANSFER_IN"    # reserved — do not use in V1 business logic
    TRANSFER_OUT = "TRANSFER_OUT"  # reserved — do not use in V1 business logic


class InvoiceMatchStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    PARTIALLY_MATCHED = "PARTIALLY_MATCHED"
    MISMATCH = "MISMATCH"
    UNLINKED = "UNLINKED"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(str, enum.Enum):
    BOQ_VARIANCE_OVERUSE = "BOQ_VARIANCE_OVERUSE"
    DELIVERY_WITHOUT_PO = "DELIVERY_WITHOUT_PO"
    INVOICE_MISMATCH = "INVOICE_MISMATCH"
    NEGATIVE_STOCK = "NEGATIVE_STOCK"
    LOW_STOCK = "LOW_STOCK"
    MISSING_REMAINING_STOCK_PHOTO = "MISSING_REMAINING_STOCK_PHOTO"
    OVERDUE_PAYMENT = "OVERDUE_PAYMENT"
    REQUEST_PENDING_TOO_LONG = "REQUEST_PENDING_TOO_LONG"
    DELIVERY_DISCREPANCY = "DELIVERY_DISCREPANCY"


class PaymentType(str, enum.Enum):
    SUPPLIER = "SUPPLIER"
    LABOUR = "LABOUR"
    OTHER = "OTHER"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BoqStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class AttachmentEntity(str, enum.Enum):
    BOQ_HEADER = "BOQ_HEADER"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    DELIVERY = "DELIVERY"
    INVOICE = "INVOICE"
    USAGE_LOG = "USAGE_LOG"
    CERTIFICATION = "CERTIFICATION"


class AttachmentType(str, enum.Enum):
    PHOTO = "PHOTO"
    PDF = "PDF"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    INVOICE_COPY = "INVOICE_COPY"
    PROOF = "PROOF"
    CERTIFICATE = "CERTIFICATE"


class EmailStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"
    bounced = "bounced"


class VatMode(str, enum.Enum):
    INCLUSIVE = "INCLUSIVE"   # entered price already includes VAT
    EXCLUSIVE = "EXCLUSIVE"   # entered price is before VAT


class FuelType(str, enum.Enum):
    DIESEL = "DIESEL"
    PETROL = "PETROL"
    PARAFFIN = "PARAFFIN"
    OTHER = "OTHER"


class FuelUsageType(str, enum.Enum):
    EQUIPMENT = "EQUIPMENT"
    DELIVERY_VEHICLE = "DELIVERY_VEHICLE"
    TRANSPORT = "TRANSPORT"
    GENERATOR = "GENERATOR"
    OTHER = "OTHER"


class OpeningFinancialStatus(str, enum.Enum):
    OUTSTANDING = "OUTSTANDING"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    DISPUTED = "DISPUTED"


class OpeningReferenceType(str, enum.Enum):
    INVOICE = "INVOICE"
    PO = "PO"
    PAYMENT = "PAYMENT"
    OTHER = "OTHER"
