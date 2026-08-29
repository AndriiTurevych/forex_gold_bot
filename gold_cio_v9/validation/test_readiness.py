"""Fail-closed preflight gate for EXP-0001 before any strategy outcome exists.

This module inspects only immutable inputs and governance identities. It must never
run the strategy, score trades, inspect PnL, or choose among configurations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Sequence

from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_locked import (
    IMPLEMENTATION_POLICY_ID,
    LOCKED_BASE_COSTS,
    MAX_SETTLEMENT_DAYS_FORWARD,
    ROLL_BUFFER_BARS,
    ROLL_BUFFER_DAYS,
    VALIDATION_POLICY_ID,
    assert_locked_costs,
)
from gold_cio_v9.validation.evidence_bundle import EvidenceBundle
from gold_cio_v9.validation.exp0001_regimes import ALLOWED_MACRO_CATEGORIES
from gold_cio_v9.validation.macro_calendar import validate_macro_calendar_for_bars

_FORBIDDEN_SOURCE_MARKERS = ("test", "synthetic", "fixture", "mock", "sample")


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class TestReadinessReport:
    ready: bool
    implementation_policy: str
    validation_policy: str
    dataset_hash: str
    bundle_hash: str
    bars: int
    contracts: tuple[str, ...]
    coverage_start: str
    coverage_end: str
    macro_events: int
    checks: tuple[ReadinessCheck, ...]

    @property
    def failed_checks(self) -> tuple[ReadinessCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)


def _is_real_source(source_id: str) -> bool:
    text = source_id.strip().lower()
    return bool(text) and not any(marker in text for marker in _FORBIDDEN_SOURCE_MARKERS)


def _check(name: str, condition: bool, detail: str) -> ReadinessCheck:
    return ReadinessCheck(name, bool(condition), detail)


def assess_exp0001_test_readiness(bundle: EvidenceBundle) -> TestReadinessReport:
    bars: Sequence[HistoricalBar] = bundle.bars
    if not bars:
        raise ValueError("readiness requires evidence bars")

    manifest = build_gc_dataset_manifest(bars)
    validate_macro_calendar_for_bars(bundle.macro_calendar, bars)
    assert_locked_costs(bundle.base_costs)

    times = [b.event_time for b in bars]
    contracts = manifest.contracts
    first_day = min(t.astimezone(timezone.utc).date() for t in times)
    last_day = max(t.astimezone(timezone.utc).date() for t in times)

    lineage = bundle.acquisition_lineage
    fetch_contracts = tuple(row[0] for row in lineage.fetch_windows)
    decision_contracts: list[str] = []
    for d in lineage.decisions:
        if not decision_contracts or decision_contracts[-1] != d.selected_contract:
            decision_contracts.append(d.selected_contract)

    macro_categories = {e.category for e in bundle.macro_calendar.events}
    bad_categories = tuple(sorted(macro_categories - ALLOWED_MACRO_CATEGORIES))
    bar_sources = tuple(sorted({b.source_id for b in bars}))
    nonreal_bar_sources = tuple(s for s in bar_sources if not _is_real_source(s))

    checks = (
        _check("dataset_hash_bound", manifest.dataset_hash == bundle.dataset_hash == lineage.dataset_hash,
               "dataset, bundle and acquisition lineage must bind the same authoritative bars"),
        _check("contract_master_hash_present", bool(lineage.contract_master_hash.strip()),
               "immutable GC contract master hash must be present"),
        _check("contract_master_hash_bound", lineage.contract_master_hash == bundle.contract_master.master_hash,
               "embedded contract master must bind to acquisition lineage"),
        _check("roll_buffer_days_locked", lineage.roll_buffer_days == ROLL_BUFFER_DAYS,
               f"expected roll_buffer_days={ROLL_BUFFER_DAYS}, got {lineage.roll_buffer_days}"),
        _check("roll_buffer_bars_locked", lineage.roll_buffer_bars == ROLL_BUFFER_BARS,
               f"expected roll_buffer_bars={ROLL_BUFFER_BARS}, got {lineage.roll_buffer_bars}"),
        _check("settlement_horizon_locked", lineage.max_settlement_days_forward == MAX_SETTLEMENT_DAYS_FORWARD,
               f"expected max settlement horizon={MAX_SETTLEMENT_DAYS_FORWARD}"),
        _check("raw_contract_only", all(b.roll_method is RollMethod.RAW_CONTRACT for b in bars),
               "continuous adjusted prices are forbidden"),
        _check("authoritative_quality", all(b.quality_state in {QualityState.LIVE, QualityState.VERIFIED} for b in bars),
               "every bar must be LIVE or VERIFIED"),
        _check("no_roll_window_blackout", all(not b.is_roll_window for b in bars),
               "Baseline V5 uses zero additional roll-boundary blackout bars"),
        _check("real_bar_sources", not nonreal_bar_sources,
               "non-production source ids: " + ",".join(nonreal_bar_sources) if nonreal_bar_sources else "all bar source ids are non-test identities"),
        _check("fetch_contract_order", fetch_contracts == contracts,
               f"fetch windows {fetch_contracts} must equal manifest contracts {contracts}"),
        _check("decision_contract_order", tuple(decision_contracts) == contracts,
               f"roll decisions {tuple(decision_contracts)} must equal manifest contracts {contracts}"),
        _check("macro_source_real", _is_real_source(bundle.macro_calendar.source_id),
               f"macro source_id={bundle.macro_calendar.source_id!r} must be an external non-test identity"),
        _check("macro_events_present", len(bundle.macro_calendar.events) > 0,
               "formal evidence requires an actual event set, not only declared coverage"),
        _check("macro_categories_locked", not bad_categories,
               "unexpected macro categories: " + ",".join(bad_categories) if bad_categories else "all macro categories are preregistered"),
        _check("macro_known_at_causal", all(e.known_at <= e.event_time for e in bundle.macro_calendar.events),
               "every event must have known_at <= event_time"),
        _check("macro_full_coverage",
               bundle.macro_calendar.coverage_start <= first_day and bundle.macro_calendar.coverage_end >= last_day,
               f"macro coverage {bundle.macro_calendar.coverage_start}..{bundle.macro_calendar.coverage_end} vs bars {first_day}..{last_day}"),
        _check("locked_costs", bundle.base_costs == LOCKED_BASE_COSTS,
               "formal costs must exactly equal Baseline V5 locked costs"),
        _check("chronological_bars", all(b > a for a, b in zip(times, times[1:])),
               "evidence bars must be globally strictly chronological"),
    )
    return TestReadinessReport(
        ready=all(c.passed for c in checks),
        implementation_policy=IMPLEMENTATION_POLICY_ID,
        validation_policy=VALIDATION_POLICY_ID,
        dataset_hash=bundle.dataset_hash,
        bundle_hash=bundle.bundle_hash,
        bars=len(bars),
        contracts=contracts,
        coverage_start=first_day.isoformat(),
        coverage_end=last_day.isoformat(),
        macro_events=len(bundle.macro_calendar.events),
        checks=checks,
    )


def require_exp0001_test_ready(bundle: EvidenceBundle) -> TestReadinessReport:
    report = assess_exp0001_test_readiness(bundle)
    if not report.ready:
        failures = "; ".join(f"{c.name}: {c.detail}" for c in report.failed_checks)
        raise ValueError("EXP-0001 TEST_NOT_READY: " + failures)
    return report
