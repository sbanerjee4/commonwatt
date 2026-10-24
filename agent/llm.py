"""
LLM client factory.

Uses Amazon Bedrock to call Claude. Auth is via a Bedrock API key
(bearer token) set in the environment as AWS_BEARER_TOKEN_BEDROCK, or falls
back to the standard AWS credential chain (boto3) if that is not set.

Env vars (see .env.example):
  AWS_BEARER_TOKEN_BEDROCK   Bedrock API key (bearer token)
  AWS_REGION                 region, e.g. us-east-1
  COMMONWATT_MODEL_ID        Bedrock model id (optional override)

Never hard-code a key. The key lives only in .env (git-ignored).
"""

from __future__ import annotations

import os

from anthropic import AnthropicBedrock
from dotenv import load_dotenv

load_dotenv(override=True)

# Default Bedrock model id for Claude 3.5 Haiku.
# Override via COMMONWATT_MODEL_ID in .env if a different model is enabled.
DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def get_model_id() -> str:
    return os.environ.get("COMMONWATT_MODEL_ID", DEFAULT_MODEL_ID)


def get_client() -> AnthropicBedrock:
    """
    Return an AnthropicBedrock client.

    The AnthropicBedrock client reads AWS_BEARER_TOKEN_BEDROCK automatically
    when present; otherwise it uses the default AWS credential chain. We pass
    the region explicitly so it is deterministic.
    """
    region = os.environ.get("AWS_REGION", "us-east-1")
    return AnthropicBedrock(aws_region=region)
