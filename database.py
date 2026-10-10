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
            CREATE TABLE IF NOT EXISTS conversation_metadata (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation'
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
        if role == "user":
            title = content.strip()[:60] or "New conversation"
            conn.execute(
                "INSERT OR IGNORE INTO conversation_metadata (session_id, title) VALUES (?, ?)",
                (session_id, title),
            )
            conn.execute(
                "UPDATE conversation_metadata SET title = ? WHERE session_id = ? AND title = 'New conversation'",
                (title, session_id),
            )


def load_conversation(session_id: str, limit: int = 10) -> list[dict[str, str]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
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
        conn.execute("DELETE FROM conversation_metadata WHERE session_id = ?", (session_id,))


def clear_all_conversations() -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations")
        conn.execute("DELETE FROM conversation_metadata")


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


def create_conversation(session_id: str, title: str = "New conversation") -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_metadata (session_id, title) VALUES (?, ?)",
            (session_id, title.strip()[:120] or "New conversation"),
        )


def conversation_exists(session_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversation_metadata WHERE session_id = ? "
            "UNION SELECT 1 FROM conversations WHERE session_id = ? LIMIT 1",
            (session_id, session_id),
        ).fetchone()
    return row is not None


def list_conversations(search: str = "", limit: int = 100) -> list[dict[str, str]]:
    pattern = f"%{search.strip()}%"
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT all_sessions.session_id, "
            "COALESCE(meta.title, first_user.content, 'Conversation') AS title, "
            "COALESCE(all_sessions.last, '') AS last "
            "FROM ("
            "  SELECT session_id, MAX(created_at) AS last FROM conversations GROUP BY session_id "
            "  UNION SELECT session_id, '' AS last FROM conversation_metadata"
            ") AS all_sessions "
            "LEFT JOIN conversation_metadata AS meta ON meta.session_id = all_sessions.session_id "
            "LEFT JOIN conversations AS first_user ON first_user.id = ("
            "  SELECT id FROM conversations WHERE session_id = all_sessions.session_id AND role = 'user' "
            "  ORDER BY created_at ASC, id ASC LIMIT 1"
            ") "
            "WHERE (? = '%%' OR COALESCE(meta.title, first_user.content, '') LIKE ?) "
            "ORDER BY all_sessions.last DESC, all_sessions.session_id DESC LIMIT ?",
            (pattern, pattern, limit),
        ).fetchall()
    return [{"id": r["session_id"], "title": r["title"], "updated_at": r["last"]} for r in rows]


def load_conversation_entries(session_id: str, limit: int = 50) -> list[dict[str, str]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM conversations "
            "WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def rename_conversation(session_id: str, title: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_metadata (session_id, title) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET title = excluded.title",
            (session_id, title.strip()[:120] or "New conversation"),
        )


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
