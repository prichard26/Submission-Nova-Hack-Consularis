"""Agent runtime using Amazon Nova via AWS Bedrock Converse API.

Flow: Planner proposes with propose_plan → user sees plan + Apply plan button → user clicks Apply → Executor runs once (run_chat_confirm). Planner never executes; execution is one call on confirm.
"""
import json
import logging
import re
from dataclasses import dataclass
from uuid import uuid4

from botocore.exceptions import ClientError

from config import (
    BEDROCK_MODELS,
    MAX_RECENT_MESSAGES,
    MAX_TOOL_ROUNDS,
    NOVA_CHEAP_MODEL_ID,
    NOVA_MODEL_ID,
)
from agent.bedrock_client import (
    get_bedrock_client,
    check_bedrock_credentials,
    converse_with_retry,
    extract_response_text,
)
import db
from graph.store import get_full_graph, get_process_id_for_step
from graph.summary import generate_graph_summary
from agent.context import prepare_chat_context
from agent.prompt import EXECUTOR_SYSTEM_PROMPT, MULTIAGENT_CONTEXT, PLANNER_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT_CLAUDE
from agent.tools import PLANNER_TOOL_SCHEMAS, TOOL_SCHEMAS, TOOL_HANDLERS, run_tool
from graph.validation import validate_step_schema, validate_full_graph

logger = logging.getLogger("consularis.agent")

PLANNER_MAX_TOKENS = 8192
PLANNER_TEMPERATURE = 0.3
EXECUTOR_MAX_TOKENS = 2048
EXECUTOR_TEMPERATURE = 0.2
REPAIR_TEMPERATURE = 0.1
MAX_ERROR_MSG_LEN = 280
MIN_REPLY_LEN = 20
MIN_SANITIZED_LEN = 10
MAX_PLAN_VALIDATION_RETRIES = 2


@dataclass
class ChatResult:
    message: str
    include_graph: bool
    tools_used: bool
    tools_called: list[str]
    api_calls: int
    input_tokens: int
    output_tokens: int
    pending_plan: dict | None
    requires_confirmation: bool

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


def _parse_tool_args(args) -> dict:
    """Normalize tool input: parse JSON strings into dicts."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return args if isinstance(args, dict) else {}


# ---------------------------------------------------------------------------
# Message format translation
# ---------------------------------------------------------------------------

def _chat_history_to_bedrock(messages: list[dict]) -> list[dict]:
    """Convert the chat-history format (role/content dicts) to Bedrock message list.
    
    Bedrock only accepts alternating user/assistant. System is passed separately.
    We skip system messages (handled via system param) and collapse consecutive same-role entries.
    Assistant messages are sanitized to strip hallucinated plan/execution text and break the feedback loop.
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
        if bedrock_role == "assistant":
            content = _sanitize_reply(content)
            if not content or not content.strip():
                continue
        entry = {"role": bedrock_role, "content": [{"text": content}]}
        if out and out[-1]["role"] == bedrock_role:
            out[-1]["content"].append({"text": content})
        else:
            out.append(entry)
    return out


