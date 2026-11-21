import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS session_config (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT
);
"""


def init_db():
    db_path = settings.db_path
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_exists(session_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,)
        ).fetchone()
        return row is not None


def add_message(session_id: str, role: str, content: str, metadata: dict | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(metadata) if metadata is not None else None,
                now_iso(),
            ),
        )
        conn.commit()


def get_messages(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = {"role": row["role"], "content": row["content"]}
            if row["metadata"]:
                item["metadata"] = json.loads(row["metadata"])
            result.append(item)
        return result


def get_history_for_llm(session_id: str) -> list[dict]:
    """Plain role/content pairs for sending to the LLM (no metadata)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]


def set_system_prompt(session_id: str, system_prompt: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO session_config (session_id, system_prompt) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET system_prompt = excluded.system_prompt",
            (session_id, system_prompt),
        )
        conn.commit()


def get_system_prompt(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT system_prompt FROM session_config WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["system_prompt"] if row else None
