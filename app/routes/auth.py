"""Auth routes: login, logout, me. Option A — seeded accounts, cookie session.

No sign-up or password-reset routes: accounts are seeded (demo) or operator-
provisioned later. Login returns a generic 401 that does not reveal whether the
email or the password was wrong.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth import (
    COOKIE_NAME,
    SESSION_TTL,
    cookie_is_secure,
    create_session,
    delete_session,
    verify_password,
)
from app.db import get_db
from app.deps import current_user, utility_id_for
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    # Plain str, not EmailStr: the seeded demo accounts use no-TLD addresses
    # (e.g. "utility@demo") a strict email validator would reject.
    email: str
    password: str


def _identity(db: DBSession, user: User) -> dict:
    """The {role, utilityId, buildingId?} shape the SPA routes on."""
    return {
        "role": user.role,
        "utilityId": utility_id_for(db, user),
        "buildingId": user.building_id,
    }


def _set_cookie(response: Response, raw_token: str) -> None:
    # The SPA (Vercel) and API (Render) are different sites, so the session
    # cookie must be SameSite=None to be sent on cross-site XHR — and a
    # SameSite=None cookie MUST also be Secure. Fall back to Lax only for local
    # insecure dev (COMMONWATT_INSECURE_COOKIES), where None+non-Secure is
    # rejected by browsers.
    secure = cookie_is_secure()
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="none" if secure else "lax",
        secure=secure,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )


@router.post("/login")
def login(body: LoginBody, response: Response, db: DBSession = Depends(get_db)) -> dict:
    user = db.execute(
        select(User).where(User.email == body.email)
    ).scalar_one_or_none()
    # Verify even when the user is missing is not required, but keep the branch
    # simple; the response is identical either way (no account enumeration).
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")

    raw = create_session(db, user)
    _set_cookie(response, raw)
    return _identity(db, user)


@router.get("/me")
def me(db: DBSession = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _identity(db, user)


@router.post("/logout")
def logout(response: Response, db: DBSession = Depends(get_db),
           cw_session: str | None = Cookie(default=None)) -> dict:
    delete_session(db, cw_session)
    # Match the attributes used when setting it, or the browser keeps the cookie.
    secure = cookie_is_secure()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        samesite="none" if secure else "lax",
        secure=secure,
    )
    return {"ok": True}