def _sanitize_reply(text: str) -> str:
    """Remove thinking tags and hallucinated plan/execution text (planner never executes tools)."""
    if not text or not text.strip():
        return text
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip "Done. Executed: tool1, tool2, ..." (planner never executes)
    text = re.sub(r"Done\.\s*Executed:.*?(?=\n|$)", "", text, flags=re.IGNORECASE | re.MULTILINE)
    # Strip "Planned tool steps (preview):" and everything after it (fake preview with no propose_plan)
    text = re.sub(
        r"\n?\s*Planned tool steps \(preview\):.*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip standalone "Click Apply plan..." / "Click **Apply plan** to execute..."
    text = re.sub(
        r"\n?\s*Click \*\*Apply plan\*\* to execute these steps\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\n?\s*Click Apply plan to execute these steps\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip() or text


def _is_protected_node_id(node_id: str) -> bool:
    nid = (node_id or "").strip()
    return nid.endswith("_start") or nid.endswith("_end")


def _validate_plan_steps(steps: list[dict], session_id: str | None = None) -> str | None:
    """Validate plan steps using Pydantic schema validation (Layer 1) plus cross-page edge check."""
    for idx, step in enumerate(steps, start=1):
        name = (step or {}).get("tool_name")
        args = (step or {}).get("arguments") or {}
        if not isinstance(name, str) or not name.strip():
            return f"Step {idx} is missing tool_name."
        if not isinstance(args, dict):
            return f"Step {idx} has non-object arguments."

        schema_err = validate_step_schema(name, args)
        if schema_err:
            return f"Step {idx} ({name}): {schema_err}"

        if name == "add_edge" and session_id:
            source = args.get("source") or args.get("from") or args.get("source_id") or args.get("from_id") or ""
            target = args.get("target") or args.get("to") or args.get("target_id") or args.get("to_id") or ""
            source, target = str(source).strip(), str(target).strip()
            if source and target:
                pid_src = get_process_id_for_step(session_id, source)
                pid_tgt = get_process_id_for_step(session_id, target)
                if pid_src is not None and pid_tgt is not None and pid_src != pid_tgt:
                    return (
                        f"Step {idx} (add_edge) connects nodes on different pages: {source} is in process {pid_src}, "
                        f"{target} is in process {pid_tgt}. Edges must be within the same process (same page)."
                    )
    return None


def _make_plan_result(
    reply: str,
    instructions: str,
    steps: list[dict] | None,
    api_calls: int,
    input_tokens: int,
    output_tokens: int,
) -> ChatResult:
    """Build a ChatResult for a validated plan ready for user confirmation."""
    plan_preview = _format_plan_preview(steps)
    final_message = reply or (instructions or "Apply the changes below.").replace("\n", "\n\n")
    if plan_preview:
        final_message = f"{final_message}\n\n{plan_preview}\n\nClick **Apply plan** to execute these steps."
    return ChatResult(
        message=final_message,
        include_graph=True,
        tools_used=False,
        tools_called=[],
        api_calls=api_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        pending_plan={"instructions": instructions, "steps": steps},
        requires_confirmation=True,
    )


def _make_error_result(message: str, api_calls: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> ChatResult:
    """Build a ChatResult for error/info responses with no plan."""
    return ChatResult(
        message=message,
        include_graph=True,
        tools_used=False,
        tools_called=[],
        api_calls=api_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        pending_plan=None,
        requires_confirmation=False,
    )


def _format_plan_preview(steps: list[dict] | None) -> str:
    if not steps:
        return ""
    lines = ["Planned tool steps (preview):"]
    for idx, step in enumerate(steps, start=1):
        name = (step or {}).get("tool_name") or "unknown_tool"
        arguments = (step or {}).get("arguments") or {}
        args_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        lines.append(f"{idx}. {name}({args_text})")
    return "\n".join(lines)


_MAX_STEP_RETRIES = 3


def _retry_failed_step_with_llm(
    client,
    session_id: str,
    step: dict,
    error_msg: str,
    full_graph_text: str,
    process_id: str | None,
    turn_id: str,
) -> tuple[dict | None, str | None, int, int, int]:
    """Ask the LLM to fix a failed tool step given the error. Returns (corrected_step, tool_result, api, in_tok, out_tok)."""
    total_api, total_in, total_out = 0, 0, 0
    for attempt in range(1, _MAX_STEP_RETRIES + 1):
        retry_prompt = (
            f"A tool call failed during plan execution.\n\n"
            f"**Failed step:**\n```json\n{json.dumps(step, ensure_ascii=False)}\n```\n\n"
            f"**Error:** {error_msg}\n\n"
            f"**Current graph state:**\n{full_graph_text}\n\n"
            f"Return ONLY a corrected tool call as a single JSON object with keys "
            f"\"tool_name\" (string) and \"arguments\" (object). No extra text."
        )
        retry_system = [{"text": MULTIAGENT_CONTEXT + "\n\n" + EXECUTOR_SYSTEM_PROMPT}]
        retry_messages = [{"role": "user", "content": [{"text": retry_prompt}]}]
        try:
            response = converse_with_retry(
                client,
                modelId=NOVA_CHEAP_MODEL_ID,
                system=retry_system,
                messages=retry_messages,
                inferenceConfig={"maxTokens": EXECUTOR_MAX_TOKENS, "temperature": REPAIR_TEMPERATURE},
            )
        except Exception as exc:
            logger.warning("[%s] RETRY_LLM_ERROR attempt=%s error=%s", turn_id, attempt, exc)
            total_api += 1
            continue

        total_api += 1
        total_in += response.get("usage", {}).get("inputTokens", 0) or 0
        total_out += response.get("usage", {}).get("outputTokens", 0) or 0
        raw_text = extract_response_text(response)
        corrected = _parse_corrected_step(raw_text)
        if not corrected:
            logger.warning("[%s] RETRY_PARSE_FAIL attempt=%s raw=%s", turn_id, attempt, raw_text[:500])
            error_msg = f"Could not parse corrected step from LLM response: {raw_text[:200]}"
            continue

        c_name = corrected.get("tool_name", "")
        c_args = corrected.get("arguments") or {}
        if c_name not in TOOL_HANDLERS:
            error_msg = f"LLM suggested unknown tool: {c_name}"
            continue

        logger.info("[%s] RETRY_STEP attempt=%s tool=%s", turn_id, attempt, c_name)
        result_str = run_tool(session_id, c_name, c_args, process_id=process_id, turn_id=turn_id)
        try:
            parsed = json.loads(result_str)
            ok = bool(parsed.get("ok", True))
        except Exception:
            ok = False
            parsed = {"error": result_str}

        if ok:
            logger.info("[%s] RETRY_SUCCESS attempt=%s tool=%s", turn_id, attempt, c_name)
            return corrected, result_str, total_api, total_in, total_out

        error_msg = parsed.get("error", "Unknown error on retried step")
        logger.info("[%s] RETRY_STILL_FAILED attempt=%s error=%s", turn_id, attempt, error_msg)

    return None, None, total_api, total_in, total_out


def _parse_corrected_step(text: str) -> dict | None:
    """Extract a {tool_name, arguments} JSON object from LLM text."""
    text = text.strip()
    # Try stripping markdown fences
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "tool_name" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    # Try finding a JSON object in the text
    match = re.search(r"\{[^{}]*\"tool_name\"[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _execute_plan_steps(
    session_id: str,
    steps: list[dict],
    process_id: str | None,
    turn_id: str,
    client=None,
    full_graph_text: str = "",
) -> tuple[str, list[str], int, int, int, bool]:
    """Execute planner-provided steps directly in Python. On failure, retries via LLM if client is provided."""
    tools_called: list[str] = []
    total_api, total_in, total_out = 0, 0, 0
    for idx, step in enumerate(steps, start=1):
        name = (step or {}).get("tool_name")
        args = (step or {}).get("arguments") or {}
        if not isinstance(name, str) or not name:
            return f"Step {idx} is invalid (missing tool_name).", tools_called, total_api, total_in, total_out, False
        if name not in TOOL_HANDLERS:
            hint = " Use add_node with type \"subprocess\" to add a subprocess." if name == "add_subprocess" else ""
            return f"Step {idx} uses unknown tool \"{name}\".{hint}", tools_called, total_api, total_in, total_out, False
        if not isinstance(args, dict):
            return f"Step {idx} has invalid arguments for {name}.", tools_called, total_api, total_in, total_out, False
        if name == "delete_node":
            node_id = (args.get("id") or args.get("node_id") or "").strip()
            if _is_protected_node_id(node_id):
                logger.warning("[%s] PLAN_REJECTED protected_node_delete node_id=%s", turn_id, node_id)
                return (
                    f"Plan rejected at step {idx}: cannot delete protected start/end node ({node_id}).",
                    tools_called, total_api, total_in, total_out, False,
                )
        logger.info("[%s] EXECUTE_STEP %s/%s tool=%s", turn_id, idx, len(steps), name)
        result = run_tool(session_id, name, args, process_id=process_id, turn_id=turn_id)
        tools_called.append(name)
        try:
            parsed = json.loads(result)
            ok = bool(parsed.get("ok", True))
        except Exception:
            ok = False
            parsed = {"error": f"Invalid tool JSON result for {name}"}
        logger.info("[%s] TOOL_RESULT tool=%s ok=%s", turn_id, name, ok)
        logger.debug("[%s] TOOL_RESULT_RAW tool=%s result=%s", turn_id, name, result[:2000])
        if not ok:
            error_msg = parsed.get("error", "Unknown error")
            if client:
                logger.info("[%s] STEP_FAILED_RETRYING step=%s/%s error=%s", turn_id, idx, len(steps), error_msg)
                graph_text = full_graph_text
                if not graph_text:
                    graph_data = get_full_graph(session_id)
                    graph_text = "**Full graph:**\n```json\n" + json.dumps(graph_data, separators=(",", ":"), ensure_ascii=False) + "\n```"
                corrected, _, r_api, r_in, r_out = _retry_failed_step_with_llm(
                    client, session_id, step, error_msg, graph_text, process_id, turn_id,
                )
                total_api += r_api
                total_in += r_in
                total_out += r_out
                if corrected:
                    tools_called.append(corrected.get("tool_name", name))
                    continue
            return f"Failed at step {idx} ({name}): {error_msg}", tools_called, total_api, total_in, total_out, False
    summary = "Executed: " + ", ".join(tools_called) if tools_called else "No tools were called."

    # Layer 3: Post-execution graph validation
    try:
        post_graph = get_full_graph(session_id)
        validation_result = validate_full_graph(post_graph)
        if not validation_result.ok:
            logger.warning("[%s] POST_EXEC_VALIDATION issues=%s", turn_id, validation_result.issues)
            summary += "\n\nNote: " + validation_result.summary()
    except Exception as exc:
        logger.warning("[%s] POST_EXEC_VALIDATION_ERROR error=%s", turn_id, exc)

    return summary, tools_called, total_api, total_in, total_out, True


def _run_executor_with_llm(
    client,
    session_id: str,
    instructions: str,
    steps: list[dict] | None,
    full_graph: str,
    process_id: str | None,
    turn_id: str,
) -> tuple[str, list[str], int, int, int, bool]:
    """Fallback executor path for plans without structured steps."""
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

    for _round in range(MAX_TOOL_ROUNDS):
        logger.info("[%s] EXECUTOR_ROUND %s/%s", turn_id, _round + 1, MAX_TOOL_ROUNDS)
        kwargs = {
            "modelId": NOVA_CHEAP_MODEL_ID,
            "system": executor_system,
            "messages": executor_messages,
            "inferenceConfig": {"maxTokens": EXECUTOR_MAX_TOKENS, "temperature": EXECUTOR_TEMPERATURE},
            "toolConfig": {"tools": BEDROCK_EXECUTOR_TOOLS},
        }
        try:
            response = client.converse(**kwargs)
        except Exception as e:
            logger.exception("[%s] EXECUTOR_ERROR session_id=%s error=%s", turn_id, session_id, e)
            return "Executor failed.", tools_called, total_api, total_in, total_out, False

        total_api += 1
        total_in += response.get("usage", {}).get("inputTokens", 0) or 0
        total_out += response.get("usage", {}).get("outputTokens", 0) or 0
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])
        executor_messages.append(output_message)

        text = extract_response_text(response)
        if text:
            executor_summary = text

        tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
        if not tool_use_blocks:
            break

        tool_results = []
        for block in tool_use_blocks:
            tu = block["toolUse"]
            name = tu["name"]
            tool_use_id = tu.get("toolUseId", "")
            args = _parse_tool_args(tu.get("input", {}))
            tools_called.append(name)
            result = run_tool(session_id, name, args, process_id=process_id, turn_id=turn_id)
            logger.debug("[%s] TOOL_RESULT_RAW tool=%s result=%s", turn_id, name, result[:2000])
            tool_results.append({
                "toolUseId": tool_use_id,
                "content": [{"text": result}],
                "status": "success",
            })
        executor_messages.append({"role": "user", "content": [{"toolResult": tr} for tr in tool_results]})

    if not executor_summary:
        executor_summary = "Executed: " + ", ".join(tools_called) if tools_called else "No tools were called."
    return executor_summary, tools_called, total_api, total_in, total_out, True


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


def _looks_like_plan_or_execution_text(text: str) -> bool:
    """True if reply looks like a plan preview or execution summary without an actual propose_plan tool call."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    plan_phrases = (
        "planned tool steps",
        "click apply plan",
        "click **apply plan**",
        "apply plan to execute",
        "executed:",
        "update_node(",
        "add_node(",
        "delete_node(",
        "rename_process(",
    )
    return any(p in t for p in plan_phrases)


def _run_planner_repair_pass(
    client,
    session_id: str,
    bedrock_messages: list[dict],
    system_block: list[dict],
    turn_id: str,
    model_id: str | None = None,
) -> tuple[dict | None, int, int, int]:
    """One strict repair pass: ask planner to respond with propose_plan only. Returns (response, api_calls, input_tokens, output_tokens)."""
    repair_instruction = (
        "Your previous reply described plan steps in text. "
        "Please call the propose_plan tool with those same steps so the user can click Apply plan. "
        "Include only the propose_plan tool call (and optional brief text)."
    )
    repair_messages = list(bedrock_messages)
    repair_messages.append({"role": "user", "content": [{"text": repair_instruction}]})
    try:
        response = converse_with_retry(
            client,
            modelId=model_id or NOVA_MODEL_ID,
            system=system_block,
            messages=repair_messages,
            inferenceConfig={"maxTokens": PLANNER_MAX_TOKENS // 2, "temperature": REPAIR_TEMPERATURE},
            toolConfig={"tools": BEDROCK_PLANNER_TOOLS},
        )
        api = 1
        ti = response.get("usage", {}).get("inputTokens", 0) or 0
        to = response.get("usage", {}).get("outputTokens", 0) or 0
        return response, api, ti, to
    except Exception as e:
        logger.warning("[%s] PLANNER_REPAIR_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return None, 1, 0, 0


def _run_planner_validation_retry(
    client,
    session_id: str,
    bedrock_messages: list[dict],
    system_block: list[dict],
    validation_error: str,
    turn_id: str,
    model_id: str | None = None,
) -> tuple[dict | None, int, int, int]:
    """Ask the planner to propose a corrected plan after a validation failure. Returns (response, api_calls, input_tokens, output_tokens)."""
    retry_instruction = (
        "Your proposed plan was rejected because it contained an invalid step.\n\n"
        f"{validation_error}\n\n"
        "Please propose a corrected plan by calling propose_plan with valid steps. "
        "Allowed tools: add_node, delete_node, update_node, rename_process, add_edge, delete_edge, update_edge. "
        "Start/end nodes (_start/_end) are protected and permanent. "
        "To add a subprocess, use add_node with type \"subprocess\" (the start/end page is created automatically). "
        "Edges connect nodes within the same page only."
    )
    retry_messages = list(bedrock_messages)
    retry_messages.append({"role": "user", "content": [{"text": retry_instruction}]})
    try:
        response = converse_with_retry(
            client,
            modelId=model_id or NOVA_MODEL_ID,
            system=system_block,
            messages=retry_messages,
            inferenceConfig={"maxTokens": PLANNER_MAX_TOKENS, "temperature": EXECUTOR_TEMPERATURE},
            toolConfig={"tools": BEDROCK_PLANNER_TOOLS},
        )
        api = 1
        ti = response.get("usage", {}).get("inputTokens", 0) or 0
        to = response.get("usage", {}).get("outputTokens", 0) or 0
        return response, api, ti, to
    except Exception as e:
        logger.warning("[%s] PLANNER_VALIDATION_RETRY_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return None, 1, 0, 0


# ---------------------------------------------------------------------------
# Plan extraction and validation helpers
# ---------------------------------------------------------------------------

def _extract_plan_from_response(response: dict) -> tuple[str, list[dict] | None] | None:
    """Extract (instructions, steps) from a propose_plan tool call in a Bedrock response. Returns None if no propose_plan found."""
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
    plan_block = next((b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"), None)
    if plan_block is None:
        return None
    tu = plan_block["toolUse"]
    args = _parse_tool_args(tu.get("input", {}))
    instructions = args.get("instructions", "") or "Apply the changes discussed."
    steps = args.get("steps")
    if not isinstance(steps, list):
        steps = None
    return instructions, steps


def _validate_and_store_plan(
    client,
    session_id: str,
    process_id: str | None,
    instructions: str,
    steps: list[dict],
    reply_text: str,
    bedrock_messages: list[dict],
    system_block: list[dict],
    model_id: str,
    turn_id: str,
    api_calls: int,
    input_tokens: int,
    output_tokens: int,
) -> ChatResult:
    """Validate plan steps, retry if invalid, store and return a ChatResult."""
    validation_error = _validate_plan_steps(steps, session_id)
    for retry_n in range(1, MAX_PLAN_VALIDATION_RETRIES + 1):
        if not validation_error:
            break
        logger.warning("[%s] PLAN_INVALID session_id=%s retry=%s/%s error=%s", turn_id, session_id, retry_n, MAX_PLAN_VALIDATION_RETRIES, validation_error)
        retry_response, retry_api, retry_in, retry_out = _run_planner_validation_retry(
            client, session_id, bedrock_messages, system_block, validation_error, turn_id, model_id=model_id
        )
        api_calls += retry_api
        input_tokens += retry_in
        output_tokens += retry_out
        if not retry_response:
            break
        extracted = _extract_plan_from_response(retry_response)
        if not extracted:
            break
        instructions, steps = extracted[0], extracted[1]
        if not isinstance(steps, list):
            break
        reply_text = _sanitize_reply(extract_response_text(retry_response)) or reply_text
        validation_error = _validate_plan_steps(steps, session_id)

    if validation_error:
        return _make_error_result(
            "The proposed plan contained an invalid step and I could not correct it automatically.\n\n"
            f"{validation_error}\n\n"
            "Start/end nodes are protected and permanent. Please rephrase your request (e.g. add or update steps, or restructure the flow).",
            api_calls, input_tokens, output_tokens,
        )

    stored_plan = {"instructions": instructions, "steps": steps, "process_id": process_id}
    db.upsert_pending_plan(session_id, stored_plan)
    logger.info("[%s] PLAN_STORED session_id=%s steps=%s", turn_id, session_id, len(steps) if steps else 0)
    reply = reply_text if (reply_text and len(reply_text.strip()) >= MIN_REPLY_LEN) else (instructions or "Apply the changes below.").replace("\n", "\n\n")
    return _make_plan_result(reply, instructions, steps, api_calls, input_tokens, output_tokens)


def _handle_proposed_plan(
    client,
    session_id: str,
    process_id: str | None,
    propose_plan_block: dict,
    planner_reply: str,
    bedrock_messages: list[dict],
    system_block: list[dict],
    model_id: str,
    turn_id: str,
    api_calls: int,
    input_tokens: int,
    output_tokens: int,
) -> ChatResult:
    """Handle a propose_plan tool call from the planner response."""
    tu = propose_plan_block["toolUse"]
    args = _parse_tool_args(tu.get("input", {}))
    instructions = args.get("instructions", "") or "Apply the changes discussed."
    steps = args.get("steps")
    if not isinstance(steps, list):
        steps = None

    if isinstance(steps, list):
        reply_text = _sanitize_reply(planner_reply) if planner_reply else ""
        return _validate_and_store_plan(
            client, session_id, process_id, instructions, steps, reply_text,
            bedrock_messages, system_block, model_id, turn_id,
            api_calls, input_tokens, output_tokens,
        )

    stored_plan = {"instructions": instructions, "steps": steps, "process_id": process_id}
    db.upsert_pending_plan(session_id, stored_plan)
    logger.info("[%s] PLAN_STORED session_id=%s steps=None", turn_id, session_id)
    reply = _sanitize_reply(planner_reply) if planner_reply else ""
    if not reply or len(reply.strip()) < MIN_REPLY_LEN:
        reply = (instructions or "Apply the changes below.").replace("\n", "\n\n")
    return _make_plan_result(reply, instructions, steps, api_calls, input_tokens, output_tokens)


def _handle_repair_pass(
    client,
    session_id: str,
    process_id: str | None,
    bedrock_messages: list[dict],
    system_block: list[dict],
    model_id: str,
    turn_id: str,
    api_calls: int,
    input_tokens: int,
    output_tokens: int,
) -> ChatResult | None:
    """Try to repair a hallucinated plan text into an actual propose_plan tool call. Returns ChatResult on success, None on failure."""
    logger.info("[%s] PLANNER_GUARD plan_text_without_tool running repair", turn_id)
    repair_response, repair_api, repair_in, repair_out = _run_planner_repair_pass(
        client, session_id, bedrock_messages, system_block, turn_id, model_id=model_id
    )
    api_calls += repair_api
    input_tokens += repair_in
    output_tokens += repair_out
    if not repair_response:
        return None

    extracted = _extract_plan_from_response(repair_response)
    if not extracted:
        return None
    instructions, steps = extracted
    if not isinstance(steps, list):
        return None

    reply_text = _sanitize_reply(extract_response_text(repair_response)) or ""
    return _validate_and_store_plan(
        client, session_id, process_id, instructions, steps, reply_text,
        bedrock_messages, system_block, model_id, turn_id,
        api_calls, input_tokens, output_tokens,
    )


# ---------------------------------------------------------------------------
# Multi-agent: Planner → (optional Executor) → Planner final reply
# ---------------------------------------------------------------------------

def _resolve_model_id(model_id: str | None) -> str:
    """Validate and resolve the model ID. Falls back to NOVA_MODEL_ID if not provided or invalid."""
    if model_id and model_id in BEDROCK_MODELS:
        return model_id
    return NOVA_MODEL_ID


def _get_planner_prompt(model_id: str) -> str:
    """Select the planner prompt based on model family."""
    model_info = BEDROCK_MODELS.get(model_id, {})
    family = model_info.get("family", "")
    if family == "claude" or "claude" in model_id.lower() or "anthropic" in model_id.lower():
        return PLANNER_SYSTEM_PROMPT_CLAUDE
    return PLANNER_SYSTEM_PROMPT


def run_chat(
    session_id: str,
    messages: list[dict],
    process_id: str | None = None,
    model_id: str | None = None,
) -> ChatResult:
    """Planner proposes and talks to user. If it calls propose_plan we store the plan and return requires_confirmation."""
    turn_id = uuid4().hex[:8]
    resolved_model = _resolve_model_id(model_id)
    logger.info("[%s] CHAT_TURN_START session_id=%s process_id=%s model=%s", turn_id, session_id, process_id, resolved_model)

    # If there is a pending plan and the user's last message is affirmative, run executor (same as clicking Apply).
    last_content = _last_user_message_content(messages)
    if db.get_pending_plan(session_id) and _is_affirmative(last_content):
        result = _run_chat_confirm_internal(session_id, process_id=process_id, turn_id=turn_id)
        if result is not None:
            return result

    # No affirmative confirmation: clear any previous pending plan and run planner.
    db.delete_pending_plan(session_id)

    cred_err = check_bedrock_credentials()
    if cred_err:
        return _make_error_result(f"I cannot run yet: {cred_err}")

    client = get_bedrock_client()
    full_graph_data = get_full_graph(session_id)
    graph_summary_text = generate_graph_summary(full_graph_data)
    graph_context = graph_summary_text + "\n\n**Full graph (all processes, nodes, edges):**\n```json\n" + json.dumps(full_graph_data, separators=(",", ":"), ensure_ascii=False) + "\n```"
    planner_prompt = _get_planner_prompt(resolved_model)
    system_block = [{"text": MULTIAGENT_CONTEXT + "\n\n" + planner_prompt + "\n\n" + graph_context}]
    summary_text, recent_msgs = prepare_chat_context(client, session_id, messages, MAX_RECENT_MESSAGES)
    if summary_text:
        system_block[0]["text"] += "\n\n**Conversation so far (summary):**\n" + summary_text
    bedrock_messages = _chat_history_to_bedrock(recent_msgs)
    # Bedrock Converse requires the conversation to start with a user message.
    while bedrock_messages and bedrock_messages[0].get("role") != "user":
        bedrock_messages = bedrock_messages[1:]
    kwargs = {
        "modelId": resolved_model,
        "system": system_block,
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": PLANNER_MAX_TOKENS, "temperature": PLANNER_TEMPERATURE},
        "toolConfig": {"tools": BEDROCK_PLANNER_TOOLS},
    }
    logger.info(
        "[%s] PLANNER_REQUEST session_id=%s model=%s messages=%s summary_used=%s",
        turn_id,
        session_id,
        resolved_model,
        len(bedrock_messages),
        bool(summary_text),
    )
    logger.debug("[%s] PLANNER_SYSTEM %s", turn_id, system_block[0]["text"][:2000])

    api_calls = 0
    input_tokens = 0
    output_tokens = 0
    planner_reply = ""

    try:
        response = converse_with_retry(client, **kwargs)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        err_msg = e.response.get("Error", {}).get("Message", str(e))
        logger.exception("[%s] PLANNER_ERROR session_id=%s code=%s error=%s", turn_id, session_id, code, e)
        user_msg = f"The assistant is temporarily unavailable (Bedrock: {code}). {err_msg}"
        if len(user_msg) > MAX_ERROR_MSG_LEN:
            user_msg = f"The assistant is temporarily unavailable (Bedrock: {code}). Please check model ID and region (e.g. eu. models need AWS_REGION in an EU region like eu-north-1)."
        return _make_error_result(user_msg, api_calls=1)
    except Exception as e:
        logger.exception("[%s] PLANNER_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return _make_error_result("The assistant is temporarily unavailable. Please try again in a moment.", api_calls=1)

    api_calls += 1
    input_tokens += response.get("usage", {}).get("inputTokens", 0) or 0
    output_tokens += response.get("usage", {}).get("outputTokens", 0) or 0
    output_message = response.get("output", {}).get("message", {})
    content_blocks = output_message.get("content", [])
    logger.info(
        "[%s] PLANNER_RESPONSE session_id=%s tokens_in=%s tokens_out=%s",
        turn_id,
        session_id,
        input_tokens,
        output_tokens,
    )
    logger.debug("[%s] PLANNER_RAW_CONTENT %s", turn_id, json.dumps(content_blocks, ensure_ascii=False)[:2000])

    planner_reply = extract_response_text(response) or planner_reply

    tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
    propose_plan_block = next((b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"), None)

    # Planner proposed a plan: validate, store, and return for user confirmation.
    if propose_plan_block is not None:
        return _handle_proposed_plan(
            client, session_id, process_id, propose_plan_block, planner_reply,
            bedrock_messages, system_block, resolved_model, turn_id,
            api_calls, input_tokens, output_tokens,
        )

    # No plan proposed: guard against hallucinated plan/execution text
    sanitized_reply = _sanitize_reply(planner_reply) if planner_reply else ""
    if _looks_like_plan_or_execution_text(sanitized_reply):
        result = _handle_repair_pass(
            client, session_id, process_id, bedrock_messages, system_block,
            resolved_model, turn_id, api_calls, input_tokens, output_tokens,
        )
        if result:
            return result
        return _make_error_result(
            "I was unable to create a valid plan for that change. Please try again or rephrase your request (e.g. 'Rename decision G1.1 to Verify complete?').",
            api_calls, input_tokens, output_tokens,
        )

    final_message = sanitized_reply if (sanitized_reply and len(sanitized_reply.strip()) >= MIN_SANITIZED_LEN) else "What would you like to do with the graph?"
    return _make_error_result(final_message, api_calls, input_tokens, output_tokens)


def run_chat_confirm(
    session_id: str,
    process_id: str | None = None,
) -> ChatResult | None:
    return _run_chat_confirm_internal(session_id, process_id=process_id, turn_id=uuid4().hex[:8])


def _run_chat_confirm_internal(
    session_id: str,
    process_id: str | None,
    turn_id: str,
) -> ChatResult | None:
    """User clicked Apply plan: execute stored plan. Returns ChatResult, or None if no pending plan."""
    plan = db.pop_pending_plan(session_id)
    if not plan:
        return None
    logger.info("[%s] PLAN_EXECUTING session_id=%s", turn_id, session_id)
    if check_bedrock_credentials():
        db.upsert_pending_plan(session_id, plan)
        return None
    client = get_bedrock_client()
    full_graph_data = get_full_graph(session_id)
    full_graph = "**Full graph:**\n```json\n" + json.dumps(full_graph_data, separators=(",", ":"), ensure_ascii=False) + "\n```"
    instructions = plan.get("instructions", "") or "Apply the changes discussed."
    steps = plan.get("steps")
    pid = plan.get("process_id") or process_id
    logger.info("[%s] PLAN_DETAILS session_id=%s instructions_len=%s steps=%s", turn_id, session_id, len(instructions), len(steps) if isinstance(steps, list) else 0)
    if isinstance(steps, list):
        executor_summary, tools_called, api_calls, input_tokens, output_tokens, execution_ok = _execute_plan_steps(
            session_id,
            steps,
            pid,
            turn_id,
            client=client,
            full_graph_text=full_graph,
        )
    else:
        logger.info("[%s] EXECUTOR_FALLBACK reason=no_structured_steps", turn_id)
        executor_summary, tools_called, api_calls, input_tokens, output_tokens, execution_ok = _run_executor_with_llm(
            client,
            session_id,
            instructions,
            steps,
            full_graph,
            pid,
            turn_id,
        )
    final_message = ("Done. " if execution_ok else "I could not apply this plan. ") + executor_summary
    return ChatResult(
        message=final_message,
        include_graph=True,
        tools_used=True,
        tools_called=tools_called,
        api_calls=api_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        pending_plan=None,
        requires_confirmation=False,
    )
