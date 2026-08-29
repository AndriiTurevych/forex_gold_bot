import pytest

from gold_cio_v9.execution.latency_stats import summarize_latency


def test_latency_distribution_reports_tail_percentiles():
    values = [float(i) for i in range(1, 101)]
    summary = summarize_latency(values)
    assert summary.count == 100
    assert summary.minimum_ms == 1.0
    assert summary.maximum_ms == 100.0
    assert summary.p50_ms == pytest.approx(50.5)
    assert summary.p95_ms == pytest.approx(95.05)
    assert summary.p99_ms == pytest.approx(99.01)
    assert summary.p999_ms == pytest.approx(99.901)


def test_latency_distribution_rejects_invalid_values():
    with pytest.raises(ValueError):
        summarize_latency([])
    with pytest.raises(ValueError):
        summarize_latency([1.0, -1.0])
    with pytest.raises(ValueError):
        summarize_latency([1.0, float("nan")])
