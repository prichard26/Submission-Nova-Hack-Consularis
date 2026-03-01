"""Fallback: apply graph updates from user message when the LLM did not use tools."""
import logging
import re

from graph_store import get_task_ids, get_edges, update_node, update_edge, delete_node, add_edge, delete_edge

logger = logging.getLogger("consularis.agent")


def _edge_exists(session_id: str, source: str, target: str) -> bool:
    for c in get_edges(session_id):
        if c.get("from") == source and c.get("to") == target:
            return True
    return False


def try_apply_message_update(session_id: str, user_message: str) -> bool:
    """
    If the LLM didn't use tool_calls, try to apply updates from the user message.
    Returns True if we applied something.
    """
    if not user_message or not user_message.strip():
        return False
    step_ids = get_task_ids(session_id)
    msg = user_message.strip()

    # Duration
    node_id, dur = None, None
    m = re.search(r"(P\d+\.\d+)\D*(?:duration\D*)?(?:to|:|=)?\s*(\d+)\s*(?:min|minutes?|minute)?", msg, re.IGNORECASE)
    if m:
        node_id, dur = m.group(1), m.group(2)
    if not node_id:
        m = re.search(r"(?:duration|durée)\s*(?:to|of|:|=)?\s*(\d+)\D*(P\d+\.\d+)", msg, re.IGNORECASE)
        if m:
            node_id, dur = m.group(2), m.group(1)
    if not node_id:
        m = re.search(r"(?:step\s+)?(P\d+\.\d+)\s*[=:]\s*(\d+)\s*(?:min|minutes?)?", msg, re.IGNORECASE)
        if m:
            node_id, dur = m.group(1), m.group(2)
    if not node_id:
        m = re.search(r"(P\d+\.\d+)\D{0,20}(\d+)\s*(?:min|minutes?|minute)\b", msg, re.IGNORECASE)
        if m:
            node_id, dur = m.group(1), m.group(2)
    if node_id and node_id in step_ids and dur:
        logger.info("[AGENT][FALLBACK] session_id=%s update_node duration node_id=%s duration_min=%s", session_id, node_id, dur)
        update_node(session_id, node_id, {"duration_min": str(dur)})
        return True

    # Name
    m = re.search(r"(P\d+\.\d+)\D*(?:name|title)\s*(?:to|:|=)\s*[\"']?([^\"'\n.]+)", msg, re.IGNORECASE)
    if m and m.group(1) in step_ids:
        logger.info("[AGENT][FALLBACK] session_id=%s update_node name node_id=%s name=%s", session_id, m.group(1), m.group(2).strip())
        update_node(session_id, m.group(1), {"name": m.group(2).strip()})
        return True

    # Remove edge
    src, tgt = None, None
    m = re.search(r"(?:remove|delete|disconnect)\s+(?:link|edge|connection)\s+(?:from\s+)?(P\d+\.\d+)\s+(?:to|->|-)\s*(P\d+\.\d+)", msg, re.IGNORECASE)
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
    if src and tgt and src in step_ids and tgt in step_ids and _edge_exists(session_id, src, tgt):
        logger.info("[AGENT][FALLBACK] session_id=%s delete_edge source=%s target=%s", session_id, src, tgt)
        delete_edge(session_id, src, tgt)
        return True

    # Rename / change link label (e.g. "change link between P7.2 and P7.3 to paul")
    m = re.search(r"(?:change|rename|set)\s+(?:link|edge|connection)\s+(?:name|label)?\s*(?:between\s+)?(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)\s+(?:to|:|=)\s*[\"']?([^\"'\n]+)", msg, re.IGNORECASE)
    if not m:
        m = re.search(r"(?:link|edge)\s+(?:between\s+)?(P\d+\.\d+)\s+(?:and|to|->|-)\s*(P\d+\.\d+)\s+(?:to|:|=)\s*[\"']?([^\"'\n]+)", msg, re.IGNORECASE)
    if m:
        src, tgt, label = m.group(1), m.group(2), m.group(3).strip()
        if src in step_ids and tgt in step_ids and _edge_exists(session_id, src, tgt) and label:
            logger.info("[AGENT][FALLBACK] session_id=%s update_edge label source=%s target=%s label=%s", session_id, src, tgt, label)
            update_edge(session_id, src, tgt, {"label": label})
            return True

    # Reconnect
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

    # Remove nodes
    if not re.search(r"(?:link|edge|connection)\s*(?:from|between)?", msg, re.IGNORECASE):
        node_ids_to_remove = re.findall(r"(P\d+\.\d+)", msg)
        remove_keywords = re.search(r"(?:remove|delete)\s+(?:step|node)s?\s*(?:P\d+\.\d+|\s|,|and)*", msg, re.IGNORECASE) or re.search(r"(?:remove|delete)\s+(?:P\d+\.\d+(?:\s*,?\s*(?:and\s+)?)?)+", msg, re.IGNORECASE)
        if remove_keywords and node_ids_to_remove:
            removed = 0
            for nid in node_ids_to_remove:
                if nid in step_ids and delete_node(session_id, nid):
                    removed += 1
                    logger.info("[AGENT][FALLBACK] session_id=%s delete_node node_id=%s", session_id, nid)
            if removed:
                return True

    return False
