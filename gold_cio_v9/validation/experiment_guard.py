"""Technical enforcement for preregistered experiment reruns.

The purpose is to prevent silent config changes or informal reruns of an
experiment after results are observed. Every repeat execution must become a
new registered trial and, when the configuration changes, must include an
explicit reason that is persisted in the trial metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .trials import TrialsRegistry, make_config_hash


class ExperimentRerunPolicyError(RuntimeError):
    """Raised when a rerun violates the preregistration policy."""


@dataclass(frozen=True)
class RerunAuthorization:
    experiment_id: str
    prior_trial_id: str | None
    prior_config_hash: str | None
    new_config_hash: str
    rerun_reason: str | None
    config_changed: bool


def authorize_rerun(
    *,
    registry: TrialsRegistry,
    experiment_id: str,
    config: dict[str, Any],
    rerun_reason: str | None = None,
) -> RerunAuthorization:
    """Authorize a new trial under the Rejection Constitution.

    Rules:
    1. First execution of an experiment requires no rerun reason.
    2. Every later execution is a new trial by construction.
    3. If config changed, an explicit non-empty rerun_reason is mandatory.
    4. Silent config mutation is a hard failure.

    This function intentionally does not allow an in-place modification of a
    previous trial. The caller must register a fresh TrialRecord after this
    authorization succeeds.
    """
    new_hash = make_config_hash(config)
    prior = [r for r in registry.read_all() if r.get("experiment_id") == experiment_id]
    if not prior:
        return RerunAuthorization(experiment_id, None, None, new_hash, None, False)

    latest = prior[-1]
    prior_hash = str(latest["config_hash"])
    changed = prior_hash != new_hash

    if changed and not (rerun_reason and rerun_reason.strip()):
        raise ExperimentRerunPolicyError(
            f"CONFIG_CHANGE_REQUIRES_REASON:{experiment_id}:{prior_hash[:12]}->{new_hash[:12]}"
        )

    return RerunAuthorization(
        experiment_id=experiment_id,
        prior_trial_id=str(latest["trial_id"]),
        prior_config_hash=prior_hash,
        new_config_hash=new_hash,
        rerun_reason=rerun_reason.strip() if rerun_reason else None,
        config_changed=changed,
    )
