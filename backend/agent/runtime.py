"""Agent runtime: run_chat loop and tool execution. Returns (message, bpmn_xml, tools_used)."""
import json
import logging
import re

from groq import Groq

from config import GROQ_KEY, MAX_TOOL_ROUNDS
from graph_store import get_bpmn_xml, get_graph_summary
from agent.prompt import SYSTEM_PROMPT
from agent.tools import TOOLS, run_tool

logger = logging.getLogger("consularis.agent")


def _sanitize_reply(text: str) -> str:
    if not text or not text.strip():
        return text
    text = re.sub(r"<function\s*\([^)]*\)[^<]*</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>.*?</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[a-z_]+\s*\([^)]*\)[^>]*>", "", text, flags=re.IGNORECASE)
    return text.strip() or text


def run_chat(session_id: str, messages: list[dict], max_rounds: int | None = None) -> tuple[str, str, bool]:
    """
    Run the agent: Groq with tools until no more tool_calls.
    Returns (final_message, updated_bpmn_xml, tools_used).
    """
    if max_rounds is None:
        max_rounds = MAX_TOOL_ROUNDS
    tools_used = False

    if not GROQ_KEY or GROQ_KEY == "missing":
        return (
            "I cannot run yet: GROQ_KEY is not set. Put your key in backend/.env (see backend/env.example) and restart.",
            get_bpmn_xml(session_id),
            False,
        )

    client = Groq(api_key=GROQ_KEY)
    graph_context = "Current steps (use these IDs only): " + get_graph_summary(session_id)

    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + graph_context},
        *messages,
    ]

    final_message = ""
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=full_messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=1024,
        )
        choice = response.choices[0]
        if not choice.message.content and not getattr(choice.message, "tool_calls", None):
            break
        if choice.message.content:
            final_message = choice.message.content.strip()
        tool_calls = getattr(choice.message, "tool_calls", None) or []
        if not tool_calls:
            break

        tools_used = True
        tool_names = [getattr(tc.function, "name", "?") for tc in tool_calls]
        logger.info("[AGENT] session_id=%s invoking %d tool(s): %s", session_id, len(tool_calls), ", ".join(tool_names))

        msg = choice.message
        as_dict = {"role": "assistant", "content": msg.content or None}
        as_dict["tool_calls"] = [
            {"id": tc.id, "type": getattr(tc, "type", "function"), "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
            for tc in tool_calls
        ]
        full_messages.append(as_dict)

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
                logger.warning("[AGENT] session_id=%s tool=%s invalid JSON arguments, using {}", session_id, name)
            result = run_tool(session_id, name, args)
            full_messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result})
        logger.info("[AGENT] session_id=%s round complete, tools_used=True", session_id)

    if not final_message and full_messages and full_messages[-1].get("role") == "tool":
        final_message = "I have applied the changes. The graph has been updated."
    if not final_message:
        final_message = "I did not quite understand. Please repeat: which step (e.g. P1.2) and what would you like to change?"

    final_message = _sanitize_reply(final_message)
    return final_message, get_bpmn_xml(session_id), tools_used
