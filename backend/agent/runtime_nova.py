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
from agent.context import prepare_chat_context
from agent.prompt import EXECUTOR_SYSTEM_PROMPT, MULTIAGENT_CONTEXT, PLANNER_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT_CLAUDE
from agent.tools import PLANNER_TOOL_SCHEMAS, TOOL_SCHEMAS, TOOL_HANDLERS, run_tool

logger = logging.getLogger("consularis.agent")


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
    for idx, step in enumerate(steps, start=1):
        name = (step or {}).get("tool_name")
        args = (step or {}).get("arguments") or {}
        if not isinstance(name, str) or not name.strip():
            return f"Step {idx} is missing tool_name."
        if not isinstance(args, dict):
            return f"Step {idx} has non-object arguments."
        if name in {"add_edge", "delete_edge", "update_edge"}:
            source = (
                args.get("source")
                or args.get("from")
                or args.get("source_id")
                or args.get("from_id")
                or ""
            )
            target = (
                args.get("target")
                or args.get("to")
                or args.get("target_id")
                or args.get("to_id")
                or ""
            )
            if not str(source).strip() or not str(target).strip():
                return f"Step {idx} ({name}) is missing required edge endpoints (source/target)."
            if name == "add_edge" and session_id and source and target:
                pid_src = get_process_id_for_step(session_id, str(source).strip())
                pid_tgt = get_process_id_for_step(session_id, str(target).strip())
                if pid_src is not None and pid_tgt is not None and pid_src != pid_tgt:
                    return (
                        f"Step {idx} (add_edge) connects nodes on different pages: {source} is in process {pid_src}, "
                        f"{target} is in process {pid_tgt}. Edges must be within the same process (same page)."
                    )
            if name == "update_edge" and not isinstance(args.get("updates"), dict):
                return f"Step {idx} (update_edge) requires an updates object."
        if name == "add_node":
            if not str(args.get("id") or "").strip():
                return f"Step {idx} (add_node) is missing id."
            node_type = str(args.get("type") or "").strip().lower()
            if not node_type:
                return f"Step {idx} (add_node) is missing type."
            if node_type in ("start", "end"):
                return (
                    f"Step {idx} (add_node): do not add start or end nodes. They are created automatically when you add a subprocess. "
                    "To add a new subprocess, only add the subprocess node (e.g. S8) and reconnect global edges; do not add S8_start, S8_end, or internal steps."
                )
        if name == "update_node":
            if not str(args.get("id") or args.get("step_id") or "").strip():
                return f"Step {idx} (update_node) is missing id."
            updates = args.get("updates")
            if not isinstance(updates, dict):
                return f"Step {idx} (update_node) requires an updates object (e.g. {{\"name\": \"...\"}})."
            if not updates:
                return f"Step {idx} (update_node) has empty updates; include at least one field (e.g. name, description)."
            if set(updates.keys()) == {"attributes"} and isinstance(updates.get("attributes"), dict):
                return (
                    f"Step {idx} (update_node) uses nested 'attributes'. "
                    "Use flat updates, e.g. {{\"name\": \"Verify complete?\"}} instead of {{\"attributes\": {{\"name\": \"...\"}}}}."
                )
        if name == "rename_process":
            if not str(args.get("id") or args.get("process_id") or "").strip():
                return f"Step {idx} (rename_process) is missing id."
            if not str(args.get("name") or "").strip():
                return f"Step {idx} (rename_process) is missing name."
        if name == "delete_node":
            node_id = (args.get("id") or args.get("node_id") or "").strip()
            if not node_id:
                return f"Step {idx} (delete_node) is missing id."
            if _is_protected_node_id(node_id):
                return f"Step {idx} tries to delete a protected node ({node_id})."
    return None


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


