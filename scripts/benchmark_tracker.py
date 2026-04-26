#!/usr/bin/env python3
"""Benchmark tracker for the morning-advisor pipeline.

Append-only JSONL log of recommendation/outcome events, with rolling
performance summary (win rate, average return, cumulative alpha vs SPY,
by-source-skill breakdown).

CLI:
    benchmark_tracker.py record-rec --thesis-id ID --ticker T --instrument call \\
        --entry-price 4.85 --entry-date 2026-04-27 --source-skill vcp-screener

    benchmark_tracker.py record-outcome --thesis-id ID --exit-price 7.20 \\
        --exit-date 2026-05-12 [--spy-return-pct 1.2]

    benchmark_tracker.py summary [--window 30d] [--by-skill]

Environment:
    ALPACA_API_KEY, ALPACA_SECRET_KEY (optional; only for auto-fetching SPY return)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path("state/benchmark_log.jsonl")

# ---------------------------------------------------------------------------
# Pure functions (testable without I/O or network)
# ---------------------------------------------------------------------------


def make_rec_event(
    *,
    thesis_id: str,
    ticker: str,
    instrument: str,
    entry_price: float,
    entry_date: str,
    source_skill: str,
    ts: str | None = None,
) -> dict:
    """Build a normalized 'rec' (entry) event dict."""
    if instrument not in {"stock", "etf", "call", "put"}:
        raise ValueError(f"unknown instrument: {instrument!r}")
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    _validate_date(entry_date, "entry_date")
    return {
        "event": "rec",
        "ts": ts or _utc_now_iso(),
        "thesis_id": thesis_id,
        "ticker": ticker,
        "instrument": instrument,
        "entry_price": float(entry_price),
        "entry_date": entry_date,
        "source_skill": source_skill,
    }


def make_outcome_event(
    *,
    thesis_id: str,
    exit_price: float,
    exit_date: str,
    rec_event: dict,
    spy_return_pct: float | None = None,
    ts: str | None = None,
) -> dict:
    """Build a normalized 'outcome' (exit) event with computed return + alpha."""
    if exit_price <= 0:
        raise ValueError(f"exit_price must be positive, got {exit_price}")
    _validate_date(exit_date, "exit_date")
    if rec_event.get("thesis_id") != thesis_id:
        raise ValueError("rec_event.thesis_id does not match outcome thesis_id")

    entry_price = float(rec_event["entry_price"])
    instrument = rec_event["instrument"]
    thesis_return_pct = _percent_change(entry_price, exit_price)

    # For long puts, the *underlying* moves opposite to the option payoff;
    # but here entry/exit prices are the option premiums themselves, so the
    # raw % change already captures the put's payoff direction.
    event = {
        "event": "outcome",
        "ts": ts or _utc_now_iso(),
        "thesis_id": thesis_id,
        "ticker": rec_event["ticker"],
        "instrument": instrument,
        "entry_date": rec_event["entry_date"],
        "exit_date": exit_date,
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "thesis_return_pct": round(thesis_return_pct, 4),
        "source_skill": rec_event["source_skill"],
    }
    if spy_return_pct is not None:
        event["spy_return_pct"] = round(float(spy_return_pct), 4)
        event["alpha_pct"] = round(thesis_return_pct - float(spy_return_pct), 4)
    return event


def summarize(events: Iterable[dict], *, window_days: int | None = None) -> dict:
    """Compute rolling performance summary from a stream of events."""
    events = list(events)
    cutoff: date | None = None
    if window_days is not None:
        cutoff = date.today() - timedelta(days=window_days)

    rec_index: dict[str, dict] = {}
    outcomes: list[dict] = []
    for ev in events:
        if ev["event"] == "rec":
            rec_index[ev["thesis_id"]] = ev
        elif ev["event"] == "outcome":
            if cutoff and _parse_date(ev["exit_date"]) < cutoff:
                continue
            outcomes.append(ev)

    open_ids = set(rec_index) - {o["thesis_id"] for o in outcomes}

    if not outcomes:
        return {
            "n_recs": len(rec_index),
            "n_open": len(open_ids),
            "n_closed": 0,
            "win_rate_pct": None,
            "avg_thesis_return_pct": None,
            "avg_spy_return_pct": None,
            "cum_alpha_pct": None,
            "by_skill": {},
            "window_days": window_days,
        }

    wins = sum(1 for o in outcomes if o["thesis_return_pct"] > 0)
    avg_thesis = _mean(o["thesis_return_pct"] for o in outcomes)
    spy_outcomes = [o for o in outcomes if "spy_return_pct" in o]
    avg_spy = _mean(o["spy_return_pct"] for o in spy_outcomes) if spy_outcomes else None
    cum_alpha = sum(o["alpha_pct"] for o in spy_outcomes) if spy_outcomes else None

    by_skill: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum_return": 0.0, "sum_alpha": 0.0, "n_alpha": 0}
    )
    for o in outcomes:
        bucket = by_skill[o["source_skill"]]
        bucket["n"] += 1
        bucket["wins"] += int(o["thesis_return_pct"] > 0)
        bucket["sum_return"] += o["thesis_return_pct"]
        if "alpha_pct" in o:
            bucket["sum_alpha"] += o["alpha_pct"]
            bucket["n_alpha"] += 1

    skill_summary = {}
    for skill, b in by_skill.items():
        skill_summary[skill] = {
            "n": b["n"],
            "win_rate_pct": round(100.0 * b["wins"] / b["n"], 2),
            "avg_return_pct": round(b["sum_return"] / b["n"], 4),
            "cum_alpha_pct": round(b["sum_alpha"], 4) if b["n_alpha"] else None,
        }

    return {
        "n_recs": len(rec_index),
        "n_open": len(open_ids),
        "n_closed": len(outcomes),
        "win_rate_pct": round(100.0 * wins / len(outcomes), 2),
        "avg_thesis_return_pct": round(avg_thesis, 4),
        "avg_spy_return_pct": round(avg_spy, 4) if avg_spy is not None else None,
        "cum_alpha_pct": round(cum_alpha, 4) if cum_alpha is not None else None,
        "by_skill": skill_summary,
        "window_days": window_days,
    }


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def append_event(log_path: Path, event: dict) -> None:
    """Append a single JSON line to the log atomically."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":")) + "\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    out: list[dict] = []
    with log_path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt log line {i}: {exc}") from exc
    return out


