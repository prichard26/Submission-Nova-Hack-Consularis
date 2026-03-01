"""Fallback: apply graph updates from user message when the LLM did not use tools."""
import logging
import re
from typing import Callable

from graph_store import get_task_ids, get_edges, update_node, update_edge, delete_node, add_edge, delete_edge

logger = logging.getLogger("consularis.agent")

# Handler: (session_id, msg, step_ids) -> True if applied
FallbackHandler = Callable[[str, str, set[str]], bool]


def _edge_exists(session_id: str, source: str, target: str) -> bool:
    for c in get_edges(session_id):
        if c.get("from") == source and c.get("to") == target:
            return True
    return False


def _apply_duration(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Update step duration from patterns like 'P1.2 duration 5 min'."""
    node_id, dur = None, None
    for pattern in [
        r"(P\d+\.\d+)\D*(?:duration\D*)?(?:to|:|=)?\s*(\d+)\s*(?:min|minutes?|minute)?",
        r"(?:duration|durée)\s*(?:to|of|:|=)?\s*(\d+)\D*(P\d+\.\d+)",
        r"(?:step\s+)?(P\d+\.\d+)\s*[=:]\s*(\d+)\s*(?:min|minutes?)?",
        r"(P\d+\.\d+)\D{0,20}(\d+)\s*(?:min|minutes?|minute)\b",
    ]:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            g = m.groups()
            node_id = g[0] if g[0].startswith("P") else g[1]
            dur = g[1] if g[1].isdigit() else g[0]
            break
    if node_id and node_id in step_ids and dur:
        logger.info("[AGENT][FALLBACK] session_id=%s update_node duration node_id=%s duration_min=%s", session_id, node_id, dur)
        update_node(session_id, node_id, {"duration_min": str(dur)})
        return True
    return False


def _apply_name(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Rename step from patterns like 'P1.2 name to X'."""
    m = re.search(r"(P\d+\.\d+)\D*(?:name|title)\s*(?:to|:|=)\s*[\"']?([^\"'\n.]+)", msg, re.IGNORECASE)
    if m and m.group(1) in step_ids:
        logger.info("[AGENT][FALLBACK] session_id=%s update_node name node_id=%s name=%s", session_id, m.group(1), m.group(2).strip())
        update_node(session_id, m.group(1), {"name": m.group(2).strip()})
        return True
    return False


def _apply_remove_edge(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Remove link between two steps."""
    src, tgt = None, None
    for pattern in [
        r"(?:remove|delete|disconnect)\s+(?:link|edge|connection)\s+(?:from\s+)?(P\d+\.\d+)\s+(?:to|->|-)\s*(P\d+\.\d+)",
        r"(?:remove|delete)\s+(?:link|edge)\s+(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)",
        r"(P\d+\.\d+)\s*(?:and|to|->|-)\s*(P\d+\.\d+)\s*(?:link|edge|connection)\s*(?:remove|delete)",
    ]:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            src, tgt = m.group(1), m.group(2)
            break
    if src and tgt and src in step_ids and tgt in step_ids and _edge_exists(session_id, src, tgt):
        logger.info("[AGENT][FALLBACK] session_id=%s delete_edge source=%s target=%s", session_id, src, tgt)
        delete_edge(session_id, src, tgt)
        return True
    return False


def _apply_edge_label(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Change link label between two steps."""
    m = re.search(
        r"(?:change|rename|set)\s+(?:link|edge|connection)\s+(?:name|label)?\s*(?:between\s+)?(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)\s+(?:to|:|=)\s*[\"']?([^\"'\n]+)",
        msg, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"(?:link|edge)\s+(?:between\s+)?(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)\s+(?:to|:|=)\s*[\"']?([^\"'\n]+)",
            msg, re.IGNORECASE,
        )
    if m:
        src, tgt, label = m.group(1), m.group(2), m.group(3).strip()
        if src in step_ids and tgt in step_ids and _edge_exists(session_id, src, tgt) and label:
            logger.info("[AGENT][FALLBACK] session_id=%s update_edge label source=%s target=%s label=%s", session_id, src, tgt, label)
            update_edge(session_id, src, tgt, {"label": label})
            return True
    return False


def _apply_reconnect(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Reconnect: move link from A->B to A->C."""
    m = re.search(r"reconnect\s+(P\d+\.\d+)\s+from\s+(P\d+\.\d+)\s+to\s+(P\d+\.\d+)", msg, re.IGNORECASE)
    if m:
        src, old_tgt, new_tgt = m.group(1), m.group(2), m.group(3)
        if src in step_ids and old_tgt in step_ids and new_tgt in step_ids and _edge_exists(session_id, src, old_tgt):
            logger.info("[AGENT][FALLBACK] session_id=%s reconnect delete_edge %s->%s add_edge %s->%s", session_id, src, old_tgt, src, new_tgt)
            delete_edge(session_id, src, old_tgt)
            add_edge(session_id, src, new_tgt)
            return True
    m = re.search(r"(?:change|move)\s+link\s+(?:from\s+)?(P\d+\.\d+)[\s\-–—]+(P\d+\.\d+)\s+to\s+(P\d+\.\d+)[\s\-–—]*(P\d+\.\d+)?", msg, re.IGNORECASE)
    if m:
        a, b, c, d = m.group(1), m.group(2), m.group(3), m.group(4)
        if d:
            if a == c and _edge_exists(session_id, a, b) and d in step_ids:
                logger.info("[AGENT][FALLBACK] session_id=%s reconnect delete_edge %s->%s add_edge %s->%s", session_id, a, b, a, d)
                delete_edge(session_id, a, b)
                add_edge(session_id, a, d)
                return True
        elif _edge_exists(session_id, a, b) and c in step_ids:
            logger.info("[AGENT][FALLBACK] session_id=%s reconnect delete_edge %s->%s add_edge %s->%s", session_id, a, b, a, c)
            delete_edge(session_id, a, b)
            add_edge(session_id, a, c)
            return True
    return False


def _apply_remove_nodes(session_id: str, msg: str, step_ids: set[str]) -> bool:
    """Remove one or more steps (when message is about steps, not edges)."""
    if re.search(r"(?:link|edge|connection)\s*(?:from|between)?", msg, re.IGNORECASE):
        return False
    node_ids_to_remove = re.findall(r"(P\d+\.\d+)", msg)
    remove_keywords = re.search(
        r"(?:remove|delete)\s+(?:step|node)s?\s*(?:P\d+\.\d+|\s|,|and)*", msg, re.IGNORECASE
    ) or re.search(r"(?:remove|delete)\s+(?:P\d+\.\d+(?:\s*,?\s*(?:and\s+)?)?)+", msg, re.IGNORECASE)
    if not remove_keywords or not node_ids_to_remove:
        return False
    removed = 0
    for nid in node_ids_to_remove:
        if nid in step_ids and delete_node(session_id, nid):
            removed += 1
            logger.info("[AGENT][FALLBACK] session_id=%s delete_node node_id=%s", session_id, nid)
    return removed > 0


# Order matters: first match wins.
FALLBACK_HANDLERS: list[FallbackHandler] = [
    _apply_duration,
    _apply_name,
    _apply_remove_edge,
    _apply_edge_label,
    _apply_reconnect,
    _apply_remove_nodes,
]


def try_apply_message_update(session_id: str, user_message: str) -> bool:
    """
    If the LLM didn't use tool_calls, try to apply updates from the user message.
    Returns True if we applied something.
    """
    if not user_message or not user_message.strip():
        return False
    step_ids = get_task_ids(session_id)
    msg = user_message.strip()
    for handler in FALLBACK_HANDLERS:
        if handler(session_id, msg, step_ids):
            return True
    return False
