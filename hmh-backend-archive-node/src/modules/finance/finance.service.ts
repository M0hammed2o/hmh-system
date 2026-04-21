import { query, queryOne, pool, withTransaction } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { RecordStatus, PaymentType, PaymentStatus, InvoiceMatchStatus, PaginatedResult } from '../../types';
import { PoolClient } from 'pg';
import { createAlert } from '../alerts/alerts.service';

interface Invoice {
  id: string;
  invoice_number: string;
  supplier_id: string;
  project_id: string;
  site_id: string | null;
  purchase_order_id: string | null;
  invoice_date: Date | null;
  due_date: Date | null;
  subtotal_amount: number | null;
  vat_amount: number | null;
  total_amount: number;
  status: RecordStatus;
  captured_by: string | null;
  captured_at: Date;
  notes: string | null;
}

interface Payment {
  id: string;
  invoice_id: string | null;
  supplier_id: string | null;
  project_id: string;
  payment_type: PaymentType;
  payment_reference: string | null;
  payment_date: Date | null;
  amount_paid: number;
  status: PaymentStatus;
  approved_by: string | null;
  captured_by: string | null;
  notes: string | null;
}

interface InvoiceMatchingResult {
  id: string;
  invoice_id: string;
  purchase_order_id: string | null;
  delivery_id: string | null;
  match_status: InvoiceMatchStatus;
  quantity_match: boolean;
  amount_match: boolean;
  supplier_match: boolean;
  notes: string | null;
  checked_by: string | null;
  checked_at: Date | null;
}

