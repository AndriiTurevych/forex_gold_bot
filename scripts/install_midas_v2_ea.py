#!/usr/bin/env python3
"""Install and optionally compile the MIDAS v2 Expert Advisor into the active MT5 data folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--source", default="mt5/MQL5/Experts/MIDAS/MIDAS_V2_DemoEA.mq5")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--mt5-timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required on the Windows MT5 host") from exc

    terminal_path = Path(args.terminal_path).resolve()
    source = Path(args.source).resolve()
    if not terminal_path.exists():
        raise RuntimeError(f"MT5_TERMINAL_NOT_FOUND:{terminal_path}")
    if not source.exists():
        raise RuntimeError(f"EA_SOURCE_NOT_FOUND:{source}")

    if not mt5.initialize(path=str(terminal_path), timeout=args.mt5_timeout_ms):
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        info = mt5.terminal_info()
        if info is None:
            raise RuntimeError("MT5_TERMINAL_INFO_UNAVAILABLE")
        data_path = Path(str(getattr(info, "data_path", "") or ""))
        commondata_path = Path(str(getattr(info, "commondata_path", "") or ""))
        if not str(data_path):
            raise RuntimeError("MT5_DATA_PATH_UNAVAILABLE")
    finally:
        mt5.shutdown()

    destination = data_path / "MQL5" / "Experts" / "MIDAS" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    result = {
        "installed": True,
        "source": str(source),
        "destination": str(destination),
        "common_files": str(commondata_path / "Files" / "MIDAS"),
        "compiled": False,
        "ex5": str(destination.with_suffix(".ex5")),
    }

    if not args.no_compile:
        candidates = [
            terminal_path.parent / "MetaEditor64.exe",
            terminal_path.parent / "metaeditor64.exe",
            terminal_path.parent / "MetaEditor.exe",
        ]
        editor = next((path for path in candidates if path.exists()), None)
        if editor is None:
            raise RuntimeError("METAEDITOR_NOT_FOUND_NEXT_TO_TERMINAL")

        log_path = destination.with_suffix(".compile.log")
        proc = subprocess.run(
            [str(editor), f"/compile:{destination}", f"/log:{log_path}"],
            cwd=str(destination.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        ex5 = destination.with_suffix(".ex5")
        if proc.returncode != 0 or not ex5.exists():
            log = log_path.read_text(encoding="utf-16", errors="replace") if log_path.exists() else ""
            raise RuntimeError(f"EA_COMPILE_FAILED:{proc.returncode}:{log[-4000:]}")
        result["compiled"] = True

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
