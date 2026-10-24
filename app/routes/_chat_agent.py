"""Automated-agent glue for the in-app chat (auto mode).

Reuses ``agent/chat.py:make_session`` (the Bedrock ``ChatSession`` restricted to
the tool-grounded ``building_info`` + ``estimate_savings`` tools). Two helpers:

- ``build_event_context`` seeds the session with the event's real values — no
  invented numbers; missing values pass through as ``None`` or a tool-deferral
  label so the agent fetches them from a tool.
- ``agent_reply_or_fallback`` runs the model inside a guard: a Bedrock error or
  a reply that trips the forbidden-word check is suppressed and replaced with a
  fixed fallback, and the thread is flagged for operator attention. The mode is
  NOT flipped to human (that is the manager's explicit choice).
"""

from __future__ import annotations

from db.models import Building, Event, Thread
from notify.templates import _contains_forbidden

# Posted instead of an agent reply when the model is unavailable or its reply
# is unsafe. Plain, safe, and honest about a human follow-up.
FALLBACK = "A Commonwatt representative will follow up with you shortly."


def build_event_context(db, event: Event, building_id: str) -> dict:
    """Assemble the event_context dict ChatSession expects, from real data."""
    from app.routes._chat_helpers import current_plan_building

    pb = current_plan_building(db, event, building_id)
    building = db.get(Building, building_id)
    return {
        "window_label": event.window_label,
        "requested_kw": pb.kw_requested if pb is not None else None,
        "reason": (pb.reason if pb is not None and pb.reason else "high afternoon load"),
        # The agent must call estimate_savings for a real, sourced figure.
        "estimated_payment_label": "see estimate_savings tool",
        "enrolled_capacity_kw": (
            building.enrolled_capacity_kw if building is not None else None
        ),
    }


# Optional test/override seam: set this to a callable(building_id, event_context)
# to bypass the real Bedrock session (used by tests to avoid importing the heavy
# agent.chat -> server.tools -> fastmcp chain). None means use the real one.
make_session = None


def _resolve_make_session():
    if make_session is not None:
        return make_session
    from agent.chat import make_session as real_make_session

    return real_make_session


def agent_reply_or_fallback(
    db, thread: Thread, ctx: dict, body: str
) -> tuple[str, bool]:
    """Return ``(reply_text, fell_back)``.

    ``fell_back`` is True when the model errored (AC-10) or its reply contained
    a forbidden word (AC-16); in both cases the text is ``FALLBACK`` and the
    caller flags the thread (``needs_human = True``) without changing the mode.
    """
    factory = _resolve_make_session()
    try:
        reply = factory(thread.building_id, event_context=ctx).chat(body)
    except Exception:
        return FALLBACK, True
    if not reply or _contains_forbidden(reply) is not None:
        return FALLBACK, True
    return reply, False
