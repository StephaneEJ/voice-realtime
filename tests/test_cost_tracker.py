"""Cost tracker model rate lookup + persist signature."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_realtime.cost_tracker import (
    DEFAULT_HOURLY_RATE_USD_BY_MODEL,
    DEFAULT_HOURLY_RATE_USD_BY_PROVIDER,
    CostTracker,
)


def test_model_rate_priority_over_provider() -> None:
    tracker = CostTracker(provider="gemini", model="gpt-realtime-2")
    # Even though provider is gemini, model-specific rate wins.
    assert tracker.hourly_rate_usd == DEFAULT_HOURLY_RATE_USD_BY_MODEL["gpt-realtime-2"]


def test_provider_fallback_for_unknown_model() -> None:
    tracker = CostTracker(provider="gemini", model="some-unknown-model")
    assert tracker.hourly_rate_usd == DEFAULT_HOURLY_RATE_USD_BY_PROVIDER["gemini"]


def test_gemini_2_5_flash_native_audio_rate() -> None:
    tracker = CostTracker(
        provider="gemini",
        model="gemini-2.5-flash-native-audio-latest",
    )
    assert tracker.hourly_rate_usd == 1.40


def test_gpt_realtime_mini_4x_cheaper_than_gpt_realtime_2() -> None:
    full = DEFAULT_HOURLY_RATE_USD_BY_MODEL["gpt-realtime-2"]
    mini = DEFAULT_HOURLY_RATE_USD_BY_MODEL["gpt-realtime-mini"]
    assert mini < full
    assert pytest.approx(full / mini, rel=0.05) == 4.0


def test_persist_writes_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirect SESSIONS_DIR to a temp path so we don't pollute ~/.voice-realtime/sessions
    from voice_realtime import cost_tracker as ct
    monkeypatch.setattr(ct, "SESSIONS_DIR", tmp_path)

    tracker = ct.CostTracker(provider="gemini", model="gemini-2.5-flash-native-audio-latest")
    out_path = tracker.persist(transcript="hello world", reason="test")

    assert out_path.exists()
    assert out_path.parent == tmp_path
    record = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert record["provider"] == "gemini"
    assert record["end_reason"] == "test"
    assert record["transcript_chars"] == len("hello world")


def test_persist_accepts_project_and_vault_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Anti-regression: cost_tracker.persist must accept the project_hint +
    # vault_note_path kwargs we wired in for NocoDB enrichment.
    from voice_realtime import cost_tracker as ct
    monkeypatch.setattr(ct, "SESSIONS_DIR", tmp_path)
    tracker = ct.CostTracker(provider="gemini", model="m")
    # Just make sure the call signature is accepted ; nocodb_writer is best-effort
    # (no config → returns False silently).
    out = tracker.persist(
        transcript="x",
        reason="test",
        project_hint="Voice Realtime",
        vault_note_path="/tmp/test.md",
    )
    assert out.exists()
