"""Shared AWS Bedrock client helpers for Consularis agent and report flows.

- get_bedrock_client: boto3 bedrock-runtime client with optional explicit credentials and timeout/retry config.
- check_bedrock_credentials: returns user-facing error string if credentials missing.
- converse_with_retry: single Converse API call with exponential backoff on ThrottlingException.
- extract_response_text: first text block from output.message.content (for assistant replies).
"""
import logging
import time

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    BEDROCK_MAX_RETRIES,
    BEDROCK_TIMEOUT,
)

logger = logging.getLogger("consularis.agent")


def get_bedrock_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    cfg = BotoConfig(read_timeout=BEDROCK_TIMEOUT, retries={"max_attempts": BEDROCK_MAX_RETRIES})
    return boto3.client("bedrock-runtime", config=cfg, **kwargs)


def check_bedrock_credentials() -> str | None:
    """Return an error message if AWS credentials are missing, or None if OK."""
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return (
            "AWS credentials are not set. "
            "Put AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in backend/.env (copy from root .env.example) and restart."
        )
    return None


def converse_with_retry(client, **kwargs) -> dict:
    """Call client.converse with retry on ThrottlingException. Raises on final failure."""
    for attempt in range(BEDROCK_MAX_RETRIES + 1):
        try:
            return client.converse(**kwargs)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if attempt < BEDROCK_MAX_RETRIES and error_code == "ThrottlingException":
                time.sleep(2 ** min(attempt, 4))
                continue
            raise
    raise RuntimeError("converse_with_retry exhausted retries without returning")


def extract_response_text(response: dict) -> str:
    """Extract the first text block from a Bedrock converse response."""
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        if "text" in block:
            return (block["text"] or "").strip()
    return ""
