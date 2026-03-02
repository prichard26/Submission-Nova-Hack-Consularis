"""Auto-layout for new nodes that have no position yet."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graph.model import ProcessGraph

GAP_X = 360
DEFAULT_X = 280
DEFAULT_Y = 80
STEP_WIDTH = 220
STEP_HEIGHT = 112
EVENT_SIZE = 44
GATEWAY_SIZE = 56


def auto_position(graph: "ProcessGraph", lane_id: str) -> dict:
    """Compute position for a new node appended to a lane (right of the rightmost positioned node)."""
    lane_steps = graph.steps_in_lane(lane_id)
    positioned = [s for s in lane_steps if s.get("position")]
    if not positioned:
        return {"x": DEFAULT_X, "y": DEFAULT_Y}
    rightmost = max(positioned, key=lambda s: s["position"]["x"])
    pos = rightmost["position"]
    w, _ = step_size(rightmost)
    return {"x": pos["x"] + w + 80, "y": pos["y"]}


def step_size(step: dict) -> tuple[int, int]:
    """Return (width, height) for a step based on its type."""
    stype = step.get("type", "step")
    if stype in ("start", "end"):
        return (EVENT_SIZE, EVENT_SIZE)
    if stype == "decision":
        return (GATEWAY_SIZE, GATEWAY_SIZE)
    name = step.get("name", "")
    w = max(len(name) * 9, STEP_WIDTH)
    w = min(w, 360)
    return (w, STEP_HEIGHT)
