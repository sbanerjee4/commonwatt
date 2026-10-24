"""Free browser Web Push notifications.

A nudge channel that costs nothing: delivery is the browser's own push service
(no Twilio, no SMS). Sending needs VAPID keys (WEBPUSH_VAPID_PRIVATE_KEY,
WEBPUSH_VAPID_CLAIM_EMAIL) and the optional `pywebpush` library. When either is
absent, send is a no-op that reports it was skipped — so the feature degrades
cleanly in a demo without keys, and nothing crashes.
"""

from __future__ import annotations

import json
import os

from db.models import PushSubscription, User


def save_subscription(db, user_id: int, endpoint: str, p256dh: str, auth: str):
    """Upsert a user's push subscription by endpoint."""
    existing = (
        db.query(PushSubscription).filter_by(endpoint=endpoint).one_or_none()
    )
    if existing:
        existing.user_id = user_id
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(user_id=user_id, endpoint=endpoint,
                                p256dh=p256dh, auth=auth))
    db.commit()


def _vapid_ready() -> bool:
    return bool(
        os.environ.get("WEBPUSH_VAPID_PRIVATE_KEY")
        and os.environ.get("WEBPUSH_VAPID_CLAIM_EMAIL")
    )


def notify_user(db, user_id: int, title: str, body: str) -> dict:
    """Send a push to every subscription of a user. Best-effort.

    Returns a summary: how many sent, skipped, or failed. Never raises on a
    missing library or missing keys — those are reported as skipped.
    """
    subs = db.query(PushSubscription).filter_by(user_id=user_id).all()
    if not subs:
        return {"sent": 0, "skipped": 0, "reason": "no subscriptions"}

    if not _vapid_ready():
        return {"sent": 0, "skipped": len(subs), "reason": "no VAPID keys"}

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {"sent": 0, "skipped": len(subs), "reason": "pywebpush not installed"}

    private_key = os.environ["WEBPUSH_VAPID_PRIVATE_KEY"]
    claims = {"sub": f"mailto:{os.environ['WEBPUSH_VAPID_CLAIM_EMAIL']}"}
    payload = json.dumps({"title": title, "body": body})

    sent = failed = 0
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=dict(claims),
            )
            sent += 1
        except WebPushException:
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": 0}
