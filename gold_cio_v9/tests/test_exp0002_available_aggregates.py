from scripts.inventory_exp0002_available_aggregates import PROBES


def test_aggregate_inventory_is_outcome_free_and_brackets_exp0002():
    assert [item["label"] for item in PROBES] == [
        "EXP0002_START", "AVAILABLE_TAIL", "EXP0002_END"
    ]
    assert PROBES[0]["start"] == "2022-01-03"
    assert PROBES[-1]["end"] == "2025-04-01"
