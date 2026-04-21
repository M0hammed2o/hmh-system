-- HMH Group Construction Management System
-- PostgreSQL Schema V1
-- Run this file once against a fresh database.

-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE user_role_enum AS ENUM ('OWNER', 'OFFICE_ADMIN', 'OFFICE_USER', 'SITE_MANAGER', 'SITE_STAFF');
CREATE TYPE project_status_enum AS ENUM ('PLANNED', 'ACTIVE', 'PAUSED', 'COMPLETED');
CREATE TYPE record_status_enum AS ENUM ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SENT', 'RECEIVED', 'MATCHED', 'PAID', 'CANCELLED');
CREATE TYPE stage_status_enum AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'AWAITING_INSPECTION', 'CERTIFIED');
CREATE TYPE item_type_enum AS ENUM ('MATERIAL', 'SERVICE', 'PACKAGE');
CREATE TYPE movement_type_enum AS ENUM ('OPENING_BALANCE', 'DELIVERY_RECEIVED', 'USAGE', 'ADJUSTMENT_ADD', 'ADJUSTMENT_SUBTRACT', 'RETURN_TO_STORE');
CREATE TYPE invoice_match_status_enum AS ENUM ('MATCHED', 'PARTIALLY_MATCHED', 'MISMATCH', 'UNLINKED');
CREATE TYPE alert_status_enum AS ENUM ('OPEN', 'ACKNOWLEDGED', 'RESOLVED');
CREATE TYPE alert_severity_enum AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
CREATE TYPE alert_type_enum AS ENUM (
  'BOQ_VARIANCE_OVERUSE',
  'DELIVERY_WITHOUT_PO',
  'INVOICE_MISMATCH',
  'NEGATIVE_STOCK',
  'LOW_STOCK',
  'MISSING_REMAINING_STOCK_PHOTO',
  'OVERDUE_PAYMENT',
  'REQUEST_PENDING_TOO_LONG',
  'DELIVERY_DISCREPANCY'
);
CREATE TYPE payment_type_enum AS ENUM ('SUPPLIER', 'LABOUR', 'OTHER');
CREATE TYPE payment_status_enum AS ENUM ('PENDING', 'APPROVED', 'PAID', 'FAILED', 'CANCELLED');
CREATE TYPE attachment_entity_enum AS ENUM (
  'BOQ_HEADER',
  'PURCHASE_ORDER',
  'DELIVERY',
  'INVOICE',
  'USAGE_LOG',
  'CERTIFICATION'
);
CREATE TYPE attachment_type_enum AS ENUM (
  'PHOTO',
  'PDF',
  'DELIVERY_NOTE',
  'INVOICE_COPY',
  'PROOF',
  'CERTIFICATE'
);
CREATE TYPE lot_status_enum AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'ON_HOLD');

-- ============================================================
-- USERS AND CORE ACCESS
-- ============================================================
CREATE TABLE users (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name             VARCHAR(255) NOT NULL,
  email                 VARCHAR(255) UNIQUE NOT NULL,
  phone                 VARCHAR(50),
  password_hash         TEXT NOT NULL,
  role                  user_role_enum NOT NULL,
  is_active             BOOLEAN NOT NULL DEFAULT TRUE,
  must_reset_password   BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at         TIMESTAMPTZ,
  failed_login_attempts INT NOT NULL DEFAULT 0,
  locked_until          TIMESTAMPTZ,
  created_by            UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- ============================================================
-- PROJECTS
-- ============================================================
CREATE TABLE projects (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                VARCHAR(255) NOT NULL,
  code                VARCHAR(100) UNIQUE NOT NULL,
  description         TEXT,
  location            TEXT,
  client_name         VARCHAR(255),
  start_date          DATE,
  estimated_end_date  DATE,
  go_live_date        DATE,
  status              project_status_enum NOT NULL DEFAULT 'PLANNED',
  created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_code ON projects(code);

-- ============================================================
-- SITES
-- ============================================================
CREATE TABLE sites (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name                  VARCHAR(255) NOT NULL,
  code                  VARCHAR(100),
  site_type             VARCHAR(100) NOT NULL DEFAULT 'construction_site',
  location_description  TEXT,
  is_active             BOOLEAN NOT NULL DEFAULT TRUE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, code)
);

CREATE INDEX idx_sites_project_id ON sites(project_id);

-- ============================================================
-- LOTS
-- ============================================================
CREATE TABLE lots (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id      UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_number   VARCHAR(100) NOT NULL,
  unit_type    VARCHAR(100),
  block_number VARCHAR(100),
  status       lot_status_enum NOT NULL DEFAULT 'PENDING',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, lot_number)
);

