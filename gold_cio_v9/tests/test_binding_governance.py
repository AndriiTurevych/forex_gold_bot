from datetime import datetime, timezone
import json

import pytest

from gold_cio_v9.validation.binding_governance import (
    build_binding_governance_attestation,
    dump_binding_governance_attestation,
    load_binding_governance_attestation,
    require_binding_governance,
)


def _att(*, protected=True, enforced=True, head="abc123", ci="SUCCESS", trust="SUCCESS"):
    return build_binding_governance_attestation(
        repository="AndriiTurevych/forex_gold_bot",
        branch="gold-cio-v9",
        head_sha=head,
        branch_protected=protected,
        required_status_checks_enforced=enforced,
        checks={"Gold CIO v9 CI": ci, "Tester Trust Gate": trust},
        captured_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
        source="github-api:v1",
    )


def _require(att):
    return require_binding_governance(
        att,
        expected_repository="AndriiTurevych/forex_gold_bot",
        expected_branch="gold-cio-v9",
        expected_head_sha="abc123",
    )


def test_green_protected_attestation_passes():
    _require(_att())


def test_unprotected_branch_blocks_binding():
    with pytest.raises(ValueError, match="branch protection"):
        _require(_att(protected=False))


def test_unenforced_required_checks_blocks_binding():
    with pytest.raises(ValueError, match="required status checks"):
        _require(_att(enforced=False))


def test_red_required_check_blocks_binding():
    with pytest.raises(ValueError, match="required checks not green"):
        _require(_att(ci="FAILURE"))


def test_wrong_commit_blocks_binding():
    with pytest.raises(ValueError, match="not for tested commit"):
        _require(_att(head="other"))


def test_attestation_round_trip_and_tamper_detection(tmp_path):
    p = tmp_path / "attestation.json"
    dump_binding_governance_attestation(_att(), p)
    loaded = load_binding_governance_attestation(p)
    assert loaded.attestation_hash == _att().attestation_hash
    raw = json.loads(p.read_text())
    raw["payload"]["branch_protected"] = False
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_binding_governance_attestation(p)
