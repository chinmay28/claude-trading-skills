"""Tests for scripts/benchmark_tracker.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark_tracker as bt  # noqa: E402

# ---------------------------------------------------------------------------
# make_rec_event
# ---------------------------------------------------------------------------


def test_make_rec_event_normalizes_fields():
    ev = bt.make_rec_event(
        thesis_id="th_x",
        ticker="NVDA",
        instrument="call",
        entry_price=4.85,
        entry_date="2026-04-27",
        source_skill="vcp-screener",
        ts="2026-04-27T13:30:00Z",
    )
    assert ev == {
        "event": "rec",
        "ts": "2026-04-27T13:30:00Z",
        "thesis_id": "th_x",
        "ticker": "NVDA",
        "instrument": "call",
        "entry_price": 4.85,
        "entry_date": "2026-04-27",
        "source_skill": "vcp-screener",
    }


def test_make_rec_event_rejects_unknown_instrument():
    with pytest.raises(ValueError, match="unknown instrument"):
        bt.make_rec_event(
            thesis_id="th_x",
            ticker="NVDA",
            instrument="straddle",
            entry_price=1.0,
            entry_date="2026-04-27",
            source_skill="vcp-screener",
        )


def test_make_rec_event_rejects_nonpositive_price():
    with pytest.raises(ValueError, match="entry_price"):
        bt.make_rec_event(
            thesis_id="th_x",
            ticker="NVDA",
            instrument="call",
            entry_price=0,
            entry_date="2026-04-27",
            source_skill="vcp-screener",
        )


def test_make_rec_event_rejects_bad_date():
    with pytest.raises(ValueError, match="entry_date"):
        bt.make_rec_event(
            thesis_id="th_x",
            ticker="NVDA",
            instrument="call",
            entry_price=1.0,
            entry_date="04/27/2026",
            source_skill="vcp-screener",
        )


# ---------------------------------------------------------------------------
# make_outcome_event
# ---------------------------------------------------------------------------


def _rec(**overrides):
    base = dict(
        thesis_id="th_x",
        ticker="NVDA",
        instrument="call",
        entry_price=4.0,
        entry_date="2026-04-27",
        source_skill="vcp-screener",
        ts="2026-04-27T13:30:00Z",
    )
    base.update(overrides)
    return bt.make_rec_event(**base)


def test_make_outcome_computes_return_and_alpha():
    rec = _rec()
    out = bt.make_outcome_event(
        thesis_id="th_x",
        exit_price=6.0,
        exit_date="2026-05-12",
        rec_event=rec,
        spy_return_pct=2.0,
        ts="2026-05-12T20:00:00Z",
    )
    assert out["thesis_return_pct"] == pytest.approx(50.0)
    assert out["spy_return_pct"] == pytest.approx(2.0)
    assert out["alpha_pct"] == pytest.approx(48.0)
    assert out["entry_date"] == "2026-04-27"
    assert out["entry_price"] == 4.0


def test_make_outcome_negative_return():
    rec = _rec()
    out = bt.make_outcome_event(
        thesis_id="th_x",
        exit_price=2.0,
        exit_date="2026-05-12",
        rec_event=rec,
        spy_return_pct=1.0,
    )
    assert out["thesis_return_pct"] == pytest.approx(-50.0)
    assert out["alpha_pct"] == pytest.approx(-51.0)


def test_make_outcome_without_spy_omits_alpha():
    rec = _rec()
    out = bt.make_outcome_event(
        thesis_id="th_x",
        exit_price=5.0,
        exit_date="2026-05-12",
        rec_event=rec,
        spy_return_pct=None,
    )
    assert "spy_return_pct" not in out
    assert "alpha_pct" not in out


def test_make_outcome_id_mismatch_raises():
    rec = _rec()
    with pytest.raises(ValueError, match="thesis_id"):
        bt.make_outcome_event(
            thesis_id="th_other",
            exit_price=5.0,
            exit_date="2026-05-12",
            rec_event=rec,
        )


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def _build_pair(thesis_id, entry, exit_, *, skill="vcp-screener", spy=1.0, exit_date="2026-05-12"):
    rec = _rec(thesis_id=thesis_id, entry_price=entry, source_skill=skill)
    out = bt.make_outcome_event(
        thesis_id=thesis_id,
        exit_price=exit_,
        exit_date=exit_date,
        rec_event=rec,
        spy_return_pct=spy,
    )
    return rec, out


def test_summarize_empty_log():
    s = bt.summarize([])
    assert s["n_recs"] == 0
    assert s["n_open"] == 0
    assert s["n_closed"] == 0
    assert s["win_rate_pct"] is None


def test_summarize_open_position_only():
    rec = _rec(thesis_id="th_a", entry_price=10.0)
    s = bt.summarize([rec])
    assert s["n_recs"] == 1
    assert s["n_open"] == 1
    assert s["n_closed"] == 0


def test_summarize_win_rate_and_alpha():
    events = []
    # Win: 50% return, SPY 2% → alpha 48
    rec, out = _build_pair("th_a", 4.0, 6.0, spy=2.0)
    events += [rec, out]
    # Loss: -25% return, SPY -1% → alpha -24
    rec, out = _build_pair("th_b", 8.0, 6.0, spy=-1.0)
    events += [rec, out]
    # Win: 10% return, SPY 0% → alpha 10
    rec, out = _build_pair("th_c", 100.0, 110.0, spy=0.0, skill="pead-screener")
    events += [rec, out]

    s = bt.summarize(events)
    assert s["n_closed"] == 3
    assert s["win_rate_pct"] == pytest.approx(66.67, rel=1e-3)
    assert s["avg_thesis_return_pct"] == pytest.approx((50 - 25 + 10) / 3, rel=1e-3)
    assert s["cum_alpha_pct"] == pytest.approx(48 - 24 + 10)


def test_summarize_by_skill_breakdown():
    events = []
    rec, out = _build_pair("th_a", 4.0, 6.0, spy=2.0, skill="vcp-screener")
    events += [rec, out]
    rec, out = _build_pair("th_b", 8.0, 6.0, spy=-1.0, skill="vcp-screener")
    events += [rec, out]
    rec, out = _build_pair("th_c", 100.0, 110.0, spy=0.0, skill="pead-screener")
    events += [rec, out]

    s = bt.summarize(events)
    assert set(s["by_skill"]) == {"vcp-screener", "pead-screener"}
    assert s["by_skill"]["vcp-screener"]["n"] == 2
    assert s["by_skill"]["vcp-screener"]["win_rate_pct"] == 50.0
    assert s["by_skill"]["pead-screener"]["n"] == 1
    assert s["by_skill"]["pead-screener"]["win_rate_pct"] == 100.0


# ---------------------------------------------------------------------------
# I/O round-trip
# ---------------------------------------------------------------------------


def test_append_and_read_round_trip(tmp_path):
    log = tmp_path / "log.jsonl"
    rec = _rec(thesis_id="th_a")
    bt.append_event(log, rec)
    out = bt.make_outcome_event(
        thesis_id="th_a",
        exit_price=5.0,
        exit_date="2026-05-12",
        rec_event=rec,
        spy_return_pct=1.0,
    )
    bt.append_event(log, out)

    events = bt.read_events(log)
    assert len(events) == 2
    assert events[0]["event"] == "rec"
    assert events[1]["event"] == "outcome"
    assert events[1]["thesis_return_pct"] == pytest.approx(25.0)


def test_read_events_missing_file_returns_empty(tmp_path):
    assert bt.read_events(tmp_path / "nope.jsonl") == []


def test_read_events_corrupt_line_raises(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text('{"event":"rec","thesis_id":"th_a"}\nNOT JSON\n')
    with pytest.raises(ValueError, match="corrupt log line 2"):
        bt.read_events(log)


def test_find_rec_returns_match():
    rec = _rec(thesis_id="th_a")
    rec2 = _rec(thesis_id="th_b", ticker="MSFT")
    found = bt.find_rec([rec, rec2], "th_b")
    assert found is rec2


def test_find_rec_no_match():
    assert bt.find_rec([_rec()], "th_missing") is None


# ---------------------------------------------------------------------------
# CLI window parsing
# ---------------------------------------------------------------------------


def test_parse_window():
    assert bt._parse_window("30d") == 30
    assert bt._parse_window("4w") == 28
    assert bt._parse_window("1y") == 365
    assert bt._parse_window("90") == 90


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_record_rec_writes_log(tmp_path, capsys):
    log = tmp_path / "log.jsonl"
    rc = bt.main(
        [
            "--log-path",
            str(log),
            "record-rec",
            "--thesis-id",
            "th_a",
            "--ticker",
            "NVDA",
            "--instrument",
            "call",
            "--entry-price",
            "4.85",
            "--entry-date",
            "2026-04-27",
            "--source-skill",
            "vcp-screener",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out.strip()
    parsed = json.loads(captured)
    assert parsed["event"] == "rec"
    assert parsed["entry_price"] == 4.85

    events = bt.read_events(log)
    assert len(events) == 1


def test_cli_record_outcome_with_explicit_spy(tmp_path, capsys):
    log = tmp_path / "log.jsonl"
    bt.main(
        [
            "--log-path",
            str(log),
            "record-rec",
            "--thesis-id",
            "th_a",
            "--ticker",
            "NVDA",
            "--instrument",
            "call",
            "--entry-price",
            "4.0",
            "--entry-date",
            "2026-04-27",
            "--source-skill",
            "vcp-screener",
        ]
    )
    capsys.readouterr()  # discard
    rc = bt.main(
        [
            "--log-path",
            str(log),
            "record-outcome",
            "--thesis-id",
            "th_a",
            "--exit-price",
            "6.0",
            "--exit-date",
            "2026-05-12",
            "--spy-return-pct",
            "2.0",
            "--no-spy",
        ]
    )
    assert rc == 0
    out_event = json.loads(capsys.readouterr().out.strip())
    assert out_event["alpha_pct"] == pytest.approx(48.0)


def test_cli_record_outcome_unknown_thesis_returns_error(tmp_path, capsys):
    log = tmp_path / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rc = bt.main(
        [
            "--log-path",
            str(log),
            "record-outcome",
            "--thesis-id",
            "th_unknown",
            "--exit-price",
            "5.0",
            "--exit-date",
            "2026-05-12",
            "--no-spy",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "no matching rec" in err


def test_cli_summary_outputs_json(tmp_path, capsys):
    log = tmp_path / "log.jsonl"
    bt.main(
        [
            "--log-path",
            str(log),
            "record-rec",
            "--thesis-id",
            "th_a",
            "--ticker",
            "NVDA",
            "--instrument",
            "call",
            "--entry-price",
            "4.0",
            "--entry-date",
            "2026-04-27",
            "--source-skill",
            "vcp-screener",
        ]
    )
    bt.main(
        [
            "--log-path",
            str(log),
            "record-outcome",
            "--thesis-id",
            "th_a",
            "--exit-price",
            "5.0",
            "--exit-date",
            "2026-05-12",
            "--spy-return-pct",
            "1.0",
            "--no-spy",
        ]
    )
    capsys.readouterr()
    rc = bt.main(["--log-path", str(log), "summary"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["n_closed"] == 1
    assert parsed["win_rate_pct"] == 100.0
