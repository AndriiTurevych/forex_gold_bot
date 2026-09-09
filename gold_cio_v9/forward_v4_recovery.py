"""Fail-closed recovery anchors for EXP-0004 prospective evidence."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

from gold_cio_v9.forward_v4 import EXPERIMENT, verified_rows
from gold_cio_v9.forward_v4_validation import checkpoint, policy_hash
from gold_cio_v9.shadow.ledger import HashChainLedger


@dataclass(frozen=True)
class RecoveryAnchor:
    schema: str
    experiment_id: str
    generation: int
    artifact_id: int
    engine_commit: str
    protocol_hash: str
    sequence: int
    tip_hash: str
    ledger_sha256: str

    @classmethod
    def parse(cls, raw: dict) -> "RecoveryAnchor":
        allowed = set(cls.__annotations__)
        if set(raw) != allowed:
            raise ValueError("INVALID_ANCHOR_SCHEMA")
        anchor = cls(**raw)
        if (anchor.schema != "gold-cio-exp0004-recovery-anchor-v1"
                or anchor.experiment_id != EXPERIMENT or anchor.generation < 1
                or anchor.artifact_id < 1 or anchor.sequence < 1
                or len(anchor.engine_commit) != 40 or len(anchor.protocol_hash) != 64
                or len(anchor.tip_hash) != 64 or len(anchor.ledger_sha256) != 64):
            raise ValueError("INVALID_ANCHOR_VALUES")
        return anchor


def read_anchor(path: str | Path) -> RecoveryAnchor:
    return RecoveryAnchor.parse(json.loads(Path(path).read_text(encoding="utf-8")))


def write_anchor(path: str | Path, anchor: RecoveryAnchor, *, exclusive=False) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with target.open(mode, encoding="utf-8") as handle:
        json.dump(asdict(anchor), handle, sort_keys=True, indent=2)
        handle.write("\n")


def verify_against_anchor(ledger: HashChainLedger, anchor: RecoveryAnchor,
                          engine_commit: str) -> None:
    if anchor.engine_commit != engine_commit or anchor.protocol_hash != policy_hash():
        raise ValueError("ANCHOR_IMPLEMENTATION_MISMATCH")
    actual = checkpoint(ledger, engine_commit)
    expected = {
        "experiment_id": EXPERIMENT, "sequence": anchor.sequence,
        "tip_hash": anchor.tip_hash, "engine_commit": anchor.engine_commit,
        "protocol_hash": anchor.protocol_hash, "ledger_sha256": anchor.ledger_sha256,
    }
    if actual != expected:
        raise ValueError("ANCHOR_LEDGER_MISMATCH_OR_ROLLBACK")


def build_anchor(ledger: HashChainLedger, *, artifact_id: int,
                 engine_commit: str, previous: RecoveryAnchor | None = None) -> RecoveryAnchor:
    rows = verified_rows(ledger)
    if not rows:
        raise ValueError("EMPTY_LEDGER")
    if previous is not None:
        if artifact_id == previous.artifact_id:
            raise ValueError("ARTIFACT_REUSE_FORBIDDEN")
        if len(rows) <= previous.sequence:
            raise ValueError("ANCHOR_MUST_ADVANCE")
        prefix = HashChainLedger(ledger.path.with_suffix(".prefix.tmp"))
        prefix.path.write_text("\n".join(
            json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for r in rows[:previous.sequence]) + "\n", encoding="utf-8")
        try:
            verify_against_anchor(prefix, previous, engine_commit)
        finally:
            prefix.path.unlink(missing_ok=True)
    state = checkpoint(ledger, engine_commit)
    return RecoveryAnchor(
        schema="gold-cio-exp0004-recovery-anchor-v1", experiment_id=EXPERIMENT,
        generation=1 if previous is None else previous.generation + 1,
        artifact_id=int(artifact_id), engine_commit=engine_commit,
        protocol_hash=policy_hash(), sequence=state["sequence"],
        tip_hash=state["tip_hash"], ledger_sha256=state["ledger_sha256"],
    )


def restore_exact_archive(archive: str | Path, output: str | Path,
                          anchor: RecoveryAnchor, engine_commit: str) -> HashChainLedger:
    with ZipFile(archive) as bundle:
        safe = [name for name in bundle.namelist()
                if name.endswith("exp0004_ledger.jsonl") and ".." not in Path(name).parts]
        if len(safe) != 1:
            raise ValueError("ARCHIVE_MUST_CONTAIN_EXACTLY_ONE_LEDGER")
        raw = bundle.read(safe[0])
    if sha256(raw).hexdigest() != anchor.ledger_sha256:
        raise ValueError("ARCHIVE_LEDGER_HASH_MISMATCH")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    ledger = HashChainLedger(target)
    verify_against_anchor(ledger, anchor, engine_commit)
    return ledger
