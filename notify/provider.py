"""SMS provider abstraction.

Two concrete providers:
- TwilioProvider: real send via the Twilio REST API. Credentials come from
  the environment, never from code. demo_mode + demo_allowlist restrict real
  sends to known numbers so a bug cannot text strangers.
- SimulatedProvider: logs to outbound_messages, no network. Used by tests and
  by `make demo`.

Provider.send() returns an SMSResult and has no DB side effects beyond what
SimulatedProvider explicitly logs; send_sms() in notify.models owns the
outbound_messages row and the audit trail.
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SMSResult:
    """Outcome of one send attempt."""

    success: bool
    provider_sid: Optional[str]
    error: Optional[str]


class Provider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(self, phone: str, body: str) -> SMSResult:
        """Send an SMS to an E.164 number. Return an SMSResult."""
        raise NotImplementedError


class TwilioProvider(Provider):
    """Live Twilio provider. Real HTTP call to the Messages endpoint."""

    name = "twilio"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        demo_mode: bool = False,
        demo_allowlist: Optional[list[str]] = None,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.demo_mode = demo_mode
        self.demo_allowlist = demo_allowlist or []

    @classmethod
    def from_env(cls) -> "TwilioProvider":
        """Build from environment. Never hard-code a credential.

        Reads TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER,
        SMS_DEMO_MODE (default true), SMS_DEMO_ALLOWLIST (comma-separated).
        """
        missing = [
            k
            for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
            if not os.environ.get(k)
        ]
        if missing:
            raise RuntimeError(
                "missing Twilio env vars: " + ", ".join(missing)
            )
        allowlist = [
            n.strip()
            for n in os.environ.get("SMS_DEMO_ALLOWLIST", "").split(",")
            if n.strip()
        ]
        demo_mode = os.environ.get("SMS_DEMO_MODE", "true").lower() != "false"
        return cls(
            account_sid=os.environ["TWILIO_ACCOUNT_SID"],
            auth_token=os.environ["TWILIO_AUTH_TOKEN"],
            from_number=os.environ["TWILIO_FROM_NUMBER"],
            demo_mode=demo_mode,
            demo_allowlist=allowlist,
        )

    async def send(self, phone: str, body: str) -> SMSResult:
        # Demo-mode guard: in demo mode, only allowlisted numbers are
        # ever contacted. Checked BEFORE any network call.
        if self.demo_mode and phone not in self.demo_allowlist:
            return SMSResult(
                success=False,
                provider_sid=None,
                error="demo mode: number not in allowlist",
            )

        # Import inside the method so the module loads without httpx present
        # (tests use SimulatedProvider and need no HTTP stack).
        try:
            import httpx
        except ImportError:  # pragma: no cover
            return SMSResult(
                success=False,
                provider_sid=None,
                error="httpx not installed; cannot reach Twilio",
            )

        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.account_sid}/Messages.json"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    data={"To": phone, "From": self.from_number, "Body": body},
                    auth=(self.account_sid, self.auth_token),
                )
            if resp.status_code // 100 == 2:
                sid = resp.json().get("sid")
                return SMSResult(success=True, provider_sid=sid, error=None)
            return SMSResult(
                success=False,
                provider_sid=None,
                error=f"twilio http {resp.status_code}: {resp.text[:200]}",
            )
        except Exception as exc:  # network, timeout, auth
            return SMSResult(
                success=False, provider_sid=None, error=f"{type(exc).__name__}: {exc}"
            )


class SimulatedProvider(Provider):
    """Logs instead of sending. No network, no credentials, no cost."""

    name = "simulated"

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.sent: list[dict] = []

    async def send(self, phone: str, body: str) -> SMSResult:
        sid = f"SIM{uuid.uuid4().hex[:16]}"
        self.sent.append({"phone": phone, "body": body, "sid": sid})
        return SMSResult(success=True, provider_sid=sid, error=None)


def resolve_provider(db_session=None) -> Provider:
    """Pick a provider from SMS_PROVIDER env (default 'simulated')."""
    choice = os.environ.get("SMS_PROVIDER", "simulated").lower()
    if choice == "twilio":
        return TwilioProvider.from_env()
    return SimulatedProvider(db_session=db_session)
