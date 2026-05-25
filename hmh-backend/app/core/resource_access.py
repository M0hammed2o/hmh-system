"""Centralized resource access helpers.

These helpers eliminate the repeated 3-line pattern found across route files:

    obj = db.get(Model, id)
    if not obj:
        raise HTTPException(404, "...")
    check_project_access(db, current_user, obj.project_id)

Usage
-----
Pattern A (pre-fetch before service call — most write routes):

    # Before
    _po = db.get(PurchaseOrder, po_id)
    if not _po:
        raise HTTPException(404, "Purchase order not found.")
    check_project_access(db, current_user, _po.project_id)
    po = po_service.update_po(db, po_id, body)

    # After
    get_and_check_project_resource(db, current_user, PurchaseOrder, po_id)
    po = po_service.update_po(db, po_id, body)

Pattern B (service fetches first — most read routes):

    # Before
    po = po_service.get_po(db, po_id)
    check_project_access(db, current_user, po.project_id)

    # After
    po = secure_project_lookup(po_service.get_po(db, po_id), db, current_user)
"""

import uuid
from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.dependencies import check_project_access

T = TypeVar("T")


def get_resource_or_404(
    db: Session,
    model_class: type[T],
    resource_id: uuid.UUID,
    detail: str | None = None,
) -> T:
    """Fetch a SQLAlchemy model by primary key or raise HTTP 404.

    This is the primitive used by the higher-level helpers but also
    useful standalone when no project-access check is required.
    """
    obj = db.get(model_class, resource_id)
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail=detail or f"{model_class.__name__} not found.",
        )
    return obj  # type: ignore[return-value]


def get_and_check_project_resource(
    db: Session,
    user: Any,
    model_class: type[T],
    resource_id: uuid.UUID,
    detail: str | None = None,
) -> T:
    """Fetch a project-scoped resource, raise 404 if missing, then 403 if no access.

    Preserves the semantics: a missing resource is always 404, not 403.
    The caller receives the already-validated instance; passing it to a
    service call avoids a second DB round-trip only when the service
    accepts the object directly. Otherwise the pre-fetch guards the
    access check and the service performs its own fetch as before.
    """
    obj = get_resource_or_404(db, model_class, resource_id, detail)
    check_project_access(db, user, obj.project_id)  # type: ignore[attr-defined]
    return obj


def secure_project_lookup(
    resource: T,
    db: Session,
    user: Any,
) -> T:
    """Verify project access for an already-fetched resource and return it.

    Used in read routes where the service layer performs the fetch (and
    raises 404 internally). Wrapping the call makes the authorization
    intent explicit and keeps the pattern consistent with write routes.

        po = secure_project_lookup(po_service.get_po(db, po_id), db, current_user)
    """
    check_project_access(db, user, resource.project_id)  # type: ignore[attr-defined]
    return resource
