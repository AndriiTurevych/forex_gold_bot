"""Durable append-only execution journal and deterministic replay primitives."""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class JournalEvent:
    seq: int
    event_type: str
    payload: dict


class SQLiteExecutionJournal:
    """Minimal durable journal using stdlib SQLite with a monotonic sequence."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "event_type TEXT NOT NULL, "
            "payload_json TEXT NOT NULL)"
        )
        self._conn.commit()

    def append(self, event_type: str, payload: dict) -> int:
        if not event_type.strip():
            raise ValueError("event_type is required")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        cur = self._conn.execute(
            "INSERT INTO events(event_type,payload_json) VALUES (?,?)", (event_type, encoded)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def read_from(self, seq_exclusive: int = 0) -> list[JournalEvent]:
        rows = self._conn.execute(
            "SELECT seq,event_type,payload_json FROM events WHERE seq>? ORDER BY seq ASC",
            (seq_exclusive,),
        ).fetchall()
        return [JournalEvent(int(s), str(t), json.loads(p)) for s, t, p in rows]

    def close(self) -> None:
        self._conn.close()


def replay(events: Iterable[JournalEvent], reducer, initial_state):
    state = initial_state
    last_seq = 0
    for event in events:
        if event.seq <= last_seq:
            raise ValueError("journal sequence must be strictly increasing")
        state = reducer(state, event)
        last_seq = event.seq
    return state
