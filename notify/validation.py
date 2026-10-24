"""Inbound validation: Twilio signature check and reply-body parser."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import Union
from urllib.parse import parse_qsl

DEFAULT_WEBHOOK_URL = "https://commonwatt.example.com/sms/inbound"


def validate_signature(
    body: bytes,
    signature: str,
    auth_token: str,
    url: str = DEFAULT_WEBHOOK_URL,
) -> bool:
    """Validate Twilio's X-Twilio-Signature.

    Twilio's scheme: take the full URL, append each POST param
    name+value sorted by name, HMAC-SHA1 with the auth token, base64.
    Compared in constant time to resist timing attacks.
    """
    if not signature or not auth_token:
        return False
    # A real Twilio signature is ASCII base64. A non-ASCII signature cannot
    # match and would make compare_digest raise, so reject it up front.
    if not signature.isascii():
        return False

    params = sorted(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))
    payload = url + "".join(k + v for k, v in params)

    digest = hmac.new(
        auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")

    return hmac.compare_digest(expected, signature)


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
