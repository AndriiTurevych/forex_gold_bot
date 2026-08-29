"""External governance attestation required for a binding EXP-0001 verdict.

The trading code cannot enable GitHub branch protection itself. A binding run must
therefore consume an immutable JSON attestation captured from repository governance
state and CI for the exact tested commit. Non-binding research runs may omit it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

REQUIRED_CHECKS = ("Gold CIO v9 CI", "Tester Trust Gate")


@dataclass(frozen=True)
class BindingGovernanceAttestation:
    repository: str
    branch: str
    head_sha: str
    branch_protected: bool
    required_status_checks_enforced: bool
    checks: tuple[tuple[str, str], ...]
    captured_at: datetime
    source: str
    attestation_hash: str


def _canonical_payload(
    *, repository: str, branch: str, head_sha: str, branch_protected: bool,
    required_status_checks_enforced: bool, checks: tuple[tuple[str, str], ...],
    captured_at: datetime, source: str,
) -> dict[str, object]:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("governance captured_at must be timezone-aware")
    if not repository.strip() or not branch.strip() or not head_sha.strip() or not source.strip():
        raise ValueError("governance identity fields are required")
    return {
        "repository": repository,
        "branch": branch,
        "head_sha": head_sha,
        "branch_protected": bool(branch_protected),
        "required_status_checks_enforced": bool(required_status_checks_enforced),
        "checks": [list(x) for x in sorted(checks)],
        "captured_at": captured_at.isoformat(),
        "source": source,
    }


def build_binding_governance_attestation(
    *, repository: str, branch: str, head_sha: str, branch_protected: bool,
    required_status_checks_enforced: bool, checks: Mapping[str, str],
    captured_at: datetime, source: str,
) -> BindingGovernanceAttestation:
    normalized = tuple(sorted((str(k), str(v).upper()) for k, v in checks.items()))
    payload = _canonical_payload(
        repository=repository, branch=branch, head_sha=head_sha,
        branch_protected=branch_protected,
        required_status_checks_enforced=required_status_checks_enforced,
        checks=normalized, captured_at=captured_at, source=source,
    )
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return BindingGovernanceAttestation(
        repository, branch, head_sha, branch_protected,
        required_status_checks_enforced, normalized, captured_at, source, digest,
    )


def dump_binding_governance_attestation(att: BindingGovernanceAttestation, path: str | Path) -> None:
    payload = _canonical_payload(
        repository=att.repository, branch=att.branch, head_sha=att.head_sha,
        branch_protected=att.branch_protected,
        required_status_checks_enforced=att.required_status_checks_enforced,
        checks=att.checks, captured_at=att.captured_at, source=att.source,
    )
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != att.attestation_hash:
        raise ValueError("governance attestation identity mismatch")
    Path(path).write_text(json.dumps({"attestation_hash": digest, "payload": payload}, sort_keys=True, indent=2), encoding="utf-8")


def load_binding_governance_attestation(path: str | Path) -> BindingGovernanceAttestation:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("governance attestation payload is required")
    captured_at = datetime.fromisoformat(str(payload.get("captured_at", "")))
    checks_raw = payload.get("checks")
    if not isinstance(checks_raw, list):
        raise ValueError("governance checks are required")
    checks = {str(row[0]): str(row[1]) for row in checks_raw if isinstance(row, list) and len(row) == 2}
    att = build_binding_governance_attestation(
        repository=str(payload.get("repository", "")), branch=str(payload.get("branch", "")),
        head_sha=str(payload.get("head_sha", "")), branch_protected=bool(payload.get("branch_protected")),
        required_status_checks_enforced=bool(payload.get("required_status_checks_enforced")),
        checks=checks, captured_at=captured_at, source=str(payload.get("source", "")),
    )
    if raw.get("attestation_hash") != att.attestation_hash:
        raise ValueError("governance attestation hash mismatch")
    return att


def require_binding_governance(
    att: BindingGovernanceAttestation,
    *, expected_repository: str,
    expected_branch: str,
    expected_head_sha: str,
) -> None:
    if att.repository != expected_repository or att.branch != expected_branch:
        raise ValueError("binding governance repository/branch mismatch")
    if att.head_sha != expected_head_sha:
        raise ValueError("binding governance attestation is not for tested commit")
    if not att.branch_protected:
        raise ValueError("binding run blocked: branch protection is not enabled")
    if not att.required_status_checks_enforced:
        raise ValueError("binding run blocked: required status checks are not enforced")
    statuses = dict(att.checks)
    missing = [name for name in REQUIRED_CHECKS if statuses.get(name) != "SUCCESS"]
    if missing:
        raise ValueError("binding run blocked: required checks not green: " + ", ".join(missing))
