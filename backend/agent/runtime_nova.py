"""Agent runtime using Amazon Nova via AWS Bedrock Converse API.

Single API call per user turn: one request, execute any tool_calls once, no follow-up round.
Same contract as Groq: (final_message, graph_json, tools_used, tools_called).
"""
import json
import logging
import re
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
from graph.store import get_graph_json, get_graph_summary
from agent.prompt import SYSTEM_PROMPT
from agent.tools import TOOL_SCHEMAS, run_tool

logger = logging.getLogger("consularis.agent")

# When only these tools were called and the model returned no text, show the tool result as the reply.
READ_ONLY_TOOLS = frozenset({"get_graph_summary", "resolve_step"})

# ---------------------------------------------------------------------------
# Helpers: translate OpenAI-style tool schemas → Bedrock toolConfig
# ---------------------------------------------------------------------------

def _build_bedrock_tools() -> list[dict]:
    """Convert TOOL_SCHEMAS (OpenAI function-calling format) to Bedrock toolSpec list."""
    specs = []
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        params = fn.get("parameters", {})
        input_schema = {
            "type": "object",
            "properties": params.get("properties", {}),
            "required": params.get("required", []),
        }
        specs.append({
            "toolSpec": {
                "name": fn["name"],
                "description": fn["description"],
                "inputSchema": {"json": input_schema},
            }
        })
    return specs


BEDROCK_TOOLS = _build_bedrock_tools()


def _get_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    cfg = BotoConfig(read_timeout=BEDROCK_TIMEOUT, retries={"max_attempts": BEDROCK_MAX_RETRIES})
    return boto3.client("bedrock-runtime", config=cfg, **kwargs)


# ---------------------------------------------------------------------------
# Message format translation
# ---------------------------------------------------------------------------

def _chat_history_to_bedrock(messages: list[dict]) -> list[dict]:
    """Convert the chat-history format (role/content dicts) to Bedrock message list.
    
    Bedrock only accepts alternating user/assistant. System is passed separately.
    We skip system messages (handled via system param) and collapse consecutive same-role entries.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue
        bedrock_role = "assistant" if role == "assistant" else "user"
        if not content:
            continue
        entry = {"role": bedrock_role, "content": [{"text": content}]}
        if out and out[-1]["role"] == bedrock_role:
            out[-1]["content"].append({"text": content})
        else:
            out.append(entry)
    return out


def _sanitize_reply(text: str) -> str:
    if not text or not text.strip():
        return text
    text = re.sub(r"<function\s*\([^)]*\)[^<]*</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>.*?</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[a-z_]+\s*\([^)]*\)[^>]*>", "", text, flags=re.IGNORECASE)
    return text.strip() or text


# ---------------------------------------------------------------------------
# Single-round: one API call, execute tool_calls once, no follow-up
# ---------------------------------------------------------------------------

def run_chat(
    session_id: str,
    messages: list[dict],
    max_rounds: int | None = None,
    process_id: str | None = None,
) -> tuple[str, str, bool, list[str], int, int, int]:
    """One Bedrock Converse call per user turn. Returns (final_message, graph_json, tools_used, tools_called_list, api_calls, input_tokens, output_tokens)."""
    tools_used = False
    tools_called: list[str] = []
    _empty_usage = (0, 0, 0)

    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return (
            "I cannot run yet: AWS credentials are not set. "
            "Put AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in backend/.env (see env.example) and restart.",
            get_graph_json(session_id, process_id=process_id),
            False,
            [],
            *_empty_usage,
        )

    client = _get_client()
    graph_context = get_graph_summary(session_id, process_id=process_id)
    system_block = [{"text": SYSTEM_PROMPT + "\n\nGraph: " + graph_context}]
    bedrock_messages = _chat_history_to_bedrock(messages)
    tool_config = {"tools": BEDROCK_TOOLS}

    final_message = ""
    for attempt in range(BEDROCK_MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=NOVA_MODEL_ID,
                system=system_block,
                messages=bedrock_messages,
                toolConfig=tool_config,
                inferenceConfig={"maxTokens": 2048, "temperature": 0.3},
            )
            break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if attempt < BEDROCK_MAX_RETRIES and error_code == "ThrottlingException":
                time.sleep(2 ** min(attempt, 4))
                continue
            logger.exception("[AGENT][NOVA] session_id=%s Bedrock failed: %s", session_id, e)
            return (
                "The assistant is temporarily unavailable (AWS Bedrock error). Please try again in a moment.",
                get_graph_json(session_id, process_id=process_id),
                False,
                [],
                *_empty_usage,
            )
        except Exception as e:
            logger.exception("[AGENT][NOVA] session_id=%s error: %s", session_id, e)
            return (
                "The assistant is temporarily unavailable. Please try again in a moment.",
                get_graph_json(session_id, process_id=process_id),
                False,
                [],
                *_empty_usage,
            )

    output = response.get("output", {})
    output_message = output.get("message", {})
    content_blocks = output_message.get("content", [])

    for block in content_blocks:
        if "text" in block:
            final_message = block["text"].strip()

    last_tool_result = None
    tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
    if tool_use_blocks:
        tools_used = True
        tool_names = [b["toolUse"]["name"] for b in tool_use_blocks]
        tools_called.extend(tool_names)
        logger.info("[AGENT][NOVA] session_id=%s invoking %d tool(s) (single round): %s", session_id, len(tool_use_blocks), ", ".join(tool_names))
        for block in tool_use_blocks:
            tu = block["toolUse"]
            name = tu["name"]
            args = tu.get("input", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            last_tool_result = run_tool(session_id, name, args, process_id=process_id)

    if not final_message and tools_used:
        if last_tool_result and tools_called and all(t in READ_ONLY_TOOLS for t in tools_called):
            final_message = last_tool_result
        else:
            final_message = "I have applied the changes. The graph has been updated."
    if not final_message:
        final_message = "I did not quite understand. Please say which step or phase you mean and what you would like to change."

    final_message = _sanitize_reply(final_message)
    usage = response.get("usage", {})
    input_tokens = usage.get("inputTokens", 0) or 0
    output_tokens = usage.get("outputTokens", 0) or 0
    return final_message, get_graph_json(session_id, process_id=process_id), tools_used, tools_called, 1, input_tokens, output_tokens
