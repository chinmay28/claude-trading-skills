#!/usr/bin/env python3
"""Check whether US equity market is open today.

Uses the Alpaca clock + calendar API (free, no FMP cost). Returns exit
code 0 if today is a regular trading day, 1 if closed (weekend or holiday),
2 if Alpaca is unreachable (treat as closed for safety).

Usage:
    python3 check_market_open.py [--date YYYY-MM-DD]

Environment:
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER (default true)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed (pip install requests)", file=sys.stderr)
    sys.exit(2)


def _base_url(paper: bool) -> str:
    return "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"


def _headers() -> dict[str, str]:
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        print("ERROR: ALPACA_API_KEY / ALPACA_SECRET_KEY not set", file=sys.stderr)
        sys.exit(2)
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}


def is_market_open(target: date | None = None, *, timeout: int = 10) -> bool:
    """Return True if `target` (default today) is a regular US equity trading day."""
    paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
    base = _base_url(paper)
    target = target or date.today()
    iso = target.isoformat()

    resp = requests.get(
        f"{base}/v2/calendar",
        headers=_headers(),
        params={"start": iso, "end": iso},
        timeout=timeout,
    )
    resp.raise_for_status()
    days = resp.json()
    return any(d.get("date") == iso for d in days)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to today (US/Eastern wall clock)")
    args = parser.parse_args()

    target: date | None = None
    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"ERROR: invalid --date {args.date!r}", file=sys.stderr)
            return 2

    try:
        open_today = is_market_open(target)
    except requests.RequestException as exc:
        print(f"ERROR: Alpaca unreachable ({exc}); treating as CLOSED", file=sys.stderr)
        return 2

    label = (target or date.today()).isoformat()
    if open_today:
        print(f"OPEN {label}")
        return 0
    print(f"CLOSED {label}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
