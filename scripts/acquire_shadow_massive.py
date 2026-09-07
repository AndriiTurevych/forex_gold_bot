#!/usr/bin/env python3
"""Acquire the latest causal GC front and recent 1m bars for shadow only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


BASE = "https://api.massive.com"
CORE_MONTHS = ((2, "G"), (4, "J"), (6, "M"), (8, "Q"), (10, "V"), (12, "Z"))


def candidate_tickers(now: datetime) -> tuple[str, ...]:
    rows = []
    for year in (now.year, now.year + 1):
        for month, code in CORE_MONTHS:
            if year == now.year and month < now.month:
                continue
            rows.append(f"GC{code}{year % 10}")
    return tuple(rows)


class Massive:
    def __init__(self, key: str):
        if not key.strip():
            raise ValueError("MASSIVE_API_KEY is required")
        self.key = key.strip()

    def get(self, target: str, params: dict[str, object]) -> dict:
        parsed = urlparse(target if target.startswith("https://") else BASE + target)
        if parsed.netloc != "api.massive.com":
            raise ValueError("pagination host veto")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({str(k): str(v) for k, v in params.items()})
        query["apiKey"] = self.key
        url = urlunparse(parsed._replace(query=urlencode(query)))
        for attempt in range(6):
            try:
                with urlopen(Request(url, headers={"User-Agent": "Gold-CIO-Shadow/1.0"}), timeout=60) as response:
                    payload = json.load(response)
                if payload.get("status") not in (None, "OK") or not isinstance(payload.get("results"), list):
                    raise ValueError("invalid Massive response")
                return payload
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 5:
                    raise
            except URLError:
                if attempt == 5:
                    raise
            time.sleep(min(16, 2 ** attempt))
        raise RuntimeError("unreachable retry state")

    def pages(self, path: str, params: dict[str, object]) -> list[dict]:
        pages, target, query, seen = [], path, params, set()
        for _ in range(20):
            page = self.get(target, query)
            pages.append(page)
            nxt = page.get("next_url")
            if not nxt:
                return pages
            if nxt in seen:
                raise ValueError("repeated Massive pagination URL")
            seen.add(nxt)
            target, query = str(nxt), {}
        raise ValueError("Massive pagination limit exceeded")


def select_front(api: Massive, now: datetime) -> tuple[str, str, float]:
    observations = []
    lower = (now.date() - timedelta(days=8)).isoformat()
    for ticker in candidate_tickers(now):
        page = api.get(f"/futures/v1/aggs/{ticker}", {
            "resolution": "1session", "window_start.gte": lower,
            "window_start.lte": now.date().isoformat(), "sort": "window_start.desc", "limit": 10,
        })
        for row in page["results"]:
            session = str(row.get("session_end_date", ""))
            if session and session < now.date().isoformat():
                observations.append((session, float(row.get("volume", 0)), ticker))
                break
    if not observations:
        raise ValueError("no completed GC session volume for front selection")
    latest_session = max(row[0] for row in observations)
    same_session = [row for row in observations if row[0] == latest_session]
    session, volume, ticker = max(same_session, key=lambda row: (row[1], row[2]))
    if volume <= 0:
        raise ValueError("selected GC front has nonpositive prior-session volume")
    return ticker, session, volume


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--now")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("--now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    api = Massive(os.environ.get("MASSIVE_API_KEY", ""))
    ticker, selection_session, selection_volume = select_front(api, now)
    pages = api.pages(f"/futures/v1/aggs/{ticker}", {
        "resolution": "1min", "window_start.gte": (now - timedelta(days=10)).isoformat(),
        "window_start.lte": now.isoformat(), "sort": "window_start.asc", "limit": 50000,
    })
    raw = [row for page in pages for row in page["results"]]
    by_time = {int(row["window_start"]): row for row in raw}
    if not by_time:
        raise ValueError("no current GC 1m bars")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    bars_path = out / "bars.jsonl"
    with bars_path.open("w", encoding="utf-8") as handle:
        for ns, row in sorted(by_time.items()):
            event_time = datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)
            payload = {
                "instrument": "GC", "contract": ticker, "event_time": event_time.isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"],
                "volume": row.get("volume"), "quality_state": "VERIFIED",
                "source_id": f"massive:{ticker}:{ns}", "roll_method": "RAW_CONTRACT",
                "is_roll_window": False,
            }
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    latest_ns = max(by_time)
    latest_close_time = datetime.fromtimestamp(latest_ns / 1_000_000_000, tz=timezone.utc) + timedelta(minutes=1)
    snapshot_hash = __import__("hashlib").sha256(bars_path.read_bytes()).hexdigest()
    meta = {
        "provider": "Massive", "acquired_at": now.isoformat(), "contract": ticker,
        "front_selection_session": selection_session, "front_selection_volume": selection_volume,
        "bars": len(by_time), "latest_bar_close_time": latest_close_time.isoformat(),
        "latest_price": float(by_time[latest_ns]["close"]),
        "feed_age_minutes": (now - latest_close_time).total_seconds() / 60,
        "data_snapshot_hash": snapshot_hash, "real_orders_enabled": False,
    }
    (out / "acquisition.json").write_text(json.dumps(meta, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(meta, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
