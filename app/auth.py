"""Authentication primitives: password hashing + server-side sessions.

The auth model (project spec, Option A):
  - credentials are the seeded bcrypt demo accounts in `users`;
  - a login mints a random 256-bit token, stores only its SHA-256 hash in the
    `sessions` table, and sets it in the `cw_session` HttpOnly cookie;
  - every request resolves identity from that cookie, never from a client
    header; logout deletes the session row.

No JWT: the `sessions` table is the source of truth, so logout and expiry are
real server-side revocations.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import secrets

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from db.models import Session as SessionRow, User

COOKIE_NAME = "cw_session"
SESSION_TTL = dt.timedelta(hours=12)
_TOKEN_BYTES = 32  # 256-bit


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash with a fresh random salt."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """True when `plaintext` matches `stored_hash`. A malformed hash is no match."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _hash_token(raw_token: str) -> str:
    """SHA-256 of the raw cookie token. Only the hash is ever stored."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def cookie_is_secure() -> bool:
    """Secure cookies everywhere except an explicit localhost dev flag."""
    return os.environ.get("COMMONWATT_INSECURE_COOKIES", "").lower() not in {"1", "true", "yes"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_session(db: DBSession, user: User) -> str:
    """Create a session row for `user` and return the RAW token for the cookie.

    The raw token is returned to the caller (to set in the cookie) but never
    stored; the row holds only its hash.
    """
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    row = SessionRow(
        token_hash=_hash_token(raw),
        user_id=user.id,
        expires_at=_now() + SESSION_TTL,
    )
    db.add(row)
    db.commit()
    return raw


def resolve_session(db: DBSession, raw_token: str | None) -> User | None:
    """Return the live User for a cookie token, or None.

    None when: no token, no matching row, or the row has expired. An expired
    row is deleted in passing so the table self-prunes.
    """
    if not raw_token:
        return None
    row = db.execute(
        select(SessionRow).where(SessionRow.token_hash == _hash_token(raw_token))
    ).scalar_one_or_none()
    if row is None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires <= _now():
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def delete_session(db: DBSession, raw_token: str | None) -> None:
    """Delete the session row for a cookie token, if any (idempotent)."""
    if not raw_token:
        return
    row = db.execute(
        select(SessionRow).where(SessionRow.token_hash == _hash_token(raw_token))
    ).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
