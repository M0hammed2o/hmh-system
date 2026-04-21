// =============================================================================
// TEMPORARY MOCK DATA — ALL MODULES
// Replace module-by-module as real backend routes are built.
// =============================================================================

export const MOCK_PROJECTS = [
  {
    id: "proj-001",
    name: "Cosmo City Phase 3",
    code: "HMH-CCP3",
    description: "Residential development — 120 mixed-income units across 3 sites.",
    location: "Cosmo City, Johannesburg",
    client_name: "Housing Development Agency",
    start_date: "2024-03-01",
    estimated_end_date: "2025-12-31",
    go_live_date: null,
    status: "ACTIVE",
    created_at: "2024-02-15T08:00:00Z",
    updated_at: "2025-04-01T10:00:00Z",
  },
  {
    id: "proj-002",
    name: "Midrand Business Park",
    code: "HMH-MBP1",
    description: "Commercial development — 3 warehouse units and 1 admin block.",
    location: "Midrand, Gauteng",
    client_name: "Midrand Industrial Holdings",
    start_date: "2024-07-01",
    estimated_end_date: "2026-06-30",
    go_live_date: null,
    status: "ACTIVE",
    created_at: "2024-06-10T09:00:00Z",
    updated_at: "2025-03-20T11:00:00Z",
  },
  {
    id: "proj-003",
    name: "Ruimsig Estate Phase 1",
    code: "HMH-REP1",
    description: "Residential estate — 45 cluster homes, gated community.",
    location: "Ruimsig, Johannesburg West",
    client_name: "Ruimsig Lifestyle Properties",
    start_date: "2025-06-01",
    estimated_end_date: "2027-05-31",
    go_live_date: null,
    status: "PLANNED",
    created_at: "2025-03-01T08:00:00Z",
    updated_at: "2025-03-01T08:00:00Z",
  },
];

export const MOCK_SITES = [
  { id: "site-001", project_id: "proj-001", name: "Site A — Block 1–40",   code: "CCP3-A", site_type: "Residential", location_description: "Northern section, Cosmo City",  is_active: true,  created_at: "2024-03-05T08:00:00Z", updated_at: "2024-03-05T08:00:00Z" },
  { id: "site-002", project_id: "proj-001", name: "Site B — Block 41–80",  code: "CCP3-B", site_type: "Residential", location_description: "Central section, Cosmo City",   is_active: true,  created_at: "2024-03-05T08:00:00Z", updated_at: "2024-03-05T08:00:00Z" },
  { id: "site-003", project_id: "proj-001", name: "Site C — Block 81–120", code: "CCP3-C", site_type: "Residential", location_description: "Southern section, Cosmo City",  is_active: false, created_at: "2024-03-05T08:00:00Z", updated_at: "2024-06-01T08:00:00Z" },
  { id: "site-004", project_id: "proj-002", name: "Warehouse Cluster",     code: "MBP-WH",  site_type: "Commercial",  location_description: "Main warehouse complex",         is_active: true,  created_at: "2024-07-10T08:00:00Z", updated_at: "2024-07-10T08:00:00Z" },
  { id: "site-005", project_id: "proj-002", name: "Admin Block",           code: "MBP-AB",  site_type: "Commercial",  location_description: "Front admin building",           is_active: true,  created_at: "2024-07-10T08:00:00Z", updated_at: "2024-07-10T08:00:00Z" },
];

