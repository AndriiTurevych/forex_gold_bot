from gold_cio_v9.validation.trials import TrialsRegistry


def test_every_registration_creates_exactly_one_record(tmp_path):
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    initial = len(registry.read_all())
    for i in range(5):
        registry.register(
            experiment_id="EXP-0001",
            config={"seed": 1729, "trial": i},
            data_snapshot_hash=f"data-{i}",
            git_commit="deadbeef",
        )
    assert len(registry.read_all()) == initial + 5


def test_trial_record_completeness(tmp_path):
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    registry.register(
        experiment_id="EXP-0001",
        config={"seed": 1729},
        data_snapshot_hash="data-hash",
        git_commit="deadbeef",
    )
    record = registry.read_all()[-1]
    required = {
        "trial_id",
        "created_at",
        "experiment_id",
        "config_hash",
        "data_snapshot_hash",
        "git_commit",
    }
    assert required.issubset(record)
    assert all(record[k] for k in required)


def test_config_hash_changes_when_config_changes(tmp_path):
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    a = registry.register(
        experiment_id="EXP-0001",
        config={"seed": 1729, "pf": 1.30},
        data_snapshot_hash="same",
        git_commit="deadbeef",
    )
    b = registry.register(
        experiment_id="EXP-0001",
        config={"seed": 1729, "pf": 1.31},
        data_snapshot_hash="same",
        git_commit="deadbeef",
    )
    assert a.config_hash != b.config_hash
