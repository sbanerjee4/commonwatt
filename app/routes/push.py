"""Browser Web Push subscription routes (free notification channel)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.db import get_db
from notify.push import save_subscription

router = APIRouter()


@router.get("/push/public-key", tags=["push"])
async def public_key():
    """The VAPID public key the browser needs to subscribe. Empty when unset."""
    return {"public_key": os.environ.get("WEBPUSH_VAPID_PUBLIC_KEY", "")}


@router.post("/push/subscribe", tags=["push"])
async def subscribe(
    request: Request,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
):
    """Store the browser's push subscription for the calling user."""
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    payload = await request.json()
    endpoint = payload.get("endpoint")
    keys = payload.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (endpoint and p256dh and auth):
        raise HTTPException(status_code=400, detail="invalid subscription")
    save_subscription(db, x_user_id, endpoint, p256dh, auth)
    return {"ok": True}
