import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as itemsService from './items.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest, ItemType } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router();
router.use(authenticate);

router.get('/categories', authorize(...ALL_ROLES), async (_req, res: Response, next: NextFunction) => {
  try {
    const cats = await itemsService.listCategories();
    res.json({ success: true, data: cats });
  } catch (err) { next(err); }
});

router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await itemsService.listItems(page, limit, {
      search: req.query.search as string,
      category_id: req.query.category_id as string,
      item_type: req.query.item_type as ItemType,
      is_active: req.query.is_active !== undefined ? req.query.is_active === 'true' : undefined,
    });
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/:id', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const item = await itemsService.getItemById(req.params.id);
    const aliases = await itemsService.getItemAliases(item.id);
    res.json({ success: true, data: { ...item, aliases } });
  } catch (err) { next(err); }
});

router.post('/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('name').trim().notEmpty().withMessage('Item name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const item = await itemsService.createItem(req.body, req.user.sub);
      res.status(201).json({ success: true, data: item });
    } catch (err) { next(err); }
  }
);

router.patch('/:id', authorize(...OFFICE_ADMIN_AND_ABOVE), validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const item = await itemsService.updateItem(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: item });
    } catch (err) { next(err); }
  }
);

router.post('/:id/aliases',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('alias_name').trim().notEmpty().withMessage('alias_name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await itemsService.addAlias(req.params.id, req.body.alias_name, req.user.sub);
      res.json({ success: true, data: null, message: 'Alias added.' });
    } catch (err) { next(err); }
  }
);

export default router;
