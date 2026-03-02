"""JSON-native process graph model.

ProcessGraph wraps a raw dict that IS the JSON document.
No parsing or serializing -- mutations are direct dict operations.
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


class ProcessGraph:
    """JSON-native process graph.  ``self.data`` IS the JSON document."""

    def __init__(self, data: dict):
        self.data = data

    # -- properties --------------------------------------------------------

    @property
    def process_id(self) -> str:
        return self.data.get("process_id", "")

    @process_id.setter
    def process_id(self, value: str) -> None:
        self.data["process_id"] = value

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
    def steps(self) -> list[dict]:
        return self.data.setdefault("steps", [])

    @property
    def flows(self) -> list[dict]:
        return self.data.setdefault("flows", [])

    @property
    def lanes(self) -> list[dict]:
        return self.data.setdefault("lanes", [])

    # -- lookups -----------------------------------------------------------

    def get_step(self, step_id: str) -> dict | None:
        return next((s for s in self.steps if s.get("id") == step_id), None)

    def get_step_by_short_id(self, short_id: str) -> dict | None:
        return next((s for s in self.steps if s.get("short_id") == short_id), None)

    def get_lane(self, lane_id: str) -> dict | None:
        return next((ln for ln in self.lanes if ln.get("id") == lane_id), None)

    def get_flow(self, from_id: str, to_id: str) -> dict | None:
        return next(
            (f for f in self.flows if f.get("from") == from_id and f.get("to") == to_id),
            None,
        )

    def all_step_ids(self) -> set[str]:
        return {s["id"] for s in self.steps if "id" in s}

    def steps_in_lane(self, lane_id: str) -> list[dict]:
        lane = self.get_lane(lane_id)
        if not lane:
            return []
        refs = set(lane.get("node_refs", []))
        return [s for s in self.steps if s.get("id") in refs]

    def step_type(self, step_id: str) -> str | None:
        step = self.get_step(step_id)
        return step.get("type") if step else None

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
