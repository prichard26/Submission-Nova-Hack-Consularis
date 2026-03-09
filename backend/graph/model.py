"""JSON-native process graph model.

ProcessGraph wraps a raw dict that IS the JSON document.
Structure: id, name, nodes, edges. Node metadata lives under attributes.
"""
from __future__ import annotations

import copy
import json

STEP_METADATA_KEYS = frozenset({
    "actor", "duration_min", "description", "inputs", "outputs", "risks",
    "automation_potential", "automation_notes", "current_state", "frequency",
    "annual_volume", "error_rate_percent", "cost_per_execution",
    "current_systems", "data_format", "external_dependencies",
    "regulatory_constraints", "sla_target", "pain_points",
})

LIST_METADATA_KEYS = frozenset({
    "inputs", "outputs", "risks", "current_systems",
    "external_dependencies", "regulatory_constraints", "pain_points",
})

STEP_TYPES = frozenset({"start", "end", "step", "decision", "subprocess"})


def default_step_metadata() -> dict:
    return {
        "actor": "",
        "duration_min": "",
        "description": "",
        "inputs": [],
        "outputs": [],
        "risks": [],
        "automation_potential": "",
        "automation_notes": "",
        "current_state": "",
        "frequency": "",
        "annual_volume": "",
        "error_rate_percent": "",
        "cost_per_execution": "",
        "current_systems": [],
        "data_format": "",
        "external_dependencies": [],
        "regulatory_constraints": [],
        "sla_target": "",
        "pain_points": [],
    }


def _node_attrs(node: dict) -> dict:
    """All metadata for a node: attributes dict plus top-level name."""
    attrs = dict(node.get("attributes") or {})
    if node.get("name") is not None:
        attrs["name"] = node["name"]
    return attrs


class ProcessGraph:
    """JSON-native process graph. self.data IS the JSON document. Uses nodes and edges."""

    def __init__(self, data: dict):
        self.data = data

    # -- properties --------------------------------------------------------

    @property
    def process_id(self) -> str:
        """Set by API when serving; not stored in JSON."""
        return self.data.get("process_id", "")

    @property
    def name(self) -> str:
        return self.data.get("name", "")

    @name.setter
    def name(self, value: str) -> None:
        self.data["name"] = value

    @property
    def metadata(self) -> dict:
        return self.data.get("metadata", {})

    @property
    def nodes(self) -> list[dict]:
        return self.data.setdefault("nodes", [])

    @property
    def edges(self) -> list[dict]:
        return self.data.setdefault("edges", [])

    @property
    def steps(self) -> list[dict]:
        """Alias for nodes (same list)."""
        return self.nodes

    @property
    def step_order(self) -> list[str]:
        """Order of node ids (nodes array order)."""
        return [n["id"] for n in self.nodes if n.get("id")]

    @step_order.setter
    def step_order(self, value: list[str] | None) -> None:
        if not value:
            return
        by_id = {n["id"]: n for n in self.nodes if n.get("id")}
        ordered = [by_id[sid] for sid in value if sid in by_id]
        # keep any nodes not in value at the end
        remaining = [n for n in self.nodes if n.get("id") not in by_id or n["id"] not in value]
        self.data["nodes"] = ordered + remaining

    @property
    def lanes(self) -> list[dict]:
        """Single synthetic lane for UI compat: one lane with all node refs."""
        return self.data.get("lanes") or [{
            "id": "default",
            "name": self.name or "",
            "description": "",
            "node_refs": self.step_order,
        }]

    def get_lane(self, lane_id: str) -> dict | None:
        return next((ln for ln in self.lanes if ln.get("id") == lane_id), None)

    # -- lookups -----------------------------------------------------------

    def get_step(self, step_id: str) -> dict | None:
        return next((n for n in self.nodes if n.get("id") == step_id), None)

    def get_flow(self, from_id: str, to_id: str) -> dict | None:
        return next(
            (e for e in self.edges if e.get("from") == from_id and e.get("to") == to_id),
            None,
        )

    def all_step_ids(self) -> set[str]:
        return {n["id"] for n in self.nodes if n.get("id")}

    def steps_in_order(self) -> list[dict]:
        """Nodes in array order."""
        return list(self.nodes)

    def step_type(self, step_id: str) -> str | None:
        node = self.get_step(step_id)
        return node.get("type") if node else None

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return self.data

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> ProcessGraph:
        return cls(json.loads(json_str))

    @classmethod
    def from_dict(cls, d: dict) -> ProcessGraph:
        return cls(d)

    def copy(self) -> ProcessGraph:
        return ProcessGraph(copy.deepcopy(self.data))
