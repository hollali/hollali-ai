from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".hollali" / "hollali.db"
_local = threading.local()
_cleanup_lock = threading.Lock()
_connections: set[sqlite3.Connection] = set()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        with _cleanup_lock:
            _connections.add(_local.conn)
    return _local.conn


def close_connections() -> None:
    with _cleanup_lock:
        for conn in _connections:
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
    if hasattr(_local, "conn"):
        _local.conn = None


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversations_session
                ON conversations(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_conversations_created
                ON conversations(created_at);
        """)


def save_conversation(session_id: str, role: str, content: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )


def load_conversation(session_id: str, limit: int = 10) -> list[dict[str, str]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_last_session_id() -> str | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT session_id FROM conversations ORDER BY created_at DESC LIMIT 1").fetchone()
    return row["session_id"] if row else None


def delete_conversation(session_id: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))


def clear_all_conversations() -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations")


def save_note(title: str, content: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
        return cur.lastrowid


def list_notes(limit: int = 10) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sessions(limit: int = 30) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT session_id, MAX(created_at) as last "
            "FROM conversations GROUP BY session_id ORDER BY last DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"session_id": r["session_id"], "last": r["last"]} for r in rows]


def get_preference(key: str, default: str = "") -> str:
    with _get_conn() as conn:
        row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_preference(key: str, value: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
