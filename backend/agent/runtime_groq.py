"""Agent runtime: single Groq API call per turn; execute any tool_calls once, no follow-up round."""
import json
import logging
import re
import time

from groq import Groq

from config import GROQ_KEY, GROQ_TIMEOUT, GROQ_MAX_RETRIES
from graph.store import get_graph_json, get_graph_summary
from agent.prompt import SYSTEM_PROMPT
from agent.tools import TOOLS, run_tool

logger = logging.getLogger("consularis.agent")

# When only these tools were called and the model returned no text, show the tool result as the reply.
READ_ONLY_TOOLS = frozenset({"get_graph_summary", "resolve_step"})


def _sanitize_reply(text: str) -> str:
    if not text or not text.strip():
        return text
    text = re.sub(r"<function\s*\([^)]*\)[^<]*</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>.*?</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[a-z_]+\s*\([^)]*\)[^>]*>", "", text, flags=re.IGNORECASE)
    return text.strip() or text


def run_chat(
    session_id: str,
    messages: list[dict],
    max_rounds: int | None = None,
    process_id: str | None = None,
) -> tuple[str, str, bool, list[str], int, int, int]:
    """
    One API call per user turn. Returns (final_message, graph_json, tools_used, tools_called_list, api_calls, input_tokens, output_tokens).
    """
    tools_used = False
    tools_called: list[str] = []
    _empty_usage = (0, 0, 0)

    if not GROQ_KEY or GROQ_KEY == "missing":
        return (
            "I cannot run yet: GROQ_KEY is not set. Put your key in backend/.env (see backend/env.example) and restart.",
            get_graph_json(session_id, process_id=process_id),
            False,
            [],
            *_empty_usage,
        )

    client = Groq(api_key=GROQ_KEY, timeout=GROQ_TIMEOUT)
    graph_context = get_graph_summary(session_id, process_id=process_id)

    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nGraph: " + graph_context},
        *messages,
    ]

    final_message = ""
    for attempt in range(GROQ_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=full_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1024,
            )
            break
        except Exception as e:
            if attempt < GROQ_MAX_RETRIES:
                delay = 2 ** attempt
                logger.warning(
                    "[AGENT] session_id=%s Groq call failed (attempt %d/%d), retrying in %ds: %s",
                    session_id, attempt + 1, GROQ_MAX_RETRIES + 1, delay, e,
                )
                time.sleep(delay)
            else:
                logger.exception("[AGENT] session_id=%s Groq call failed after %d attempts", session_id, GROQ_MAX_RETRIES + 1)
                return (
                    "The assistant is temporarily unavailable (API error or timeout). Please try again in a moment.",
                    get_graph_json(session_id, process_id=process_id),
                    False,
                    [],
                    *_empty_usage,
                )

    choice = response.choices[0]
    if choice.message.content:
        final_message = choice.message.content.strip()
    tool_calls = getattr(choice.message, "tool_calls", None) or []

    last_tool_result = None
    if tool_calls:
        tools_used = True
        tool_names = [getattr(tc.function, "name", "?") for tc in tool_calls]
        tools_called.extend(tool_names)
        logger.info("[AGENT] session_id=%s invoking %d tool(s) (single round): %s", session_id, len(tool_calls), ", ".join(tool_names))
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
                logger.warning("[AGENT] session_id=%s tool=%s invalid JSON arguments, using {}", session_id, name)
            last_tool_result = run_tool(session_id, name, args, process_id=process_id)

    if not final_message and tools_used:
        if last_tool_result and tools_called and all(t in READ_ONLY_TOOLS for t in tools_called):
            final_message = last_tool_result
        else:
            final_message = "I have applied the changes. The graph has been updated."
    if not final_message:
        final_message = "I did not quite understand. Please say which step or phase you mean and what you would like to change."

    final_message = _sanitize_reply(final_message)
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None) or 0
    output_tokens = getattr(usage, "completion_tokens", None) or 0
    return final_message, get_graph_json(session_id, process_id=process_id), tools_used, tools_called, 1, input_tokens, output_tokens
