/**
 * Database seed script — creates the initial OWNER user and stage_master records.
 * Run once after migration: npm run db:seed
 */
import bcrypt from 'bcryptjs';
import { pool } from '../config/database';
import { logger } from '../config/logger';

const STAGES = [
  { name: 'Foundation', sequence_order: 1 },
  { name: 'Slab', sequence_order: 2 },
  { name: 'Brickwork', sequence_order: 3 },
  { name: 'Wallplate', sequence_order: 4 },
  { name: 'Roof Structure', sequence_order: 5 },
  { name: 'Roof Cover', sequence_order: 6 },
  { name: 'Electrical Rough-in', sequence_order: 7 },
  { name: 'Plumbing Rough-in', sequence_order: 8 },
  { name: 'Plastering', sequence_order: 9 },
  { name: 'Windows & Doors', sequence_order: 10 },
  { name: 'Electrical Fit-out', sequence_order: 11 },
  { name: 'Plumbing Fit-out', sequence_order: 12 },
  { name: 'Tiling', sequence_order: 13 },
  { name: 'Painting', sequence_order: 14 },
  { name: 'Finishing', sequence_order: 15 },
  { name: 'Handover', sequence_order: 16 },
];

async function seed(): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Seed stage_master
    logger.info('Seeding stage_master...');
    for (const stage of STAGES) {
      await client.query(
        `INSERT INTO stage_master (name, sequence_order)
         VALUES ($1, $2)
         ON CONFLICT (name) DO NOTHING`,
        [stage.name, stage.sequence_order]
      );
    }

    // Seed initial OWNER user
    const ownerEmail = 'admin@hmhgroup.co.za';
    const tempPassword = 'HMH@Admin2024!';
    const passwordHash = await bcrypt.hash(tempPassword, 12);

    await client.query(
      `INSERT INTO users (full_name, email, password_hash, role, must_reset_password, is_active)
       VALUES ($1, $2, $3, 'OWNER', TRUE, TRUE)
       ON CONFLICT (email) DO NOTHING`,
      ['HMH Admin', ownerEmail, passwordHash]
    );

    // Seed default item categories
    const categories = [
      'Concrete & Masonry',
      'Steel & Metalwork',
      'Timber & Roofing',
      'Plumbing',
      'Electrical',
      'Finishing & Painting',
      'Labour',
      'Plant & Equipment',
      'General Materials',
    ];

    logger.info('Seeding item categories...');
    for (const cat of categories) {
      await client.query(
        `INSERT INTO item_categories (name) VALUES ($1) ON CONFLICT (name) DO NOTHING`,
        [cat]
      );
    }

    await client.query('COMMIT');

    logger.info('Seed completed.');
    logger.info(`Owner login: ${ownerEmail} / ${tempPassword}`);
    logger.info('User will be required to change password on first login.');
  } catch (err) {
    await client.query('ROLLBACK');
    logger.error('Seed failed', { error: (err as Error).message });
    throw err;
  } finally {
    client.release();
    await pool.end();
  }
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