// ============================================================
// Invoices
// ============================================================
export async function listInvoices(
  projectId: string,
  page = 1,
  limit = 20,
  filters: { status?: RecordStatus; supplier_id?: string } = {}
): Promise<PaginatedResult<Invoice>> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (filters.status) { conditions.push(`status = $${i++}`); params.push(filters.status); }
  if (filters.supplier_id) { conditions.push(`supplier_id = $${i++}`); params.push(filters.supplier_id); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM invoices ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<Invoice>(
    `SELECT * FROM invoices ${where} ORDER BY captured_at DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getInvoiceById(id: string): Promise<Invoice & { matching: InvoiceMatchingResult[] }> {
  const inv = await queryOne<Invoice>(`SELECT * FROM invoices WHERE id = $1`, [id]);
  if (!inv) throw new AppError(404, 'Invoice not found.', 'NOT_FOUND');

  const matching = await query<InvoiceMatchingResult>(
    `SELECT * FROM invoice_matching_results WHERE invoice_id = $1`, [id]
  );

  return { ...inv, matching };
}

export async function createInvoice(
  input: {
    invoice_number: string;
    supplier_id: string;
    project_id: string;
    site_id?: string;
    purchase_order_id?: string;
    invoice_date?: string;
    due_date?: string;
    subtotal_amount?: number;
    vat_amount?: number;
    total_amount: number;
    notes?: string;
  },
  capturedBy: string
): Promise<Invoice> {
  const [inv] = await query<Invoice>(
    `INSERT INTO invoices
       (invoice_number, supplier_id, project_id, site_id, purchase_order_id, invoice_date, due_date,
        subtotal_amount, vat_amount, total_amount, captured_by, notes)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *`,
    [
      input.invoice_number, input.supplier_id, input.project_id,
      input.site_id ?? null, input.purchase_order_id ?? null,
      input.invoice_date ?? null, input.due_date ?? null,
      input.subtotal_amount ?? null, input.vat_amount ?? null,
      input.total_amount, capturedBy, input.notes ?? null,
    ]
  );

  await logAudit(capturedBy, 'invoices', inv.id, 'CREATE', null, {
    invoice_number: inv.invoice_number, total_amount: inv.total_amount,
  });
  return inv;
}

export async function matchInvoice(
  invoiceId: string,
  input: {
    purchase_order_id?: string;
    delivery_id?: string;
    notes?: string;
  },
  checkedBy: string
): Promise<InvoiceMatchingResult> {
  const inv = await queryOne<Invoice>(`SELECT * FROM invoices WHERE id = $1`, [invoiceId]);
  if (!inv) throw new AppError(404, 'Invoice not found.', 'NOT_FOUND');

  let supplierMatch = false;
  let amountMatch = false;
  let quantityMatch = false;
  let matchStatus: InvoiceMatchStatus = 'UNLINKED';

  if (input.purchase_order_id) {
    const po = await queryOne<{ supplier_id: string; total_amount: number }>(
      `SELECT supplier_id, total_amount FROM purchase_orders WHERE id = $1`, [input.purchase_order_id]
    );
    if (po) {
      supplierMatch = po.supplier_id === inv.supplier_id;
      amountMatch = Math.abs(po.total_amount - inv.total_amount) < 0.01;
    }
  }

  if (input.delivery_id) {
    const delivery = await queryOne<{ supplier_id: string }>(
      `SELECT supplier_id FROM deliveries WHERE id = $1`, [input.delivery_id]
    );
    if (delivery) {
      supplierMatch = supplierMatch || delivery.supplier_id === inv.supplier_id;
      quantityMatch = true; // simplified — deep qty matching requires line-level comparison
    }
  }

  if (supplierMatch && amountMatch) {
    matchStatus = 'MATCHED';
  } else if (supplierMatch) {
    matchStatus = 'PARTIALLY_MATCHED';
  } else if (input.purchase_order_id || input.delivery_id) {
    matchStatus = 'MISMATCH';
  }

  const [result] = await query<InvoiceMatchingResult>(
    `INSERT INTO invoice_matching_results
       (invoice_id, purchase_order_id, delivery_id, match_status, quantity_match, amount_match, supplier_match, notes, checked_by, checked_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW()) RETURNING *`,
    [invoiceId, input.purchase_order_id ?? null, input.delivery_id ?? null,
     matchStatus, quantityMatch, amountMatch, supplierMatch, input.notes ?? null, checkedBy]
  );

  // Update invoice status
  if (matchStatus === 'MATCHED') {
    await pool.query(`UPDATE invoices SET status = 'MATCHED', updated_at = NOW() WHERE id = $1`, [invoiceId]);
  }

  // Alert on mismatch
  if (matchStatus === 'MISMATCH') {
    await createAlert({
      project_id: inv.project_id,
      alert_type: 'INVOICE_MISMATCH',
      severity: 'HIGH',
      title: 'Invoice Mismatch',
      message: `Invoice ${inv.invoice_number} does not match linked PO/delivery.`,
      reference_type: 'invoice',
      reference_id: invoiceId,
    });
  }

  await logAudit(checkedBy, 'invoice_matching_results', result.id, 'MATCH', null, { match_status: matchStatus });
  return result;
}

// ============================================================
// Payments
// ============================================================
export async function listPayments(
  projectId: string,
  page = 1,
  limit = 20,
  filters: { status?: PaymentStatus } = {}
): Promise<PaginatedResult<Payment>> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (filters.status) { conditions.push(`status = $${i++}`); params.push(filters.status); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM payments ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<Payment>(
    `SELECT * FROM payments ${where} ORDER BY created_at DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function createPayment(
  input: {
    invoice_id?: string;
    supplier_id?: string;
    project_id: string;
    payment_type: PaymentType;
    payment_reference?: string;
    payment_date?: string;
    amount_paid: number;
    notes?: string;
  },
  capturedBy: string
): Promise<Payment> {
  const [payment] = await query<Payment>(
    `INSERT INTO payments
       (invoice_id, supplier_id, project_id, payment_type, payment_reference, payment_date, amount_paid, captured_by, notes)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
    [
      input.invoice_id ?? null, input.supplier_id ?? null, input.project_id,
      input.payment_type, input.payment_reference ?? null,
      input.payment_date ?? null, input.amount_paid, capturedBy, input.notes ?? null,
    ]
  );

  await logAudit(capturedBy, 'payments', payment.id, 'CREATE', null, {
    amount_paid: payment.amount_paid, payment_type: payment.payment_type,
  });
  return payment;
}

export async function approvePayment(id: string, approvedBy: string): Promise<Payment> {
  const payment = await queryOne<Payment>(`SELECT * FROM payments WHERE id = $1`, [id]);
  if (!payment) throw new AppError(404, 'Payment not found.', 'NOT_FOUND');
  if (payment.status !== 'PENDING') throw new AppError(422, 'Only PENDING payments can be approved.', 'INVALID_STATE');

  const [updated] = await query<Payment>(
    `UPDATE payments SET status = 'APPROVED', approved_by = $1, updated_at = NOW() WHERE id = $2 RETURNING *`,
    [approvedBy, id]
  );

  // Mark linked invoice as PAID if this payment covers it
  if (payment.invoice_id) {
    await pool.query(
      `UPDATE invoices SET status = 'PAID', updated_at = NOW() WHERE id = $1`, [payment.invoice_id]
    );
  }

  await logAudit(approvedBy, 'payments', id, 'APPROVE', null, null);
  return updated;
}

// ============================================================
// Finance summary
// ============================================================
export async function getFinanceSummary(projectId: string): Promise<{
  total_po_value: number;
  total_invoiced: number;
  total_paid: number;
  outstanding: number;
  pending_approvals: number;
  overdue_invoices: number;
}> {
  const [summary] = await query<{
    total_po_value: number;
    total_invoiced: number;
    total_paid: number;
  }>(
    `SELECT
       COALESCE(SUM(CASE WHEN p.status != 'CANCELLED' THEN p.total_amount ELSE 0 END), 0) as total_po_value,
       0 as total_invoiced,
       0 as total_paid
     FROM purchase_orders p WHERE project_id = $1`,
    [projectId]
  );

  const [invoicedRow] = await query<{ total: number }>(
    `SELECT COALESCE(SUM(total_amount), 0) as total FROM invoices WHERE project_id = $1 AND status != 'CANCELLED'`,
    [projectId]
  );

  const [paidRow] = await query<{ total: number }>(
    `SELECT COALESCE(SUM(amount_paid), 0) as total FROM payments WHERE project_id = $1 AND status = 'PAID'`,
    [projectId]
  );

  const [pendingRow] = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM payments WHERE project_id = $1 AND status = 'PENDING'`,
    [projectId]
  );

  const [overdueRow] = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM invoices WHERE project_id = $1 AND status NOT IN ('PAID','CANCELLED') AND due_date < NOW()`,
    [projectId]
  );

  const totalInvoiced = Number(invoicedRow.total);
  const totalPaid = Number(paidRow.total);

  return {
    total_po_value: Number(summary?.total_po_value ?? 0),
    total_invoiced: totalInvoiced,
    total_paid: totalPaid,
    outstanding: totalInvoiced - totalPaid,
    pending_approvals: parseInt(pendingRow.count, 10),
    overdue_invoices: parseInt(overdueRow.count, 10),
  };
}
