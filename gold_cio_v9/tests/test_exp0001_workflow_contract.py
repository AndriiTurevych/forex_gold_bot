from pathlib import Path


WORKFLOW = Path('.github/workflows/exp0001-nonbinding.yml')


def _text() -> str:
    return WORKFLOW.read_text(encoding='utf-8')


def test_formal_workflow_requires_manual_confirmation_contract():
    text = _text()
    assert 'workflow_dispatch:' in text
    assert 'confirmation:' in text
    assert 'Type EXP-0001 to authorize a formal outcome-generating run' in text
    assert 'test "$CONFIRMATION" = "$EXP_ID"' in text


def test_formal_workflow_is_nonbinding_and_hash_bound():
    text = _text()
    assert '--mode nonbinding' in text
    assert '--git-commit "$GITHUB_SHA"' in text
    assert 'evidence_bundle.json' in text
    assert 'evidence_ledger.jsonl' in text
    assert 'trials.jsonl' in text


def test_formal_workflow_fails_closed_before_outcomes():
    text = _text()
    credential = text.index('Verify Massive credential exists')
    entitlement = text.index('Verify Massive Futures entitlement before bulk acquisition')
    qa = text.index('Run full unit and trust suites before evidence')
    acquire = text.index('Acquire authoritative GC evidence')
    preflight = text.index('Zero-outcome readiness preflight')
    formal = text.index('Run EXP-0001 nonbinding formal test')
    assert credential < entitlement < qa < acquire < preflight < formal
    assert "MASSIVE_API_KEY: ${{ secrets.MASSIVE_API_KEY }}" in text
    assert 'set -euo pipefail' in text


def test_formal_workflow_preserves_artifacts_and_prevents_overlap():
    text = _text()
    assert 'cancel-in-progress: false' in text
    assert 'if: always()' in text
    assert 'retention-days: 90' in text
    assert 'github.run_attempt' in text


def test_strategy_code_changes_do_not_auto_generate_formal_outcomes():
    text = _text()
    push_block = text.split('push:', 1)[1].split('permissions:', 1)[0]
    assert "- '.github/workflows/exp0001-nonbinding.yml'" in push_block
    assert "gold_cio_v9/**" not in push_block
    assert "scripts/**" not in push_block
