"""
Aurelius agent: Groq chat with tools. Personality + bullshit handling in the prompt.
"""
import os
import json
import re
from groq import Groq

from graph_store import (
    get_graph,
    get_node,
    update_node,
    add_node,
    delete_node,
    get_edges,
    update_edge,
    add_edge,
    delete_edge,
    validate_graph,
)

# Load key from environment. Set GROQ_KEY in backend/.env (copy from backend/env.example)
GROQ_KEY = os.getenv("GROQ_KEY")
if not GROQ_KEY:
    GROQ_KEY = os.getenv("GROQ_KEY", "missing")

SYSTEM_PROMPT = """You are Aurelius, a process consul in the style of ancient Rome. You help users refine their pharmacy medication process graph. You speak formally but helpfully, using occasional Latin flourishes (e.g. "Salve", "the Senate shall note") and phrases like "we shall", "excellent", "as you wish".

You have full powers over the graph. You may:
- Update steps: name, actor, duration_min, description, inputs, outputs, risks (use update_node).
- Add steps to a phase (add_node) or remove steps (delete_node). Removing a step also removes its edges.
- Add links between steps (add_edge), remove links (delete_edge), or change a link's label/condition (update_edge).
- Reconnect: to move a link from A→B to A→C, first delete_edge(A,B) then add_edge(A,C). Use get_edges or get_graph to see current connections.

RULES:
- You may ONLY modify the graph by using the tools provided. Never invent step IDs or edges; use only existing IDs from the graph (except when adding a new step, which gets an id from the phase).
- When the user asks to change something (duration, name, remove a link, add/remove a step, reconnect), you MUST call the corresponding tool. Do not only reply with "I have updated..." without calling the tool — the change will not happen otherwise.
- If the user wants to remove multiple steps or edges, call the appropriate tool once per item (e.g. delete_node for each step, delete_edge for each link).
- If the user's request is ambiguous, or you cannot identify which step (e.g. P1.2) or link they mean, do NOT call any tool. Ask briefly for clarification.
- If the user asks something unrelated to the pharmacy process graph, reply politely that you are here only to help refine the graph.
- After successful tool calls, confirm what you did in one short sentence.
- Keep replies concise (one to three sentences) unless the user asks for more.
- Never output function call syntax, tool names, or raw JSON in your reply. Reply only in natural language.
"""

