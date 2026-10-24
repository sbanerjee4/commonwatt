"""App configuration from environment. No secrets hard-coded."""

from __future__ import annotations

import os


def twilio_auth_token() -> str:
    return os.environ.get("TWILIO_AUTH_TOKEN", "")


def webhook_url() -> str:
    return os.environ.get(
        "SMS_WEBHOOK_URL", "https://commonwatt.example.com/sms/inbound"
    )
