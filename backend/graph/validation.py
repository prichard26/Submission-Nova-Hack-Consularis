"""Three-layer validation pipeline for plan steps and graph structure.

Layer 1 -- Schema: Pydantic models validate tool-call arguments before execution.
Layer 2 -- Structural (per-step): lightweight checks after each tool step.
Layer 3 -- Post-execution: full graph reachability, orphan, and flow checks.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, field_validator

logger = logging.getLogger("consularis.validation")


# ---------------------------------------------------------------------------
# Layer 1: Pydantic argument schemas
# ---------------------------------------------------------------------------

class AddNodeArgs(BaseModel):
    id: str
    type: Literal["step", "decision", "subprocess"]
    name: str | None = None

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id must not be empty")
        return v.strip()

    @field_validator("type")
    @classmethod
    def type_not_start_end(cls, v: str) -> str:
        if v in ("start", "end"):
            raise ValueError(
                "Do not add start or end nodes. They are created automatically "
                "when you add a subprocess."
            )
        return v


class InsertStepBetweenArgs(BaseModel):
    after_id: str
    before_id: str
    name: str
    type: Literal["step", "decision"] = "step"
    process_id: str | None = None

    @field_validator("after_id", "before_id", "name")
    @classmethod
    def fields_not_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("after_id, before_id and name must not be empty")
        return str(v).strip()


class InsertSubprocessBetweenArgs(BaseModel):
    after_id: str
    before_id: str
    name: str

    @field_validator("after_id", "before_id", "name")
    @classmethod
    def fields_not_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("after_id, before_id and name must not be empty")
        return str(v).strip()


class DeleteNodeArgs(BaseModel):
    id: str

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id must not be empty")
        v = v.strip()
        if v.endswith("_start") or v.endswith("_end"):
            raise ValueError(f"Cannot delete protected start/end node: {v}")
        return v


class UpdateNodeArgs(BaseModel):
    id: str
    updates: dict[str, Any]

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id must not be empty")
        return v.strip()

    @field_validator("updates")
    @classmethod
    def updates_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("updates must contain at least one field")
        if set(v.keys()) == {"attributes"} and isinstance(v.get("attributes"), dict):
            raise ValueError(
                "Use flat updates (e.g. {\"name\": \"X\"}), not nested "
                "{\"attributes\": {\"name\": \"X\"}}"
            )
        return v


class AddEdgeArgs(BaseModel):
    source: str
    target: str
    label: str | None = None

    @field_validator("source", "target")
    @classmethod
    def endpoints_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("edge endpoint must not be empty")
        return v.strip()


class DeleteEdgeArgs(BaseModel):
    source: str
    target: str

    @field_validator("source", "target")
    @classmethod
    def endpoints_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("edge endpoint must not be empty")
        return v.strip()


class UpdateEdgeArgs(BaseModel):
    source: str
    target: str
    updates: dict[str, Any]

    @field_validator("source", "target")
    @classmethod
    def endpoints_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("edge endpoint must not be empty")
        return v.strip()

    @field_validator("updates")
    @classmethod
    def updates_is_dict(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("updates must be an object")
        return v


class RenameProcessArgs(BaseModel):
    id: str
    name: str

    @field_validator("id", "name")
    @classmethod
    def fields_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id and name must not be empty")
        return v.strip()


TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "add_node": AddNodeArgs,
    "insert_step_between": InsertStepBetweenArgs,
    "insert_subprocess_between": InsertSubprocessBetweenArgs,
    "delete_node": DeleteNodeArgs,
    "update_node": UpdateNodeArgs,
    "add_edge": AddEdgeArgs,
    "delete_edge": DeleteEdgeArgs,
    "update_edge": UpdateEdgeArgs,
    "rename_process": RenameProcessArgs,
}


def validate_step_schema(tool_name: str, arguments: dict) -> str | None:
    """Layer 1: Validate a single plan step's arguments against its Pydantic model.

    Returns None on success, or an error message string on failure.
    """
    model_cls = TOOL_ARG_MODELS.get(tool_name)
    if model_cls is None:
        if tool_name == "get_full_graph":
            return None
        return f"Unknown tool: {tool_name}"
    # Normalize alternate field names before validation
    args = _normalize_args(tool_name, arguments)
    try:
        model_cls.model_validate(args)
        return None
    except Exception as exc:
        return str(exc)


def _normalize_args(tool_name: str, args: dict) -> dict:
    """Normalize common alternative field names the LLM may use."""
    out = dict(args)
    if tool_name in ("add_edge", "delete_edge", "update_edge"):
        for alias in ("from", "source_id", "from_id"):
            if alias in out and "source" not in out:
                out["source"] = out.pop(alias)
        for alias in ("to", "target_id", "to_id"):
            if alias in out and "target" not in out:
                out["target"] = out.pop(alias)
    if tool_name in ("update_node", "delete_node"):
        if "step_id" in out and "id" not in out:
            out["id"] = out.pop("step_id")
        if "node_id" in out and "id" not in out:
            out["id"] = out.pop("node_id")
    if tool_name == "rename_process":
        if "process_id" in out and "id" not in out:
            out["id"] = out.pop("process_id")
    return out



# ---------------------------------------------------------------------------
# Layer 3: Post-execution full graph validation
# ---------------------------------------------------------------------------

class GraphValidationResult:
    """Collects all validation issues found across the full graph."""

    def __init__(self) -> None:
        self.issues: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0

    def add(self, msg: str) -> None:
        self.issues.append(msg)

    def summary(self) -> str:
        if self.ok:
            return "Graph validation passed."
        return "Graph validation found issues:\n" + "\n".join(
            f"  - {issue}" for issue in self.issues
        )


def validate_full_graph(full_graph: dict[str, Any]) -> GraphValidationResult:
    """Layer 3: Run all structural checks on the full graph after plan execution."""
    result = GraphValidationResult()
    for proc in full_graph.get("processes") or []:
        pid = proc.get("id", "?")
        nodes = proc.get("nodes") or []
        edges = proc.get("edges") or []
        _validate_reachability(pid, nodes, edges, result)
        _validate_no_orphans(pid, nodes, edges, result)
        _validate_flow_completeness(pid, nodes, edges, result)
    _validate_no_cross_page_edges(full_graph, result)
    return result


def _validate_reachability(
    pid: str, nodes: list[dict], edges: list[dict], result: GraphValidationResult
) -> None:
    """Every node should be reachable from the start node."""
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    start = None
    for n in nodes:
        nid = n.get("id", "")
        if n.get("type") == "start" or nid.endswith("_start"):
            start = nid
            break
    if not start:
        return

    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        src, tgt = e.get("from", ""), e.get("to", "")
        if src and tgt:
            adj[src].append(tgt)

    visited: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                stack.append(neighbor)

    unreachable = node_ids - visited
    for nid in sorted(unreachable):
        result.add(f"[{pid}] Node '{nid}' is not reachable from {start}")


def _validate_no_orphans(
    pid: str, nodes: list[dict], edges: list[dict], result: GraphValidationResult
) -> None:
    """No non-start/end node should have zero edges."""
    connected: set[str] = set()
    for e in edges:
        src, tgt = e.get("from", ""), e.get("to", "")
        if src:
            connected.add(src)
        if tgt:
            connected.add(tgt)

    for n in nodes:
        nid = n.get("id", "")
        ntype = n.get("type", "")
        if ntype in ("start", "end") or nid.endswith("_start") or nid.endswith("_end"):
            continue
        if nid and nid not in connected:
            result.add(f"[{pid}] Orphan node '{nid}' has no edges")


def _validate_flow_completeness(
    pid: str, nodes: list[dict], edges: list[dict], result: GraphValidationResult
) -> None:
    """Every non-start/end node should have at least one incoming AND one outgoing edge."""
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    for e in edges:
        src, tgt = e.get("from", ""), e.get("to", "")
        if src:
            outgoing[src] += 1
        if tgt:
            incoming[tgt] += 1

    for n in nodes:
        nid = n.get("id", "")
        ntype = n.get("type", "")
        if not nid:
            continue
        is_start = ntype == "start" or nid.endswith("_start")
        is_end = ntype == "end" or nid.endswith("_end")
        if is_start or is_end:
            continue
        if incoming.get(nid, 0) == 0:
            result.add(f"[{pid}] Node '{nid}' has no incoming edges")
        if outgoing.get(nid, 0) == 0:
            result.add(f"[{pid}] Node '{nid}' has no outgoing edges")


def _validate_no_cross_page_edges(
    full_graph: dict[str, Any], result: GraphValidationResult
) -> None:
    """Edges should only connect nodes within the same process page."""
    for proc in full_graph.get("processes") or []:
        pid = proc.get("id", "?")
        node_ids = {n.get("id") for n in proc.get("nodes", []) if n.get("id")}
        for e in proc.get("edges") or []:
            src, tgt = e.get("from", ""), e.get("to", "")
            if src and src not in node_ids:
                result.add(
                    f"[{pid}] Edge source '{src}' does not belong to this process page"
                )
            if tgt and tgt not in node_ids:
                result.add(
                    f"[{pid}] Edge target '{tgt}' does not belong to this process page"
                )
