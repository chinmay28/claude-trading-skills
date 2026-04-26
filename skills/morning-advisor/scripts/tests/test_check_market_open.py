"""Tests for check_market_open.is_market_open."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

# Ensure the script under test is importable.
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_market_open  # noqa: E402


@pytest.fixture(autouse=True)
def _alpaca_env():
    with mock.patch.dict(
        os.environ,
        {
            "ALPACA_API_KEY": "test-key",  # pragma: allowlist secret
            "ALPACA_SECRET_KEY": "test-secret",  # pragma: allowlist secret
            "ALPACA_PAPER": "true",
        },
        clear=False,
    ):
        yield


def _mock_response(payload, status: int = 200):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_returns_true_for_calendar_match():
    target = date(2026, 4, 27)
    payload = [{"date": "2026-04-27", "open": "09:30", "close": "16:00"}]
    with mock.patch.object(check_market_open.requests, "get", return_value=_mock_response(payload)):
        assert check_market_open.is_market_open(target) is True


def test_returns_false_when_date_missing_from_calendar():
    target = date(2026, 4, 25)  # Saturday — Alpaca returns []
    with mock.patch.object(check_market_open.requests, "get", return_value=_mock_response([])):
        assert check_market_open.is_market_open(target) is False


def test_returns_false_when_calendar_returns_other_date():
    target = date(2026, 7, 4)  # Independence Day — calendar may return adjacent days only
    payload = [{"date": "2026-07-03", "open": "09:30", "close": "13:00"}]
    with mock.patch.object(check_market_open.requests, "get", return_value=_mock_response(payload)):
        assert check_market_open.is_market_open(target) is False


def test_missing_credentials_exits_two():
    with mock.patch.dict(os.environ, {"ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""}, clear=False):
        with pytest.raises(SystemExit) as exc:
            check_market_open._headers()
        assert exc.value.code == 2


def test_paper_flag_selects_paper_url():
    with mock.patch.dict(os.environ, {"ALPACA_PAPER": "true"}, clear=False):
        assert check_market_open._base_url(True).startswith("https://paper-api")
    assert check_market_open._base_url(False).startswith("https://api.alpaca.markets")