def find_rec(events: list[dict], thesis_id: str) -> dict | None:
    for ev in events:
        if ev["event"] == "rec" and ev["thesis_id"] == thesis_id:
            return ev
    return None


def fetch_spy_return_pct(entry_date: str, exit_date: str, *, timeout: int = 10) -> float | None:
    """Fetch SPY return between two dates via Alpaca bars API. None on failure."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        return None
    try:
        import requests
    except ImportError:
        return None
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        resp = requests.get(
            "https://data.alpaca.markets/v2/stocks/SPY/bars",
            headers=headers,
            params={
                "start": entry_date,
                "end": exit_date,
                "timeframe": "1Day",
                "adjustment": "all",
                "limit": 100,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        bars = resp.json().get("bars", [])
    except Exception:  # noqa: BLE001 — graceful degradation
        return None
    if len(bars) < 2:
        return None
    open_px = float(bars[0]["o"])
    close_px = float(bars[-1]["c"])
    return round(_percent_change(open_px, close_px), 4)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_date(value: str, field: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD: {value!r}") from exc


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _percent_change(start: float, end: float) -> float:
    return 100.0 * (end - start) / start


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_window(window: str) -> int:
    """Parse '30d', '90d', '1y' → days."""
    window = window.strip().lower()
    if window.endswith("d"):
        return int(window[:-1])
    if window.endswith("w"):
        return int(window[:-1]) * 7
    if window.endswith("y"):
        return int(window[:-1]) * 365
    return int(window)


def _cmd_record_rec(args, log_path: Path) -> int:
    event = make_rec_event(
        thesis_id=args.thesis_id,
        ticker=args.ticker,
        instrument=args.instrument,
        entry_price=args.entry_price,
        entry_date=args.entry_date,
        source_skill=args.source_skill,
    )
    append_event(log_path, event)
    print(json.dumps(event))
    return 0


def _cmd_record_outcome(args, log_path: Path) -> int:
    events = read_events(log_path)
    rec = find_rec(events, args.thesis_id)
    if rec is None:
        print(f"ERROR: no matching rec for thesis_id={args.thesis_id}", file=sys.stderr)
        return 1
    spy_pct = args.spy_return_pct
    if spy_pct is None and not args.no_spy:
        spy_pct = fetch_spy_return_pct(rec["entry_date"], args.exit_date)
    event = make_outcome_event(
        thesis_id=args.thesis_id,
        exit_price=args.exit_price,
        exit_date=args.exit_date,
        rec_event=rec,
        spy_return_pct=spy_pct,
    )
    append_event(log_path, event)
    print(json.dumps(event))
    return 0


def _cmd_summary(args, log_path: Path) -> int:
    events = read_events(log_path)
    window = _parse_window(args.window) if args.window else None
    summary = summarize(events, window_days=window)
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-path",
        default=str(DEFAULT_LOG_PATH),
        help=f"Path to JSONL log (default: {DEFAULT_LOG_PATH})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record-rec", help="Append an entry recommendation")
    p_rec.add_argument("--thesis-id", required=True)
    p_rec.add_argument("--ticker", required=True)
    p_rec.add_argument("--instrument", required=True, choices=["stock", "etf", "call", "put"])
    p_rec.add_argument("--entry-price", required=True, type=float)
    p_rec.add_argument("--entry-date", required=True)
    p_rec.add_argument("--source-skill", required=True)

    p_out = sub.add_parser("record-outcome", help="Append an exit outcome")
    p_out.add_argument("--thesis-id", required=True)
    p_out.add_argument("--exit-price", required=True, type=float)
    p_out.add_argument("--exit-date", required=True)
    p_out.add_argument("--spy-return-pct", type=float, default=None)
    p_out.add_argument("--no-spy", action="store_true", help="Skip SPY auto-fetch")

    p_sum = sub.add_parser("summary", help="Rolling performance summary")
    p_sum.add_argument("--window", default=None, help="e.g. 30d, 12w, 1y")

    args = parser.parse_args(argv)
    log_path = Path(args.log_path)

    if args.cmd == "record-rec":
        return _cmd_record_rec(args, log_path)
    if args.cmd == "record-outcome":
        return _cmd_record_outcome(args, log_path)
    if args.cmd == "summary":
        return _cmd_summary(args, log_path)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
