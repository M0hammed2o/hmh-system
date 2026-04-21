import { Request, Response, NextFunction } from 'express';
import { validationResult } from 'express-validator';
import { ApiError } from '../types';

export function validate(req: Request, res: Response, next: NextFunction): void {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    const grouped: Record<string, string[]> = {};
    for (const err of errors.array()) {
      const field = 'path' in err ? (err.path as string) : 'general';
      if (!grouped[field]) grouped[field] = [];
      grouped[field].push(err.msg as string);
    }
    const body: ApiError = { success: false, message: 'Validation failed.', errors: grouped };
    res.status(422).json(body);
    return;
  }
  next();
}
