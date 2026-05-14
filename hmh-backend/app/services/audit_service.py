"""Audit service — write immutable audit events for all critical actions."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.enums import AuditAction


def write_event(
    db: Session,
    action: AuditAction | str,
    entity_type: str,
    actor_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    before_value: Optional[Any] = None,
    after_value: Optional[Any] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None,
    commit: bool = False,
) -> AuditEvent:
    """
    Append one audit event to the log.

    Call with commit=False (default) when inside an existing transaction so the
    audit row and the business row commit together atomically.
    Call with commit=True only from background tasks or standalone scripts.
    """
    event = AuditEvent(
        id=uuid.uuid4(),
        actor_id=actor_id,
        action=action.value if isinstance(action, AuditAction) else action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_value=before_value,
        after_value=after_value,
        notes=notes,
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event
