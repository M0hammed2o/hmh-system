import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as suppliersService from './suppliers.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router();
router.use(authenticate);

router.get('/', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await suppliersService.listSuppliers(page, limit, {
      search: req.query.search as string,
      is_active: req.query.is_active !== undefined ? req.query.is_active === 'true' : undefined,
    });
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/:id', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const s = await suppliersService.getSupplierById(req.params.id);
    res.json({ success: true, data: s });
  } catch (err) { next(err); }
});

router.post('/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('name').trim().notEmpty().withMessage('Supplier name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const s = await suppliersService.createSupplier(req.body, req.user.sub);
      res.status(201).json({ success: true, data: s });
    } catch (err) { next(err); }
  }
);

router.patch('/:id', authorize(...OFFICE_ADMIN_AND_ABOVE), validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const s = await suppliersService.updateSupplier(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: s });
    } catch (err) { next(err); }
  }
);

export default router;
