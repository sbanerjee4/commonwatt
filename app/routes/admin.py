"""Admin seed route — a one-time way to seed the demo data on a host with no
shell (Render free tier can't run `python -m db.seed`).

Gated by a shared secret: set COMMONWATT_SEED_TOKEN in the environment, then
POST /admin/seed with header `X-Seed-Token: <that value>`. When the env var is
unset the route is disabled entirely (404-equivalent 403), so it is inert in any
environment that does not opt in. Seeding is idempotent (db.seed upserts), so a
second call is harmless. Remove the token once seeded to re-disable it.
"""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException

from db.seed import (
    seed_demo_accounts,
    seed_demo_event,
    seed_placeholder_territory,
)
from db.config import SessionLocal

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed")
def seed(x_seed_token: str | None = Header(default=None)) -> dict:
    expected = os.environ.get("COMMONWATT_SEED_TOKEN", "")
    if not expected:
        # Not opted in: the route is effectively off.
        raise HTTPException(status_code=403, detail="seeding disabled")
    # Constant-time compare so the token can't be guessed by timing.
    if not x_seed_token or not hmac.compare_digest(x_seed_token, expected):
        raise HTTPException(status_code=403, detail="bad seed token")

    with SessionLocal() as session:
        seed_placeholder_territory(session)
        seed_demo_accounts(session)
        seed_demo_event(session)
    return {"ok": True, "seeded": ["territory", "demo_accounts", "demo_event"]}
