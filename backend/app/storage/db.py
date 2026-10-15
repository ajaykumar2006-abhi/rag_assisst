"""SQLite metadata persistence.

Structured, low-volume state lives here: documents, pipeline stage progress,
chunk metadata, conversations, request events and evaluation runs. Chunk *text*
is also stored so citations and the source viewer work without re-reading files.

The heavy numeric payload (the embedding matrix) lives in the on-disk vector
index instead -- see ``app/storage/vector_store.py``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    page_count INTEGER,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    embedding_provider TEXT NOT NULL DEFAULT '',
    embedding_dim INTEGER NOT NULL DEFAULT 0,
    answer_provider TEXT NOT NULL DEFAULT '',
    indexed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stages (
    document_id TEXT NOT NULL,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    state TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY (document_id, name)
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    page INTEGER,
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL DEFAULT 0,
    char_end INTEGER NOT NULL DEFAULT 0,
    token_estimate INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    document_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]',
    answer_mode TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    latency_ms REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    top_k INTEGER NOT NULL,
    metrics TEXT NOT NULL,
    cases TEXT NOT NULL,
    result_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
"""


def utcnow() -> str:
    """ISO-8601 UTC timestamp (second precision is plenty here)."""
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Database:
    """Thin, thread-safe wrapper around a single SQLite file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- connection handling -------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        existing = getattr(self._local, "conn", None)
        if existing is None:
            existing = self._connect()
            self._local.conn = existing
        return existing

    @contextmanager
    def write(self):
        """Serialise writes so concurrent uploads cannot interleave."""
        with self._write_lock:
            conn = self.conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self) -> None:
        existing = getattr(self._local, "conn", None)
        if existing is not None:
            existing.close()
            self._local.conn = None

    # -- documents -----------------------------------------------------
    def create_document(self, record: Dict[str, Any]) -> None:
        now = utcnow()
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    id, filename, stored_path, extension, size_bytes, sha256, status,
                    error, page_count, chunk_count, char_count, embedding_provider,
                    embedding_dim, answer_provider, indexed, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["id"],
                    record["filename"],
                    record["stored_path"],
                    record["extension"],
                    record["size_bytes"],
                    record["sha256"],
                    record.get("status", "queued"),
                    record.get("error"),
                    record.get("page_count"),
                    record.get("chunk_count", 0),
                    record.get("char_count", 0),
                    record.get("embedding_provider", ""),
                    record.get("embedding_dim", 0),
                    record.get("answer_provider", ""),
                    int(record.get("indexed", False)),
                    now,
                    now,
                ),
            )

    def update_document(self, document_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        if "indexed" in fields:
            fields["indexed"] = int(bool(fields["indexed"]))
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [document_id]
        with self.write() as conn:
            conn.execute(f"UPDATE documents SET {columns} WHERE id = ?", values)

    def get_document(self, document_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()

    def list_documents(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM documents ORDER BY created_at DESC"))

    def delete_document(self, document_id: str) -> None:
        with self.write() as conn:
            for statement in (
                "DELETE FROM chunks WHERE document_id = ?",
                "DELETE FROM stages WHERE document_id = ?",
                "DELETE FROM documents WHERE id = ?",
            ):
                conn.execute(statement, (document_id,))

    def count_by_status(self) -> Dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) AS n FROM documents GROUP BY status")
        return {row["status"]: row["n"] for row in rows}

    # -- stages --------------------------------------------------------
    def reset_stages(self, document_id: str, stages: Iterable[Dict[str, Any]]) -> None:
        with self.write() as conn:
            conn.execute("DELETE FROM stages WHERE document_id = ?", (document_id,))
            conn.executemany(
                """
                INSERT INTO stages (document_id, name, label, state, detail, progress, started_at, finished_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        document_id,
                        stage["name"],
                        stage["label"],
                        stage.get("state", "pending"),
                        stage.get("detail", ""),
                        stage.get("progress", 0.0),
                        stage.get("started_at"),
                        stage.get("finished_at"),
                    )
                    for stage in stages
                ],
            )

    def set_stage(
        self,
        document_id: str,
        name: str,
        *,
        state: str,
        detail: str = "",
        progress: float = 0.0,
        touch_started: bool = False,
    ) -> None:
        now = utcnow()
        with self.write() as conn:
            conn.execute(
                """
                UPDATE stages
                   SET state = ?, detail = ?, progress = ?,
                       started_at = COALESCE(started_at, ?),
                       finished_at = CASE WHEN ? IN ('completed','failed') THEN ? ELSE finished_at END
                 WHERE document_id = ? AND name = ?
                """,
                (state, detail, progress, now if touch_started else None, state, now, document_id, name),
            )

    def get_stages(self, document_id: str) -> List[sqlite3.Row]:
        return list(
            self.conn.execute("SELECT * FROM stages WHERE document_id = ? ORDER BY rowid", (document_id,))
        )

    # -- chunks --------------------------------------------------------
    def insert_chunks(self, chunks: Iterable[Dict[str, Any]]) -> None:
        rows = [
            (
                chunk["id"],
                chunk["document_id"],
                chunk["ordinal"],
                chunk.get("page"),
                chunk["text"],
                chunk.get("char_start", 0),
                chunk.get("char_end", 0),
                chunk.get("token_estimate", 0),
            )
            for chunk in chunks
        ]
        if not rows:
            return
        with self.write() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                    (id, document_id, ordinal, page, text, char_start, char_end, token_estimate)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                rows,
            )

    def get_chunks(self, document_id: str) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal", (document_id,)
            )
        )

    def get_chunk(self, chunk_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()

    def chunk_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"]) if row else 0

    # -- conversations -------------------------------------------------
    def create_conversation(self, title: str, document_ids: List[str]) -> str:
        conversation_id = new_id("conv")
        now = utcnow()
        with self.write() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, document_ids, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conversation_id, title, json.dumps(document_ids), now, now),
            )
        return conversation_id

    def touch_conversation(self, conversation_id: str) -> None:
        with self.write() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (utcnow(), conversation_id)
            )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        answer_mode: Optional[str] = None,
    ) -> str:
        message_id = new_id("msg")
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, citations, answer_mode, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    json.dumps(citations or []),
                    answer_mode,
                    utcnow(),
                ),
            )
        return message_id

    def get_conversation(self, conversation_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()

    def list_conversations(self) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                  FROM conversations c
              ORDER BY c.updated_at DESC
                """
            )
        )

    def get_messages(self, conversation_id: str) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                (conversation_id,),
            )
        )

    def clear_conversations(self) -> int:
        with self.write() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM conversations")
        return int(count)

    # -- events --------------------------------------------------------
    def log_event(self, kind: str, payload: Optional[Dict[str, Any]] = None, latency_ms: float = 0.0) -> None:
        with self.write() as conn:
            conn.execute(
                "INSERT INTO events (id, kind, payload, latency_ms, created_at) VALUES (?,?,?,?,?)",
                (new_id("evt"), kind, json.dumps(payload or {}), float(latency_ms), utcnow()),
            )

    def event_stats(self) -> Dict[str, Any]:
        rows = list(
            self.conn.execute(
                "SELECT kind, COUNT(*) AS n, AVG(latency_ms) AS avg_ms FROM events GROUP BY kind"
            )
        )
        stats: Dict[str, Any] = {row["kind"]: {"count": row["n"], "avg_ms": row["avg_ms"] or 0.0} for row in rows}
        latencies = [
            row["latency_ms"]
            for row in self.conn.execute(
                "SELECT latency_ms FROM events WHERE kind = 'answer' ORDER BY latency_ms"
            )
        ]
        return {"kinds": stats, "answer_latencies": latencies}

    # -- evaluation ----------------------------------------------------
    def save_eval_run(self, run: Dict[str, Any]) -> None:
        with self.write() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_runs
                    (id, dataset, created_at, sample_count, top_k, metrics, cases, result_path)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    run["run_id"],
                    run["dataset"],
                    run["created_at"],
                    run["sample_count"],
                    run["top_k"],
                    json.dumps(run["metrics"]),
                    json.dumps(run["cases"]),
                    run.get("result_path"),
                ),
            )

    def list_eval_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [
            {
                "run_id": row["id"],
                "dataset": row["dataset"],
                "created_at": row["created_at"],
                "sample_count": row["sample_count"],
                "top_k": row["top_k"],
                "metrics": json.loads(row["metrics"]),
                "result_path": row["result_path"],
            }
            for row in rows
        ]