def _execute_plan_steps(
    session_id: str,
    steps: list[dict],
    process_id: str | None,
    turn_id: str,
) -> tuple[str, list[str], int, int, int, bool]:
    """Execute planner-provided steps directly in Python (no LLM round-trip)."""
    tools_called: list[str] = []
    for idx, step in enumerate(steps, start=1):
        name = (step or {}).get("tool_name")
        args = (step or {}).get("arguments") or {}
        if not isinstance(name, str) or not name:
            return f"Step {idx} is invalid (missing tool_name).", tools_called, 0, 0, 0, False
        if name not in TOOL_HANDLERS:
            hint = " Use add_node with type \"subprocess\" to add a subprocess." if name == "add_subprocess" else ""
            return f"Step {idx} uses unknown tool \"{name}\".{hint}", tools_called, 0, 0, 0, False
        if not isinstance(args, dict):
            return f"Step {idx} has invalid arguments for {name}.", tools_called, 0, 0, 0, False
        if name == "delete_node":
            node_id = (args.get("id") or args.get("node_id") or "").strip()
            if _is_protected_node_id(node_id):
                logger.warning("[%s] PLAN_REJECTED protected_node_delete node_id=%s", turn_id, node_id)
                return (
                    f"Plan rejected at step {idx}: cannot delete protected start/end node ({node_id}).",
                    tools_called,
                    0,
                    0,
                    0,
                    False,
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
            return f"Failed at step {idx} ({name}): {parsed.get('error', 'Unknown error')}", tools_called, 0, 0, 0, False
    summary = "Executed: " + ", ".join(tools_called) if tools_called else "No tools were called."
    return summary, tools_called, 0, 0, 0, True


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
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.2},
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
            modelId=NOVA_MODEL_ID,
            system=system_block,
            messages=repair_messages,
            inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
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
            modelId=NOVA_MODEL_ID,
            system=system_block,
            messages=retry_messages,
            inferenceConfig={"maxTokens": 8192, "temperature": 0.2},
            toolConfig={"tools": BEDROCK_PLANNER_TOOLS},
        )
        api = 1
        ti = response.get("usage", {}).get("inputTokens", 0) or 0
        to = response.get("usage", {}).get("outputTokens", 0) or 0
        return response, api, ti, to
    except Exception as e:
        logger.warning("[%s] PLANNER_VALIDATION_RETRY_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return None, 1, 0, 0


# Multi-agent: Planner → (optional Executor) → Planner final reply
# ---------------------------------------------------------------------------

def run_chat(
    session_id: str,
    messages: list[dict],
    process_id: str | None = None,
) -> ChatResult:
    """Planner proposes and talks to user. If it calls propose_plan we store the plan and return requires_confirmation."""
    turn_id = uuid4().hex[:8]
    logger.info("[%s] CHAT_TURN_START session_id=%s process_id=%s", turn_id, session_id, process_id)

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
        return ChatResult(
            message=f"I cannot run yet: {cred_err}",
            include_graph=True,
            tools_used=False,
            tools_called=[],
            api_calls=0,
            input_tokens=0,
            output_tokens=0,
            pending_plan=None,
            requires_confirmation=False,
        )

    client = get_bedrock_client()
    full_graph_data = get_full_graph(session_id)
    full_graph_block = "**Full graph (all processes, nodes, edges):**\n```json\n" + json.dumps(full_graph_data, separators=(",", ":"), ensure_ascii=False) + "\n```"
    planner_prompt = PLANNER_SYSTEM_PROMPT_CLAUDE if "claude" in NOVA_MODEL_ID.lower() or "anthropic" in NOVA_MODEL_ID.lower() else PLANNER_SYSTEM_PROMPT
    system_block = [{"text": MULTIAGENT_CONTEXT + "\n\n" + planner_prompt + "\n\n" + full_graph_block}]
    summary_text, recent_msgs = prepare_chat_context(client, session_id, messages, MAX_RECENT_MESSAGES)
    if summary_text:
        system_block[0]["text"] += "\n\n**Conversation so far (summary):**\n" + summary_text
    bedrock_messages = _chat_history_to_bedrock(recent_msgs)
    # Bedrock Converse requires the conversation to start with a user message.
    while bedrock_messages and bedrock_messages[0].get("role") != "user":
        bedrock_messages = bedrock_messages[1:]
    kwargs = {
        "modelId": NOVA_MODEL_ID,
        "system": system_block,
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": 8192, "temperature": 0.3},
        "toolConfig": {"tools": BEDROCK_PLANNER_TOOLS},
    }
    logger.info(
        "[%s] PLANNER_REQUEST session_id=%s model=%s messages=%s summary_used=%s",
        turn_id,
        session_id,
        NOVA_MODEL_ID,
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
        logger.exception("[%s] PLANNER_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return ChatResult(
            message="The assistant is temporarily unavailable (AWS Bedrock error). Please try again in a moment.",
            include_graph=True,
            tools_used=False,
            tools_called=[],
            api_calls=1,
            input_tokens=0,
            output_tokens=0,
            pending_plan=None,
            requires_confirmation=False,
        )
    except Exception as e:
        logger.exception("[%s] PLANNER_ERROR session_id=%s error=%s", turn_id, session_id, e)
        return ChatResult(
            message="The assistant is temporarily unavailable. Please try again in a moment.",
            include_graph=True,
            tools_used=False,
            tools_called=[],
            api_calls=1,
            input_tokens=0,
            output_tokens=0,
            pending_plan=None,
            requires_confirmation=False,
        )

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

    # Planner proposed a plan: store it and return. Executor runs only when user clicks Apply plan (run_chat_confirm).
    if propose_plan_block is not None:
        tu = propose_plan_block["toolUse"]
        args = _parse_tool_args(tu.get("input", {}))
        instructions = args.get("instructions", "") or "Apply the changes discussed."
        steps = args.get("steps")
        if not isinstance(steps, list):
            steps = None
        if isinstance(steps, list):
            validation_error = _validate_plan_steps(steps, session_id)
            if validation_error:
                logger.warning("[%s] PLAN_INVALID session_id=%s error=%s", turn_id, session_id, validation_error)
                # Auto-retry: ask planner to propose a corrected plan with validation feedback
                retry_response, retry_api, retry_in, retry_out = _run_planner_validation_retry(
                    client, session_id, bedrock_messages, system_block, validation_error, turn_id
                )
                api_calls += retry_api
                input_tokens += retry_in
                output_tokens += retry_out
                if retry_response:
                    content_blocks = retry_response.get("output", {}).get("message", {}).get("content", [])
                    tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
                    retry_plan_block = next(
                        (b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"),
                        None,
                    )
                    if retry_plan_block is not None:
                        tu = retry_plan_block["toolUse"]
                        args = _parse_tool_args(tu.get("input", {}))
                        instructions = args.get("instructions", "") or "Apply the changes discussed."
                        steps = args.get("steps")
                        if isinstance(steps, list):
                            retry_validation_error = _validate_plan_steps(steps, session_id)
                            if not retry_validation_error:
                                stored_plan = {
                                    "instructions": instructions,
                                    "steps": steps,
                                    "process_id": process_id,
                                }
                                db.upsert_pending_plan(session_id, stored_plan)
                                logger.info("[%s] PLAN_STORED after validation retry session_id=%s steps=%s", turn_id, session_id, len(steps))
                                reply = _sanitize_reply(extract_response_text(retry_response)) or (instructions or "Apply the changes below.").replace("\n", "\n\n")
                                plan_preview = _format_plan_preview(steps)
                                final_message = reply
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
                            logger.warning("[%s] PLAN_INVALID after retry session_id=%s error=%s", turn_id, session_id, retry_validation_error)
                            validation_error = retry_validation_error
                # Retry did not yield a valid plan: return error so user can rephrase
                return ChatResult(
                    message=(
                        "The proposed plan contained an invalid step and I could not correct it automatically.\n\n"
                        f"{validation_error}\n\n"
                        "Start/end nodes are protected and permanent. Please rephrase your request (e.g. add or update steps, or restructure the flow)."
                    ),
                    include_graph=True,
                    tools_used=False,
                    tools_called=[],
                    api_calls=api_calls,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    pending_plan=None,
                    requires_confirmation=False,
                )
        stored_plan = {
            "instructions": instructions,
            "steps": steps,
            "process_id": process_id,
        }
        db.upsert_pending_plan(session_id, stored_plan)
        logger.info("[%s] PLAN_STORED session_id=%s steps=%s", turn_id, session_id, len(steps) if steps else 0)
        reply = _sanitize_reply(planner_reply) if planner_reply else ""
        if not reply or len(reply.strip()) < 20:
            reply = (instructions or "Apply the changes below.").replace("\n", "\n\n")
        plan_preview = _format_plan_preview(steps)
        final_message = reply
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

    # No plan proposed: sanitize first, then guard against any remaining hallucinated plan/execution text
    sanitized_reply = _sanitize_reply(planner_reply) if planner_reply else ""
    if _looks_like_plan_or_execution_text(sanitized_reply):
        logger.info("[%s] PLANNER_GUARD plan_text_without_tool running repair", turn_id)
        repair_response, repair_api, repair_in, repair_out = _run_planner_repair_pass(
            client, session_id, bedrock_messages, system_block, turn_id
        )
        api_calls += repair_api
        input_tokens += repair_in
        output_tokens += repair_out
        if repair_response:
            content_blocks = repair_response.get("output", {}).get("message", {}).get("content", [])
            tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
            propose_plan_block = next(
                (b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"),
                None,
            )
            if propose_plan_block is not None:
                tu = propose_plan_block["toolUse"]
                args = _parse_tool_args(tu.get("input", {}))
                instructions = args.get("instructions", "") or "Apply the changes discussed."
                steps = args.get("steps")
                if not isinstance(steps, list):
                    steps = None
                if isinstance(steps, list):
                    validation_error = _validate_plan_steps(steps, session_id)
                    if validation_error:
                        logger.warning("[%s] PLAN_INVALID after repair session_id=%s error=%s", turn_id, session_id, validation_error)
                        repair_messages = list(bedrock_messages)
                        repair_messages.append({"role": "user", "content": [{"text": (
                            "Your previous reply described plan steps in text. "
                            "Please call the propose_plan tool with those same steps so the user can click Apply plan. "
                            "Include only the propose_plan tool call (and optional brief text)."
                        )}]})
                        retry_response, retry_api, retry_in, retry_out = _run_planner_validation_retry(
                            client, session_id, repair_messages, system_block, validation_error, turn_id
                        )
                        api_calls += retry_api
                        input_tokens += retry_in
                        output_tokens += retry_out
                        if retry_response:
                            content_blocks = retry_response.get("output", {}).get("message", {}).get("content", [])
                            tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
                            retry_plan_block = next(
                                (b for b in tool_use_blocks if b.get("toolUse", {}).get("name") == "propose_plan"),
                                None,
                            )
                            if retry_plan_block is not None:
                                tu = retry_plan_block["toolUse"]
                                args = _parse_tool_args(tu.get("input", {}))
                                instructions = args.get("instructions", "") or "Apply the changes discussed."
                                steps = args.get("steps")
                                if isinstance(steps, list):
                                    retry_validation_error = _validate_plan_steps(steps, session_id)
                                    if not retry_validation_error:
                                        stored_plan = {"instructions": instructions, "steps": steps, "process_id": process_id}
                                        db.upsert_pending_plan(session_id, stored_plan)
                                        logger.info("[%s] PLAN_STORED after repair+validation retry session_id=%s steps=%s", turn_id, session_id, len(steps))
                                        reply = _sanitize_reply(extract_response_text(retry_response)) or (instructions or "Apply the changes below.").replace("\n", "\n\n")
                                        plan_preview = _format_plan_preview(steps)
                                        final_message = f"{reply}\n\n{plan_preview}\n\nClick **Apply plan** to execute these steps." if plan_preview else f"{reply}\n\nClick **Apply plan** to execute these steps."
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
                    if not validation_error:
                        stored_plan = {"instructions": instructions, "steps": steps, "process_id": process_id}
                        db.upsert_pending_plan(session_id, stored_plan)
                        logger.info("[%s] PLAN_STORED after repair session_id=%s steps=%s", turn_id, session_id, len(steps) if steps else 0)
                        reply = _sanitize_reply(extract_response_text(repair_response)) or (instructions or "Apply the changes below.").replace("\n", "\n\n")
                        plan_preview = _format_plan_preview(steps)
                        final_message = f"{reply}\n\n{plan_preview}\n\nClick **Apply plan** to execute these steps." if plan_preview else f"{reply}\n\nClick **Apply plan** to execute these steps."
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
        # Repair did not yield a valid plan: return deterministic fallback (no fake preview)
        return ChatResult(
            message="I was unable to create a valid plan for that change. Please try again or rephrase your request (e.g. 'Rename decision G1.1 to Verify complete?').",
            include_graph=True,
            tools_used=False,
            tools_called=[],
            api_calls=api_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pending_plan=None,
            requires_confirmation=False,
        )

    # No plan and no hallucination markers left after sanitize: return sanitized reply (or fallback if empty)
    final_message = sanitized_reply if (sanitized_reply and len(sanitized_reply.strip()) >= 10) else "What would you like to do with the graph?"
    return ChatResult(
        message=final_message,
        include_graph=True,
        tools_used=False,
        tools_called=[],
        api_calls=api_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        pending_plan=None,
        requires_confirmation=False,
    )


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
