"""Property tests: the two core safety invariants of send_sms.

Property 2: an opted-out or phone-less user is NEVER contacted.
Property 1: a building_ask is NEVER sent for a building not in the event.
Both assert the provider was not called on the forbidden paths.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from notify.models import send_sms
from notify.provider import SimulatedProvider
from tests.conftest import make_building, make_event, make_user

_SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _run(coro):
    return asyncio.run(coro)


@_SETTINGS
@given(opted_out=st.booleans(), has_phone=st.booleans())
def test_optout_and_no_phone_never_send(db_factory, opted_out, has_phone):
    db = db_factory()
    bld = make_building(db)
    event = make_event(db, building_ids=[bld.id])
    user = make_user(
        db,
        building_id=bld.id,
        phone="+12025550100" if has_phone else None,
        sms_opted_out=opted_out,
    )
    provider = SimulatedProvider(db_session=db)

    result = _run(
        send_sms(
            user_id=user.id,
            template="building_ask",
            params=dict(window="Tue", building_name="B", kw_requested=20,
                        kw_enrolled=100, reason="peak", payment=200),
            event_id=event.id,
            db_session=db,
            provider=provider,
        )
    )

    should_send = has_phone and not opted_out
    assert result["sent"] is should_send
    # Invariant: provider is only ever touched when a send was allowed.
    assert (len(provider.sent) == 1) is should_send
    db.close()


@_SETTINGS
@given(in_event=st.booleans())
def test_building_ask_only_for_building_in_event(db_factory, in_event):
    db = db_factory()
    asked = make_building(db)
    other = make_building(db)
    event = make_event(db, building_ids=[asked.id])
    user = make_user(
        db,
        building_id=asked.id if in_event else other.id,
        phone="+12025550101",
    )
    provider = SimulatedProvider(db_session=db)

    result = _run(
        send_sms(
            user_id=user.id,
            template="building_ask",
            params=dict(window="Tue", building_name="B", kw_requested=20,
                        kw_enrolled=100, reason="peak", payment=200),
            event_id=event.id,
            db_session=db,
            provider=provider,
        )
    )

    assert result["sent"] is in_event
    assert (len(provider.sent) == 1) is in_event
    if not in_event:
        assert result["reason_skipped"] == "building_not_in_event"
    db.close()
