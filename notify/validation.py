"""Inbound validation: reply-body parser for in-app chat.

A manager's chat reply is parsed to a structured YES / NO / kW decision so it
can also be recorded as a `replies` row. (The former Twilio signature check was
removed when SMS was dropped.)
"""

from __future__ import annotations

import re
from typing import Union


_KW_RE = re.compile(r"^(\d+)\s*(kw)?$")


def parse_reply_body(body: str) -> Union[str, int, None]:
    """Parse an inbound SMS body.

    Returns "yes" / "no" / "STOP" / "START", a positive int (kW), or
    None for anything unrecognized. Case-insensitive, whitespace-tolerant.
    A non-positive number is unrecognized (None).
    """
    if body is None:
        return None
    text = body.strip().lower()
    if text == "yes":
        return "yes"
    if text == "no":
        return "no"
    if text == "stop":
        return "STOP"
    if text == "start":
        return "START"

    m = _KW_RE.match(text)
    if m:
        n = int(m.group(1))
        return n if n > 0 else None
    return None
