import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import compression from 'compression';
import morgan from 'morgan';
import rateLimit from 'express-rate-limit';
import path from 'path';
import fs from 'fs';

import { env } from './config/env';
import { logger } from './config/logger';
import { testConnection } from './config/database';
import { errorHandler, notFound } from './middleware/errorHandler';

// Route imports
import authRoutes from './modules/auth/auth.routes';
import usersRoutes from './modules/users/users.routes';
import projectsRoutes from './modules/projects/projects.routes';
import sitesRoutes from './modules/sites/sites.routes';
import lotsRoutes from './modules/lots/lots.routes';
import stagesRoutes from './modules/stages/stages.routes';
import suppliersRoutes from './modules/suppliers/suppliers.routes';
import itemsRoutes from './modules/items/items.routes';
import boqRoutes from './modules/boq/boq.routes';
import procurementRoutes from './modules/procurement/procurement.routes';
import stockRoutes from './modules/stock/stock.routes';
import financeRoutes from './modules/finance/finance.routes';
import alertsRoutes from './modules/alerts/alerts.routes';

const app = express();

// ============================================================
// Security and infrastructure middleware
// ============================================================
app.use(helmet());
app.use(cors({
  origin: env.NODE_ENV === 'production' ? process.env.FRONTEND_URL : '*',
  credentials: true,
}));
app.use(compression());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

if (env.NODE_ENV !== 'test') {
  app.use(morgan(env.NODE_ENV === 'production' ? 'combined' : 'dev'));
}

// Rate limiting
const limiter = rateLimit({
  windowMs: env.rateLimit.windowMs,
  max: env.rateLimit.max,
  standardHeaders: true,
  legacyHeaders: false,
  message: { success: false, message: 'Too many requests. Please try again later.' },
});

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: { success: false, message: 'Too many login attempts. Please try again in 15 minutes.' },
});

app.use('/api', limiter);
app.use('/api/auth/login', authLimiter);

// Ensure uploads directory exists
const uploadDir = path.resolve(env.upload.dir);
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

// ============================================================
// Routes
// ============================================================
app.get('/health', (_req, res) => {
  res.json({ success: true, data: { status: 'ok', env: env.NODE_ENV, ts: new Date().toISOString() } });
});

app.use('/api/auth', authRoutes);
app.use('/api/users', usersRoutes);
app.use('/api/projects', projectsRoutes);
app.use('/api/projects/:projectId/sites', sitesRoutes);
app.use('/api/projects/:projectId/lots', lotsRoutes);
app.use('/api/projects/:projectId/stages', stagesRoutes);
app.use('/api/stages', stagesRoutes); // for /master endpoint
app.use('/api/suppliers', suppliersRoutes);
app.use('/api/items', itemsRoutes);
app.use('/api/projects/:projectId/boq', boqRoutes);
app.use('/api/projects/:projectId/procurement', procurementRoutes);
app.use('/api/projects/:projectId/stock', stockRoutes);
app.use('/api/projects/:projectId/finance', financeRoutes);
app.use('/api/projects/:projectId/alerts', alertsRoutes);

// ============================================================
// Error handling
// ============================================================
app.use(notFound);
app.use(errorHandler);

// ============================================================
// Start
// ============================================================
async function start(): Promise<void> {
  await testConnection();

  app.listen(env.PORT, () => {
    logger.info(`HMH API running on port ${env.PORT} [${env.NODE_ENV}]`);
    logger.info(`Health check: http://localhost:${env.PORT}/health`);
  });
}

start().catch((err) => {
  logger.error('Failed to start server', { error: (err as Error).message });
  process.exit(1);
});

export default app;
