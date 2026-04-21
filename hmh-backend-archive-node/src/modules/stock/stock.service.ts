import { query, queryOne, pool, withTransaction } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { MovementType } from '../../types';
import { PoolClient } from 'pg';
import { createAlert } from '../alerts/alerts.service';

interface StockLedgerEntry {
  id: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  item_id: string;
  boq_item_id: string | null;
  movement_type: MovementType;
  reference_type: string;
  reference_id: string | null;
  quantity_in: number;
  quantity_out: number;
  unit: string | null;
  unit_cost: number | null;
  movement_date: Date;
  entered_by: string | null;
  notes: string | null;
  created_at: Date;
}

interface StockBalance {
  project_id: string;
  site_id: string;
  lot_id: string | null;
  item_id: string;
  item_name?: string;
  balance: number;
  last_movement_date: Date | null;
}

interface UsageLog {
  id: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  stage_id: string | null;
  item_id: string;
  boq_item_id: string | null;
  quantity_used: number;
  used_by_person_name: string | null;
  used_by_team_name: string | null;
  recorded_by_user_id: string;
  remaining_quantity_after_use: number | null;
  usage_date: Date;
  comments: string | null;
}

// ============================================================
// Stock balance queries
// ============================================================
export async function getStockBalance(
  projectId: string,
  siteId: string,
  itemId?: string
): Promise<StockBalance[]> {
  if (itemId) {
    return query<StockBalance>(
      `SELECT vsb.*, i.name as item_name
       FROM v_stock_balance vsb
       JOIN items i ON i.id = vsb.item_id
       WHERE vsb.project_id = $1 AND vsb.site_id = $2 AND vsb.item_id = $3`,
      [projectId, siteId, itemId]
    );
  }
  return query<StockBalance>(
    `SELECT vsb.*, i.name as item_name
     FROM v_stock_balance vsb
     JOIN items i ON i.id = vsb.item_id
     WHERE vsb.project_id = $1 AND vsb.site_id = $2
     ORDER BY i.name`,
    [projectId, siteId]
  );
}

export async function getCurrentBalance(
  projectId: string,
  siteId: string,
  itemId: string
): Promise<number> {
  const result = await queryOne<{ balance: number }>(
    `SELECT COALESCE(SUM(quantity_in) - SUM(quantity_out), 0) as balance
     FROM stock_ledger
     WHERE project_id = $1 AND site_id = $2 AND item_id = $3`,
    [projectId, siteId, itemId]
  );
  return result?.balance ?? 0;
}

