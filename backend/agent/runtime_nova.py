"""Agent runtime using Amazon Nova via AWS Bedrock Converse API.

Flow: Planner proposes with propose_plan → user sees plan + Apply plan button → user clicks Apply → Executor runs once (run_chat_confirm). Planner never executes; execution is one call on confirm.
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
from graph.store import get_full_graph, get_graph_json
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
        body += "\n\n**Steps to execute (call these tools in this order with these arguments; ids only, process is inferred from ids):**\n" + json.dumps(steps, indent=2)
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
# Pending plan: when planner calls propose_plan we store it here; confirm endpoint runs executor.
_pending_plans: dict[str, dict] = {}  # session_id -> { instructions, steps, process_id }


def _is_affirmative(text: str) -> bool:
    """True if the user message is a short confirmation (apply / confirm / yes etc.)."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    affirmatives = frozenset({
        "apply", "confirm", "yes", "y", "ok", "okay", "do it", "go ahead", "sure", "proceed",
        "apply plan", "confirm plan", "looks good", "sounds good",
    })
    if t in affirmatives:
        return True
    if t.startswith("apply") or t.startswith("confirm"):
        return True
    return False


def _last_user_message_content(messages: list[dict]) -> str:
    """Last user message content, or empty string."""
    for m in reversed(messages):
        if m.get("role") == "user":
            return (m.get("content") or "").strip()
    return ""


# Multi-agent: Planner → (optional Executor) → Planner final reply
# ---------------------------------------------------------------------------

def run_chat(
    session_id: str,
    messages: list[dict],
    max_rounds: int | None = None,
    process_id: str | None = None,
) -> tuple[str, str, bool, list[str], int, int, int, dict | None, bool]:
    """Planner proposes and talks to user. If it calls propose_plan we store the plan and return requires_confirmation (user sees Apply plan button). Executor runs when user clicks Apply or types apply/confirm/yes. Returns (final_message, graph_json, tools_used, tools_called_list, api_calls, input_tokens, output_tokens, pending_plan, requires_confirmation)."""
    tools_used = False
    tools_called: list[str] = []
    _empty_usage = (0, 0, 0)
    pending_plan: dict | None = None
    requires_confirmation = False

    # If there is a pending plan and the user's last message is affirmative, run executor (same as clicking Apply).
    last_content = _last_user_message_content(messages)
    if _pending_plans.get(session_id) and _is_affirmative(last_content):
        result = run_chat_confirm(session_id, process_id)
        if result is not None:
            return result

    # No affirmative confirmation: clear any previous pending plan and run planner.
    _pending_plans.pop(session_id, None)

    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return (
            "I cannot run yet: AWS credentials are not set. "
            "Put AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in backend/.env (see env.example) and restart.",
            get_graph_json(session_id, process_id=process_id),
            False,
            [],
            *_empty_usage,
            None,
            False,
        )

    client = _get_client()
    full_graph_data = get_full_graph(session_id)
    full_graph_block = "**Full graph (all processes, nodes, edges):**\n```json\n" + json.dumps(full_graph_data, indent=2, ensure_ascii=False) + "\n```"
    system_block = [{"text": MULTIAGENT_CONTEXT + "\n\n" + PLANNER_SYSTEM_PROMPT + "\n\n" + full_graph_block}]
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
                None,
                False,
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
                None,
                False,
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
    propose_plan_block = next((b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"), None)

    # Planner proposed a plan: store it and return. Executor runs only when user clicks Apply plan (run_chat_confirm).
    if propose_plan_block is not None:
        tu = propose_plan_block["toolUse"]
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
        _pending_plans[session_id] = {
            "instructions": instructions,
            "steps": steps,
            "process_id": process_id,
        }
        reply = _sanitize_reply(planner_reply) if planner_reply else ""
        if not reply or len(reply.strip()) < 20:
            reply = (instructions or "Apply the changes below.").replace("\n", "\n\n")
        final_message = reply
        return (
            final_message,
            get_graph_json(session_id, process_id=process_id),
            False,
            [],
            api_calls,
            input_tokens,
            output_tokens,
            {"instructions": instructions, "steps": steps},
            True,
        )

    # No plan proposed: just return planner reply
    final_message = _sanitize_reply(planner_reply) if planner_reply else "What would you like to do with the graph?"
    return final_message, get_graph_json(session_id, process_id=process_id), False, [], api_calls, input_tokens, output_tokens, None, False


def run_chat_confirm(
    session_id: str,
    process_id: str | None = None,
) -> tuple[str, str, bool, list[str], int, int, int, None, bool] | None:
    """User clicked Apply plan: run the executor once with the stored plan. Returns same 9-tuple as run_chat, or None if no pending plan."""
    plan = _pending_plans.pop(session_id, None)
    if not plan:
        return None
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        _pending_plans[session_id] = plan  # restore so they can retry after setting creds
        return None
    client = _get_client()
    full_graph_data = get_full_graph(session_id)
    full_graph = "**Full graph:**\n```json\n" + json.dumps(full_graph_data, indent=2, ensure_ascii=False) + "\n```"
    instructions = plan.get("instructions", "") or "Apply the changes discussed."
    steps = plan.get("steps")
    pid = plan.get("process_id") or process_id
    logger.info("[AGENT][NOVA] session_id=%s confirm: running executor (instructions len=%s, steps=%s)", session_id, len(instructions), len(steps) if steps else 0)
    executor_summary, tools_called, api_calls, input_tokens, output_tokens = _run_executor(
        client, session_id, instructions, steps, full_graph, pid
    )
    final_message = "Done. " + executor_summary
    return (
        final_message,
        get_graph_json(session_id, process_id=pid),
        True,
        tools_called,
        api_calls,
        input_tokens,
        output_tokens,
        None,
        False,
    )
