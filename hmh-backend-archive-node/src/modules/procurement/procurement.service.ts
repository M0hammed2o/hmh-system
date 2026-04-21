import { query, queryOne, pool, withTransaction } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { RecordStatus, PaginatedResult } from '../../types';
import { PoolClient } from 'pg';

interface MaterialRequest {
  id: string;
  request_number: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  stage_id: string | null;
  requested_by: string;
  preferred_supplier_id: string | null;
  status: RecordStatus;
  requested_date: Date;
  needed_by_date: Date | null;
  reviewed_by: string | null;
  reviewed_at: Date | null;
  rejection_reason: string | null;
  notes: string | null;
}

interface MaterialRequestItem {
  id: string;
  material_request_id: string;
  item_id: string;
  boq_item_id: string | null;
  requested_quantity: number;
  unit: string | null;
  remarks: string | null;
}

interface PurchaseOrder {
  id: string;
  po_number: string;
  project_id: string;
  site_id: string | null;
  supplier_id: string;
  material_request_id: string | null;
  status: RecordStatus;
  po_date: Date;
  expected_delivery_date: Date | null;
  subtotal_amount: number;
  vat_amount: number;
  total_amount: number;
  created_by: string;
  approved_by: string | null;
  sent_at: Date | null;
  notes: string | null;
}

interface PurchaseOrderItem {
  id: string;
  purchase_order_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  lot_id: string | null;
  stage_id: string | null;
  description: string;
  quantity_ordered: number;
  unit: string | null;
  rate: number | null;
  line_total: number | null;
}

// ============================================================
// Material Requests
// ============================================================
export async function listMaterialRequests(
  projectId: string,
  page = 1,
  limit = 20,
  filters: { status?: RecordStatus; site_id?: string } = {}
): Promise<PaginatedResult<MaterialRequest>> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (filters.status) { conditions.push(`status = $${i++}`); params.push(filters.status); }
  if (filters.site_id) { conditions.push(`site_id = $${i++}`); params.push(filters.site_id); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM material_requests ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<MaterialRequest>(
    `SELECT * FROM material_requests ${where} ORDER BY requested_date DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getMaterialRequestById(id: string): Promise<MaterialRequest & { items: MaterialRequestItem[] }> {
  const mr = await queryOne<MaterialRequest>(`SELECT * FROM material_requests WHERE id = $1`, [id]);
  if (!mr) throw new AppError(404, 'Material request not found.', 'NOT_FOUND');

  const items = await query<MaterialRequestItem>(
    `SELECT * FROM material_request_items WHERE material_request_id = $1`, [id]
  );

  return { ...mr, items };
}

export async function createMaterialRequest(
  input: {
    project_id: string;
    site_id: string;
    lot_id?: string;
    stage_id?: string;
    preferred_supplier_id?: string;
    needed_by_date?: string;
    notes?: string;
    items: { item_id: string; boq_item_id?: string; requested_quantity: number; unit?: string; remarks?: string }[];
  },
  requestedBy: string
): Promise<MaterialRequest & { items: MaterialRequestItem[] }> {
  return withTransaction(async (client: PoolClient) => {
    const requestNumber = await generateRequestNumber(client, 'MR');

    const mrResult = await client.query<MaterialRequest>(
      `INSERT INTO material_requests
         (request_number, project_id, site_id, lot_id, stage_id, requested_by, preferred_supplier_id, needed_by_date, notes)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
      [requestNumber, input.project_id, input.site_id, input.lot_id ?? null,
       input.stage_id ?? null, requestedBy, input.preferred_supplier_id ?? null,
       input.needed_by_date ?? null, input.notes ?? null]
    );
    const mr = mrResult.rows[0];

    const mrItems: MaterialRequestItem[] = [];
    for (const item of input.items) {
      const itemResult = await client.query<MaterialRequestItem>(
        `INSERT INTO material_request_items (material_request_id, item_id, boq_item_id, requested_quantity, unit, remarks)
         VALUES ($1,$2,$3,$4,$5,$6) RETURNING *`,
        [mr.id, item.item_id, item.boq_item_id ?? null, item.requested_quantity, item.unit ?? null, item.remarks ?? null]
      );
      mrItems.push(itemResult.rows[0]);
    }

    await logAudit(requestedBy, 'material_requests', mr.id, 'CREATE', null, { request_number: mr.request_number });
    return { ...mr, items: mrItems };
  });
}