// ============================================================
// Record delivery receipt → posts to ledger
// ============================================================
export async function recordDelivery(
  input: {
    purchase_order_id?: string;
    supplier_id: string;
    project_id: string;
    site_id: string;
    delivery_number?: string;
    supplier_delivery_note_number?: string;
    comments?: string;
    items: {
      item_id: string;
      boq_item_id?: string;
      purchase_order_item_id?: string;
      description: string;
      quantity_expected?: number;
      quantity_received: number;
      unit?: string;
      unit_cost?: number;
      discrepancy_reason?: string;
    }[];
  },
  receivedBy: string
): Promise<{ delivery_id: string }> {
  return withTransaction(async (client: PoolClient) => {
    // Create delivery record
    const deliveryResult = await client.query(
      `INSERT INTO deliveries
         (delivery_number, purchase_order_id, supplier_id, project_id, site_id,
          received_by_user_id, supplier_delivery_note_number, comments)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id`,
      [
        input.delivery_number ?? null,
        input.purchase_order_id ?? null,
        input.supplier_id,
        input.project_id,
        input.site_id,
        receivedBy,
        input.supplier_delivery_note_number ?? null,
        input.comments ?? null,
      ]
    );
    const deliveryId = deliveryResult.rows[0].id as string;

    for (const item of input.items) {
      // Insert delivery item
      await client.query(
        `INSERT INTO delivery_items
           (delivery_id, purchase_order_item_id, item_id, boq_item_id, description,
            quantity_expected, quantity_received, unit, discrepancy_reason)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
        [
          deliveryId, item.purchase_order_item_id ?? null, item.item_id,
          item.boq_item_id ?? null, item.description, item.quantity_expected ?? null,
          item.quantity_received, item.unit ?? null, item.discrepancy_reason ?? null,
        ]
      );

      // Post to stock ledger
      await client.query(
        `INSERT INTO stock_ledger
           (project_id, site_id, item_id, boq_item_id, movement_type, reference_type, reference_id,
            quantity_in, quantity_out, unit, unit_cost, entered_by)
         VALUES ($1,$2,$3,$4,'DELIVERY_RECEIVED','delivery',$5,$6,0,$7,$8,$9)`,
        [
          input.project_id, input.site_id, item.item_id, item.boq_item_id ?? null,
          deliveryId, item.quantity_received, item.unit ?? null,
          item.unit_cost ?? null, receivedBy,
        ]
      );

      // Check for discrepancy
      if (item.quantity_expected && item.quantity_received !== item.quantity_expected) {
        await createAlert({
          project_id: input.project_id,
          site_id: input.site_id,
          alert_type: 'DELIVERY_DISCREPANCY',
          severity: 'MEDIUM',
          title: 'Delivery Discrepancy',
          message: `Item "${item.description}": expected ${item.quantity_expected}, received ${item.quantity_received}.`,
          reference_type: 'delivery',
          reference_id: deliveryId,
        });
      }
    }

    // Alert if no linked PO
    if (!input.purchase_order_id) {
      await createAlert({
        project_id: input.project_id,
        site_id: input.site_id,
        alert_type: 'DELIVERY_WITHOUT_PO',
        severity: 'MEDIUM',
        title: 'Delivery without Purchase Order',
        message: `Delivery received without a linked PO. Delivery ID: ${deliveryId}`,
        reference_type: 'delivery',
        reference_id: deliveryId,
      });
    }

    await logAudit(receivedBy, 'deliveries', deliveryId, 'CREATE', null, { delivery_id: deliveryId });
    return { delivery_id: deliveryId };
  });
}

// ============================================================
// Record usage → posts OUT to ledger, checks for negative stock
// ============================================================
export async function recordUsage(
  input: {
    project_id: string;
    site_id: string;
    lot_id?: string;
    stage_id?: string;
    item_id: string;
    boq_item_id?: string;
    quantity_used: number;
    used_by_person_name?: string;
    used_by_team_name?: string;
    usage_date?: string;
    comments?: string;
  },
  recordedBy: string
): Promise<UsageLog> {
  return withTransaction(async (client: PoolClient) => {
    // Get current balance
    const balanceResult = await client.query<{ balance: number }>(
      `SELECT COALESCE(SUM(quantity_in) - SUM(quantity_out), 0) as balance
       FROM stock_ledger WHERE project_id = $1 AND site_id = $2 AND item_id = $3`,
      [input.project_id, input.site_id, input.item_id]
    );
    const currentBalance = Number(balanceResult.rows[0]?.balance ?? 0);
    const remainingAfter = currentBalance - input.quantity_used;

    // Insert usage log
    const usageResult = await client.query<UsageLog>(
      `INSERT INTO usage_logs
         (project_id, site_id, lot_id, stage_id, item_id, boq_item_id, quantity_used,
          used_by_person_name, used_by_team_name, recorded_by_user_id, remaining_quantity_after_use,
          usage_date, comments)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *`,
      [
        input.project_id, input.site_id, input.lot_id ?? null, input.stage_id ?? null,
        input.item_id, input.boq_item_id ?? null, input.quantity_used,
        input.used_by_person_name ?? null, input.used_by_team_name ?? null,
        recordedBy, remainingAfter,
        input.usage_date ? new Date(input.usage_date) : new Date(),
        input.comments ?? null,
      ]
    );
    const usageLog = usageResult.rows[0];

    // Post to stock ledger
    await client.query(
      `INSERT INTO stock_ledger
         (project_id, site_id, lot_id, item_id, boq_item_id, movement_type, reference_type, reference_id,
          quantity_in, quantity_out, entered_by)
       VALUES ($1,$2,$3,$4,$5,'USAGE','usage_log',$6,0,$7,$8)`,
      [
        input.project_id, input.site_id, input.lot_id ?? null,
        input.item_id, input.boq_item_id ?? null,
        usageLog.id, input.quantity_used, recordedBy,
      ]
    );

    // Alert for negative stock
    if (remainingAfter < 0) {
      await createAlert({
        project_id: input.project_id,
        site_id: input.site_id,
        alert_type: 'NEGATIVE_STOCK',
        severity: 'HIGH',
        title: 'Negative Stock',
        message: `Stock for item went negative. Balance after usage: ${remainingAfter}`,
        reference_type: 'usage_log',
        reference_id: usageLog.id,
      });
    }

    await logAudit(recordedBy, 'usage_logs', usageLog.id, 'CREATE', null, { item_id: input.item_id, quantity_used: input.quantity_used });
    return usageLog;
  });
}

// ============================================================
// Adjust stock (admin)
// ============================================================
export async function adjustStock(
  input: {
    project_id: string;
    site_id: string;
    lot_id?: string;
    item_id: string;
    adjustment_type: 'ADD' | 'SUBTRACT';
    quantity: number;
    unit?: string;
    notes: string;
  },
  enteredBy: string
): Promise<void> {
  const movementType: MovementType = input.adjustment_type === 'ADD' ? 'ADJUSTMENT_ADD' : 'ADJUSTMENT_SUBTRACT';
  const quantityIn = input.adjustment_type === 'ADD' ? input.quantity : 0;
  const quantityOut = input.adjustment_type === 'SUBTRACT' ? input.quantity : 0;

  await pool.query(
    `INSERT INTO stock_ledger
       (project_id, site_id, lot_id, item_id, movement_type, reference_type,
        quantity_in, quantity_out, unit, entered_by, notes)
     VALUES ($1,$2,$3,$4,$5,'adjustment',$6,$7,$8,$9,$10)`,
    [input.project_id, input.site_id, input.lot_id ?? null, input.item_id,
     movementType, quantityIn, quantityOut, input.unit ?? null, enteredBy, input.notes]
  );

  await logAudit(enteredBy, 'stock_ledger', null, 'ADJUSTMENT', null, {
    item_id: input.item_id, adjustment_type: input.adjustment_type, quantity: input.quantity,
  });
}

// ============================================================
// Post opening balances
// ============================================================
export async function postOpeningBalance(
  balanceId: string,
  postedBy: string
): Promise<void> {
  const balance = await queryOne<{
    id: string; project_id: string; site_id: string | null; lot_id: string | null;
    item_id: string; quantity_on_hand: number; unit_cost?: number; is_posted: boolean;
  }>(`SELECT * FROM project_opening_balances WHERE id = $1`, [balanceId]);

  if (!balance) throw new AppError(404, 'Opening balance not found.', 'NOT_FOUND');
  if (balance.is_posted) throw new AppError(422, 'Opening balance has already been posted.', 'ALREADY_POSTED');
  if (!balance.site_id) throw new AppError(422, 'Opening balance must have a site_id to post.', 'MISSING_SITE');

  await withTransaction(async (client: PoolClient) => {
    await client.query(
      `INSERT INTO stock_ledger
         (project_id, site_id, lot_id, item_id, movement_type, reference_type, reference_id,
          quantity_in, quantity_out, entered_by, notes)
       VALUES ($1,$2,$3,$4,'OPENING_BALANCE','opening_balance',$5,$6,0,$7,'Opening balance posted')`,
      [balance.project_id, balance.site_id, balance.lot_id, balance.item_id,
       balance.id, balance.quantity_on_hand, postedBy]
    );

    await client.query(
      `UPDATE project_opening_balances SET is_posted = TRUE, posted_at = NOW() WHERE id = $1`,
      [balanceId]
    );
  });

  await logAudit(postedBy, 'project_opening_balances', balanceId, 'POST', null, null);
}

export async function getStockLedger(
  projectId: string,
  siteId: string,
  itemId?: string,
  page = 1,
  limit = 50
): Promise<{ items: StockLedgerEntry[]; total: number }> {
  const conditions = ['sl.project_id = $1', 'sl.site_id = $2'];
  const params: unknown[] = [projectId, siteId];
  let i = 3;

  if (itemId) { conditions.push(`sl.item_id = $${i++}`); params.push(itemId); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM stock_ledger sl ${where}`, params
  );
  const total = parseInt(countRow.count, 10);

  const items = await query<StockLedgerEntry>(
    `SELECT sl.*, i.name as item_name FROM stock_ledger sl
     JOIN items i ON i.id = sl.item_id
     ${where} ORDER BY sl.movement_date DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total };
}

export async function listUsageLogs(
  projectId: string,
  siteId?: string,
  page = 1,
  limit = 20
): Promise<{ items: UsageLog[]; total: number }> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (siteId) { conditions.push(`site_id = $${i++}`); params.push(siteId); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM usage_logs ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<UsageLog>(
    `SELECT * FROM usage_logs ${where} ORDER BY usage_date DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total };
}
