"""One-shot real-SMS smoke test.

Loads .env, seeds an in-memory user + approved event whose manager's phone is
the first number in SMS_DEMO_ALLOWLIST, then sends one real building_ask.
Prints the outcome. Demo mode still gates the send to the allowlist.

Run: .venv/bin/python -m scripts.send_test_sms
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base, Building, Event, EventBuilding, User, Utility
from notify.models import send_sms
from notify.provider import resolve_provider


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


async def _send_trial_template(phone: str) -> None:
    """Trial-safe real send: Twilio only accepts a PREDEFINED template name as
    the body on a trial account. We send 'sms_body' / 'sms_appointment_reminder'
    style names; Twilio expands them into a canned message to the verified
    number, for free. This proves real delivery with trial credentials. The
    CommonWatt wording is used by the simulated provider and after upgrade.
    """
    import httpx

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    frm = os.environ["TWILIO_FROM_NUMBER"]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    # Try the documented predefined template names in order.
    for template_body in ("sms_body", "sms_appointment_reminder", "sms_2fa"):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={"To": phone, "From": frm, "Body": template_body},
                auth=(sid, token),
            )
        print(f"  body={template_body!r} -> http {resp.status_code}")
        if resp.status_code // 100 == 2:
            print(f"SENT (trial template {template_body!r}). Check {phone}. "
                  f"SID: {resp.json().get('sid')}")
            return
        else:
            print(f"    {resp.text[:160]}")
    print("No predefined template accepted — see the names on the console "
          "'Try out SMS' page and set one here.")


async def main() -> None:
    _load_dotenv()

    allowlist = [n.strip() for n in
                 os.environ.get("SMS_DEMO_ALLOWLIST", "").split(",") if n.strip()]
    if not allowlist:
        raise SystemExit("SMS_DEMO_ALLOWLIST is empty — add your number to .env")
    phone = allowlist[0]

    # Trial mode: send a predefined template so a trial account can deliver.
    if "--trial" in sys.argv:
        print(f"trial real send to {phone} using predefined templates…")
        await _send_trial_template(phone)
        return

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)

    util = Utility(name="Demo Util")
    bld = Building(name="Test Building", kw_enrolled=100, kw_requested=20)
    db.add_all([util, bld])
    db.commit()
    user = User(email="you@test", role="building_manager",
                building_id=bld.id, phone=phone)
    ev = Event(utility_id=util.id, status="approved", window_label="Tue 2-6PM",
               reason_text="peak day", estimated_payment=200)
    db.add_all([user, ev])
    db.commit()
    db.add(EventBuilding(event_id=ev.id, building_id=bld.id))
    db.commit()

    provider = resolve_provider(db_session=db)
    print(f"provider={provider.name}  demo_mode="
          f"{getattr(provider, 'demo_mode', 'n/a')}  to={phone}")

    result = await send_sms(
        user_id=user.id,
        template="building_ask",
        params=dict(window="Tue 2-6PM", building_name="Test Building",
                    kw_requested=20, kw_enrolled=100, reason="peak day",
                    payment=200),
        event_id=ev.id,
        db_session=db,
        provider=provider,
    )
    print("result:", result)
    if result["sent"]:
        print(f"SENT — check {phone}. Twilio SID: {result['provider_sid']}")
    else:
        print(f"NOT sent — reason: {result['reason_skipped']}")


if __name__ == "__main__":
    asyncio.run(main())
