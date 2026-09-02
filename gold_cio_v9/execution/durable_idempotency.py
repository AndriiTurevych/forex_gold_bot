"""Durable idempotency reservation for broker submissions.

The store is deliberately broker-neutral. A client order key is reserved before any
external submit call. Replays/restarts observe the persisted reservation and must not
submit the same logical order twice without explicit reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3


class ReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    SUBMITTED = "SUBMITTED"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class Reservation:
    order_key: str
    status: ReservationStatus
    broker_order_id: str | None


class DurableIdempotencyStore:
    """SQLite-backed atomic check-and-reserve store surviving process restart."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reservations ("
            "order_key TEXT PRIMARY KEY, "
            "status TEXT NOT NULL, "
            "broker_order_id TEXT NULL)"
        )

    def reserve_once(self, order_key: str) -> bool:
        if not order_key.strip():
            raise ValueError("order_key is required")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT 1 FROM reservations WHERE order_key=?", (order_key,)
            ).fetchone()
            if row is not None:
                self._conn.execute("ROLLBACK")
                return False
            self._conn.execute(
                "INSERT INTO reservations(order_key,status,broker_order_id) VALUES (?,?,NULL)",
                (order_key, ReservationStatus.RESERVED.value),
            )
            self._conn.execute("COMMIT")
            return True
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def mark_submitted(self, order_key: str, broker_order_id: str) -> None:
        if not broker_order_id.strip():
            raise ValueError("broker_order_id is required")
        current = self.get(order_key)
        if current is None:
            raise ValueError("order_key must be reserved before submit")
        if current.status is ReservationStatus.TERMINAL:
            raise ValueError("terminal reservation cannot be submitted")
        if current.status is ReservationStatus.SUBMITTED:
            if current.broker_order_id != broker_order_id:
                raise ValueError("broker order id mismatch for submitted reservation")
            return
        self._conn.execute(
            "UPDATE reservations SET status=?,broker_order_id=? WHERE order_key=?",
            (ReservationStatus.SUBMITTED.value, broker_order_id, order_key),
        )

    def mark_terminal(self, order_key: str) -> None:
        current = self.get(order_key)
        if current is None:
            raise ValueError("unknown order_key")
        self._conn.execute(
            "UPDATE reservations SET status=? WHERE order_key=?",
            (ReservationStatus.TERMINAL.value, order_key),
        )

    def get(self, order_key: str) -> Reservation | None:
        row = self._conn.execute(
            "SELECT order_key,status,broker_order_id FROM reservations WHERE order_key=?",
            (order_key,),
        ).fetchone()
        if row is None:
            return None
        return Reservation(str(row[0]), ReservationStatus(str(row[1])), row[2])

    def close(self) -> None:
        self._conn.close()
