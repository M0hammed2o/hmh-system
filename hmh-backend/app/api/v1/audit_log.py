"""Audit log read API — surfaces the audit_events table for admin review."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import OFFICE_AND_ABOVE, DbSession
from app.models.audit import AuditEvent
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=ApiSuccess[list[dict]], dependencies=[OFFICE_AND_ABOVE])
def list_audit_events(
    db: DbSession,
    actor_id:    Optional[uuid.UUID] = Query(None, description="Filter by user (actor)"),
    entity_type: Optional[str]        = Query(None, description="e.g. material_request, purchase_order"),
    action:      Optional[str]        = Query(None, description="CREATE, UPDATE, APPROVE, etc."),
    from_date:   Optional[datetime]   = Query(None),
    to_date:     Optional[datetime]   = Query(None),
    limit:       int                  = Query(100, le=500),
    offset:      int                  = Query(0),
):
    """
    Return audit events in descending chronological order.
    Supports filtering by actor, entity type, action, and date range.
    """
    q = db.query(AuditEvent).order_by(AuditEvent.created_at.desc())

    if actor_id:
        q = q.filter(AuditEvent.actor_id == actor_id)
    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type.lower())
    if action:
        q = q.filter(AuditEvent.action == action.upper())
    if from_date:
        q = q.filter(AuditEvent.created_at >= from_date)
    if to_date:
        q = q.filter(AuditEvent.created_at <= to_date)

    total = q.count()
    events = q.offset(offset).limit(limit).all()

    return ApiSuccess(data=[{
        "id":          str(e.id),
        "actor_id":    str(e.actor_id) if e.actor_id else None,
        "action":      e.action,
        "entity_type": e.entity_type,
        "entity_id":   str(e.entity_id) if e.entity_id else None,
        "before_value": e.before_value,
        "after_value":  e.after_value,
        "notes":        e.notes,
        "created_at":   e.created_at.isoformat(),
    } for e in events], message=f"{total} total events.")