# OpenAI-format tools for Groq (Groq uses same schema)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_graph",
            "description": "Get the full process graph (phases and steps). Use this to see current state before making changes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_node",
            "description": "Get one step by id (e.g. P1.2, P3.1).",
            "parameters": {
                "type": "object",
                "properties": {"node_id": {"type": "string", "description": "Step id, e.g. P1.2"}},
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a step's name, actor, duration_min, description, inputs, outputs, or risks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "updates": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "actor": {"type": "string"},
                            "duration_min": {"type": "string"},
                            "description": {"type": "string"},
                            "inputs": {"type": "array", "items": {"type": "string"}},
                            "outputs": {"type": "array", "items": {"type": "string"}},
                            "risks": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "required": ["node_id", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_node",
            "description": "Add a new step to a phase. Use when the user wants to add a step. phase_id is e.g. P1, P2, ... P7.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phase_id": {"type": "string"},
                    "step_data": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "actor": {"type": "string"},
                            "duration_min": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
                "required": ["phase_id", "step_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a step and all its incoming/outgoing edges. Use when the user wants to remove one or more steps (call once per step).",
            "parameters": {
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_edges",
            "description": "List edges. Optionally filter by source step id.",
            "parameters": {
                "type": "object",
                "properties": {"source_id": {"type": "string", "description": "Optional. If given, only edges from this step."}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_edge",
            "description": "Update an edge's label or condition. Edge is identified by source and target step ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "updates": {"type": "object", "properties": {"label": {"type": "string"}, "condition": {"type": "string"}}},
                },
                "required": ["source", "target", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Add a link between two steps. Use to connect steps or to reconnect (after removing an edge).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source step id, e.g. P1.1"},
                    "target": {"type": "string", "description": "Target step id, e.g. P1.2"},
                    "label": {"type": "string"},
                    "condition": {"type": "string"},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_edge",
            "description": "Remove a link between two steps. Use when the user wants to remove a connection, disconnect steps, or before reconnecting (remove old edge then add_edge for the new one).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source step id of the edge to remove"},
                    "target": {"type": "string", "description": "Target step id of the edge to remove"},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_graph",
            "description": "Check the graph for consistency (orphan edges, duplicate ids, etc.). Call after making several changes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _sanitize_reply(text: str) -> str:
    """Remove raw function/tool syntax so the user only sees natural language."""
    if not text or not text.strip():
        return text
    # Remove <function(name){...}</function> (no > before </function>)
    text = re.sub(r"<function\s*\([^)]*\)[^<]*</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove <function(...)>...</function> blocks
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>.*?</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function\s*\([^)]*\)[^>]*>\s*", "", text, flags=re.IGNORECASE)
    # Any remaining <function(...)...> without closing tag
    text = re.sub(r"<[a-z_]+\s*\([^)]*\)[^>]*>", "", text, flags=re.IGNORECASE)
    return text.strip() or text


def _edge_exists(graph: dict, source: str, target: str) -> bool:
    for c in graph.get("flow_connections", []):
        if c.get("from") == source and c.get("to") == target:
            return True
    return False


def try_apply_message_update(session_id: str, user_message: str) -> bool:
    """
    Fallback: if the LLM didn't use tool_calls, try to apply updates from the user message
    so the graph still updates. Returns True if we applied something.
    """
    if not user_message or not user_message.strip():
        return False
    graph = get_graph(session_id)
    step_ids = {s["id"] for phase in graph["phases"] for s in phase["steps"]}
    msg = user_message.strip()

    # Duration: "P1.1 duration to 15", "change P2.3 to 10 min", "set P1.1 to 20 minutes", "make P1.1 take 15 min"
    node_id, dur = None, None
    m = re.search(
        r"(P\d+\.\d+)\D*(?:duration\D*)?(?:to|:|=)?\s*(\d+)\s*(?:min|minutes?|minute)?",
        msg, re.IGNORECASE
    )
    if m:
        node_id, dur = m.group(1), m.group(2)
    if not node_id:
        m = re.search(
            r"(?:duration|durée)\s*(?:to|of|:|=)?\s*(\d+)\D*(P\d+\.\d+)",
            msg, re.IGNORECASE
        )
        if m:
            node_id, dur = m.group(2), m.group(1)
    # "P1.1 15", "P1.1 = 15", "step P1.1 15 min" (number immediately after or nearby)
    if not node_id:
        m = re.search(r"(?:step\s+)?(P\d+\.\d+)\s*[=:]\s*(\d+)\s*(?:min|minutes?)?", msg, re.IGNORECASE)
        if m:
            node_id, dur = m.group(1), m.group(2)
    if not node_id:
        m = re.search(r"(P\d+\.\d+)\D{0,20}(\d+)\s*(?:min|minutes?|minute)\b", msg, re.IGNORECASE)
        if m:
            node_id, dur = m.group(1), m.group(2)
    if node_id and node_id in step_ids and dur:
        update_node(session_id, node_id, {"duration_min": str(dur)})
        return True

    # Name: "rename P1.1 to ..." or "P1.1 name to ..."
    m = re.search(r"(P\d+\.\d+)\D*(?:name|title)\s*(?:to|:|=)\s*[\"']?([^\"'\n.]+)", msg, re.IGNORECASE)
    if m and m.group(1) in step_ids:
        update_node(session_id, m.group(1), {"name": m.group(2).strip()})
        return True

    # Remove edge: "remove link from P1.1 to P1.2", "delete edge P1.1 P1.2", "remove connection P1.1 to P1.2"
    src, tgt = None, None
    m = re.search(
        r"(?:remove|delete|disconnect)\s+(?:link|edge|connection)\s+(?:from\s+)?(P\d+\.\d+)\s+(?:to|->|-)\s*(P\d+\.\d+)",
        msg, re.IGNORECASE
    )
    if m:
        src, tgt = m.group(1), m.group(2)
    if not src:
        m = re.search(r"(?:remove|delete)\s+(?:link|edge)\s+(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)", msg, re.IGNORECASE)
        if m:
            src, tgt = m.group(1), m.group(2)
    if not src:
        m = re.search(r"(P\d+\.\d+)\s*(?:and|to|->|-)\s*(P\d+\.\d+)\s*(?:link|edge|connection)\s*(?:remove|delete)", msg, re.IGNORECASE)
        if m:
            src, tgt = m.group(1), m.group(2)
    if src and tgt and src in step_ids and tgt in step_ids and _edge_exists(graph, src, tgt):
        delete_edge(session_id, src, tgt)
        return True

    # Reconnect: "reconnect P1.1 from P1.2 to P1.3", "change link P1.1-P1.2 to P1.1-P1.3"
    m = re.search(
        r"reconnect\s+(P\d+\.\d+)\s+from\s+(P\d+\.\d+)\s+to\s+(P\d+\.\d+)",
        msg, re.IGNORECASE
    )
    if m:
        src, old_tgt, new_tgt = m.group(1), m.group(2), m.group(3)
        if src in step_ids and old_tgt in step_ids and new_tgt in step_ids and _edge_exists(graph, src, old_tgt):
            delete_edge(session_id, src, old_tgt)
            add_edge(session_id, src, new_tgt)
            return True
    m = re.search(r"(?:change|move)\s+link\s+(?:from\s+)?(P\d+\.\d+)[\s\-–—]+(P\d+\.\d+)\s+to\s+(P\d+\.\d+)[\s\-–—]*(P\d+\.\d+)?", msg, re.IGNORECASE)
    if m:
        a, b, c, d = m.group(1), m.group(2), m.group(3), m.group(4)
        if d:  # "P1.1-P1.2 to P1.1-P1.3" -> (a,b) to (c,d)
            if a == c and _edge_exists(graph, a, b) and d in step_ids:
                delete_edge(session_id, a, b)
                add_edge(session_id, a, d)
                return True
        elif _edge_exists(graph, a, b) and c in step_ids:  # "P1.1-P1.2 to P1.3" -> new target P1.3
            delete_edge(session_id, a, b)
            add_edge(session_id, a, c)
            return True

    # Remove one or more nodes: "remove step P1.1", "delete P1.1", "remove P1.1, P1.2 and P1.3"
    # Only if they didn't say "link/edge/connection" (that was handled above)
    if not re.search(r"(?:link|edge|connection)\s*(?:from|between)?", msg, re.IGNORECASE):
        node_ids_to_remove = re.findall(r"(P\d+\.\d+)", msg)
        remove_keywords = re.search(
            r"(?:remove|delete)\s+(?:step|node)s?\s*(?:P\d+\.\d+|\s|,|and)*",
            msg, re.IGNORECASE
        ) or re.search(
            r"(?:remove|delete)\s+(?:P\d+\.\d+(?:\s*,?\s*(?:and\s+)?)?)+",
            msg, re.IGNORECASE
        )
        if remove_keywords and node_ids_to_remove:
            removed = 0
            for nid in node_ids_to_remove:
                if nid in step_ids and delete_node(session_id, nid):
                    removed += 1
            if removed:
                return True

    return False


def _run_tool(session_id: str, name: str, arguments: dict) -> str:
    try:
        if name == "get_graph":
            out = get_graph(session_id)
            return json.dumps(out, indent=2)
        if name == "get_node":
            n = get_node(session_id, arguments["node_id"])
            return json.dumps(n) if n else json.dumps({"error": "Node not found"})
        if name == "update_node":
            n = update_node(session_id, arguments["node_id"], arguments.get("updates", {}))
            return json.dumps(n) if n else json.dumps({"error": "Node not found"})
        if name == "add_node":
            n = add_node(session_id, arguments["phase_id"], arguments.get("step_data", {}))
            return json.dumps(n) if n else json.dumps({"error": "Phase not found or invalid"})
        if name == "delete_node":
            ok = delete_node(session_id, arguments["node_id"])
            return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Node not found"})
        if name == "get_edges":
            edges = get_edges(session_id, arguments.get("source_id"))
            return json.dumps(edges)
        if name == "update_edge":
            e = update_edge(
                session_id,
                arguments["source"],
                arguments["target"],
                arguments.get("updates", {}),
            )
            return json.dumps(e) if e else json.dumps({"error": "Edge not found"})
        if name == "add_edge":
            e = add_edge(
                session_id,
                arguments["source"],
                arguments["target"],
                arguments.get("label", ""),
                arguments.get("condition"),
            )
            return json.dumps(e) if e else json.dumps({"error": "Invalid source/target or edge exists"})
        if name == "delete_edge":
            ok = delete_edge(
                session_id,
                arguments["source"],
                arguments["target"],
            )
            return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Edge not found"})
        if name == "validate_graph":
            out = validate_graph(session_id)
            return json.dumps(out)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": "Unknown tool"})


def run_chat(session_id: str, messages: list[dict], max_rounds: int = 10) -> tuple[str, dict]:
    """
    Run the agent: append graph context, call Groq with tools, execute tool_calls until done.
    Returns (final_message, updated_graph).
    """
    if not GROQ_KEY or GROQ_KEY == "missing":
        return (
            "I cannot run yet: GROQ_KEY is not set. Put your key in backend/.env (see backend/env.example) and restart.",
            get_graph(session_id),
        )

    client = Groq(api_key=GROQ_KEY)

    # Build message list: system + optional graph summary + conversation
    graph = get_graph(session_id)
    summary_parts = []
    for phase in graph["phases"]:
        ids = [s["id"] for s in phase["steps"]]
        summary_parts.append(f"{phase['id']} {phase['name']}: {', '.join(ids)}")
    graph_context = "Current steps (use these IDs only): " + " | ".join(summary_parts)

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

        # Append assistant message in dict form (Groq/OpenAI format)
        msg = choice.message
        as_dict = {"role": "assistant", "content": msg.content or None}
        if tool_calls:
            as_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", "function"),
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
                }
                for tc in tool_calls
            ]
        full_messages.append(as_dict)

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(session_id, name, args)
            full_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": result,
            })

    if not final_message and full_messages and full_messages[-1].get("role") == "tool":
        final_message = "I have applied the changes. The graph has been updated."
    if not final_message:
        final_message = "I did not quite understand. Please repeat: which step (e.g. P1.2) and what would you like to change?"

    final_message = _sanitize_reply(final_message)
    return final_message, get_graph(session_id)
