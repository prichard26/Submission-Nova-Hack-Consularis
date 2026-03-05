"""Agent runtime using Amazon Nova via AWS Bedrock Converse API.

Multi-agent flow: Planner (top) decides and talks to user; Executor (bottom) runs graph tools.
Same contract: (final_message, graph_json, tools_used, tools_called, api_calls, input_tokens, output_tokens).
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
from graph.store import get_full_graph_summary, get_graph_json
from agent.prompt import EXECUTOR_SYSTEM_PROMPT, MULTIAGENT_CONTEXT, PLANNER_SYSTEM_PROMPT
from agent.tools import PLANNER_TOOL_SCHEMAS, TOOL_SCHEMAS, run_tool

logger = logging.getLogger("consularis.agent")

READ_ONLY_TOOLS = frozenset()

# ---------------------------------------------------------------------------
# Helpers: translate OpenAI-style tool schemas → Bedrock toolConfig
# ---------------------------------------------------------------------------

def _build_bedrock_tools_from_schemas(schemas: list[dict]) -> list[dict]:
    """Convert OpenAI-style function schemas to Bedrock toolSpec list."""
    specs = []
    for schema in schemas:
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


BEDROCK_PLANNER_TOOLS = _build_bedrock_tools_from_schemas(PLANNER_TOOL_SCHEMAS)
BEDROCK_EXECUTOR_TOOLS = _build_bedrock_tools_from_schemas(TOOL_SCHEMAS)


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


def _run_executor(
    client,
    session_id: str,
    instructions: str,
    steps: list[dict] | None,
    full_graph: str,
    process_id: str | None,
) -> tuple[str, list[str], int, int, int]:
    """Run executor agent (multi-round): execute planner instructions with graph tools. Returns (summary, tools_called, api_calls, input_tokens, output_tokens)."""
    executor_system = [{"text": MULTIAGENT_CONTEXT + "\n\n" + EXECUTOR_SYSTEM_PROMPT + "\n\n" + full_graph}]
    body = "Execute the following.\n\n**Instructions:**\n" + instructions
    if steps:
        body += "\n\n**Suggested steps (execute or adapt using the graph):**\n" + json.dumps(steps, indent=2)
    executor_messages: list[dict] = [{"role": "user", "content": [{"text": body}]}]
    tools_called: list[str] = []
    total_api = 0
    total_in = 0
    total_out = 0
    executor_summary = ""

    max_executor_rounds = 5
    for _round in range(max_executor_rounds):
        kwargs = {
            "modelId": NOVA_MODEL_ID,
            "system": executor_system,
            "messages": executor_messages,
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.2},
            "toolConfig": {"tools": BEDROCK_EXECUTOR_TOOLS},
        }
        try:
            response = client.converse(**kwargs)
        except Exception as e:
            logger.exception("[AGENT][NOVA] executor session_id=%s error: %s", session_id, e)
            return "Executor failed.", tools_called, total_api, total_in, total_out

        total_api += 1
        total_in += response.get("usage", {}).get("inputTokens", 0) or 0
        total_out += response.get("usage", {}).get("outputTokens", 0) or 0
        output = response.get("output", {})
        output_message = output.get("message", {})
        content_blocks = output_message.get("content", [])
        executor_messages.append(output_message)

        for block in content_blocks:
            if "text" in block:
                executor_summary = block["text"].strip()

        tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
        if not tool_use_blocks:
            break

        tool_results = []
        for block in tool_use_blocks:
            tu = block["toolUse"]
            name = tu["name"]
            tool_use_id = tu.get("toolUseId", "")
            args = tu.get("input", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tools_called.append(name)
            result = run_tool(session_id, name, args, process_id=process_id)
            tool_results.append({
                "toolUseId": tool_use_id,
                "content": [{"text": result}],
                "status": "success",
            })
        executor_messages.append({"role": "user", "content": [{"toolResult": tr} for tr in tool_results]})

    if not executor_summary:
        executor_summary = "Executed: " + ", ".join(tools_called) if tools_called else "No tools were called."
    return executor_summary, tools_called, total_api, total_in, total_out


# ---------------------------------------------------------------------------
# Multi-agent: Planner → (optional Executor) → Planner final reply
# ---------------------------------------------------------------------------

def run_chat(
    session_id: str,
    messages: list[dict],
    max_rounds: int | None = None,
    process_id: str | None = None,
) -> tuple[str, str, bool, list[str], int, int, int]:
    """Planner decides and talks to user; when it calls request_execution, Executor runs graph tools; then Planner replies with summary. Returns (final_message, graph_json, tools_used, tools_called_list, api_calls, input_tokens, output_tokens)."""
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
    full_graph = get_full_graph_summary(session_id)
    system_block = [{"text": MULTIAGENT_CONTEXT + "\n\n" + PLANNER_SYSTEM_PROMPT + "\n\n" + full_graph}]
    bedrock_messages = _chat_history_to_bedrock(messages)
    kwargs = {
        "modelId": NOVA_MODEL_ID,
        "system": system_block,
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": 2048, "temperature": 0.3},
        "toolConfig": {"tools": BEDROCK_PLANNER_TOOLS},
    }

    api_calls = 0
    input_tokens = 0
    output_tokens = 0
    planner_reply = ""

    for attempt in range(BEDROCK_MAX_RETRIES + 1):
        try:
            response = client.converse(**kwargs)
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
                1,
                *_empty_usage,
            )
        except Exception as e:
            logger.exception("[AGENT][NOVA] session_id=%s error: %s", session_id, e)
            return (
                "The assistant is temporarily unavailable. Please try again in a moment.",
                get_graph_json(session_id, process_id=process_id),
                False,
                [],
                1,
                *_empty_usage,
            )

    api_calls += 1
    input_tokens += response.get("usage", {}).get("inputTokens", 0) or 0
    output_tokens += response.get("usage", {}).get("outputTokens", 0) or 0
    output_message = response.get("output", {}).get("message", {})
    content_blocks = output_message.get("content", [])

    for block in content_blocks:
        if "text" in block:
            planner_reply = block["text"].strip()

    tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
    request_execution_block = next((b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "request_execution"), None)

    if request_execution_block is None:
        final_message = _sanitize_reply(planner_reply) if planner_reply else "I didn't catch that. What would you like to do?"
        return final_message, get_graph_json(session_id, process_id=process_id), False, [], api_calls, input_tokens, output_tokens

    tu = request_execution_block["toolUse"]
    args = tu.get("input", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    instructions = args.get("instructions", "") or "Apply the changes discussed."
    steps = args.get("steps")
    if not isinstance(steps, list):
        steps = None

    logger.info("[AGENT][NOVA] session_id=%s running executor (instructions len=%s, steps=%s)", session_id, len(instructions), len(steps) if steps else 0)
    executor_summary, tools_called, exec_api, exec_in, exec_out = _run_executor(
        client, session_id, instructions, steps, full_graph, process_id
    )
    api_calls += exec_api
    input_tokens += exec_in
    output_tokens += exec_out
    tools_used = True

    # Second planner call: summarize execution for the user
    followup_messages = list(bedrock_messages)
    followup_messages.append(output_message)
    followup_messages.append({
        "role": "user",
        "content": [{"text": "Execution completed.\n\n**Results:** " + executor_summary + "\n\nReply to the user in a few sentences summarizing what was done. Do not call any tool."}],
    })
    kwargs_followup = {
        "modelId": NOVA_MODEL_ID,
        "system": system_block,
        "messages": followup_messages,
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.3},
    }
    try:
        response2 = client.converse(**kwargs_followup)
    except Exception as e:
        logger.exception("[AGENT][NOVA] planner follow-up session_id=%s error: %s", session_id, e)
        final_message = _sanitize_reply(planner_reply) + "\n\n" + executor_summary
        return final_message, get_graph_json(session_id, process_id=process_id), tools_used, tools_called, api_calls, input_tokens, output_tokens

    api_calls += 1
    input_tokens += response2.get("usage", {}).get("inputTokens", 0) or 0
    output_tokens += response2.get("usage", {}).get("outputTokens", 0) or 0
    content2 = response2.get("output", {}).get("message", {}).get("content", [])
    final_message = ""
    for block in content2:
        if "text" in block:
            final_message = block["text"].strip()
            break
    if not final_message:
        final_message = _sanitize_reply(planner_reply) + "\n\n" + executor_summary
    else:
        final_message = _sanitize_reply(final_message)
    return final_message, get_graph_json(session_id, process_id=process_id), tools_used, tools_called, api_calls, input_tokens, output_tokens
