import { query, queryOne } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { Supplier, PaginatedResult } from '../../types';

export async function listSuppliers(
  page = 1,
  limit = 20,
  filters: { search?: string; is_active?: boolean } = {}
): Promise<PaginatedResult<Supplier>> {
  const conditions: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  if (filters.is_active !== undefined) { conditions.push(`is_active = $${i++}`); params.push(filters.is_active); }
  if (filters.search) {
    conditions.push(`(name ILIKE $${i} OR email ILIKE $${i} OR contact_person ILIKE $${i})`);
    params.push(`%${filters.search}%`);
    i++;
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM suppliers ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<Supplier>(
    `SELECT * FROM suppliers ${where} ORDER BY name LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getSupplierById(id: string): Promise<Supplier> {
  const s = await queryOne<Supplier>(`SELECT * FROM suppliers WHERE id = $1`, [id]);
  if (!s) throw new AppError(404, 'Supplier not found.', 'NOT_FOUND');
  return s;
}

export async function createSupplier(
  input: Omit<Supplier, 'id' | 'is_active' | 'created_at' | 'updated_at'>,
  createdBy: string
): Promise<Supplier> {
  const [s] = await query<Supplier>(
    `INSERT INTO suppliers (name, code, email, phone, address, contact_person, payment_terms, notes)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *`,
    [input.name, input.code ?? null, input.email ?? null, input.phone ?? null,
     input.address ?? null, input.contact_person ?? null, input.payment_terms ?? null, input.notes ?? null]
  );
  await logAudit(createdBy, 'suppliers', s.id, 'CREATE', null, { name: s.name });
  return s;
}

export async function updateSupplier(
  id: string,
  input: Partial<Omit<Supplier, 'id' | 'created_at' | 'updated_at'>>,
  updatedBy: string
): Promise<Supplier> {
  const existing = await getSupplierById(id);
  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  const fields = ['name', 'code', 'email', 'phone', 'address', 'contact_person', 'payment_terms', 'notes', 'is_active'] as const;
  for (const f of fields) {
    if (input[f] !== undefined) { sets.push(`${f} = $${i++}`); params.push(input[f]); }
  }

  if (sets.length === 0) return existing;
  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<Supplier>(
    `UPDATE suppliers SET ${sets.join(', ')} WHERE id = $${i} RETURNING *`, params
  );
  await logAudit(updatedBy, 'suppliers', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}
