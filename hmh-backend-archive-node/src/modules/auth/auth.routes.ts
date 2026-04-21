import { Router } from 'express';
import {
  loginHandler,
  refreshHandler,
  changePasswordHandler,
  getMeHandler,
  loginValidators,
  changePasswordValidators,
  validate,
  authenticate,
} from './auth.controller';

const router = Router();

// POST /api/auth/login
router.post('/login', loginValidators, validate, loginHandler);

// POST /api/auth/refresh
router.post('/refresh', refreshHandler);

// POST /api/auth/change-password  (requires auth)
router.post('/change-password', authenticate, changePasswordValidators, validate, changePasswordHandler);

// GET /api/auth/me  (requires auth)
router.get('/me', authenticate, getMeHandler);

export default router;