export const MOCK_LOTS = [
  { id: "lot-001", project_id: "proj-001", site_id: "site-001", lot_number: "LOT-001", unit_type: "2-Bedroom", block_number: "BLK-01", status: "COMPLETED",    created_at: "2024-03-10T08:00:00Z", updated_at: "2025-01-15T08:00:00Z" },
  { id: "lot-002", project_id: "proj-001", site_id: "site-001", lot_number: "LOT-002", unit_type: "2-Bedroom", block_number: "BLK-01", status: "IN_PROGRESS",  created_at: "2024-03-10T08:00:00Z", updated_at: "2025-03-20T08:00:00Z" },
  { id: "lot-003", project_id: "proj-001", site_id: "site-001", lot_number: "LOT-003", unit_type: "3-Bedroom", block_number: "BLK-02", status: "IN_PROGRESS",  created_at: "2024-03-10T08:00:00Z", updated_at: "2025-04-01T08:00:00Z" },
  { id: "lot-004", project_id: "proj-001", site_id: "site-001", lot_number: "LOT-004", unit_type: "3-Bedroom", block_number: "BLK-02", status: "AVAILABLE",    created_at: "2024-03-10T08:00:00Z", updated_at: "2024-03-10T08:00:00Z" },
  { id: "lot-005", project_id: "proj-001", site_id: "site-002", lot_number: "LOT-041", unit_type: "2-Bedroom", block_number: "BLK-09", status: "IN_PROGRESS",  created_at: "2024-04-01T08:00:00Z", updated_at: "2025-02-10T08:00:00Z" },
  { id: "lot-006", project_id: "proj-001", site_id: "site-002", lot_number: "LOT-042", unit_type: "2-Bedroom", block_number: "BLK-09", status: "ON_HOLD",      created_at: "2024-04-01T08:00:00Z", updated_at: "2025-03-05T08:00:00Z" },
  { id: "lot-007", project_id: "proj-002", site_id: "site-004", lot_number: "WH-001",  unit_type: "Warehouse", block_number: "WH-A",   status: "IN_PROGRESS",  created_at: "2024-07-15T08:00:00Z", updated_at: "2025-03-01T08:00:00Z" },
  { id: "lot-008", project_id: "proj-002", site_id: "site-004", lot_number: "WH-002",  unit_type: "Warehouse", block_number: "WH-B",   status: "AVAILABLE",    created_at: "2024-07-15T08:00:00Z", updated_at: "2024-07-15T08:00:00Z" },
];

export const STAGE_NAMES = ["Platform", "Slab", "Wallplate", "Roof", "Completion", "Plumbing", "Paint", "Tank", "Apron", "Screed", "Beam Filling"];

