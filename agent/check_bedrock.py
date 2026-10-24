"""
Bedrock connectivity check.

Run this to confirm your Bedrock key + region + model access are working
before testing the planner or chat agent:

    PYTHONPATH=. python -m agent.check_bedrock

It prints a clear pass/fail and, on failure, decodes a presigned short-term
token to show its signed region and expiry so you can spot mismatches.
"""

from __future__ import annotations

import base64
import datetime
import os
import urllib.parse

from dotenv import load_dotenv

load_dotenv(override=True)


def _inspect_token(tok: str) -> None:
    if not tok.startswith("bedrock-api-key-"):
        print("  token does not start with 'bedrock-api-key-'")
        return
    blob = tok[len("bedrock-api-key-"):]
    try:
        padded = blob + "=" * (-len(blob) % 4)
        url = base64.b64decode(padded).decode("utf-8", "replace")
        if "?" not in url:
            print("  (long-term key — no embedded presigned URL to inspect)")
            return
        qs = urllib.parse.parse_qs(url.split("?", 1)[1])
        cred = urllib.parse.unquote(qs.get("X-Amz-Credential", [""])[0])
        print(f"  signed credential scope: {cred}")
        amzdate = qs.get("X-Amz-Date", [""])[0]
        exp = int(qs.get("X-Amz-Expires", ["0"])[0] or 0)
        if amzdate and exp:
            t0 = datetime.datetime.strptime(amzdate, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=datetime.timezone.utc
            )
            expiry = t0 + datetime.timedelta(seconds=exp)
            now = datetime.datetime.now(datetime.timezone.utc)
            status = "EXPIRED" if now > expiry else f"valid for {expiry - now}"
            print(f"  token expiry: {expiry.isoformat()} ({status})")
    except Exception as e:  # noqa: BLE001
        print(f"  could not decode token: {e}")


def main() -> int:
    tok = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    region = os.environ.get("AWS_REGION", "us-east-1")

    print(f"AWS_REGION = {region}")
    print(f"token present = {bool(tok)} (length {len(tok)})")
    if tok:
        _inspect_token(tok)

    if not tok:
        print("\nFAIL: no token. Put it in .env as AWS_BEARER_TOKEN_BEDROCK=...")
        return 1

    from agent.llm import get_client, get_model_id

    try:
        client = get_client()
        resp = client.messages.create(
            model=get_model_id(),
            max_tokens=20,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        print(f"\nPASS: Bedrock responded: {text!r}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\nFAIL: Bedrock call failed: {type(e).__name__}: {e}")
        print(
            "\nLikely causes:\n"
            "  1. Short-term token's STS session ended (regenerate a fresh key)\n"
            "  2. Claude model access not enabled in this region (Bedrock console → Model access)\n"
            "  3. AWS_REGION does not match the token's signed region (see scope above)\n"
            "  4. IAM principal lacks bedrock:InvokeModel"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
