"""Causal regime labels for the locked EXP-0001 validation policy V4."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Mapping, Sequence

from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.experiments.exp0001_evidence_book import EvidenceBook
from gold_cio_v9.ict_engine.sessions import DEFAULT_WINDOWS, in_window

ALLOWED_MACRO_CATEGORIES = frozenset({"FOMC", "FED_CHAIR", "CPI", "CORE_PCE", "NFP", "RETAIL_SALES"})
MACRO_BEFORE_MINUTES = 30
MACRO_AFTER_MINUTES = 30
VOL_LOOKBACK_DAYS = 20
VOL_HIGH_MIN = 1.25
VOL_LOW_MAX = 0.80


@dataclass(frozen=True)
class MacroEvent:
    event_time: datetime
    known_at: datetime
    category: str

    def __post_init__(self) -> None:
        for value in (self.event_time, self.known_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("macro event timestamps must be timezone-aware")
        if self.category not in ALLOWED_MACRO_CATEGORIES:
            raise ValueError("macro event category is outside locked policy")
        if self.known_at > self.event_time:
            raise ValueError("macro event cannot become known after its scheduled event time")


@dataclass(frozen=True)
class _DailyRange:
    day: object
    high: float
    low: float
    close: float
    true_range: float | None


def _daily_ranges(segment: Sequence[HistoricalBar]) -> tuple[_DailyRange, ...]:
    if not segment:
        raise ValueError("contract bars are required")
    contract = segment[0].contract
    if any(b.contract != contract for b in segment):
        raise ValueError("volatility regime must be computed within one raw contract")
    by_day: dict[object, list[HistoricalBar]] = {}
    for b in segment:
        by_day.setdefault(b.event_time.astimezone(timezone.utc).date(), []).append(b)
    days = sorted(by_day)
    out: list[_DailyRange] = []
    previous_close: float | None = None
    for day in days:
        rows = sorted(by_day[day], key=lambda b: b.event_time)
        hi = max(b.high for b in rows)
        lo = min(b.low for b in rows)
        close = rows[-1].close
        tr = None if previous_close is None else max(hi - lo, abs(hi - previous_close), abs(lo - previous_close))
        out.append(_DailyRange(day, hi, lo, close, tr))
        previous_close = close
    return tuple(out)


def _volatility_label(signal_time: datetime, daily: Sequence[_DailyRange]) -> str:
    day = signal_time.astimezone(timezone.utc).date()
    completed = [d for d in daily if d.day < day and d.true_range is not None]
    if len(completed) < VOL_LOOKBACK_DAYS + 1:
        raise ValueError("insufficient completed-day history for locked volatility regime")
    prior = completed[-1]
    history = completed[-(VOL_LOOKBACK_DAYS + 1):-1]
    base = median(d.true_range for d in history if d.true_range is not None)
    if base <= 0 or prior.true_range is None:
        raise ValueError("invalid volatility regime denominator")
    ratio = prior.true_range / base
    if ratio >= VOL_HIGH_MIN:
        return "VOL_HIGH"
    if ratio <= VOL_LOW_MAX:
        return "VOL_LOW"
    return "VOL_NORMAL"


def _session_label(signal_time: datetime) -> str:
    if in_window(signal_time, DEFAULT_WINDOWS["LONDON"]):
        return "LONDON"
    if in_window(signal_time, DEFAULT_WINDOWS["NY_AM"]):
        return "NY_AM"
    return "OTHER_SESSION"


def _macro_labels(signal_time: datetime, events: Sequence[MacroEvent]) -> tuple[str, ...]:
    visible = []
    for event in events:
        if event.known_at > signal_time:
            continue
        delta_minutes = (signal_time - event.event_time).total_seconds() / 60.0
        if -MACRO_BEFORE_MINUTES <= delta_minutes <= MACRO_AFTER_MINUTES:
            visible.append(event)
    if not visible:
        return ("NO_MACRO_WINDOW",)
    visible.sort(key=lambda e: (abs((signal_time - e.event_time).total_seconds()), e.category, e.event_time))
    nearest = visible[0]
    return ("MACRO_WINDOW", f"MACRO_{nearest.category}")


def build_regime_labels(
    *,
    bars: Sequence[HistoricalBar],
    book: EvidenceBook,
    macro_events: Sequence[MacroEvent],
    horizon_minutes: int = 60,
) -> Mapping[str, tuple[str, ...]]:
    """Return deterministic labels for every candidate at the requested horizon."""
    by_contract: dict[str, list[HistoricalBar]] = {}
    for b in bars:
        if b.instrument != "GC" or not b.contract:
            raise ValueError("regime labelling requires explicit raw GC contracts")
        if not b.is_roll_window:
            by_contract.setdefault(b.contract, []).append(b)
    daily = {contract: _daily_ranges(rows) for contract, rows in by_contract.items()}

    out: dict[str, tuple[str, ...]] = {}
    for trade in book.trades_for_horizon(horizon_minutes):
        if trade.candidate_id in out:
            raise ValueError("duplicate candidate ID in regime labelling")
        if trade.contract not in daily:
            raise ValueError("candidate contract missing from regime bars")
        labels = (
            _session_label(trade.signal_time),
            _volatility_label(trade.signal_time, daily[trade.contract]),
            *_macro_labels(trade.signal_time, macro_events),
        )
        out[trade.candidate_id] = tuple(labels)
    return out
