"""In-memory SQLite storage for baseline processes, session state, and chat history.

JSON-native: stores graph_json instead of bpmn_xml.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_conn: sqlite3.Connection | None = None
_conn_lock = threading.RLock()


def get_conn() -> sqlite3.Connection:
    """Return the singleton in-memory SQLite connection, creating schema on first call."""
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(":memory:", check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS baseline_processes (
            process_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            parent_id  TEXT,
            graph_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS baseline_workspace (
            id             INTEGER PRIMARY KEY CHECK (id = 1),
            workspace_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_processes (
            session_id TEXT NOT NULL,
            process_id TEXT NOT NULL,
            graph_json TEXT NOT NULL,
            PRIMARY KEY (session_id, process_id)
        );

        CREATE TABLE IF NOT EXISTS session_workspace (
            session_id     TEXT PRIMARY KEY,
            workspace_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS appointment_requests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            email      TEXT NOT NULL,
            name       TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            session_id       TEXT PRIMARY KEY,
            summary_text     TEXT NOT NULL,
            summarized_up_to INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_plans (
            session_id   TEXT PRIMARY KEY,
            plan_json    TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_session_processes_sid
            ON session_processes(session_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_sid
            ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_appointment_requests_sid
            ON appointment_requests(session_id);
    """)


def insert_appointment_request(session_id: str, email: str, name: str | None = None) -> None:
    """Store an appointment request (user wants to be contacted for automation help)."""
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO appointment_requests (session_id, email, name) VALUES (?, ?, ?)",
            (session_id.strip(), email.strip(), (name or "").strip() or None),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Baseline seeding
# ---------------------------------------------------------------------------

def seed_baseline(workspace_path: Path, graphs_dir: Path) -> None:
    """Read workspace.json + graph JSON files and insert into baseline tables."""
    with _conn_lock:
        conn = get_conn()
        row = conn.execute("SELECT count(*) FROM baseline_processes").fetchone()
        if row is not None and (row[0] or 0) > 0:
            return

        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR REPLACE INTO baseline_workspace (id, workspace_json) VALUES (1, ?)",
            (json.dumps(workspace, ensure_ascii=False),),
        )

        processes = workspace.get("process_tree", {}).get("processes", {})
        for pid, info in processes.items():
            graph_file = graphs_dir / info["graph_file"]
            if not graph_file.exists():
                raise FileNotFoundError(f"Graph JSON not found: {graph_file}")
            graph_json = graph_file.read_text(encoding="utf-8")
            parent_id = None
            path = info.get("path", "")
            parts = [p for p in path.strip("/").split("/") if p]
            if len(parts) >= 2:
                parent_id = parts[-2]
            conn.execute(
                "INSERT OR REPLACE INTO baseline_processes (process_id, name, parent_id, graph_json) VALUES (?, ?, ?, ?)",
                (pid, info["name"], parent_id, graph_json),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Baseline reads
# ---------------------------------------------------------------------------

def get_baseline_process_ids() -> list[str]:
    conn = get_conn()
    rows = conn.execute("SELECT process_id FROM baseline_processes").fetchall()
    return [r["process_id"] for r in rows]


def get_baseline_json(process_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT graph_json FROM baseline_processes WHERE process_id = ?", (process_id,)
    ).fetchone()
    return row["graph_json"] if row else None


def get_baseline_workspace() -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT workspace_json FROM baseline_workspace WHERE id = 1").fetchone()
    return row["workspace_json"] if row else None


# ---------------------------------------------------------------------------
# Session cloning
# ---------------------------------------------------------------------------

def clone_baseline_to_session(session_id: str) -> None:
    """Copy all baseline rows into session tables for the given session."""
    sid = str(session_id)
    with _conn_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT count(*) FROM session_processes WHERE session_id = ?", (sid,)
        ).fetchone()
        existing = (row[0] if row is not None else 0)
        if existing > 0:
            return
        conn.execute(
            "INSERT OR IGNORE INTO session_processes (session_id, process_id, graph_json) "
            "SELECT ?, process_id, graph_json FROM baseline_processes",
            (sid,),
        )
        ws = get_baseline_workspace()
        if ws:
            conn.execute(
                "INSERT OR IGNORE INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
                (sid, ws),
            )
        conn.commit()


def force_clone_baseline_to_session(session_id: str) -> None:
    """Overwrite session with baseline: all process graphs and workspace."""
    sid = str(session_id)
    with _conn_lock:
        conn = get_conn()
        conn.execute("DELETE FROM session_processes WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM session_workspace WHERE session_id = ?", (sid,))
        conn.execute(
            "INSERT INTO session_processes (session_id, process_id, graph_json) "
            "SELECT ?, process_id, graph_json FROM baseline_processes",
            (sid,),
        )
        ws = get_baseline_workspace()
        if ws:
            conn.execute(
                "INSERT INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
                (sid, ws),
            )
        conn.commit()


