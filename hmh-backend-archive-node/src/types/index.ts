import { Request } from 'express';

// ============================================================
// ENUMS (mirror the DB enums in TypeScript)
// ============================================================
export type UserRole = 'OWNER' | 'OFFICE_ADMIN' | 'OFFICE_USER' | 'SITE_MANAGER' | 'SITE_STAFF';
export type ProjectStatus = 'PLANNED' | 'ACTIVE' | 'PAUSED' | 'COMPLETED';
export type RecordStatus = 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED' | 'SENT' | 'RECEIVED' | 'MATCHED' | 'PAID' | 'CANCELLED';
export type StageStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'AWAITING_INSPECTION' | 'CERTIFIED';
export type ItemType = 'MATERIAL' | 'SERVICE' | 'PACKAGE';
export type MovementType = 'OPENING_BALANCE' | 'DELIVERY_RECEIVED' | 'USAGE' | 'ADJUSTMENT_ADD' | 'ADJUSTMENT_SUBTRACT' | 'RETURN_TO_STORE';
export type InvoiceMatchStatus = 'MATCHED' | 'PARTIALLY_MATCHED' | 'MISMATCH' | 'UNLINKED';
export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AlertType =
  | 'BOQ_VARIANCE_OVERUSE'
  | 'DELIVERY_WITHOUT_PO'
  | 'INVOICE_MISMATCH'
  | 'NEGATIVE_STOCK'
  | 'LOW_STOCK'
  | 'MISSING_REMAINING_STOCK_PHOTO'
  | 'OVERDUE_PAYMENT'
  | 'REQUEST_PENDING_TOO_LONG'
  | 'DELIVERY_DISCREPANCY';
export type PaymentType = 'SUPPLIER' | 'LABOUR' | 'OTHER';
export type PaymentStatus = 'PENDING' | 'APPROVED' | 'PAID' | 'FAILED' | 'CANCELLED';

// ============================================================
// DOMAIN MODELS (row shapes returned from DB)
// ============================================================
export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  password_hash: string;
  role: UserRole;
  is_active: boolean;
  must_reset_password: boolean;
  last_login_at: Date | null;
  failed_login_attempts: number;
  locked_until: Date | null;
  created_by: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface Project {
  id: string;
  name: string;
  code: string;
  description: string | null;
  location: string | null;
  client_name: string | null;
  start_date: Date | null;
  estimated_end_date: Date | null;
  go_live_date: Date | null;
  status: ProjectStatus;
  created_by: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface Site {
  id: string;
  project_id: string;
  name: string;
  code: string | null;
  site_type: string;
  location_description: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

export interface Lot {
  id: string;
  project_id: string;
  site_id: string | null;
  lot_number: string;
  unit_type: string | null;
  block_number: string | null;
  status: string;
  created_at: Date;
  updated_at: Date;
}

export interface StageMaster {
  id: string;
  name: string;
  sequence_order: number;
  description: string | null;
  created_at: Date;
}

export interface Supplier {
  id: string;
  name: string;
  code: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  contact_person: string | null;
  payment_terms: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

export interface Item {
  id: string;
  name: string;
  normalized_name: string;
  category_id: string | null;
  default_unit: string | null;
  item_type: ItemType;
  requires_remaining_photo: boolean;
  is_high_risk: boolean;
  is_active: boolean;
  notes: string | null;
  created_at: Date;
  updated_at: Date;
}

// ============================================================
// AUTH TYPES
// ============================================================
export interface JwtPayload {
  sub: string;       // user id
  email: string;
  role: UserRole;
  iat?: number;
  exp?: number;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: string;
}

// ============================================================
// REQUEST EXTENSIONS
// ============================================================
export interface AuthRequest extends Request {
  user?: JwtPayload;
}

// ============================================================
// API RESPONSE SHAPES
// ============================================================
export interface ApiSuccess<T = unknown> {
  success: true;
  data: T;
  message?: string;
}

export interface ApiError {
  success: false;
  message: string;
  errors?: Record<string, string[]>;
  code?: string;
}

export type ApiResponse<T = unknown> = ApiSuccess<T> | ApiError;

// ============================================================
// PAGINATION
// ============================================================
export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface PaginationQuery {
  page?: number;
  limit?: number;
}
