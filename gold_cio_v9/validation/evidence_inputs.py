"""Strict loaders for external EXP-0001 evidence components.

These functions perform parsing and identity checks only. They never calculate
strategy signals or outcomes.
"""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Mapping

from gold_cio_v9.data.contract_master import ContractMaster, build_gc_contract_master
from gold_cio_v9.data.evidence_lineage import (
    AcquisitionLineageManifest,
    RollDecisionLineage,
    assert_acquisition_lineage_integrity,
)
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.exp0001_regimes import MacroEvent
from gold_cio_v9.validation.macro_calendar import MacroCalendarSnapshot, build_macro_calendar_snapshot


def _dt(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO datetime text")
    out = datetime.fromisoformat(value)
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return out


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO date text")
    return date.fromisoformat(value)


def _map(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def load_authoritative_bars_jsonl(path: str | Path) -> tuple[HistoricalBar, ...]:
    rows: list[HistoricalBar] = []
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            r = _map(json.loads(raw), f"bar line {lineno}")
            bar = HistoricalBar(
                instrument=str(r["instrument"]), contract=None if r.get("contract") is None else str(r["contract"]),
                event_time=_dt(r["event_time"], f"bar line {lineno} event_time"),
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]),
                volume=None if r.get("volume") is None else float(r["volume"]),
                quality_state=QualityState(str(r["quality_state"])), source_id=str(r["source_id"]),
                roll_method=RollMethod(str(r["roll_method"])), is_roll_window=bool(r.get("is_roll_window", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid authoritative bar at line {lineno}") from exc
        rows.append(bar)
    if not rows:
        raise ValueError("authoritative bars JSONL is empty")
    times = [b.event_time for b in rows]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("authoritative bars must already be globally chronological and unique")
    return tuple(rows)


def load_contract_master_json(path: str | Path) -> ContractMaster:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("specs") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("contract master JSON must be a list or object with specs")
    master = build_gc_contract_master(rows)
    if isinstance(raw, dict) and raw.get("master_hash") is not None and raw.get("master_hash") != master.master_hash:
        raise ValueError("declared contract master hash mismatch")
    return master


def load_acquisition_lineage_json(path: str | Path) -> AcquisitionLineageManifest:
    raw = _map(json.loads(Path(path).read_text(encoding="utf-8")), "acquisition lineage")
    decisions_raw = raw.get("decisions")
    windows_raw = raw.get("fetch_windows")
    if not isinstance(decisions_raw, list) or not decisions_raw:
        raise ValueError("acquisition lineage decisions are required")
    if not isinstance(windows_raw, list) or not windows_raw:
        raise ValueError("acquisition lineage fetch_windows are required")
    decisions = tuple(RollDecisionLineage(
        str(d["as_of"]), str(d["liquidity_session_date"]), str(d["selected_contract"]),
        tuple((str(k), float(v)) for k, v in d["volume_by_contract"]),
    ) for d in decisions_raw)
    manifest = AcquisitionLineageManifest(
        int(raw["roll_buffer_days"]), int(raw["roll_buffer_bars"]), decisions,
        tuple(tuple(str(v) for v in row) for row in windows_raw),
        str(raw["dataset_hash"]), str(raw["lineage_hash"]),
        int(raw["max_settlement_days_forward"]), str(raw["contract_master_hash"]),
    )
    assert_acquisition_lineage_integrity(manifest)
    return manifest


def load_macro_calendar_json(path: str | Path) -> MacroCalendarSnapshot:
    raw = _map(json.loads(Path(path).read_text(encoding="utf-8")), "macro calendar")
    events_raw = raw.get("events")
    if not isinstance(events_raw, list):
        raise ValueError("macro calendar events must be a list")
    events = tuple(MacroEvent(
        _dt(r["event_time"], "macro event_time"),
        _dt(r["known_at"], "macro known_at"),
        str(r["category"]),
    ) for r in events_raw)
    snapshot = build_macro_calendar_snapshot(
        coverage_start=_date(raw["coverage_start"], "coverage_start"),
        coverage_end=_date(raw["coverage_end"], "coverage_end"),
        source_id=str(raw["source_id"]), events=events,
    )
    if raw.get("calendar_hash") is not None and raw.get("calendar_hash") != snapshot.calendar_hash:
        raise ValueError("declared macro calendar hash mismatch")
    return snapshot
