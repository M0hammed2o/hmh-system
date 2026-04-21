import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as procurementService from './procurement.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest, RecordStatus } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

// ---- Material Requests ----

router.get('/requests', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await procurementService.listMaterialRequests(
      req.params.projectId, page, limit,
      { status: req.query.status as RecordStatus, site_id: req.query.site_id as string }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/requests/:id', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const mr = await procurementService.getMaterialRequestById(req.params.id);
    res.json({ success: true, data: mr });
  } catch (err) { next(err); }
});

router.post('/requests',
  authorize(...ALL_ROLES),
  [
    body('site_id').isUUID().withMessage('site_id is required.'),
    body('items').isArray({ min: 1 }).withMessage('At least one item is required.'),
    body('items.*.item_id').isUUID().withMessage('item_id is required for each item.'),
    body('items.*.requested_quantity').isNumeric().withMessage('requested_quantity must be numeric.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const mr = await procurementService.createMaterialRequest(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: mr });
    } catch (err) { next(err); }
  }
);

router.post('/requests/:id/submit', authorize(...ALL_ROLES),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const mr = await procurementService.submitMaterialRequest(req.params.id, req.user.sub);
      res.json({ success: true, data: mr });
    } catch (err) { next(err); }
  }
);

router.post('/requests/:id/review',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('action').isIn(['APPROVE', 'REJECT']).withMessage('action must be APPROVE or REJECT.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const mr = await procurementService.reviewMaterialRequest(
        req.params.id,
        req.body.action,
        req.body.rejection_reason ?? null,
        req.user.sub
      );
      res.json({ success: true, data: mr });
    } catch (err) { next(err); }
  }
);

// ---- Purchase Orders ----

router.get('/orders', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await procurementService.listPurchaseOrders(
      req.params.projectId, page, limit,
      { status: req.query.status as RecordStatus, supplier_id: req.query.supplier_id as string }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/orders/:id', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const po = await procurementService.getPurchaseOrderById(req.params.id);
    res.json({ success: true, data: po });
  } catch (err) { next(err); }
});

router.post('/orders',
  authorize(...OFFICE_AND_ABOVE),
  [
    body('supplier_id').isUUID().withMessage('supplier_id is required.'),
    body('items').isArray({ min: 1 }).withMessage('At least one item is required.'),
    body('items.*.description').notEmpty().withMessage('description is required for each item.'),
    body('items.*.quantity_ordered').isNumeric().withMessage('quantity_ordered must be numeric.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const po = await procurementService.createPurchaseOrder(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: po });
    } catch (err) { next(err); }
  }
);

router.post('/orders/:id/approve', authorize(...OFFICE_ADMIN_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const po = await procurementService.approvePurchaseOrder(req.params.id, req.user.sub);
      res.json({ success: true, data: po });
    } catch (err) { next(err); }
  }
);

router.post('/orders/:id/send', authorize(...OFFICE_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const po = await procurementService.markPoSent(req.params.id, req.user.sub);
      res.json({ success: true, data: po });
    } catch (err) { next(err); }
  }
);

export default router;
