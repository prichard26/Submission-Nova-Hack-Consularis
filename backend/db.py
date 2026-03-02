"""In-memory SQLite storage for baseline processes, session state, and chat history.

JSON-native: stores graph_json instead of bpmn_xml.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    """Return the singleton in-memory SQLite connection, creating schema on first call."""
    global _conn
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

        CREATE TABLE IF NOT EXISTS session_process_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            process_id TEXT NOT NULL,
            graph_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_session_processes_sid
            ON session_processes(session_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_sid
            ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_process_history_sid_pid
            ON session_process_history(session_id, process_id);
    """)


# ---------------------------------------------------------------------------
# Baseline seeding
# ---------------------------------------------------------------------------

def seed_baseline(workspace_path: Path, graphs_dir: Path) -> None:
    """Read workspace.json + graph JSON files and insert into baseline tables."""
    conn = get_conn()
    if conn.execute("SELECT count(*) FROM baseline_processes").fetchone()[0] > 0:
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
    conn = get_conn()
    existing = conn.execute(
        "SELECT count(*) FROM session_processes WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    if existing > 0:
        return
    conn.execute(
        "INSERT OR IGNORE INTO session_processes (session_id, process_id, graph_json) "
        "SELECT ?, process_id, graph_json FROM baseline_processes",
        (session_id,),
    )
    ws = get_baseline_workspace()
    if ws:
        conn.execute(
            "INSERT OR IGNORE INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
            (session_id, ws),
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
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO session_workspace (session_id, workspace_json) VALUES (?, ?)",
        (session_id, workspace_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# History (undo support)
# ---------------------------------------------------------------------------

def push_history(session_id: str, process_id: str, graph_json: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO session_process_history (session_id, process_id, graph_json) VALUES (?, ?, ?)",
        (session_id, process_id, graph_json),
    )
    conn.commit()


def pop_history(session_id: str, process_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, graph_json FROM session_process_history "
        "WHERE session_id = ? AND process_id = ? ORDER BY id DESC LIMIT 1",
        (session_id, process_id),
    ).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM session_process_history WHERE id = ?", (row["id"],))
    conn.commit()
    return row["graph_json"]


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

def get_chat_history(session_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def append_chat_message(session_id: str, role: str, content: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
