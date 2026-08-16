"""Explicit role-to-permission mapping for Fuel Management."""

from fastapi import Depends, HTTPException

from app.dependencies import CurrentUserPayload
from app.models.enums import UserRole

FUEL_PERMISSIONS = {
    "fuel.view", "fuel.request", "fuel.submit", "fuel.approve", "fuel.order",
    "fuel.receive", "fuel.issue", "fuel.reconcile", "fuel.adjust", "fuel.export", "fuel.admin",
}

_ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.OWNER: set(FUEL_PERMISSIONS),
    UserRole.OFFICE_ADMIN: set(FUEL_PERMISSIONS),
    UserRole.PROCUREMENT_LEAD: {
        "fuel.view", "fuel.request", "fuel.submit", "fuel.approve", "fuel.order",
        "fuel.receive", "fuel.export",
    },
    UserRole.OFFICE_USER: {
        "fuel.view", "fuel.request", "fuel.submit", "fuel.receive", "fuel.issue", "fuel.export",
    },
    UserRole.SITE_MANAGER: {
        "fuel.view", "fuel.request", "fuel.submit", "fuel.receive", "fuel.issue", "fuel.reconcile",
    },
    UserRole.SITE_STAFF: {"fuel.view", "fuel.request", "fuel.submit", "fuel.receive", "fuel.issue"},
    UserRole.SITE_MANAGER_VIEW: {"fuel.view"},
    UserRole.READ_ONLY: {"fuel.view", "fuel.export"},
}


def has_fuel_permission(role: UserRole, permission: str) -> bool:
    return permission in _ROLE_PERMISSIONS.get(role, set())


def require_fuel_permission(permission: str):
    if permission not in FUEL_PERMISSIONS:
        raise ValueError(f"Unknown fuel permission: {permission}")

    def _check(payload: CurrentUserPayload) -> None:
        try:
            role = UserRole(payload.get("role"))
        except (ValueError, TypeError):
            raise HTTPException(403, "Invalid role for Fuel Management.")
        if not has_fuel_permission(role, permission):
            raise HTTPException(403, f"Permission '{permission}' is required.")

    return Depends(_check)
