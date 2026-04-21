import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as financeService from './finance.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, OWNER_ONLY } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest, RecordStatus, PaymentStatus } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

// ---- Invoices ----

router.get('/invoices', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await financeService.listInvoices(
      req.params.projectId, page, limit,
      { status: req.query.status as RecordStatus, supplier_id: req.query.supplier_id as string }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/invoices/summary', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const summary = await financeService.getFinanceSummary(req.params.projectId);
    res.json({ success: true, data: summary });
  } catch (err) { next(err); }
});

router.get('/invoices/:id', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const inv = await financeService.getInvoiceById(req.params.id);
    res.json({ success: true, data: inv });
  } catch (err) { next(err); }
});

router.post('/invoices',
  authorize(...OFFICE_AND_ABOVE),
  [
    body('invoice_number').trim().notEmpty().withMessage('invoice_number is required.'),
    body('supplier_id').isUUID().withMessage('supplier_id is required.'),
    body('total_amount').isNumeric().withMessage('total_amount is required.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const inv = await financeService.createInvoice(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: inv });
    } catch (err) { next(err); }
  }
);

router.post('/invoices/:id/match',
  authorize(...OFFICE_AND_ABOVE),
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const result = await financeService.matchInvoice(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: result });
    } catch (err) { next(err); }
  }
);

// ---- Payments ----

router.get('/payments', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await financeService.listPayments(
      req.params.projectId, page, limit,
      { status: req.query.status as PaymentStatus }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.post('/payments',
  authorize(...OFFICE_AND_ABOVE),
  [
    body('payment_type').isIn(['SUPPLIER', 'LABOUR', 'OTHER']).withMessage('Valid payment_type is required.'),
    body('amount_paid').isNumeric().isFloat({ min: 0.01 }).withMessage('amount_paid must be > 0.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const payment = await financeService.createPayment(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: payment });
    } catch (err) { next(err); }
  }
);

router.post('/payments/:id/approve',
  authorize(...OWNER_ONLY),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const payment = await financeService.approvePayment(req.params.id, req.user.sub);
      res.json({ success: true, data: payment });
    } catch (err) { next(err); }
  }
);

export default router;
