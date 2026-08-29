"""Portable, hash-bound input bundle for the formal EXP-0001 evidence run."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest, RollDecisionLineage
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.exp0001_regimes import MacroEvent
from gold_cio_v9.validation.macro_calendar import MacroCalendarSnapshot, build_macro_calendar_snapshot, validate_macro_calendar_for_bars

BUNDLE_SCHEMA = "gold-cio-exp0001-evidence-bundle-v2"


@dataclass(frozen=True)
class EvidenceBundle:
    bars: tuple[HistoricalBar, ...]
    acquisition_lineage: AcquisitionLineageManifest
    macro_calendar: MacroCalendarSnapshot
    base_costs: CostAssumptions
    dataset_hash: str
    bundle_hash: str


def _stable_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


def _bar_payload(b: HistoricalBar) -> dict[str, Any]:
    return {
        "instrument": b.instrument, "contract": b.contract, "event_time": b.event_time.isoformat(),
        "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume,
        "quality_state": b.quality_state.value, "source_id": b.source_id,
        "roll_method": b.roll_method.value, "is_roll_window": b.is_roll_window,
    }


def _lineage_payload(m: AcquisitionLineageManifest) -> dict[str, Any]:
    return {
        "roll_buffer_days": m.roll_buffer_days, "roll_buffer_bars": m.roll_buffer_bars,
        "decisions": [asdict(d) for d in m.decisions],
        "fetch_windows": [list(x) for x in m.fetch_windows],
        "dataset_hash": m.dataset_hash, "lineage_hash": m.lineage_hash,
    }


def _macro_payload(m: MacroCalendarSnapshot) -> dict[str, Any]:
    return {
        "coverage_start": m.coverage_start.isoformat(),
        "coverage_end": m.coverage_end.isoformat(),
        "source_id": m.source_id,
        "calendar_hash": m.calendar_hash,
        "events": [
            {"event_time": e.event_time.isoformat(), "known_at": e.known_at.isoformat(), "category": e.category}
            for e in m.events
        ],
    }


def canonical_bundle_payload(
    *, bars: Sequence[HistoricalBar], acquisition_lineage: AcquisitionLineageManifest,
    macro_calendar: MacroCalendarSnapshot, base_costs: CostAssumptions,
) -> dict[str, Any]:
    materialized = tuple(bars)
    manifest = build_gc_dataset_manifest(materialized)
    if acquisition_lineage.dataset_hash != manifest.dataset_hash:
        raise ValueError("acquisition lineage does not bind to authoritative bars")
    validate_macro_calendar_for_bars(macro_calendar, materialized)
    if base_costs.stress_multiple != 1.0:
        raise ValueError("bundle base costs must use stress_multiple=1.0")
    return {
        "schema": BUNDLE_SCHEMA,
        "dataset_hash": manifest.dataset_hash,
        "bars": [_bar_payload(b) for b in materialized],
        "acquisition_lineage": _lineage_payload(acquisition_lineage),
        "macro_calendar": _macro_payload(macro_calendar),
        "base_costs": asdict(base_costs),
    }


def build_evidence_bundle(
    *, bars: Sequence[HistoricalBar], acquisition_lineage: AcquisitionLineageManifest,
    macro_calendar: MacroCalendarSnapshot, base_costs: CostAssumptions,
) -> EvidenceBundle:
    materialized = tuple(bars)
    payload = canonical_bundle_payload(
        bars=materialized, acquisition_lineage=acquisition_lineage,
        macro_calendar=macro_calendar, base_costs=base_costs,
    )
    return EvidenceBundle(materialized, acquisition_lineage, macro_calendar, base_costs, payload["dataset_hash"], _stable_hash(payload))


def dump_evidence_bundle(bundle: EvidenceBundle, path: str | Path) -> None:
    payload = canonical_bundle_payload(
        bars=bundle.bars, acquisition_lineage=bundle.acquisition_lineage,
        macro_calendar=bundle.macro_calendar, base_costs=bundle.base_costs,
    )
    computed = _stable_hash(payload)
    if computed != bundle.bundle_hash or payload["dataset_hash"] != bundle.dataset_hash:
        raise ValueError("bundle identity mismatch")
    Path(path).write_text(json.dumps({"bundle_hash": bundle.bundle_hash, "payload": payload}, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def _parse_dt(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO datetime text")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return dt


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO date text")
    return date.fromisoformat(value)


def _require_map(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def load_evidence_bundle(path: str | Path) -> EvidenceBundle:
    envelope = _require_map(json.loads(Path(path).read_text(encoding="utf-8")), "bundle")
    payload = _require_map(envelope.get("payload"), "payload")
    if payload.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("unsupported evidence bundle schema")
    expected_hash = envelope.get("bundle_hash")
    if not isinstance(expected_hash, str) or _stable_hash(payload) != expected_hash:
        raise ValueError("evidence bundle hash mismatch")

    bars_raw = payload.get("bars")
    if not isinstance(bars_raw, list) or not bars_raw:
        raise ValueError("bundle bars are required")
    bars = tuple(HistoricalBar(
        instrument=r["instrument"], contract=r.get("contract"), event_time=_parse_dt(r["event_time"], "event_time"),
        open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]),
        volume=None if r.get("volume") is None else float(r["volume"]),
        quality_state=QualityState(r["quality_state"]), source_id=str(r["source_id"]),
        roll_method=RollMethod(r["roll_method"]), is_roll_window=bool(r.get("is_roll_window", False)),
    ) for r in bars_raw)

    lm = _require_map(payload.get("acquisition_lineage"), "acquisition_lineage")
    decisions_raw = lm.get("decisions")
    if not isinstance(decisions_raw, list) or not decisions_raw:
        raise ValueError("lineage decisions are required")
    decisions = tuple(RollDecisionLineage(
        str(d["as_of"]), str(d["liquidity_session_date"]), str(d["selected_contract"]),
        tuple((str(k), float(v)) for k, v in d["volume_by_contract"]),
    ) for d in decisions_raw)
    fetch_windows_raw = lm.get("fetch_windows")
    if not isinstance(fetch_windows_raw, list) or not fetch_windows_raw:
        raise ValueError("lineage fetch windows are required")
    lineage = AcquisitionLineageManifest(
        int(lm["roll_buffer_days"]), int(lm["roll_buffer_bars"]), decisions,
        tuple(tuple(str(x) for x in row) for row in fetch_windows_raw),
        str(lm["dataset_hash"]), str(lm["lineage_hash"]),
    )

    mm = _require_map(payload.get("macro_calendar"), "macro_calendar")
    events_raw = mm.get("events")
    if not isinstance(events_raw, list):
        raise ValueError("macro calendar events must be a list")
    events = tuple(MacroEvent(_parse_dt(r["event_time"], "macro event_time"), _parse_dt(r["known_at"], "macro known_at"), str(r["category"])) for r in events_raw)
    macro = build_macro_calendar_snapshot(
        coverage_start=_parse_date(mm["coverage_start"], "macro coverage_start"),
        coverage_end=_parse_date(mm["coverage_end"], "macro coverage_end"),
        source_id=str(mm["source_id"]), events=events,
    )
    if macro.calendar_hash != mm.get("calendar_hash"):
        raise ValueError("macro calendar hash mismatch")

    costs_raw = _require_map(payload.get("base_costs"), "base_costs")
    costs = CostAssumptions(**{k: float(v) for k, v in costs_raw.items()})
    manifest = build_gc_dataset_manifest(bars)
    if manifest.dataset_hash != payload.get("dataset_hash"):
        raise ValueError("bundle dataset hash does not match bars")
    if lineage.dataset_hash != manifest.dataset_hash:
        raise ValueError("lineage dataset hash does not match bars")
    rebuilt = canonical_bundle_payload(bars=bars, acquisition_lineage=lineage, macro_calendar=macro, base_costs=costs)
    if _stable_hash(rebuilt) != expected_hash:
        raise ValueError("bundle canonical replay mismatch")
    return EvidenceBundle(bars, lineage, macro, costs, manifest.dataset_hash, expected_hash)
