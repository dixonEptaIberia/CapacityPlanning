"""Authentication and role/scope-based authorization (R12).

In dev mode (AUTH_MODE=dev) the caller identity is taken from the ``X-User``
header and resolved against the users table, so the app is usable locally
without Cognito. In production (AUTH_MODE=cognito) this is where the Cognito
JWT would be verified against the JWKS endpoint and mapped to an app role.

Authorization is enforced on the server for every protected endpoint, not just
in the UI.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.base import get_db
from app.models import Plant, RoleName, User

# Role hierarchy for "at least this role" checks.
_ROLE_RANK = {
    RoleName.plant_viewer: 0,
    RoleName.viewer: 1,
    RoleName.planner: 2,
    RoleName.central_admin: 3,
}

# Roles allowed to edit planning data / configuration.
EDIT_ROLES = {RoleName.planner, RoleName.central_admin}


def get_current_user(
    db: Session = Depends(get_db),
    x_user: str | None = Header(default=None),
) -> User:
    """Resolve the authenticated user.

    Dev mode: ``X-User`` header names an existing user (defaults to 'admin').
    Cognito mode: would verify the bearer JWT (not enabled in this build).
    """
    if settings.auth_mode == "cognito":
        # Placeholder: production verifies the JWT against the Cognito JWKS here.
        raise UnauthorizedError("Cognito auth is not configured in this build.")

    username = x_user or "admin"
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise UnauthorizedError(f"Unknown user '{username}'.")
    return user


def require_role(minimum: RoleName) -> Callable[..., User]:
    """Dependency factory enforcing a minimum role (R12.1, R12.5)."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
            raise ForbiddenError(
                f"Requires role '{minimum.value}' or higher; you have '{user.role.value}'."
            )
        return user

    return _dep


def require_edit(user: User = Depends(get_current_user)) -> User:
    """Require a role that may modify planning data or config (R12.5)."""
    if user.role not in EDIT_ROLES:
        raise ForbiddenError("You do not have edit rights.")
    return user


def check_plant_scope(user: User, plant: Plant) -> None:
    """Enforce a user's plant/region scope (R12.4).

    central-admin has no scope limit. A user scoped to a plant may only act on
    that plant; a user scoped to a region only within that region.
    """
    if user.role == RoleName.central_admin:
        return
    if user.scope_plant_id is not None and user.scope_plant_id != plant.id:
        raise ForbiddenError("Outside your plant scope.")
    if user.scope_region is not None and user.scope_region != plant.region:
        raise ForbiddenError("Outside your region scope.")
