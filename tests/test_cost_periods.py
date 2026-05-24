"""Tests for daily/weekly/historical cost aggregations (Phase 3.E)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from voice_realtime import cost_tracker as ct


@pytest.fixture
def tmp_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect SESSIONS_DIR to a tmp_path scoped per test."""
    monkeypatch.setattr(ct, "SESSIONS_DIR", tmp_path)
    return tmp_path


def _write_record(dir_: Path, ended_iso: str, cost: float) -> None:
    p = dir_ / "test.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "started_iso": ended_iso,
            "ended_iso": ended_iso,
            "elapsed_seconds": 60,
            "provider": "gemini",
            "model": "gemini-2.5-flash-native-audio-latest",
            "hourly_rate_usd": 1.40,
            "estimated_cost_usd": cost,
            "end_reason": "ended",
            "transcript_chars": 100,
        }) + "\n")


def test_daily_total_no_sessions(tmp_sessions: Path) -> None:
    assert ct.daily_total_usd() == 0.0


def test_daily_total_today_only(tmp_sessions: Path) -> None:
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    _write_record(tmp_sessions, now.isoformat(), 0.50)
    _write_record(tmp_sessions, now.isoformat(), 0.25)
    _write_record(tmp_sessions, yesterday.isoformat(), 9.99)  # yesterday — excluded

    total = ct.daily_total_usd()
    assert total == pytest.approx(0.75)


def test_weekly_total_window(tmp_sessions: Path) -> None:
    now = datetime.now(timezone.utc)
    _write_record(tmp_sessions, now.isoformat(), 1.00)
    _write_record(tmp_sessions, (now - timedelta(days=3)).isoformat(), 0.50)
    _write_record(tmp_sessions, (now - timedelta(days=6)).isoformat(), 0.25)
    _write_record(tmp_sessions, (now - timedelta(days=10)).isoformat(), 99.99)  # outside 7d

    total = ct.weekly_total_usd(days=7, now=now)
    assert total == pytest.approx(1.75)


def test_historical_series_30d(tmp_sessions: Path) -> None:
    now = datetime.now(timezone.utc)
    _write_record(tmp_sessions, now.isoformat(), 0.10)
    _write_record(tmp_sessions, (now - timedelta(days=5)).isoformat(), 0.20)
    _write_record(tmp_sessions, (now - timedelta(days=29)).isoformat(), 0.30)
    _write_record(tmp_sessions, (now - timedelta(days=40)).isoformat(), 99.99)  # outside

    series = ct.historical_series(days=30, now=now)
    assert len(series) == 30
    # All days present, oldest first
    dates = [d for d, _ in series]
    assert dates == sorted(dates)
    # Sums match
    total = sum(v for _, v in series)
    assert total == pytest.approx(0.60)


def test_historical_handles_malformed_records(tmp_sessions: Path) -> None:
    p = tmp_sessions / "broken.jsonl"
    p.write_text("not json\n{}\n{\"ended_iso\":\"bogus\",\"estimated_cost_usd\":1.0}\n",
                 encoding="utf-8")
    # No crashes; broken records skipped, no totals from them
    assert ct.daily_total_usd() == 0.0
    assert ct.weekly_total_usd() == 0.0
    series = ct.historical_series(days=7)
    assert sum(v for _, v in series) == 0.0
