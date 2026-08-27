from gold_cio_v9.backtest.splits import LabelInterval, purged_kfold, walk_forward


def test_purged_kfold_removes_label_overlap_and_embargo():
    rows = tuple(LabelInterval(i, i * 10, i * 10 + 12) for i in range(12))
    folds = purged_kfold(rows, k=3, embargo=5)
    assert len(folds) == 3
    by_id = {r.index: r for r in rows}
    for fold in folds:
        test_rows = [by_id[i] for i in fold.test]
        lo = min(r.start for r in test_rows)
        hi = max(r.end for r in test_rows)
        for i in fold.train:
            r = by_id[i]
            assert r.end < lo or r.start > hi
            assert not (hi < r.start <= hi + 5)


def test_walk_forward_is_strictly_out_of_sample():
    folds = walk_forward(n=30, min_train=10, test_size=5)
    assert len(folds) == 4
    for fold in folds:
        assert max(fold.train) < min(fold.test)
        assert set(fold.train).isdisjoint(fold.test)


def test_rolling_walk_forward_caps_training_history():
    folds = walk_forward(n=40, min_train=10, test_size=5, rolling_train=15)
    assert folds
    assert all(len(f.train) <= 15 for f in folds)
