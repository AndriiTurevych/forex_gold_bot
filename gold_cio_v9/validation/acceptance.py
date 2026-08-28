"""Deterministic ACCEPT/REJECT evaluator for Gold CIO v9.1 EXP-0001."""
from dataclasses import dataclass


MAX_AMBIGUITY_RATE = 0.05


@dataclass(frozen=True)
class ValidationMetrics:
    oos_expectancy: float
    oos_profit_factor: float
    raw_oos_setups: int
    effective_sample_ok: bool
    walk_forward_stable: bool
    holdout_expectancy: float
    dsr_ok: bool
    pbo: float
    expectancy_cost_1_5x: float
    top_trade_removal_ok: bool
    concentration_ok: bool
    catastrophic_regime: bool
    data_integrity_ok: bool
    post_result_parameter_edits: bool
    ambiguous_oos_setups: int = 0
    ambiguity_rate: float = 0.0


@dataclass(frozen=True)
class AcceptanceDecision:
    accepted: bool
    failed_gates: tuple[str, ...]


def evaluate_exp0001(m: ValidationMetrics) -> AcceptanceDecision:
    failed: list[str] = []
    if m.oos_expectancy <= 0:
        failed.append("OOS_EXPECTANCY")
    if m.oos_profit_factor < 1.30:
        failed.append("OOS_PROFIT_FACTOR")
    # raw_oos_setups is precommitted to mean RESOLVED OOS setups only.
    # Same-bar ambiguous outcomes are excluded from realized-R metrics and do
    # not count toward the >=200 sample requirement.
    if m.raw_oos_setups < 200:
        failed.append("RAW_OOS_SAMPLE")
    if m.ambiguous_oos_setups < 0 or not 0.0 <= m.ambiguity_rate <= 1.0:
        failed.append("DATA_RESOLUTION_RISK")
    elif m.ambiguity_rate > MAX_AMBIGUITY_RATE:
        failed.append("DATA_RESOLUTION_RISK")
    if not m.effective_sample_ok:
        failed.append("EFFECTIVE_INDEPENDENCE")
    if not m.walk_forward_stable:
        failed.append("WALK_FORWARD_STABILITY")
    if m.holdout_expectancy <= 0:
        failed.append("UNTOUCHED_HOLDOUT")
    if not m.dsr_ok:
        failed.append("DEFLATED_SHARPE")
    if m.pbo >= 0.20:
        failed.append("PBO")
    if m.expectancy_cost_1_5x <= 0:
        failed.append("COST_STRESS_1_5X")
    if not m.top_trade_removal_ok:
        failed.append("TOP_TRADE_DEPENDENCE")
    if not m.concentration_ok:
        failed.append("PNL_CONCENTRATION")
    if m.catastrophic_regime:
        failed.append("CATASTROPHIC_REGIME")
    if not m.data_integrity_ok:
        failed.append("DATA_INTEGRITY")
    if m.post_result_parameter_edits:
        failed.append("POST_RESULT_PARAMETER_EDIT")
    return AcceptanceDecision(not failed, tuple(failed))
