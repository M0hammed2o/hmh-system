import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as stockService from './stock.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

// GET /api/projects/:projectId/stock/balance
router.get('/balance', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { site_id, item_id } = req.query as { site_id?: string; item_id?: string };
    if (!site_id) {
      res.status(400).json({ success: false, message: 'site_id query param is required.' });
      return;
    }
    const balances = await stockService.getStockBalance(req.params.projectId, site_id, item_id);
    res.json({ success: true, data: balances });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/stock/ledger
router.get('/ledger', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { site_id, item_id } = req.query as { site_id?: string; item_id?: string };
    if (!site_id) {
      res.status(400).json({ success: false, message: 'site_id query param is required.' });
      return;
    }
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '50', 10), 200);
    const result = await stockService.getStockLedger(req.params.projectId, site_id, item_id, page, limit);
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/stock/usage
router.get('/usage', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await stockService.listUsageLogs(
      req.params.projectId, req.query.site_id as string, page, limit
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

// POST /api/projects/:projectId/stock/delivery
router.post('/delivery',
  authorize(...ALL_ROLES),
  [
    body('supplier_id').isUUID().withMessage('supplier_id is required.'),
    body('site_id').isUUID().withMessage('site_id is required.'),
    body('items').isArray({ min: 1 }).withMessage('At least one item is required.'),
    body('items.*.item_id').isUUID().withMessage('item_id is required for each item.'),
    body('items.*.quantity_received').isNumeric().withMessage('quantity_received must be numeric.'),
    body('items.*.description').notEmpty().withMessage('description is required for each item.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const result = await stockService.recordDelivery(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: result });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/stock/usage
router.post('/usage',
  authorize(...ALL_ROLES),
  [
    body('site_id').isUUID().withMessage('site_id is required.'),
    body('item_id').isUUID().withMessage('item_id is required.'),
    body('quantity_used').isNumeric().isFloat({ min: 0.001 }).withMessage('quantity_used must be > 0.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const log = await stockService.recordUsage(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: log });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/stock/adjust
router.post('/adjust',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [
    body('site_id').isUUID().withMessage('site_id is required.'),
    body('item_id').isUUID().withMessage('item_id is required.'),
    body('adjustment_type').isIn(['ADD', 'SUBTRACT']).withMessage('adjustment_type must be ADD or SUBTRACT.'),
    body('quantity').isNumeric().isFloat({ min: 0.001 }),
    body('notes').notEmpty().withMessage('notes is required for adjustments.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await stockService.adjustStock({ ...req.body, project_id: req.params.projectId }, req.user.sub);
      res.json({ success: true, data: null, message: 'Stock adjustment recorded.' });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/stock/opening-balances/:id/post
router.post('/opening-balances/:id/post',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await stockService.postOpeningBalance(req.params.id, req.user.sub);
      res.json({ success: true, data: null, message: 'Opening balance posted to ledger.' });
    } catch (err) { next(err); }
  }
);

export default router;