export async function reviewMaterialRequest(
  id: string,
  action: 'APPROVE' | 'REJECT',
  rejectionReason: string | null,
  reviewedBy: string
): Promise<MaterialRequest> {
  const mr = await queryOne<MaterialRequest>(`SELECT * FROM material_requests WHERE id = $1`, [id]);
  if (!mr) throw new AppError(404, 'Material request not found.', 'NOT_FOUND');
  if (mr.status !== 'SUBMITTED') {
    throw new AppError(422, 'Only SUBMITTED requests can be reviewed.', 'INVALID_STATE');
  }

  const newStatus: RecordStatus = action === 'APPROVE' ? 'APPROVED' : 'REJECTED';
  const [updated] = await query<MaterialRequest>(
    `UPDATE material_requests SET status = $1, reviewed_by = $2, reviewed_at = NOW(),
     rejection_reason = $3, updated_at = NOW() WHERE id = $4 RETURNING *`,
    [newStatus, reviewedBy, rejectionReason ?? null, id]
  );

  await logAudit(reviewedBy, 'material_requests', id, action, null, { status: newStatus });
  return updated;
}

export async function submitMaterialRequest(id: string, submittedBy: string): Promise<MaterialRequest> {
  const mr = await queryOne<MaterialRequest>(`SELECT * FROM material_requests WHERE id = $1`, [id]);
  if (!mr) throw new AppError(404, 'Material request not found.', 'NOT_FOUND');
  if (mr.status !== 'DRAFT') throw new AppError(422, 'Only DRAFT requests can be submitted.', 'INVALID_STATE');

  const [updated] = await query<MaterialRequest>(
    `UPDATE material_requests SET status = 'SUBMITTED', updated_at = NOW() WHERE id = $1 RETURNING *`, [id]
  );
  await logAudit(submittedBy, 'material_requests', id, 'SUBMIT', null, null);
  return updated;
}

