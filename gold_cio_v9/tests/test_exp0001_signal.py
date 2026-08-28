from datetime import datetime, timedelta, timezone

from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep, generate_exp0001_signal
from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent

T0 = datetime(2026, 1, 5, 13, 30, tzinfo=timezone.utc)


def _bar(close=100.5, low=100.0, high=101.0):
    return Bar(T0.isoformat(), 100.4, high, low, close)


def _long_components():
    sweep = TimedSweep(T0, Sweep("SSL", 99.5, 0.5))
    structure = TimedStructure(T0 + timedelta(minutes=1), StructureEvent("MSS", "BULLISH", 100.2, 101.0, 1.0))
    zone = FVGZone(T0 + timedelta(minutes=2), 100.0, 100.8, "BULLISH")
    return sweep, structure, zone


def test_locked_sequence_emits_long_on_bullish_retest():
    sweep, structure, zone = _long_components()
    signal = generate_exp0001_signal(
        htf_location_ok=True,
        sweep=sweep,
        structure=structure,
        zone=zone,
        retest_time=T0 + timedelta(minutes=3),
        retest_bar=_bar(),
    )
    assert signal is not None
    assert signal.direction == "LONG"
    assert signal.entry_price == 100.5


def test_wrong_event_order_is_rejected():
    sweep, structure, zone = _long_components()
    signal = generate_exp0001_signal(
        htf_location_ok=True,
        sweep=sweep,
        structure=structure,
        zone=zone,
        retest_time=T0 + timedelta(minutes=2),
        retest_bar=_bar(),
    )
    assert signal is None


def test_non_mss_structure_is_rejected():
    sweep, _, zone = _long_components()
    structure = TimedStructure(T0 + timedelta(minutes=1), StructureEvent("CHOCH", "BULLISH", 100.2, 101.0, 0.5))
    assert generate_exp0001_signal(
        htf_location_ok=True, sweep=sweep, structure=structure, zone=zone,
        retest_time=T0 + timedelta(minutes=3), retest_bar=_bar()
    ) is None


def test_direction_mismatch_is_rejected():
    sweep, structure, _ = _long_components()
    zone = FVGZone(T0 + timedelta(minutes=2), 100.0, 100.8, "BEARISH")
    assert generate_exp0001_signal(
        htf_location_ok=True, sweep=sweep, structure=structure, zone=zone,
        retest_time=T0 + timedelta(minutes=3), retest_bar=_bar()
    ) is None


def test_no_htf_permission_no_signal():
    sweep, structure, zone = _long_components()
    assert generate_exp0001_signal(
        htf_location_ok=False, sweep=sweep, structure=structure, zone=zone,
        retest_time=T0 + timedelta(minutes=3), retest_bar=_bar()
    ) is None


def test_zone_must_actually_be_retested():
    sweep, structure, zone = _long_components()
    bar = Bar(T0.isoformat(), 102.0, 102.2, 101.5, 102.1)
    assert generate_exp0001_signal(
        htf_location_ok=True, sweep=sweep, structure=structure, zone=zone,
        retest_time=T0 + timedelta(minutes=3), retest_bar=bar
    ) is None