CREATE INDEX idx_lots_project_id ON lots(project_id);
CREATE INDEX idx_lots_site_id ON lots(site_id);

-- ============================================================
-- USER ACCESS CONTROL
-- ============================================================
CREATE TABLE user_project_access (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  can_view    BOOLEAN NOT NULL DEFAULT TRUE,
  can_edit    BOOLEAN NOT NULL DEFAULT FALSE,
  can_approve BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, project_id)
);

CREATE INDEX idx_upa_user_id ON user_project_access(user_id);
CREATE INDEX idx_upa_project_id ON user_project_access(project_id);

CREATE TABLE user_site_access (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  site_id                 UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  can_receive_delivery    BOOLEAN NOT NULL DEFAULT FALSE,
  can_record_usage        BOOLEAN NOT NULL DEFAULT FALSE,
  can_request_stock       BOOLEAN NOT NULL DEFAULT FALSE,
  can_update_stage        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, site_id)
);

CREATE INDEX idx_usa_user_id ON user_site_access(user_id);
CREATE INDEX idx_usa_site_id ON user_site_access(site_id);

-- ============================================================
-- STAGES
-- ============================================================
CREATE TABLE stage_master (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           VARCHAR(100) UNIQUE NOT NULL,
  sequence_order INT UNIQUE NOT NULL,
  description    TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_stage_status (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id                  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id                     UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_id                      UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id                    UUID NOT NULL REFERENCES stage_master(id),
  status                      stage_status_enum NOT NULL DEFAULT 'NOT_STARTED',
  started_at                  TIMESTAMPTZ,
  completed_at                TIMESTAMPTZ,
  certified_at                TIMESTAMPTZ,
  inspection_required         BOOLEAN NOT NULL DEFAULT FALSE,
  certification_required      BOOLEAN NOT NULL DEFAULT FALSE,
  ready_for_labour_payment    BOOLEAN NOT NULL DEFAULT FALSE,
  notes                       TEXT,
  updated_by                  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, site_id, lot_id, stage_id)
);

CREATE INDEX idx_pss_project_id ON project_stage_status(project_id);
CREATE INDEX idx_pss_site_id ON project_stage_status(site_id);
CREATE INDEX idx_pss_lot_id ON project_stage_status(lot_id);

