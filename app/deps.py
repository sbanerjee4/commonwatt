"""FastAPI auth dependencies: resolve identity from the session cookie.

These REPLACE the pre-auth `X-User-Id` / `X-Role` header stand-in. A route that
needs a user depends on `current_user`; a route restricted to one role depends
on `require_role(...)`. Identity comes only from the `cw_session` cookie.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth import COOKIE_NAME, resolve_session
from app.db import get_db
from db.models import User, ZipUtility, Building


def current_user(
    db: DBSession = Depends(get_db),
    cw_session: str | None = Cookie(default=None),
) -> User:
    """Return the logged-in User, or 401. The auth boundary for the whole app."""
    user = resolve_session(db, cw_session)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def optional_user(
    db: DBSession = Depends(get_db),
    cw_session: str | None = Cookie(default=None),
) -> User | None:
    """Return the logged-in User or None. For routes that adapt to auth state."""
    return resolve_session(db, cw_session)


def require_role(role: str):
    """Dependency factory: 401 if unauthenticated, 403 if the role does not match."""

    def _dep(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="not authorized for this role")
        return user

    return _dep


def utility_id_for(db: DBSession, user: User) -> str | None:
    """Resolve the user's utility id.

    A `utility` user carries it directly. A `building_manager` has it derived by
    joining their building -> zip -> zip_utility (spec /auth/me behavior).
    """
    if user.utility_id is not None:
        return user.utility_id
    if user.building_id is None:
        return None
    return db.execute(
        select(ZipUtility.utility_id)
        .join(Building, Building.zip == ZipUtility.zip)
        .where(Building.id == user.building_id)
    ).scalar_one_or_none()
