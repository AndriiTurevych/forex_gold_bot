"""Causal sequence assembly for preregistered EXP-0001.

Consumes the already-causal StreamEvent series and emits ReplaySetup objects only
when the locked event order is observed: sweep -> MSS -> FVG -> later retest.
No parameter search, repair, or future peeking occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gold_cio_v9.data.governance import HistoricalBar, eligible_for_signal_generation
from gold_cio_v9.experiments.exp0001_inputs import DirectionalPermission
from gold_cio_v9.experiments.exp0001_replay import ReplaySetup
from gold_cio_v9.experiments.exp0001_stream import ContextPoint, StreamEvent
from gold_cio_v9.ict_engine.features import Bar


@dataclass(frozen=True)
class _Pending:
    sweep_index: int
    sweep: object
    direction: str
    structure_index: int | None = None
    structure: object | None = None
    zone_index: int | None = None
    zone: object | None = None


def _bar(h: HistoricalBar) -> Bar:
    return Bar(h.event_time.isoformat(), h.open, h.high, h.low, h.close)


def _overlaps_zone(h: HistoricalBar, zone) -> bool:
    return h.high >= zone.low and h.low <= zone.high


def assemble_replay_setups(
    *,
    bars: Sequence[HistoricalBar],
    events: Sequence[StreamEvent],
    context: Sequence[ContextPoint],
    htf_permission: Mapping[int, DirectionalPermission],
    horizon_bars: int,
) -> tuple[ReplaySetup, ...]:
    """Assemble time-ordered EXP-0001 setups without discretionary repair.

    Rules:
    - SSL starts a LONG sequence; BSL starts a SHORT sequence.
    - matching MSS must occur strictly after the sweep.
    - matching-direction FVG must occur at/after MSS and strictly before retest.
    - first later eligible bar overlapping the FVG is the retest.
    - a new sweep replaces any unfinished sequence for the same direction.
    - all components must remain on the same raw futures contract.
    - opposing liquidity is the contemporaneous opposite reference level.
    - HTF permission is directional: LONG/SHORT cannot share one ambiguous bool.
    """
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    if not bars:
        raise ValueError("bars are required")
    if any(a.index >= b.index for a, b in zip(events, events[1:])):
        raise ValueError("events must be strictly ordered")

    ctx = {c.index: c for c in context}
    if len(ctx) != len(context):
        raise ValueError("duplicate context indices")
    if any(i < 0 or i >= len(bars) for i in ctx):
        raise ValueError("context index outside bars")

    event_by_index = {e.index: e for e in events}
    if len(event_by_index) != len(events):
        raise ValueError("duplicate event indices")
    if any(i < 0 or i >= len(bars) for i in event_by_index):
        raise ValueError("event index outside bars")

    pending: dict[str, _Pending | None] = {"LONG": None, "SHORT": None}
    out: list[ReplaySetup] = []

    for i, h in enumerate(bars):
        if not eligible_for_signal_generation(h):
            pending = {"LONG": None, "SHORT": None}
            continue
        e = event_by_index.get(i)
        c = ctx.get(i)
        if e is not None and c is None:
            raise ValueError("event missing contemporaneous context")

        if e and e.sweep is not None:
            direction = "LONG" if e.sweep.sweep.side == "SSL" else "SHORT"
            pending[direction] = _Pending(i, e.sweep, direction)

        for direction in ("LONG", "SHORT"):
            p = pending[direction]
            if p is None:
                continue
            if bars[p.sweep_index].contract != h.contract:
                pending[direction] = None
                continue

            if e and e.structure is not None and i > p.sweep_index and p.structure is None:
                expected = "BULLISH" if direction == "LONG" else "BEARISH"
                if e.structure.event.kind == "MSS" and e.structure.event.direction == expected:
                    p = _Pending(p.sweep_index, p.sweep, direction, i, e.structure)
                    pending[direction] = p

            if p.structure is not None and p.zone is None and e is not None and i >= p.structure_index:
                zone = e.bullish_fvg if direction == "LONG" else e.bearish_fvg
                if zone is not None:
                    p = _Pending(p.sweep_index, p.sweep, direction, p.structure_index, p.structure, i, zone)
                    pending[direction] = p
                    continue

            if p.zone is not None and i > p.zone_index and _overlaps_zone(h, p.zone):
                c_now = ctx.get(i)
                if c_now is None:
                    pending[direction] = None
                    continue
                target = c_now.reference_high if direction == "LONG" else c_now.reference_low
                permission = htf_permission.get(i, DirectionalPermission(False, False))
                out.append(
                    ReplaySetup(
                        setup_id=f"EXP-0001-{direction}-{h.event_time.isoformat()}",
                        signal_index=i,
                        htf_location_ok=permission.allows(direction),
                        sweep=p.sweep,
                        structure=p.structure,
                        zone=p.zone,
                        retest_time=h.event_time,
                        retest_bar=_bar(h),
                        sweep_depth=p.sweep.sweep.depth,
                        opposing_liquidity=target,
                        horizon_bars=horizon_bars,
                    )
                )
                pending[direction] = None

    return tuple(out)