def _empty_graph_json(session_id: str) -> str:
    """Minimal graph: id, name, nodes, edges (new format). Start and end only, no edge — user or agent adds subprocesses and edges."""
    name = f"{session_id}_map"
    return json.dumps({
        "id": "global",
        "name": name,
        "nodes": [
            {"id": "global_start", "type": "start", "position": {"x": 200, "y": 80}},
            {"id": "global_end", "type": "end", "position": {"x": 500, "y": 80}},
        ],
        "edges": [],
    }, ensure_ascii=False, indent=2)


def _empty_workspace_json(session_id: str) -> str:
    """Minimal workspace: root global, no children."""
    name = f"{session_id}_map"
    return json.dumps({
        "format_version": "1.0",
        "workspace_id": "ws_session",
        "name": session_id,
        "process_tree": {
            "root": "global",
            "processes": {
                "global": {
                    "name": name,
                    "depth": 0,
                    "path": "/global",
                    "children": [],
                    "summary": {"step_count": 0, "subprocess_count": 0},
                }
            },
        },
        "cross_links": [],
        "tags": {},
    }, ensure_ascii=False, indent=2)


def init_empty_session(session_id: str) -> None:
    """Create a session with an empty graph (start + end only). Overwrites any existing session data so 'from blank' always wins."""
    sid = str(session_id).strip()
    if not sid:
        return
    with _conn_lock:
        conn = get_conn()
        conn.execute("DELETE FROM session_processes WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM session_workspace WHERE session_id = ?", (sid,))
        graph_json = _empty_graph_json(sid)
        workspace_json = _empty_workspace_json(sid)
        conn.execute(
            "INSERT INTO session_processes (session_id, process_id, graph_json) VALUES (?, 'global', ?)",
            (sid, graph_json),
        )
        conn.execute(
            "INSERT INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
            (sid, workspace_json),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Session graph reads / writes
# ---------------------------------------------------------------------------

def get_session_json(session_id: str, process_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT graph_json FROM session_processes WHERE session_id = ? AND process_id = ?",
        (session_id, process_id),
    ).fetchone()
    return row["graph_json"] if row else None


def get_session_process_ids(session_id: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT process_id FROM session_processes WHERE session_id = ?", (session_id,)
    ).fetchall()
    return [r["process_id"] for r in rows]


def upsert_session_json(session_id: str, process_id: str, graph_json: str) -> None:
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO session_processes (session_id, process_id, graph_json) VALUES (?, ?, ?)",
            (session_id, process_id, graph_json),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Session workspace reads / writes
# ---------------------------------------------------------------------------

def get_session_workspace(session_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT workspace_json FROM session_workspace WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row["workspace_json"] if row else None


def upsert_session_workspace(session_id: str, workspace_json: str) -> None:
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
            (session_id, workspace_json),
        )
        conn.commit()


def delete_session_process(session_id: str, process_id: str) -> None:
    """Remove a process's graph from the session (e.g. when deleting a subprocess)."""
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "DELETE FROM session_processes WHERE session_id = ? AND process_id = ?",
            (session_id, process_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

def get_chat_history(session_id: str) -> list[dict]:
    """Return all chat messages for the session in order. Each dict has id, role, content."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in rows]


def get_conversation_summary(session_id: str) -> tuple[str, int] | None:
    """Return (summary_text, summarized_up_to_id) for the session, or None if none stored."""
    conn = get_conn()
    row = conn.execute(
        "SELECT summary_text, summarized_up_to FROM conversation_summaries WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return (row["summary_text"], row["summarized_up_to"])


def upsert_conversation_summary(session_id: str, summary_text: str, summarized_up_to: int) -> None:
    """Store or replace the rolling conversation summary for the session."""
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO conversation_summaries (session_id, summary_text, summarized_up_to) VALUES (?, ?, ?)",
            (session_id, summary_text, summarized_up_to),
        )
        conn.commit()


def upsert_pending_plan(session_id: str, plan: dict) -> None:
    """Store or replace the pending plan for a session."""
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO pending_plans (session_id, plan_json) VALUES (?, ?)",
            (session_id, json.dumps(plan, ensure_ascii=False)),
        )
        conn.commit()


def get_pending_plan(session_id: str) -> dict | None:
    """Return pending plan for a session, or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT plan_json FROM pending_plans WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["plan_json"])
    except Exception:
        return None


def delete_pending_plan(session_id: str) -> None:
    """Delete pending plan for a session."""
    with _conn_lock:
        conn = get_conn()
        conn.execute("DELETE FROM pending_plans WHERE session_id = ?", (session_id,))
        conn.commit()


def pop_pending_plan(session_id: str) -> dict | None:
    """Atomically fetch and delete pending plan for a session."""
    with _conn_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT plan_json FROM pending_plans WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM pending_plans WHERE session_id = ?", (session_id,))
        conn.commit()
    try:
        return json.loads(row["plan_json"])
    except Exception:
        return None


def append_chat_message(session_id: str, role: str, content: str) -> None:
    with _conn_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()
