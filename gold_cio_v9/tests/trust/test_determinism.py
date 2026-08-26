from gold_cio_v9.validation.trust import canonical_hash


def test_canonical_hash_is_order_independent_for_dicts():
    a = {"metrics": {"pf": 1.4, "exp": 0.2}, "trades": [{"id": 1}, {"id": 2}]}
    b = {"trades": [{"id": 1}, {"id": 2}], "metrics": {"exp": 0.2, "pf": 1.4}}
    assert canonical_hash(a) == canonical_hash(b)


def test_identical_replay_payload_is_hash_identical():
    payload = {
        "data_snapshot_hash": "abc123",
        "seed": 1729,
        "trade_log": [
            {"ts": "2026-01-01T10:00:00Z", "side": "LONG", "r": 2.0},
            {"ts": "2026-01-01T11:00:00Z", "side": "SHORT", "r": -1.0},
        ],
        "equity_curve": [0.0, 2.0, 1.0],
    }
    assert canonical_hash(payload) == canonical_hash(payload)


def test_trade_order_changes_replay_hash():
    a = {"trade_log": [{"id": 1}, {"id": 2}]}
    b = {"trade_log": [{"id": 2}, {"id": 1}]}
    assert canonical_hash(a) != canonical_hash(b)
