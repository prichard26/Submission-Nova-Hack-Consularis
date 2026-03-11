"""Generate a concise, LLM-friendly structural summary of the full graph.

The summary traces the flow topology (start -> A -> B -> ... -> end) for each
process page and highlights decision branches. It is injected into the planner
system prompt so the LLM can quickly understand the process without parsing raw JSON.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def generate_graph_summary(full_graph: dict[str, Any]) -> str:
    """Return a human-readable structural summary of every process in the graph."""
    sections: list[str] = []
    processes = full_graph.get("processes") or []
    total_nodes = sum(len(p.get("nodes", [])) for p in processes)

    for proc in processes:
        pid = proc.get("id", "?")
        name = proc.get("name") or pid
        nodes = proc.get("nodes") or []
        edges = proc.get("edges") or []

        steps = [n for n in nodes if n.get("type") == "step"]
        decisions = [n for n in nodes if n.get("type") == "decision"]
        subprocesses = [n for n in nodes if n.get("type") == "subprocess"]
        counts = f"{len(steps)} steps, {len(decisions)} decisions, {len(subprocesses)} subprocesses"

        flow = _trace_main_flow(nodes, edges)
        lines = [f"### {name} ({pid})", f"  {counts}", f"  Flow: {flow}"]

        for d in decisions:
            did = d.get("id", "")
            dname = d.get("name") or ""
            branches = [e for e in edges if e.get("from") == did]
            if branches:
                branch_parts = []
                for e in branches:
                    label = e.get("label") or "→"
                    branch_parts.append(f"{label} {e.get('to', '?')}")
                branch_desc = ", ".join(branch_parts)
                label_str = f' "{dname}"' if dname else ""
                lines.append(f"  Decision {did}{label_str}: {branch_desc}")

        sections.append("\n".join(lines))

    header = f"**Graph overview** ({len(processes)} pages, {total_nodes} nodes total)"
    return header + "\n\n" + "\n\n".join(sections)


def _trace_main_flow(nodes: list[dict], edges: list[dict]) -> str:
    """Trace the main flow path from the start node to the end node.

    Follows the first outgoing edge at each step to build a linear path.
    Decision branches are shown inline as (decision -> ...).
    """
    node_map = {n.get("id"): n for n in nodes if n.get("id")}
    outgoing: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        src = e.get("from")
        if src:
            outgoing[src].append(e)

    start_node = None
    for n in nodes:
        ntype = n.get("type", "")
        nid = n.get("id", "")
        if ntype == "start" or nid.endswith("_start"):
            start_node = nid
            break

    if not start_node:
        ids = [n.get("id", "?") for n in nodes if n.get("type") not in ("start", "end")]
        return " -> ".join(ids) if ids else "(empty)"

    path_parts: list[str] = []
    visited: set[str] = set()
    current = start_node

    while current and current not in visited:
        visited.add(current)
        node = node_map.get(current, {})
        ntype = node.get("type", "")
        name = node.get("name") or ""

        if ntype in ("start",) or current.endswith("_start"):
            label = current
        elif ntype in ("end",) or current.endswith("_end"):
            label = current
        elif name:
            label = f"{current}({name})"
        else:
            label = current
        path_parts.append(label)

        outs = outgoing.get(current, [])
        if not outs:
            break
        current = outs[0].get("to")

    return " -> ".join(path_parts) if path_parts else "(empty)"


def count_total_nodes(full_graph: dict[str, Any]) -> int:
    """Return the total number of nodes across all processes."""
    return sum(len(p.get("nodes", [])) for p in full_graph.get("processes", []))
