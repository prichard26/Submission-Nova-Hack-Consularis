"""
Session store and graph tools. Each session has a mutable copy of the pharmacy circuit.
Tools validate all inputs to avoid invalid edits (bullshit detection at execution).
"""
import json
import copy
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CIRCUIT_PATH = _DATA_DIR / "pharmacy_circuit.json"

# In-memory: session_id -> { "phases": [...], "flow_connections": [...] }
_sessions: dict = {}


def _load_default():
    with open(_CIRCUIT_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_or_create_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = copy.deepcopy(_load_default())
    return _sessions[session_id]


def get_graph(session_id: str) -> dict:
    return get_or_create_session(session_id)


def _step_ids(session: dict) -> set:
    ids = set()
    for phase in session["phases"]:
        for step in phase["steps"]:
            ids.add(step["id"])
    return ids


def _edge_key(conn: dict) -> tuple:
    return (conn["from"], conn["to"])


def get_node(session_id: str, node_id: str) -> dict | None:
    session = get_or_create_session(session_id)
    for phase in session["phases"]:
        for step in phase["steps"]:
            if step["id"] == node_id:
                return {**step, "phaseName": phase["name"], "phaseId": phase["id"]}
    return None


def update_node(session_id: str, node_id: str, updates: dict) -> dict | None:
    session = get_or_create_session(session_id)
    allowed = {"name", "actor", "duration_min", "description", "inputs", "outputs", "risks"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    for phase in session["phases"]:
        for step in phase["steps"]:
            if step["id"] == node_id:
                step.update(updates)
                return {**step, "phaseName": phase["name"], "phaseId": phase["id"]}
    return None


def add_node(session_id: str, phase_id: str, step_data: dict) -> dict | None:
    session = get_or_create_session(session_id)
    for phase in session["phases"]:
        if phase["id"] != phase_id:
            continue
        existing_ids = [s["id"] for s in phase["steps"]]
        # New id: e.g. P2 -> P2.5 (next free .N)
        parts = [int(x) for x in existing_ids[-1].split(".")] if existing_ids else [int(phase_id[1]), 0]
        new_id = f"{phase_id}.{parts[-1] + 1}"
        new_step = {
            "id": new_id,
            "name": step_data.get("name", "New step"),
            "actor": step_data.get("actor", "Pharmacist"),
            "duration_min": step_data.get("duration_min", "—"),
            "description": step_data.get("description", ""),
            "inputs": step_data.get("inputs", []),
            "outputs": step_data.get("outputs", []),
            "risks": step_data.get("risks", []),
        }
        phase["steps"].append(new_step)
        return {**new_step, "phaseName": phase["name"], "phaseId": phase["id"]}
    return None


def delete_node(session_id: str, node_id: str) -> bool:
    session = get_or_create_session(session_id)
    for phase in session["phases"]:
        for i, step in enumerate(phase["steps"]):
            if step["id"] == node_id:
                phase["steps"].pop(i)
                session["flow_connections"][:] = [
                    c for c in session["flow_connections"]
                    if c["from"] != node_id and c["to"] != node_id
                ]
                return True
    return False


def get_edges(session_id: str, source_id: str | None = None) -> list:
    session = get_or_create_session(session_id)
    conns = session["flow_connections"]
    if source_id is not None:
        conns = [c for c in conns if c["from"] == source_id]
    return list(conns)


def update_edge(session_id: str, source: str, target: str, updates: dict) -> dict | None:
    session = get_or_create_session(session_id)
    allowed = {"label", "condition"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    for conn in session["flow_connections"]:
        if conn["from"] == source and conn["to"] == target:
            conn.update(updates)
            return conn
    return None


def add_edge(session_id: str, source: str, target: str, label: str = "", condition: str | None = None) -> dict | None:
    session = get_or_create_session(session_id)
    ids = _step_ids(session)
    if source not in ids or target not in ids:
        return None
    for c in session["flow_connections"]:
        if c["from"] == source and c["to"] == target:
            return c  # already exists
    conn = {"from": source, "to": target, "label": label or f"{source} → {target}"}
    if condition:
        conn["condition"] = condition
    session["flow_connections"].append(conn)
    return conn


def delete_edge(session_id: str, source: str, target: str) -> bool:
    session = get_or_create_session(session_id)
    for i, c in enumerate(session["flow_connections"]):
        if c["from"] == source and c["to"] == target:
            session["flow_connections"].pop(i)
            return True
    return False


def validate_graph(session_id: str) -> dict:
    session = get_or_create_session(session_id)
    ids = _step_ids(session)
    issues = []
    for conn in session["flow_connections"]:
        if conn["from"] not in ids:
            issues.append(f"Edge source '{conn['from']}' is not a valid step id.")
        if conn["to"] not in ids:
            issues.append(f"Edge target '{conn['to']}' is not a valid step id.")
    for phase in session["phases"]:
        step_ids = [s["id"] for s in phase["steps"]]
        if len(step_ids) != len(set(step_ids)):
            issues.append(f"Phase {phase['id']} has duplicate step ids.")
        for step in phase["steps"]:
            if not (step.get("name") or step.get("id")):
                issues.append(f"Step {step.get('id', '?')} has no name.")
    return {"valid": len(issues) == 0, "issues": issues}
