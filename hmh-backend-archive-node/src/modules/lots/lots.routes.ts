import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as lotsService from './lots.service';
import { authenticate, authorize, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const lots = await lotsService.listLots(req.params.projectId, req.query.site_id as string);
    res.json({ success: true, data: lots });
  } catch (err) { next(err); }
});

router.get('/:id', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const lot = await lotsService.getLotById(req.params.id);
    res.json({ success: true, data: lot });
  } catch (err) { next(err); }
});

router.post('/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('lot_number').trim().notEmpty().withMessage('Lot number is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const lot = await lotsService.createLot({ ...req.body, project_id: req.params.projectId }, req.user.sub);
      res.status(201).json({ success: true, data: lot });
    } catch (err) { next(err); }
  }
);

router.patch('/:id', authorize(...OFFICE_ADMIN_AND_ABOVE), validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const lot = await lotsService.updateLot(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: lot });
    } catch (err) { next(err); }
  }
);

export default router;