-- ============================================================
-- SUPPLIERS AND ITEMS
-- ============================================================
CREATE TABLE suppliers (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           VARCHAR(255) UNIQUE NOT NULL,
  code           VARCHAR(100),
  email          VARCHAR(255),
  phone          VARCHAR(50),
  address        TEXT,
  contact_person VARCHAR(255),
  payment_terms  VARCHAR(100),
  notes          TEXT,
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_suppliers_name ON suppliers(name);

CREATE TABLE item_categories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        VARCHAR(100) UNIQUE NOT NULL,
  description TEXT,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE items (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                      VARCHAR(255) NOT NULL,
  normalized_name           VARCHAR(255) NOT NULL,
  category_id               UUID REFERENCES item_categories(id) ON DELETE SET NULL,
  default_unit              VARCHAR(50),
  item_type                 item_type_enum NOT NULL DEFAULT 'MATERIAL',
  requires_remaining_photo  BOOLEAN NOT NULL DEFAULT FALSE,
  is_high_risk              BOOLEAN NOT NULL DEFAULT FALSE,
  is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
  notes                     TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_items_normalized_name ON items(normalized_name);
CREATE INDEX idx_items_category_id ON items(category_id);

CREATE TABLE item_aliases (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id     UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  alias_name  VARCHAR(255) NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(alias_name)
);

CREATE INDEX idx_item_aliases_item_id ON item_aliases(item_id);

-- ============================================================
-- BOQ
-- ============================================================
CREATE TYPE boq_status_enum AS ENUM ('DRAFT', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'ARCHIVED');

CREATE TABLE boq_headers (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version_name      VARCHAR(255) NOT NULL,
  source_file_name  VARCHAR(255),
  source_type       VARCHAR(50) NOT NULL DEFAULT 'pdf',
  status            boq_status_enum NOT NULL DEFAULT 'DRAFT',
  is_active_version BOOLEAN NOT NULL DEFAULT FALSE,
  uploaded_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes             TEXT
);

-- Only one active BOQ version per project
CREATE UNIQUE INDEX idx_boq_one_active_per_project
  ON boq_headers(project_id)
  WHERE is_active_version = TRUE;

CREATE INDEX idx_boq_headers_project_id ON boq_headers(project_id);

CREATE TABLE boq_sections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  boq_header_id   UUID NOT NULL REFERENCES boq_headers(id) ON DELETE CASCADE,
  stage_id        UUID REFERENCES stage_master(id) ON DELETE SET NULL,
  section_name    VARCHAR(255) NOT NULL,
  sequence_order  INT NOT NULL DEFAULT 0,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_boq_sections_header_id ON boq_sections(boq_header_id);

CREATE TABLE boq_items (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  boq_section_id          UUID NOT NULL REFERENCES boq_sections(id) ON DELETE CASCADE,
  project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id                 UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_id                  UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id                UUID REFERENCES stage_master(id) ON DELETE SET NULL,
  item_id                 UUID REFERENCES items(id) ON DELETE SET NULL,
  supplier_id             UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  raw_description         TEXT NOT NULL,
  normalized_description  TEXT,
  specification           TEXT,
  item_type               item_type_enum NOT NULL DEFAULT 'MATERIAL',
  unit                    VARCHAR(50),
  planned_quantity        NUMERIC(14,3),
  planned_rate            NUMERIC(14,2),
  planned_total           NUMERIC(14,2) GENERATED ALWAYS AS (
                            CASE WHEN planned_quantity IS NOT NULL AND planned_rate IS NOT NULL
                            THEN ROUND(planned_quantity * planned_rate, 2)
                            ELSE planned_total_override END
                          ) STORED,
  planned_total_override  NUMERIC(14,2),
  sort_order              INT NOT NULL DEFAULT 0,
  is_active               BOOLEAN NOT NULL DEFAULT TRUE,
  notes                   TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_boq_items_section_id ON boq_items(boq_section_id);
CREATE INDEX idx_boq_items_project_id ON boq_items(project_id);
CREATE INDEX idx_boq_items_item_id ON boq_items(item_id);

-- ============================================================
-- MATERIAL REQUESTS
-- ============================================================
CREATE TABLE material_requests (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_number        VARCHAR(100) UNIQUE NOT NULL,
  project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id               UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  lot_id                UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id              UUID REFERENCES stage_master(id) ON DELETE SET NULL,
  requested_by          UUID NOT NULL REFERENCES users(id),
  preferred_supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  status                record_status_enum NOT NULL DEFAULT 'DRAFT',
  requested_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  needed_by_date        DATE,
  reviewed_by           UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at           TIMESTAMPTZ,
  rejection_reason      TEXT,
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mr_project_id ON material_requests(project_id);
CREATE INDEX idx_mr_site_id ON material_requests(site_id);
CREATE INDEX idx_mr_status ON material_requests(status);

CREATE TABLE material_request_items (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  material_request_id  UUID NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
  item_id              UUID NOT NULL REFERENCES items(id),
  boq_item_id          UUID REFERENCES boq_items(id) ON DELETE SET NULL,
  requested_quantity   NUMERIC(14,3) NOT NULL,
  unit                 VARCHAR(50),
  remarks              TEXT
);

CREATE INDEX idx_mri_request_id ON material_request_items(material_request_id);

-- ============================================================
-- PURCHASE ORDERS
-- ============================================================
CREATE TABLE purchase_orders (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  po_number               VARCHAR(100) UNIQUE NOT NULL,
  project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id                 UUID REFERENCES sites(id) ON DELETE SET NULL,
  supplier_id             UUID NOT NULL REFERENCES suppliers(id),
  material_request_id     UUID REFERENCES material_requests(id) ON DELETE SET NULL,
  status                  record_status_enum NOT NULL DEFAULT 'DRAFT',
  po_date                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expected_delivery_date  DATE,
  subtotal_amount         NUMERIC(14,2) NOT NULL DEFAULT 0,
  vat_amount              NUMERIC(14,2) NOT NULL DEFAULT 0,
  total_amount            NUMERIC(14,2) NOT NULL DEFAULT 0,
  created_by              UUID NOT NULL REFERENCES users(id),
  approved_by             UUID REFERENCES users(id) ON DELETE SET NULL,
  sent_at                 TIMESTAMPTZ,
  notes                   TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_po_project_id ON purchase_orders(project_id);
CREATE INDEX idx_po_supplier_id ON purchase_orders(supplier_id);
CREATE INDEX idx_po_status ON purchase_orders(status);

CREATE TABLE purchase_order_items (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_order_id   UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  item_id             UUID REFERENCES items(id) ON DELETE SET NULL,
  boq_item_id         UUID REFERENCES boq_items(id) ON DELETE SET NULL,
  lot_id              UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id            UUID REFERENCES stage_master(id) ON DELETE SET NULL,
  description         TEXT NOT NULL,
  quantity_ordered    NUMERIC(14,3) NOT NULL,
  unit                VARCHAR(50),
  rate                NUMERIC(14,2),
  line_total          NUMERIC(14,2),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_poi_po_id ON purchase_order_items(purchase_order_id);

CREATE TYPE email_status_enum AS ENUM ('queued', 'sent', 'failed', 'bounced');

CREATE TABLE po_email_logs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_order_id     UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  sent_to_email         VARCHAR(255) NOT NULL,
  sent_by               UUID REFERENCES users(id) ON DELETE SET NULL,
  email_subject         VARCHAR(255),
  provider_message_id   VARCHAR(255),
  status                email_status_enum NOT NULL DEFAULT 'queued',
  error_message         TEXT,
  sent_at               TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_po_email_logs_po_id ON po_email_logs(purchase_order_id);

-- ============================================================
-- DELIVERIES
-- ============================================================
CREATE TABLE deliveries (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_number                 VARCHAR(100) UNIQUE,
  purchase_order_id               UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
  supplier_id                     UUID NOT NULL REFERENCES suppliers(id),
  project_id                      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id                         UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  received_by_user_id             UUID NOT NULL REFERENCES users(id),
  delivery_date                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  supplier_delivery_note_number   VARCHAR(100),
  delivery_status                 record_status_enum NOT NULL DEFAULT 'RECEIVED',
  comments                        TEXT,
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deliveries_project_id ON deliveries(project_id);
CREATE INDEX idx_deliveries_site_id ON deliveries(site_id);
CREATE INDEX idx_deliveries_po_id ON deliveries(purchase_order_id);

CREATE TABLE delivery_items (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_id              UUID NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
  purchase_order_item_id   UUID REFERENCES purchase_order_items(id) ON DELETE SET NULL,
  item_id                  UUID REFERENCES items(id) ON DELETE SET NULL,
  boq_item_id              UUID REFERENCES boq_items(id) ON DELETE SET NULL,
  description              TEXT NOT NULL,
  quantity_expected        NUMERIC(14,3),
  quantity_received        NUMERIC(14,3) NOT NULL,
  unit                     VARCHAR(50),
  discrepancy_reason       TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_delivery_items_delivery_id ON delivery_items(delivery_id);

-- ============================================================
-- STOCK LEDGER
-- ============================================================
CREATE TABLE stock_ledger (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id         UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  lot_id          UUID REFERENCES lots(id) ON DELETE SET NULL,
  item_id         UUID NOT NULL REFERENCES items(id),
  boq_item_id     UUID REFERENCES boq_items(id) ON DELETE SET NULL,
  movement_type   movement_type_enum NOT NULL,
  reference_type  VARCHAR(50) NOT NULL,
  reference_id    UUID,
  quantity_in     NUMERIC(14,3) NOT NULL DEFAULT 0,
  quantity_out    NUMERIC(14,3) NOT NULL DEFAULT 0,
  unit            VARCHAR(50),
  unit_cost       NUMERIC(14,2),
  movement_date   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  entered_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stock_ledger_project_site_item ON stock_ledger(project_id, site_id, item_id);
CREATE INDEX idx_stock_ledger_movement_date ON stock_ledger(movement_date);
CREATE INDEX idx_stock_ledger_reference ON stock_ledger(reference_type, reference_id);

-- ============================================================
-- USAGE LOGS
-- ============================================================
CREATE TABLE usage_logs (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id                  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id                     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  lot_id                      UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id                    UUID REFERENCES stage_master(id) ON DELETE SET NULL,
  item_id                     UUID NOT NULL REFERENCES items(id),
  boq_item_id                 UUID REFERENCES boq_items(id) ON DELETE SET NULL,
  quantity_used               NUMERIC(14,3) NOT NULL,
  used_by_person_name         VARCHAR(255),
  used_by_team_name           VARCHAR(255),
  recorded_by_user_id         UUID NOT NULL REFERENCES users(id),
  remaining_quantity_after_use NUMERIC(14,3),
  usage_date                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  comments                    TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_usage_logs_project_id ON usage_logs(project_id);
CREATE INDEX idx_usage_logs_site_id ON usage_logs(site_id);
CREATE INDEX idx_usage_logs_item_id ON usage_logs(item_id);

-- ============================================================
-- INVOICES
-- ============================================================
CREATE TABLE invoices (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_number    VARCHAR(100) NOT NULL,
  supplier_id       UUID NOT NULL REFERENCES suppliers(id),
  project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id           UUID REFERENCES sites(id) ON DELETE SET NULL,
  purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
  invoice_date      DATE,
  due_date          DATE,
  subtotal_amount   NUMERIC(14,2),
  vat_amount        NUMERIC(14,2),
  total_amount      NUMERIC(14,2) NOT NULL,
  status            record_status_enum NOT NULL DEFAULT 'DRAFT',
  captured_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  captured_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(supplier_id, invoice_number)
);

CREATE INDEX idx_invoices_project_id ON invoices(project_id);
CREATE INDEX idx_invoices_supplier_id ON invoices(supplier_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);

-- ============================================================
-- PAYMENTS
-- ============================================================
CREATE TABLE payments (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id         UUID REFERENCES invoices(id) ON DELETE SET NULL,
  supplier_id        UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  payment_type       payment_type_enum NOT NULL,
  payment_reference  VARCHAR(100) UNIQUE,
  payment_date       DATE,
  amount_paid        NUMERIC(14,2) NOT NULL,
  status             payment_status_enum NOT NULL DEFAULT 'PENDING',
  approved_by        UUID REFERENCES users(id) ON DELETE SET NULL,
  captured_by        UUID REFERENCES users(id) ON DELETE SET NULL,
  notes              TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payments_project_id ON payments(project_id);
CREATE INDEX idx_payments_invoice_id ON payments(invoice_id);
CREATE INDEX idx_payments_status ON payments(status);

-- ============================================================
-- INVOICE MATCHING
-- ============================================================
CREATE TABLE invoice_matching_results (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id        UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
  delivery_id       UUID REFERENCES deliveries(id) ON DELETE SET NULL,
  match_status      invoice_match_status_enum NOT NULL DEFAULT 'UNLINKED',
  quantity_match    BOOLEAN NOT NULL DEFAULT FALSE,
  amount_match      BOOLEAN NOT NULL DEFAULT FALSE,
  supplier_match    BOOLEAN NOT NULL DEFAULT FALSE,
  notes             TEXT,
  checked_by        UUID REFERENCES users(id) ON DELETE SET NULL,
  checked_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_imr_invoice_id ON invoice_matching_results(invoice_id);
CREATE INDEX idx_imr_po_id ON invoice_matching_results(purchase_order_id);

-- ============================================================
-- ATTACHMENTS
-- ============================================================
CREATE TABLE attachments (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type       attachment_entity_enum NOT NULL,
  entity_id         UUID NOT NULL,
  file_name         VARCHAR(255) NOT NULL,
  stored_path       TEXT NOT NULL,
  mime_type         VARCHAR(100) NOT NULL,
  file_size_bytes   BIGINT,
  attachment_type   attachment_type_enum NOT NULL,
  uploaded_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_attachments_entity ON attachments(entity_type, entity_id);

CREATE TABLE usage_remaining_proofs (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usage_log_id         UUID NOT NULL REFERENCES usage_logs(id) ON DELETE CASCADE,
  photo_attachment_id  UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  notes                TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SYSTEM ALERTS
-- ============================================================
CREATE TABLE system_alerts (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID REFERENCES projects(id) ON DELETE SET NULL,
  site_id               UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_id                UUID REFERENCES lots(id) ON DELETE SET NULL,
  reference_type        VARCHAR(100),
  reference_id          UUID,
  alert_type            alert_type_enum NOT NULL,
  severity              alert_severity_enum NOT NULL DEFAULT 'MEDIUM',
  title                 VARCHAR(255) NOT NULL,
  message               TEXT NOT NULL,
  status                alert_status_enum NOT NULL DEFAULT 'OPEN',
  notification_channel  VARCHAR(50) DEFAULT 'in_app',
  sent_at               TIMESTAMPTZ,
  read_at               TIMESTAMPTZ,
  acknowledged_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  acknowledged_at       TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at           TIMESTAMPTZ,
  resolved_by           UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_alerts_project_id ON system_alerts(project_id);
CREATE INDEX idx_alerts_status ON system_alerts(status);
CREATE INDEX idx_alerts_type ON system_alerts(alert_type);

-- ============================================================
-- AUDIT LOGS
-- ============================================================
CREATE TABLE audit_logs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
  entity_type     VARCHAR(100) NOT NULL,
  entity_id       UUID,
  action          VARCHAR(100) NOT NULL,
  old_values_json JSONB,
  new_values_json JSONB,
  ip_address      VARCHAR(100),
  user_agent      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);

-- ============================================================
-- MID-PROJECT ONBOARDING
-- ============================================================
CREATE TABLE project_opening_balances (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id          UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_id           UUID REFERENCES lots(id) ON DELETE SET NULL,
  item_id          UUID NOT NULL REFERENCES items(id),
  quantity_on_hand NUMERIC(14,3) NOT NULL,
  estimated_value  NUMERIC(14,2),
  as_of_date       DATE NOT NULL,
  entered_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  is_posted        BOOLEAN NOT NULL DEFAULT FALSE,
  posted_at        TIMESTAMPTZ,
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opening_balances_project_id ON project_opening_balances(project_id);

CREATE TABLE project_opening_stage_status (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  site_id     UUID REFERENCES sites(id) ON DELETE SET NULL,
  lot_id      UUID REFERENCES lots(id) ON DELETE SET NULL,
  stage_id    UUID NOT NULL REFERENCES stage_master(id),
  status      stage_status_enum NOT NULL,
  as_of_date  DATE NOT NULL,
  entered_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  notes       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE opening_financial_status_enum AS ENUM ('OUTSTANDING', 'PARTIALLY_PAID', 'PAID', 'DISPUTED');
CREATE TYPE opening_reference_type_enum AS ENUM ('INVOICE', 'PO', 'PAYMENT', 'OTHER');

CREATE TABLE project_opening_financials (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  supplier_id      UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  reference_type   opening_reference_type_enum NOT NULL,
  reference_number VARCHAR(100),
  amount           NUMERIC(14,2) NOT NULL,
  status           opening_financial_status_enum NOT NULL DEFAULT 'OUTSTANDING',
  as_of_date       DATE NOT NULL,
  entered_by       UUID REFERENCES users(id) ON DELETE SET NULL,
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opening_financials_project_id ON project_opening_financials(project_id);

-- ============================================================
-- SYSTEM CONFIG (alert thresholds, configurable values)
-- ============================================================
CREATE TABLE system_config (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  config_key  VARCHAR(100) UNIQUE NOT NULL,
  config_value TEXT NOT NULL,
  description TEXT,
  updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default config values
INSERT INTO system_config (config_key, config_value, description) VALUES
  ('boq_variance_overuse_threshold_pct', '10', 'Percentage over BOQ planned quantity before alert fires'),
  ('low_stock_threshold_pct', '20', 'Percentage of planned quantity remaining before LOW_STOCK alert'),
  ('overdue_payment_days', '30', 'Days past due_date before OVERDUE_PAYMENT alert fires'),
  ('request_pending_too_long_days', '5', 'Days a material request can sit in SUBMITTED before alert fires');

-- ============================================================
-- VIEWS — convenience
-- ============================================================
CREATE VIEW v_stock_balance AS
SELECT
  project_id,
  site_id,
  lot_id,
  item_id,
  SUM(quantity_in) - SUM(quantity_out) AS balance,
  MAX(movement_date) AS last_movement_date
FROM stock_ledger
GROUP BY project_id, site_id, lot_id, item_id;
