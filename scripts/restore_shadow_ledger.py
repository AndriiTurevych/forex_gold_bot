#!/usr/bin/env python3
"""Restore the latest immutable shadow-ledger artifact, or create genesis."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        output.write_text("", encoding="utf-8")
        print(json.dumps({"restored": False, "reason": "NO_GITHUB_CONTEXT"}))
        return 0
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/actions/artifacts?name=gold-cio-shadow-ledger&per_page=100"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        artifacts = json.load(response).get("artifacts", [])
    usable = [a for a in artifacts if not a.get("expired")]
    if not usable:
        output.write_text("", encoding="utf-8")
        print(json.dumps({"restored": False, "reason": "GENESIS"}))
        return 0
    artifact = max(usable, key=lambda a: (a.get("created_at", ""), int(a["id"])))
    with urlopen(Request(artifact["archive_download_url"], headers=headers), timeout=60) as response:
        archive = response.read()
    with ZipFile(BytesIO(archive)) as bundle:
        names = [n for n in bundle.namelist() if n.endswith("shadow_ledger.jsonl") and ".." not in Path(n).parts]
        if len(names) != 1:
            raise ValueError("shadow ledger artifact must contain exactly one ledger")
        output.write_bytes(bundle.read(names[0]))
    print(json.dumps({"restored": True, "artifact_id": artifact["id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
