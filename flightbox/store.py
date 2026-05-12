"""SQLite-based storage for recorded LLM sessions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = Path(".flightbox") / "recordings.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    name TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    seq INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    request TEXT,
    response TEXT,
    latency_ms REAL,
    token_usage TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
"""


class RecordStore:
    """Thin wrapper around a SQLite database for flight recordings."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- runs --

    def create_run(self, name: str | None = None, metadata: dict | None = None) -> str:
        run_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO runs (run_id, name, started_at, metadata) VALUES (?, ?, ?, ?)",
            (run_id, name, now, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE runs SET finished_at = ? WHERE run_id = ?", (now, run_id)
        )
        self.conn.commit()

    def list_runs(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def delete_run(self, run_id: str):
        self.conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
        self.conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        self.conn.commit()

    # -- events --

    def add_event(
        self,
        run_id: str,
        seq: int,
        event_type: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        request: Any = None,
        response: Any = None,
        latency_ms: float | None = None,
        token_usage: dict | None = None,
        error: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO events
               (run_id, seq, timestamp, event_type, provider, model,
                request, response, latency_ms, token_usage, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, seq, now, event_type, provider, model,
                json.dumps(request) if request else None,
                json.dumps(response) if response else None,
                latency_ms,
                json.dumps(token_usage) if token_usage else None,
                error,
            ),
        )
        self.conn.commit()

    def get_events(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_event_count(self, run_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0]

    def get_run_stats(self, run_id: str) -> dict[str, Any]:
        events = self.get_events(run_id)
        latencies = [
            float(ev["latency_ms"])
            for ev in events
            if ev.get("latency_ms") is not None
        ]

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        errors = 0

        for ev in events:
            if ev.get("error"):
                errors += 1

            usage_raw = ev.get("token_usage")
            if not usage_raw:
                continue
            usage = json.loads(usage_raw) if isinstance(usage_raw, str) else usage_raw
            if not isinstance(usage, dict):
                continue

            prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            completion = int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            )
            total = int(usage.get("total_tokens") or prompt + completion)

            prompt_tokens += prompt
            completion_tokens += completion
            total_tokens += total

        return {
            "events": len(events),
            "llm_calls": sum(1 for ev in events if ev["event_type"] == "llm_call"),
            "errors": errors,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms_total": sum(latencies),
            "latency_ms_avg": (sum(latencies) / len(latencies)) if latencies else 0,
        }
