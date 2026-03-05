"""Automation analyzer: read-only LLM that analyzes the process graph for automation opportunities.

Uses the same Nova/Bedrock stack as Aurelius but no tools; single system + user message, one reply.
Distinct character (e.g. Automation Advisor) so it's clear this is not Aurelius.
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
    NOVA_MODEL_ID,
)
from graph.store import get_full_graph_summary_for_analysis

logger = logging.getLogger("consularis.agent")

ANALYZER_SYSTEM_PROMPT = """You are the Automation Advisor for Consularis. Your role is to analyze process graphs and recommend where automation can help.

You will receive the full process graph summary for a workspace: processes, steps (with names, actors, durations, costs, error rates, automation potential, and automation notes). Use this to:

1. **Identify automation opportunities**: List processes or steps that are good candidates for automation. Prefer steps marked high or medium automation potential and use the automation_notes when present to explain why.

2. **Suggest integration tools**: For high-value or high-potential steps, suggest concrete tools by name with a one-line rationale. Examples: n8n (workflow automation, self-hosted), Zapier (no-code app connections), Make (Integromat), Microsoft Power Automate (enterprise workflows), UiPath or other RPA tools for repetitive UI tasks. Match suggestions to the automation_notes where possible (e.g. "E-prescribing, CDS" might suggest EHR integrations or n8n workflows).

3. **Close with a CTA**: In one short paragraph, say that the user can **book an appointment with Consularis** to get help implementing automation. Mention that they can enter their email on this page to request an appointment.

Output a single markdown reply: clear sections (e.g. Automation opportunities, Suggested tools, Next steps). Be concise and actionable."""

USER_MESSAGE = "Analyze the process graph above for automation opportunities. List concrete opportunities with step/process names where useful, suggest integration tools (e.g. n8n, Zapier, Make, Power Automate) with a brief rationale for each, and end with a short note that the user can book an appointment with Consularis to get the process automated by entering their email on this page."


def _get_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    cfg = BotoConfig(read_timeout=BEDROCK_TIMEOUT, retries={"max_attempts": BEDROCK_MAX_RETRIES})
    return boto3.client("bedrock-runtime", config=cfg, **kwargs)


def run_analysis(session_id: str) -> str:
    """Run the automation analyzer on the session's full graph. Returns markdown text or an error message."""
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return (
            "Automation analysis is not available: AWS credentials are not set. "
            "Configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in backend/.env to enable it."
        )

    try:
        graph_summary = get_full_graph_summary_for_analysis(session_id)
    except Exception as e:
        logger.exception("[ANALYZER] get_full_graph_summary_for_analysis session_id=%s error=%s", session_id, e)
        return "Could not load the process graph. Please try again or return to the dashboard."

    system_block = [{"text": ANALYZER_SYSTEM_PROMPT + "\n\n--- Process graph ---\n\n" + graph_summary}]
    messages = [{"role": "user", "content": [{"text": USER_MESSAGE}]}]

    client = _get_client()
    for attempt in range(BEDROCK_MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=NOVA_MODEL_ID,
                system=system_block,
                messages=messages,
                inferenceConfig={"maxTokens": 2048, "temperature": 0.4},
            )
            break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if attempt < BEDROCK_MAX_RETRIES and error_code == "ThrottlingException":
                time.sleep(2 ** min(attempt, 4))
                continue
            logger.exception("[ANALYZER] session_id=%s Bedrock error: %s", session_id, e)
            return "The automation advisor is temporarily unavailable (AWS error). Please try again in a moment."
        except Exception as e:
            logger.exception("[ANALYZER] session_id=%s error: %s", session_id, e)
            return "The automation advisor is temporarily unavailable. Please try again in a moment."

    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        if "text" in block:
            return (block["text"] or "").strip()

    return "The automation advisor did not return a response. Please try again."
