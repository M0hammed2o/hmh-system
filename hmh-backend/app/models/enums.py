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
    SITE_MANAGER_VIEW = "SITE_MANAGER_VIEW"  # View-only site manager: can see site data, cannot write
    SITE_STAFF = "SITE_STAFF"
    READ_ONLY = "READ_ONLY"   # View-only owner: can see everything, cannot write


class ProjectStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class RecordStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    SUPPLIER_CONFIRMED = "SUPPLIER_CONFIRMED"  # Phase 3I: supplier acknowledged the PO
    CONVERTED_TO_PO = "CONVERTED_TO_PO"
    ORDERED = "ORDERED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    MATCHED = "MATCHED"
    INVOICED        = "INVOICED"        # Phase 3I: PO has a linked invoice
    PARTIALLY_PAID  = "PARTIALLY_PAID"  # Phase 3L: invoice partially settled
    OVERPAID        = "OVERPAID"        # Phase 3L: payments exceed invoice total
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class DeliveryDestination(str, enum.Enum):
    MAIN_WAREHOUSE = "MAIN_WAREHOUSE"
    SITE_STORE = "SITE_STORE"
    LOT = "LOT"


class MRPriority(str, enum.Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class StageStatus(str, enum.Enum):
    NOT_STARTED         = "NOT_STARTED"
    IN_PROGRESS         = "IN_PROGRESS"
    BLOCKED             = "BLOCKED"           # Phase 3J
    AWAITING_INSPECTION = "AWAITING_INSPECTION"
    COMPLETED           = "COMPLETED"
    CERTIFIED           = "CERTIFIED"


class LotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"


class ItemType(str, enum.Enum):
    MATERIAL = "MATERIAL"
    LABOUR = "LABOUR"
    PLANT = "PLANT"
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
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    MISSING_DELIVERY_NOTE = "MISSING_DELIVERY_NOTE"
    MISSING_SIGNATURE = "MISSING_SIGNATURE"
    MISSING_INVOICE = "MISSING_INVOICE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED_FOR_PAYMENT = "APPROVED_FOR_PAYMENT"
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
    MATERIAL_OVERUSE = "MATERIAL_OVERUSE"
    BOQ_VARIANCE_OVERUSE = "BOQ_VARIANCE_OVERUSE"
    BOQ_ALLOCATION_EXCEEDED = "BOQ_ALLOCATION_EXCEEDED"
    DELIVERY_WITHOUT_PO = "DELIVERY_WITHOUT_PO"
    DELIVERY_MISMATCH = "DELIVERY_MISMATCH"
    DELIVERY_NOTE_MISSING = "DELIVERY_NOTE_MISSING"
    SIGNATURE_MISSING = "SIGNATURE_MISSING"
    INVOICE_MISMATCH = "INVOICE_MISMATCH"
    INVOICE_UNMATCHED = "INVOICE_UNMATCHED"
    INVOICE_MISSING_DELIVERY_NOTE = "INVOICE_MISSING_DELIVERY_NOTE"
    NEGATIVE_STOCK = "NEGATIVE_STOCK"
    LOW_STOCK = "LOW_STOCK"
    MISSING_REMAINING_STOCK_PHOTO = "MISSING_REMAINING_STOCK_PHOTO"
    OVERDUE_PAYMENT = "OVERDUE_PAYMENT"
    REQUEST_PENDING_TOO_LONG = "REQUEST_PENDING_TOO_LONG"
    DELIVERY_DISCREPANCY = "DELIVERY_DISCREPANCY"
    DELIVERY_SIGNATURE_MISSING = "DELIVERY_SIGNATURE_MISSING"
    VEHICLE_REPAIR_LOGGED = "VEHICLE_REPAIR_LOGGED"
    FUEL_USAGE_HIGH = "FUEL_USAGE_HIGH"
    SITE_DELAY = "SITE_DELAY"
    LOT_DELAYED = "LOT_DELAYED"
    STAGE_DELAYED = "STAGE_DELAYED"
    PROJECT_OVER_BUDGET = "PROJECT_OVER_BUDGET"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    WEEKLY_SUMMARY = "WEEKLY_SUMMARY"
    # Phase 3Q.1 — operational notification types
    MR_APPROVED                  = "MR_APPROVED"
    PO_SENT_ALERT                = "PO_SENT_ALERT"
    DELIVERY_RECEIVED_ALERT      = "DELIVERY_RECEIVED_ALERT"
    WAREHOUSE_TRANSFER_COMPLETED = "WAREHOUSE_TRANSFER_COMPLETED"
    INVOICE_CAPTURED             = "INVOICE_CAPTURED"
    PAYMENT_COMPLETED            = "PAYMENT_COMPLETED"
    PARTIAL_PAYMENT_RECORDED     = "PARTIAL_PAYMENT_RECORDED"
    MILESTONE_COMPLETED_ALERT    = "MILESTONE_COMPLETED_ALERT"
    MILESTONE_DELAYED_ALERT      = "MILESTONE_DELAYED_ALERT"
    # Phase 3Q.3 — finance alerts
    PAYMENT_DUE                  = "PAYMENT_DUE"  # approaching due date (scan-based)
    # Phase E — Gmail OCR pipeline
    DUPLICATE_INVOICE            = "DUPLICATE_INVOICE"      # same invoice number submitted again
    OCR_EXTRACTION_FAILED        = "OCR_EXTRACTION_FAILED"  # attachment OCR produced no usable text
    SUPPLIER_MISMATCH            = "SUPPLIER_MISMATCH"      # supplier in doc ≠ PO supplier


class NotificationChannel(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    MOCK_SENT = "MOCK_SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CANCELLED = "CANCELLED"


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
    BOQ_HEADER       = "BOQ_HEADER"
    PURCHASE_ORDER   = "PURCHASE_ORDER"
    DELIVERY         = "DELIVERY"
    INVOICE          = "INVOICE"
    USAGE_LOG        = "USAGE_LOG"
    CERTIFICATION    = "CERTIFICATION"
    STAGE_STATUS     = "STAGE_STATUS"      # milestone progress photos
    PAYMENT          = "PAYMENT"           # proof of payment
    FUEL_LOG         = "FUEL_LOG"          # extra fuel evidence photos
    MATERIAL_REQUEST = "MATERIAL_REQUEST"  # Phase 3I: MR documents
    SUPPLIER         = "SUPPLIER"          # Phase 3I: supplier documents
    LOT              = "LOT"               # Phase 3K: lot/unit documents
    PROJECT          = "PROJECT"           # Phase 3K: project-level documents


class AttachmentType(str, enum.Enum):
    # Generic types
    PHOTO          = "PHOTO"
    PDF            = "PDF"
    # Procurement
    DELIVERY_NOTE  = "DELIVERY_NOTE"
    INVOICE_COPY   = "INVOICE_COPY"
    PROOF          = "PROOF"
    CERTIFICATE    = "CERTIFICATE"
    QUOTATION      = "QUOTATION"        # Phase 3K: supplier quotation
    PO_DOCUMENT    = "PO_DOCUMENT"      # Phase 3K: purchase order document
    # Site/progress
    PROGRESS_PHOTO    = "PROGRESS_PHOTO"    # Phase 3K: construction progress shot
    PROOF_OF_WORK     = "PROOF_OF_WORK"     # Phase 3K: work completion evidence
    FUEL_SLIP         = "FUEL_SLIP"         # Phase 3K: fuel receipt/pump photo
    # Phase FINAL-2: milestone/delivery categorised photos
    BEFORE_PHOTO      = "BEFORE_PHOTO"      # before-work photo
    COMPLETION_PHOTO  = "COMPLETION_PHOTO"  # completion evidence
    ISSUE_PHOTO       = "ISSUE_PHOTO"       # defect/issue photo
    DELIVERY_EVIDENCE = "DELIVERY_EVIDENCE" # delivery verification photo


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


class JobCardStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SITE_APPROVED = "SITE_APPROVED"
    OFFICE_APPROVED = "OFFICE_APPROVED"
    OWNER_APPROVED = "OWNER_APPROVED"
    PAYMENT_APPROVED = "PAYMENT_APPROVED"
    PAID = "PAID"
    REJECTED = "REJECTED"


class JobCardWorkType(str, enum.Enum):
    DAILY_LABOUR = "DAILY_LABOUR"
    CONTRACT = "CONTRACT"
    SUBCONTRACTOR = "SUBCONTRACTOR"
    OVERTIME = "OVERTIME"


class VehicleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"


class VehicleType(str, enum.Enum):
    BAKKIE = "BAKKIE"
    TRUCK = "TRUCK"
    TLB = "TLB"
    EXCAVATOR = "EXCAVATOR"
    CRANE = "CRANE"
    VAN = "VAN"
    OTHER = "OTHER"


class VehicleCostType(str, enum.Enum):
    FUEL = "FUEL"
    TYRE = "TYRE"
    REPAIR = "REPAIR"
    SERVICE = "SERVICE"
    LICENCE = "LICENCE"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    TRANSFER = "TRANSFER"
    ISSUE = "ISSUE"
    OVERRUN_ACCEPTED = "OVERRUN_ACCEPTED"
    UPLOAD = "UPLOAD"
    SIGN = "SIGN"
    SEND = "SEND"


# ── Document AI / Site Capture enums ─────────────────────────────────────────

class ExtractionStatus(str, enum.Enum):
    EXTRACTED          = "EXTRACTED"
    OCR_REQUIRED       = "OCR_REQUIRED"
    OCR_NOT_AVAILABLE  = "OCR_NOT_AVAILABLE"
    FAILED             = "FAILED"
    NEEDS_REVIEW       = "NEEDS_REVIEW"


class DocumentSourceType(str, enum.Enum):
    INVOICE          = "INVOICE"
    DELIVERY_NOTE    = "DELIVERY_NOTE"
    QUOTE            = "QUOTE"
    GMAIL_ATTACHMENT = "GMAIL_ATTACHMENT"
    SITE_UPLOAD      = "SITE_UPLOAD"
    EXPENSE          = "EXPENSE"


class VerificationStatus(str, enum.Enum):
    DRAFT    = "DRAFT"
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    REJECTED = "REJECTED"


class ExpenseCategory(str, enum.Enum):
    VEHICLE_REPAIR = "VEHICLE_REPAIR"
    FUEL           = "FUEL"
    TOOL_REPAIR    = "TOOL_REPAIR"
    SITE_EXPENSE   = "SITE_EXPENSE"
    OTHER          = "OTHER"


class ExpenseStatus(str, enum.Enum):
    UPLOADED     = "UPLOADED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED     = "APPROVED"
    REJECTED     = "REJECTED"
    PAID         = "PAID"


class DocMatchStatus(str, enum.Enum):
    MATCHED      = "MATCHED"
    MISMATCH     = "MISMATCH"
    UNMATCHED    = "UNMATCHED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
