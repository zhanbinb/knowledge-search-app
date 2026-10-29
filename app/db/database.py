from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.models import utc_now

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    page_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '',
    page_number INTEGER,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'demo-user',
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    route TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER DEFAULT 0,
    error_code TEXT,
    route_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    tool_source TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    result_summary TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_retrieval_run ON retrieval_logs(run_id, stage);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            self._connection.commit()
            return cursor

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def create_document(
        self,
        *,
        document_id: str,
        filename: str,
        file_type: str,
        checksum: str,
        char_count: int,
        page_count: int,
    ) -> dict[str, Any]:
        now = utc_now()
        self._execute(
            """
            INSERT INTO documents(
                id, filename, file_type, checksum, status, page_count,
                char_count, chunk_count, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'PROCESSING', ?, ?, 0, NULL, ?, ?)
            """,
            (document_id, filename, file_type, checksum, page_count, char_count, now, now),
        )
        return self.get_document(document_id)

    def update_document(
        self,
        document_id: str,
        *,
        status: str,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, utc_now()]
        if chunk_count is not None:
            fields.append("chunk_count = ?")
            values.append(chunk_count)
        fields.append("error_message = ?")
        values.append(error_message)
        values.append(document_id)
        self._execute(f"UPDATE documents SET {', '.join(fields)} WHERE id = ?", tuple(values))
        return self.get_document(document_id)

    def save_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        self._execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        for item in chunks:
            self._execute(
                """
                INSERT INTO chunks(
                    id, document_id, content, heading_path, page_number,
                    chunk_index, char_start, char_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    document_id,
                    item["content"],
                    item["heading_path"],
                    item["page_number"],
                    item["chunk_index"],
                    item["char_start"],
                    item["char_end"],
                ),
            )

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM documents ORDER BY updated_at DESC")
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any]:
        row = self._query("SELECT * FROM documents WHERE id = ?", (document_id,))
        return dict(row[0]) if row else {}

    def get_document_by_checksum(self, checksum: str) -> dict[str, Any]:
        row = self._query("SELECT * FROM documents WHERE checksum = ?", (checksum,))
        return dict(row[0]) if row else {}

    def delete_document(self, document_id: str) -> None:
        self._execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = self._query(
            f"""
            SELECT c.*, d.filename
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.id IN ({placeholders})
            """,
            tuple(chunk_ids),
        )
        by_id = {row["id"]: dict(row) for row in rows}
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def all_chunks(self) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT c.*, d.filename
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE d.status = 'READY'
            ORDER BY c.document_id, c.chunk_index
            """
        )
        return [dict(row) for row in rows]

    def create_session(self, title: str = "新对话", user_id: str = "demo-user") -> dict[str, Any]:
        session_id = f"ses_{uuid.uuid4().hex}"
        now = utc_now()
        self._execute(
            "INSERT INTO sessions(id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, title, now, now),
        )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(rows[0]) if rows else {}

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM sessions ORDER BY updated_at DESC")
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        self._execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def add_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        message_id = f"msg_{uuid.uuid4().hex}"
        now = utc_now()
        self._execute(
            "INSERT INTO messages(id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, now),
        )
        self._execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }

    def list_messages(self, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT * FROM (
                SELECT * FROM messages WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, limit),
        )
        return [dict(row) for row in rows]

    def create_run(self, *, run_id: str, trace_id: str, session_id: str) -> dict[str, Any]:
        now = utc_now()
        self._execute(
            """
            INSERT INTO agent_runs(id, trace_id, session_id, route, status, created_at)
            VALUES (?, ?, ?, 'unknown', 'RUNNING', ?)
            """,
            (run_id, trace_id, session_id, now),
        )
        return self.get_run(run_id)

    def update_run(
        self,
        run_id: str,
        *,
        route: str,
        status: str,
        latency_ms: int = 0,
        error_code: str | None = None,
        route_reason: str = "",
    ) -> None:
        self._execute(
            """
            UPDATE agent_runs
            SET route = ?, status = ?, latency_ms = ?, error_code = ?, route_reason = ?
            WHERE id = ?
            """,
            (route, status, latency_ms, error_code, route_reason, run_id),
        )

    def add_tool_call(
        self,
        *,
        run_id: str,
        tool_name: str,
        tool_source: str,
        arguments: dict[str, Any],
        result_summary: str,
        status: str,
        latency_ms: int,
    ) -> str:
        call_id = f"call_{uuid.uuid4().hex}"
        self._execute(
            """
            INSERT INTO tool_calls(
                id, run_id, tool_name, tool_source, arguments_json,
                result_summary, status, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                run_id,
                tool_name,
                tool_source,
                json.dumps(arguments, ensure_ascii=False),
                result_summary,
                status,
                latency_ms,
                utc_now(),
            ),
        )
        return call_id

    def add_retrieval_logs(
        self, run_id: str, stage: str, items: list[dict[str, Any]]
    ) -> None:
        for rank, item in enumerate(items, start=1):
            self._execute(
                """
                INSERT INTO retrieval_logs(run_id, stage, chunk_id, rank, score, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stage,
                    item.get("chunk_id", ""),
                    rank,
                    float(item.get("score", 0)),
                    json.dumps(item.get("payload", {}), ensure_ascii=False),
                ),
            )

    def get_run(self, run_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
        return dict(rows[0]) if rows else {}

    def get_run_details(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if not run:
            return {}
        tool_rows = self._query(
            "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY created_at", (run_id,)
        )
        retrieval_rows = self._query(
            "SELECT * FROM retrieval_logs WHERE run_id = ? ORDER BY stage, rank",
            (run_id,),
        )
        run["tool_calls"] = [dict(row) for row in tool_rows]
        run["retrieval_logs"] = [dict(row) for row in retrieval_rows]
        return run