export const MOCK_STAGE_STATUSES = [
  // LOT-001 (COMPLETED)
  { id: "ss-001", project_id: "proj-001", site_id: "site-001", lot_id: "lot-001", stage_name: "Platform",     status: "CERTIFIED",    completed_at: "2024-05-10T00:00:00Z", certified_at: "2024-05-15T00:00:00Z" },
  { id: "ss-002", project_id: "proj-001", site_id: "site-001", lot_id: "lot-001", stage_name: "Slab",         status: "CERTIFIED",    completed_at: "2024-06-20T00:00:00Z", certified_at: "2024-06-25T00:00:00Z" },
  { id: "ss-003", project_id: "proj-001", site_id: "site-001", lot_id: "lot-001", stage_name: "Wallplate",    status: "CERTIFIED",    completed_at: "2024-08-15T00:00:00Z", certified_at: "2024-08-20T00:00:00Z" },
  { id: "ss-004", project_id: "proj-001", site_id: "site-001", lot_id: "lot-001", stage_name: "Roof",         status: "CERTIFIED",    completed_at: "2024-10-05T00:00:00Z", certified_at: "2024-10-10T00:00:00Z" },
  { id: "ss-005", project_id: "proj-001", site_id: "site-001", lot_id: "lot-001", stage_name: "Completion",   status: "CERTIFIED",    completed_at: "2024-12-20T00:00:00Z", certified_at: "2024-12-28T00:00:00Z" },
  // LOT-002 (IN_PROGRESS — roof done, completion not started)
  { id: "ss-006", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", stage_name: "Platform",     status: "CERTIFIED",    completed_at: "2024-06-01T00:00:00Z", certified_at: "2024-06-05T00:00:00Z" },
  { id: "ss-007", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", stage_name: "Slab",         status: "CERTIFIED",    completed_at: "2024-07-10T00:00:00Z", certified_at: "2024-07-15T00:00:00Z" },
  { id: "ss-008", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", stage_name: "Wallplate",    status: "CERTIFIED",    completed_at: "2024-09-01T00:00:00Z", certified_at: "2024-09-05T00:00:00Z" },
  { id: "ss-009", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", stage_name: "Roof",         status: "IN_PROGRESS",  completed_at: null,                   certified_at: null },
  { id: "ss-010", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", stage_name: "Completion",   status: "NOT_STARTED",  completed_at: null,                   certified_at: null },
  // LOT-003 (IN_PROGRESS — slab done)
  { id: "ss-011", project_id: "proj-001", site_id: "site-001", lot_id: "lot-003", stage_name: "Platform",     status: "CERTIFIED",    completed_at: "2024-09-01T00:00:00Z", certified_at: "2024-09-05T00:00:00Z" },
  { id: "ss-012", project_id: "proj-001", site_id: "site-001", lot_id: "lot-003", stage_name: "Slab",         status: "AWAITING_INSPECTION", completed_at: "2025-03-15T00:00:00Z", certified_at: null },
  { id: "ss-013", project_id: "proj-001", site_id: "site-001", lot_id: "lot-003", stage_name: "Wallplate",    status: "NOT_STARTED",  completed_at: null,                   certified_at: null },
];

export const MOCK_BOQ_HEADERS = [
  { id: "boq-001", project_id: "proj-001", version_name: "Version 1.2 (Approved)", source_type: "manual", status: "ACTIVE", is_active_version: true,  uploaded_at: "2024-02-20T08:00:00Z", notes: "Revised after soil report" },
  { id: "boq-002", project_id: "proj-001", version_name: "Version 1.0 (Original)", source_type: "manual", status: "SUPERSEDED", is_active_version: false, uploaded_at: "2024-02-01T08:00:00Z", notes: null },
  { id: "boq-003", project_id: "proj-002", version_name: "Version 1.0 (Draft)",    source_type: "manual", status: "UNDER_REVIEW", is_active_version: false, uploaded_at: "2024-07-05T08:00:00Z", notes: "Awaiting client sign-off" },
];

export const MOCK_BOQ_ITEMS = [
  // Cosmo City — Foundation
  { id: "bi-001", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Foundation Work", raw_description: "Concrete M20 (foundations)", unit: "m³",   planned_quantity: 320, planned_rate: 1850, planned_total: 592000, sort_order: 1 },
  { id: "bi-002", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Foundation Work", raw_description: "Steel Rebar Y16",            unit: "kg",   planned_quantity: 18000, planned_rate: 18,   planned_total: 324000, sort_order: 2 },
  { id: "bi-003", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Foundation Work", raw_description: "Waterproofing membrane",     unit: "m²",   planned_quantity: 480,  planned_rate: 95,   planned_total: 45600,  sort_order: 3 },
  // Cosmo City — Brickwork
  { id: "bi-004", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Brickwork & Masonry", raw_description: "Face Brick (Engineering)", unit: "1000's", planned_quantity: 240, planned_rate: 4800, planned_total: 1152000, sort_order: 1 },
  { id: "bi-005", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Brickwork & Masonry", raw_description: "Plaster Sand",             unit: "m³",    planned_quantity: 180, planned_rate: 285,  planned_total: 51300,   sort_order: 2 },
  { id: "bi-006", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Brickwork & Masonry", raw_description: "OPC Cement 42.5N",         unit: "bag",   planned_quantity: 4800, planned_rate: 95,  planned_total: 456000,  sort_order: 3 },
  // Cosmo City — Roofing
  { id: "bi-007", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Roofing",             raw_description: "IBR Roof Sheet (0.58mm)",  unit: "m²",  planned_quantity: 6000, planned_rate: 185,  planned_total: 1110000, sort_order: 1 },
  { id: "bi-008", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Roofing",             raw_description: "Fascia Board 228x25mm",    unit: "m",   planned_quantity: 1200, planned_rate: 65,   planned_total: 78000,   sort_order: 2 },
  // Cosmo City — Plumbing
  { id: "bi-009", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Plumbing",            raw_description: "UPVC Pipe 110mm",          unit: "m",   planned_quantity: 2400, planned_rate: 55,   planned_total: 132000,  sort_order: 1 },
  { id: "bi-010", boq_header_id: "boq-001", project_id: "proj-001", section_name: "Plumbing",            raw_description: "PVC Ball Valve 25mm",      unit: "each", planned_quantity: 480, planned_rate: 85,   planned_total: 40800,   sort_order: 2 },
];

export const MOCK_SUPPLIERS = [
  { id: "sup-001", name: "AfriCon Materials (Pty) Ltd", code: "AFRI", email: "orders@africon.co.za", phone: "011 345 6789", payment_terms: "30 days", is_active: true },
  { id: "sup-002", name: "BuildSmart SA",                code: "BSM",  email: "sales@buildsmart.co.za", phone: "011 567 8901", payment_terms: "14 days", is_active: true },
  { id: "sup-003", name: "Maverix Roofing Supplies",     code: "MAV",  email: "info@maverix.co.za",  phone: "011 234 5678", payment_terms: "30 days", is_active: true },
  { id: "sup-004", name: "National Brick (SA)",          code: "NBSA", email: "orders@natlbrick.co.za", phone: "011 789 0123", payment_terms: "30 days", is_active: true },
  { id: "sup-005", name: "PlumbPro Supplies",            code: "PPR",  email: "trade@plumbpro.co.za", phone: "011 456 7890", payment_terms: "7 days",  is_active: true },
];

export const MOCK_PURCHASE_ORDERS = [
  { id: "po-001", po_number: "PO-2025-001", project_id: "proj-001", site_id: "site-001", supplier_id: "sup-001", supplier_name: "AfriCon Materials (Pty) Ltd", status: "APPROVED",  po_date: "2025-01-10T08:00:00Z", subtotal_amount: 592000, vat_amount: 77739, total_amount: 592000, notes: "Concrete and steel for Phase 3A" },
  { id: "po-002", po_number: "PO-2025-002", project_id: "proj-001", site_id: "site-001", supplier_id: "sup-004", supplier_name: "National Brick (SA)",          status: "SENT",      po_date: "2025-01-25T08:00:00Z", subtotal_amount: 1152000, vat_amount: 151304, total_amount: 1152000, notes: "Engineering bricks — Site A" },
  { id: "po-003", po_number: "PO-2025-003", project_id: "proj-001", site_id: "site-002", supplier_id: "sup-003", supplier_name: "Maverix Roofing Supplies",     status: "DRAFT",     po_date: "2025-02-05T08:00:00Z", subtotal_amount: 1110000, vat_amount: 145826, total_amount: 1110000, notes: "IBR roofing — Site B" },
  { id: "po-004", po_number: "PO-2025-004", project_id: "proj-001", site_id: "site-001", supplier_id: "sup-005", supplier_name: "PlumbPro Supplies",            status: "RECEIVED",  po_date: "2025-02-15T08:00:00Z", subtotal_amount: 132000,  vat_amount: 17339,  total_amount: 132000,  notes: "Plumbing materials — LOT-001 to LOT-020" },
  { id: "po-005", po_number: "PO-2025-005", project_id: "proj-002", site_id: "site-004", supplier_id: "sup-001", supplier_name: "AfriCon Materials (Pty) Ltd", status: "SUBMITTED", po_date: "2025-03-01T08:00:00Z", subtotal_amount: 325000,  vat_amount: 42717,  total_amount: 325000,  notes: "Foundation concrete — Warehouse A" },
  { id: "po-006", po_number: "PO-2025-006", project_id: "proj-001", site_id: "site-001", supplier_id: "sup-002", supplier_name: "BuildSmart SA",               status: "CANCELLED", po_date: "2025-01-05T08:00:00Z", subtotal_amount: 45600,   vat_amount: 5991,   total_amount: 45600,   notes: "Waterproofing — cancelled, changed supplier" },
];

export const MOCK_MATERIAL_REQUESTS = [
  { id: "mr-001", request_number: "MR-2025-001", project_id: "proj-001", site_id: "site-001", requested_by_name: "Sipho Nkosi", status: "SUBMITTED", requested_date: "2025-03-10T08:00:00Z", needed_by_date: "2025-03-20", notes: "Urgent — LOT-003 slab pour scheduled" },
  { id: "mr-002", request_number: "MR-2025-002", project_id: "proj-001", site_id: "site-002", requested_by_name: "Ahmed Patel",  status: "APPROVED",  requested_date: "2025-03-15T08:00:00Z", needed_by_date: "2025-04-01", notes: null },
  { id: "mr-003", request_number: "MR-2025-003", project_id: "proj-001", site_id: "site-001", requested_by_name: "Sipho Nkosi", status: "DRAFT",     requested_date: "2025-04-01T08:00:00Z", needed_by_date: "2025-04-15", notes: "Roofing materials" },
  { id: "mr-004", request_number: "MR-2025-004", project_id: "proj-002", site_id: "site-004", requested_by_name: "Johan Botha", status: "REJECTED",  requested_date: "2025-02-20T08:00:00Z", needed_by_date: "2025-03-01", notes: "Wrong item codes submitted" },
];

export const MOCK_DELIVERIES = [
  { id: "del-001", delivery_number: "DEL-2025-001", project_id: "proj-001", site_id: "site-001", purchase_order_id: "po-001", po_number: "PO-2025-001", supplier_name: "AfriCon Materials (Pty) Ltd", delivery_date: "2025-01-18T10:00:00Z", delivery_status: "MATCHED",   items_count: 3, comments: "All items received, no discrepancies" },
  { id: "del-002", delivery_number: "DEL-2025-002", project_id: "proj-001", site_id: "site-001", purchase_order_id: "po-002", po_number: "PO-2025-002", supplier_name: "National Brick (SA)",          delivery_date: "2025-02-05T09:00:00Z", delivery_status: "RECEIVED",  items_count: 1, comments: "Short delivery — 12 000 bricks received, 15 000 ordered" },
  { id: "del-003", delivery_number: "DEL-2025-003", project_id: "proj-001", site_id: "site-001", purchase_order_id: "po-004", po_number: "PO-2025-004", supplier_name: "PlumbPro Supplies",            delivery_date: "2025-02-22T11:00:00Z", delivery_status: "MATCHED",   items_count: 2, comments: null },
  { id: "del-004", delivery_number: "DEL-2025-004", project_id: "proj-001", site_id: "site-002", purchase_order_id: null,     po_number: null,           supplier_name: "AfriCon Materials (Pty) Ltd", delivery_date: "2025-03-10T08:00:00Z", delivery_status: "RECEIVED",  items_count: 1, comments: "Delivery without PO — site manager authorised" },
  { id: "del-005", delivery_number: "DEL-2025-005", project_id: "proj-002", site_id: "site-004", purchase_order_id: "po-005", po_number: "PO-2025-005", supplier_name: "AfriCon Materials (Pty) Ltd", delivery_date: "2025-03-20T09:00:00Z", delivery_status: "RECEIVED",  items_count: 2, comments: null },
];

export const MOCK_STOCK_BALANCES = [
  { id: "sb-001", project_id: "proj-001", site_id: "site-001", item_name: "Concrete M20",           unit: "m³",    balance: 48.5,  last_movement_date: "2025-03-28T08:00:00Z" },
  { id: "sb-002", project_id: "proj-001", site_id: "site-001", item_name: "Steel Rebar Y16",        unit: "kg",    balance: 2400,  last_movement_date: "2025-03-25T08:00:00Z" },
  { id: "sb-003", project_id: "proj-001", site_id: "site-001", item_name: "Face Brick (Eng.)",      unit: "1000's",balance: 18.5,  last_movement_date: "2025-04-01T08:00:00Z" },
  { id: "sb-004", project_id: "proj-001", site_id: "site-001", item_name: "OPC Cement 42.5N",       unit: "bags",  balance: 320,   last_movement_date: "2025-04-02T08:00:00Z" },
  { id: "sb-005", project_id: "proj-001", site_id: "site-001", item_name: "Plaster Sand",           unit: "m³",    balance: 24,    last_movement_date: "2025-03-30T08:00:00Z" },
  { id: "sb-006", project_id: "proj-001", site_id: "site-001", item_name: "UPVC Pipe 110mm",        unit: "m",     balance: 185,   last_movement_date: "2025-02-22T08:00:00Z" },
  { id: "sb-007", project_id: "proj-001", site_id: "site-001", item_name: "PVC Ball Valve 25mm",    unit: "each",  balance: 38,    last_movement_date: "2025-02-22T08:00:00Z" },
  { id: "sb-008", project_id: "proj-001", site_id: "site-002", item_name: "Concrete M20",           unit: "m³",    balance: 12,    last_movement_date: "2025-03-10T08:00:00Z" },
  { id: "sb-009", project_id: "proj-001", site_id: "site-002", item_name: "OPC Cement 42.5N",       unit: "bags",  balance: 85,    last_movement_date: "2025-03-10T08:00:00Z" },
  { id: "sb-010", project_id: "proj-002", site_id: "site-004", item_name: "Concrete M20",           unit: "m³",    balance: 32,    last_movement_date: "2025-03-20T08:00:00Z" },
  { id: "sb-011", project_id: "proj-002", site_id: "site-004", item_name: "Steel Rebar Y16",        unit: "kg",    balance: 5200,  last_movement_date: "2025-03-20T08:00:00Z" },
];

export const MOCK_INVOICES = [
  { id: "inv-001", invoice_number: "AFR-INV-2025-0123", supplier_id: "sup-001", supplier_name: "AfriCon Materials (Pty) Ltd", project_id: "proj-001", purchase_order_id: "po-001", invoice_date: "2025-01-20", due_date: "2025-02-19", total_amount: 592000, status: "PAID",     captured_at: "2025-01-22T08:00:00Z" },
  { id: "inv-002", invoice_number: "NBS-INV-2025-0056", supplier_id: "sup-004", supplier_name: "National Brick (SA)",          project_id: "proj-001", purchase_order_id: "po-002", invoice_date: "2025-02-08", due_date: "2025-03-10", total_amount: 921600, status: "MATCHED",  captured_at: "2025-02-10T08:00:00Z" },
  { id: "inv-003", invoice_number: "PPR-INV-2025-0012", supplier_id: "sup-005", supplier_name: "PlumbPro Supplies",            project_id: "proj-001", purchase_order_id: "po-004", invoice_date: "2025-02-25", due_date: "2025-03-04", total_amount: 132000, status: "PAID",     captured_at: "2025-02-26T08:00:00Z" },
  { id: "inv-004", invoice_number: "AFR-INV-2025-0189", supplier_id: "sup-001", supplier_name: "AfriCon Materials (Pty) Ltd", project_id: "proj-002", purchase_order_id: "po-005", invoice_date: "2025-03-22", due_date: "2025-04-21", total_amount: 325000, status: "SUBMITTED", captured_at: "2025-03-24T08:00:00Z" },
];

export const MOCK_PAYMENTS = [
  { id: "pay-001", invoice_id: "inv-001", supplier_name: "AfriCon Materials (Pty) Ltd", project_id: "proj-001", payment_type: "SUPPLIER", payment_reference: "EFT-2025-0012", payment_date: "2025-02-15", amount_paid: 592000, status: "PAID",     notes: "EFT payment" },
  { id: "pay-002", invoice_id: "inv-003", supplier_name: "PlumbPro Supplies",            project_id: "proj-001", payment_type: "SUPPLIER", payment_reference: "EFT-2025-0018", payment_date: "2025-03-03", amount_paid: 132000, status: "PAID",     notes: null },
  { id: "pay-003", invoice_id: null,      supplier_name: null,                           project_id: "proj-001", payment_type: "LABOUR",   payment_reference: "PAYROLL-MAR-A", payment_date: "2025-03-31", amount_paid: 185000, status: "APPROVED", notes: "March labour — Site A" },
  { id: "pay-004", invoice_id: null,      supplier_name: null,                           project_id: "proj-001", payment_type: "LABOUR",   payment_reference: "PAYROLL-MAR-B", payment_date: "2025-03-31", amount_paid: 95000,  status: "PENDING",  notes: "March labour — Site B" },
  { id: "pay-005", invoice_id: "inv-002", supplier_name: "National Brick (SA)",          project_id: "proj-001", payment_type: "SUPPLIER", payment_reference: null,             payment_date: null,          amount_paid: 921600, status: "PENDING",  notes: "Awaiting approval" },
];

export const MOCK_ALERTS = [
  { id: "al-001", project_id: "proj-001", site_id: "site-002", lot_id: null, alert_type: "DELIVERY_WITHOUT_PO",        severity: "HIGH",     title: "Delivery without purchase order",        message: "Delivery DEL-2025-004 was received at Site B without a linked PO. Authorised by site manager.", status: "OPEN",         created_at: "2025-03-10T08:00:00Z" },
  { id: "al-002", project_id: "proj-001", site_id: "site-001", lot_id: null, alert_type: "BOQ_VARIANCE_OVERUSE",       severity: "MEDIUM",   title: "BOQ variance — Face Brick",               message: "Face brick usage at Site A has exceeded planned quantity by 12%. Current: 268 000 units, Planned: 240 000.", status: "ACKNOWLEDGED", created_at: "2025-04-01T08:00:00Z" },
  { id: "al-003", project_id: "proj-001", site_id: null,       lot_id: null, alert_type: "OVERDUE_PAYMENT",            severity: "HIGH",     title: "Overdue payment — National Brick (SA)",  message: "Invoice NBS-INV-2025-0056 (R921 600) was due 2025-03-10. Now 33 days overdue.", status: "OPEN",         created_at: "2025-04-12T06:00:00Z" },
  { id: "al-004", project_id: "proj-001", site_id: "site-001", lot_id: null, alert_type: "LOW_STOCK",                  severity: "MEDIUM",   title: "Low stock — Concrete M20 (Site A)",      message: "Concrete M20 balance is 48.5m³ — below the 20% threshold of 64m³ (original planned 320m³).", status: "OPEN",         created_at: "2025-03-28T09:00:00Z" },
  { id: "al-005", project_id: "proj-001", site_id: "site-001", lot_id: "lot-002", alert_type: "MISSING_REMAINING_STOCK_PHOTO", severity: "LOW", title: "Missing stock photo — LOT-002 Roof",  message: "Stage 'Roof' for LOT-002 marked IN_PROGRESS but no remaining stock photo has been uploaded.", status: "OPEN",         created_at: "2025-04-05T08:00:00Z" },
  { id: "al-006", project_id: "proj-002", site_id: "site-004", lot_id: null, alert_type: "REQUEST_PENDING_TOO_LONG",   severity: "LOW",      title: "Material request pending — MBP Warehouse", message: "MR-2025-001 has been in SUBMITTED status for 6 days without review.", status: "RESOLVED",     created_at: "2025-03-10T08:00:00Z" },
  { id: "al-007", project_id: "proj-001", site_id: "site-001", lot_id: null, alert_type: "INVOICE_MISMATCH",           severity: "CRITICAL", title: "Invoice mismatch — AfriCon partial delivery", message: "Invoice AFR-INV-2025-0123 amount R592 000 does not match delivered quantity. 15% under-delivery detected.", status: "OPEN",         created_at: "2025-04-10T07:00:00Z" },
];
