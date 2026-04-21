import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { Item, ItemType, PaginatedResult } from '../../types';

interface ItemCategory {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

export async function listCategories(): Promise<ItemCategory[]> {
  return query<ItemCategory>(`SELECT * FROM item_categories WHERE is_active = TRUE ORDER BY name`);
}

export async function listItems(
  page = 1,
  limit = 20,
  filters: { search?: string; category_id?: string; item_type?: ItemType; is_active?: boolean } = {}
): Promise<PaginatedResult<Item>> {
  const conditions: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  if (filters.category_id) { conditions.push(`category_id = $${i++}`); params.push(filters.category_id); }
  if (filters.item_type) { conditions.push(`item_type = $${i++}`); params.push(filters.item_type); }
  if (filters.is_active !== undefined) { conditions.push(`is_active = $${i++}`); params.push(filters.is_active); }
  if (filters.search) {
    conditions.push(`(name ILIKE $${i} OR normalized_name ILIKE $${i})`);
    params.push(`%${filters.search}%`);
    i++;
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM items ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<Item>(
    `SELECT * FROM items ${where} ORDER BY normalized_name LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getItemById(id: string): Promise<Item> {
  const item = await queryOne<Item>(`SELECT * FROM items WHERE id = $1`, [id]);
  if (!item) throw new AppError(404, 'Item not found.', 'NOT_FOUND');
  return item;
}

export async function createItem(
  input: {
    name: string;
    normalized_name?: string;
    category_id?: string;
    default_unit?: string;
    item_type?: ItemType;
    requires_remaining_photo?: boolean;
    is_high_risk?: boolean;
    notes?: string;
  },
  createdBy: string
): Promise<Item> {
  const normalizedName = input.normalized_name ?? input.name.toLowerCase().trim().replace(/\s+/g, ' ');

  const [item] = await query<Item>(
    `INSERT INTO items (name, normalized_name, category_id, default_unit, item_type, requires_remaining_photo, is_high_risk, notes)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *`,
    [
      input.name, normalizedName, input.category_id ?? null,
      input.default_unit ?? null, input.item_type ?? 'MATERIAL',
      input.requires_remaining_photo ?? false, input.is_high_risk ?? false,
      input.notes ?? null,
    ]
  );
  await logAudit(createdBy, 'items', item.id, 'CREATE', null, { name: item.name });
  return item;
}

export async function updateItem(
  id: string,
  input: Partial<{
    name: string;
    normalized_name: string;
    category_id: string;
    default_unit: string;
    item_type: ItemType;
    requires_remaining_photo: boolean;
    is_high_risk: boolean;
    is_active: boolean;
    notes: string;
  }>,
  updatedBy: string
): Promise<Item> {
  const existing = await getItemById(id);
  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  const fields = ['name', 'normalized_name', 'category_id', 'default_unit', 'item_type',
    'requires_remaining_photo', 'is_high_risk', 'is_active', 'notes'] as const;
  for (const f of fields) {
    if (input[f] !== undefined) { sets.push(`${f} = $${i++}`); params.push(input[f]); }
  }

  if (sets.length === 0) return existing;
  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<Item>(
    `UPDATE items SET ${sets.join(', ')} WHERE id = $${i} RETURNING *`, params
  );
  await logAudit(updatedBy, 'items', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}

export async function addAlias(itemId: string, aliasName: string, createdBy: string): Promise<void> {
  await pool.query(
    `INSERT INTO item_aliases (item_id, alias_name) VALUES ($1, $2) ON CONFLICT (alias_name) DO NOTHING`,
    [itemId, aliasName.toLowerCase().trim()]
  );
  await logAudit(createdBy, 'item_aliases', itemId, 'ADD_ALIAS', null, { aliasName });
}

export async function getItemAliases(itemId: string): Promise<{ id: string; alias_name: string }[]> {
  return query(`SELECT id, alias_name FROM item_aliases WHERE item_id = $1 ORDER BY alias_name`, [itemId]);
}
