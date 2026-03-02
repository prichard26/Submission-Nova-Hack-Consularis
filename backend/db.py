"""In-memory SQLite storage for baseline processes, session state, and chat history."""
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
            bpmn_xml   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_processes (
            session_id TEXT NOT NULL,
            process_id TEXT NOT NULL,
            bpmn_xml   TEXT NOT NULL,
            PRIMARY KEY (session_id, process_id)
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
            bpmn_xml   TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_session_processes_sid
            ON session_processes(session_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_sid
            ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_process_history_sid_pid
            ON session_process_history(session_id, process_id);
    """)


def seed_baseline(registry_path: Path, graphs_dir: Path) -> None:
    """Read registry.json + BPMN files and insert into baseline_processes."""
    conn = get_conn()
    if conn.execute("SELECT count(*) FROM baseline_processes").fetchone()[0] > 0:
        return

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for entry in registry["processes"]:
        bpmn_file = graphs_dir / entry["bpmn_file"]
        if not bpmn_file.exists():
            raise FileNotFoundError(f"BPMN file not found: {bpmn_file}")
        bpmn_xml = bpmn_file.read_text(encoding="utf-8")
        conn.execute(
            "INSERT OR REPLACE INTO baseline_processes (process_id, name, parent_id, bpmn_xml) VALUES (?, ?, ?, ?)",
            (entry["process_id"], entry["name"], entry.get("parent_id"), bpmn_xml),
        )
    conn.commit()


def get_baseline_process_ids() -> list[str]:
    conn = get_conn()
    rows = conn.execute("SELECT process_id FROM baseline_processes").fetchall()
    return [r["process_id"] for r in rows]


def get_baseline_xml(process_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT bpmn_xml FROM baseline_processes WHERE process_id = ?", (process_id,)
    ).fetchone()
    return row["bpmn_xml"] if row else None


def clone_baseline_to_session(session_id: str) -> None:
    """Copy all baseline rows into session_processes for the given session.
    Uses INSERT OR IGNORE so concurrent requests for the same session do not raise UNIQUE."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT count(*) FROM session_processes WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    if existing > 0:
        return
    conn.execute(
        "INSERT OR IGNORE INTO session_processes (session_id, process_id, bpmn_xml) "
        "SELECT ?, process_id, bpmn_xml FROM baseline_processes",
        (session_id,),
    )
    conn.commit()


def get_session_xml(session_id: str, process_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT bpmn_xml FROM session_processes WHERE session_id = ? AND process_id = ?",
        (session_id, process_id),
    ).fetchone()
    return row["bpmn_xml"] if row else None


def get_session_process_ids(session_id: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT process_id FROM session_processes WHERE session_id = ?", (session_id,)
    ).fetchall()
    return [r["process_id"] for r in rows]


def upsert_session_xml(session_id: str, process_id: str, bpmn_xml: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO session_processes (session_id, process_id, bpmn_xml) VALUES (?, ?, ?)",
        (session_id, process_id, bpmn_xml),
    )
    conn.commit()


def push_history(session_id: str, process_id: str, bpmn_xml: str) -> None:
    """Append a snapshot to session process history (used before overwriting with a mutation)."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO session_process_history (session_id, process_id, bpmn_xml) VALUES (?, ?, ?)",
        (session_id, process_id, bpmn_xml),
    )
    conn.commit()


def pop_history(session_id: str, process_id: str) -> str | None:
    """Remove and return the most recent history entry for (session_id, process_id), or None if empty."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, bpmn_xml FROM session_process_history "
        "WHERE session_id = ? AND process_id = ? ORDER BY id DESC LIMIT 1",
        (session_id, process_id),
    ).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM session_process_history WHERE id = ?", (row["id"],))
    conn.commit()
    return row["bpmn_xml"]


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