// ============================================================
// Purchase Orders
// ============================================================
export async function listPurchaseOrders(
  projectId: string,
  page = 1,
  limit = 20,
  filters: { status?: RecordStatus; supplier_id?: string } = {}
): Promise<PaginatedResult<PurchaseOrder>> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (filters.status) { conditions.push(`status = $${i++}`); params.push(filters.status); }
  if (filters.supplier_id) { conditions.push(`supplier_id = $${i++}`); params.push(filters.supplier_id); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM purchase_orders ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<PurchaseOrder>(
    `SELECT * FROM purchase_orders ${where} ORDER BY po_date DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getPurchaseOrderById(id: string): Promise<PurchaseOrder & { items: PurchaseOrderItem[] }> {
  const po = await queryOne<PurchaseOrder>(`SELECT * FROM purchase_orders WHERE id = $1`, [id]);
  if (!po) throw new AppError(404, 'Purchase order not found.', 'NOT_FOUND');

  const items = await query<PurchaseOrderItem>(
    `SELECT * FROM purchase_order_items WHERE purchase_order_id = $1`, [id]
  );

  return { ...po, items };
}

export async function createPurchaseOrder(
  input: {
    project_id: string;
    site_id?: string;
    supplier_id: string;
    material_request_id?: string;
    expected_delivery_date?: string;
    notes?: string;
    items: {
      item_id?: string;
      boq_item_id?: string;
      lot_id?: string;
      stage_id?: string;
      description: string;
      quantity_ordered: number;
      unit?: string;
      rate?: number;
    }[];
  },
  createdBy: string
): Promise<PurchaseOrder & { items: PurchaseOrderItem[] }> {
  return withTransaction(async (client: PoolClient) => {
    const poNumber = await generateRequestNumber(client, 'PO');

    // Calculate totals
    let subtotal = 0;
    for (const item of input.items) {
      subtotal += (item.quantity_ordered ?? 0) * (item.rate ?? 0);
    }
    const vatAmount = Math.round(subtotal * 0.15 * 100) / 100;
    const totalAmount = Math.round((subtotal + vatAmount) * 100) / 100;

    const poResult = await client.query<PurchaseOrder>(
      `INSERT INTO purchase_orders
         (po_number, project_id, site_id, supplier_id, material_request_id,
          expected_delivery_date, subtotal_amount, vat_amount, total_amount, created_by, notes)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *`,
      [poNumber, input.project_id, input.site_id ?? null, input.supplier_id,
       input.material_request_id ?? null, input.expected_delivery_date ?? null,
       subtotal, vatAmount, totalAmount, createdBy, input.notes ?? null]
    );
    const po = poResult.rows[0];

    const poItems: PurchaseOrderItem[] = [];
    for (const item of input.items) {
      const lineTotal = item.rate ? Math.round(item.quantity_ordered * item.rate * 100) / 100 : null;
      const itemResult = await client.query<PurchaseOrderItem>(
        `INSERT INTO purchase_order_items
           (purchase_order_id, item_id, boq_item_id, lot_id, stage_id,
            description, quantity_ordered, unit, rate, line_total)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *`,
        [po.id, item.item_id ?? null, item.boq_item_id ?? null,
         item.lot_id ?? null, item.stage_id ?? null, item.description,
         item.quantity_ordered, item.unit ?? null, item.rate ?? null, lineTotal]
      );
      poItems.push(itemResult.rows[0]);
    }

    await logAudit(createdBy, 'purchase_orders', po.id, 'CREATE', null, { po_number: po.po_number });
    return { ...po, items: poItems };
  });
}

export async function approvePurchaseOrder(id: string, approvedBy: string): Promise<PurchaseOrder> {
  const po = await queryOne<PurchaseOrder>(`SELECT * FROM purchase_orders WHERE id = $1`, [id]);
  if (!po) throw new AppError(404, 'Purchase order not found.', 'NOT_FOUND');
  if (po.status !== 'SUBMITTED') throw new AppError(422, 'Only SUBMITTED POs can be approved.', 'INVALID_STATE');

  const [updated] = await query<PurchaseOrder>(
    `UPDATE purchase_orders SET status = 'APPROVED', approved_by = $1, updated_at = NOW() WHERE id = $2 RETURNING *`,
    [approvedBy, id]
  );
  await logAudit(approvedBy, 'purchase_orders', id, 'APPROVE', null, null);
  return updated;
}

export async function markPoSent(id: string, sentBy: string): Promise<PurchaseOrder> {
  const po = await queryOne<PurchaseOrder>(`SELECT * FROM purchase_orders WHERE id = $1`, [id]);
  if (!po) throw new AppError(404, 'Purchase order not found.', 'NOT_FOUND');
  if (po.status !== 'APPROVED') throw new AppError(422, 'Only APPROVED POs can be sent.', 'INVALID_STATE');

  const [updated] = await query<PurchaseOrder>(
    `UPDATE purchase_orders SET status = 'SENT', sent_at = NOW(), updated_at = NOW() WHERE id = $1 RETURNING *`,
    [id]
  );
  await logAudit(sentBy, 'purchase_orders', id, 'SENT', null, null);
  return updated;
}

async function generateRequestNumber(client: PoolClient, prefix: string): Promise<string> {
  const year = new Date().getFullYear();
  const tableName = prefix === 'MR' ? 'material_requests' : 'purchase_orders';
  const colName = prefix === 'MR' ? 'request_number' : 'po_number';

  const result = await client.query<{ count: string }>(
    `SELECT COUNT(*) as count FROM ${tableName} WHERE ${colName} LIKE $1`,
    [`${prefix}-${year}-%`]
  );
  const seq = parseInt(result.rows[0].count, 10) + 1;
  return `${prefix}-${year}-${String(seq).padStart(4, '0')}`;
}
