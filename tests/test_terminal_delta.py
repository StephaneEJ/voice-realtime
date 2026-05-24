"""Tests for the rolling-terminal delta reader (Phase 3.H)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_realtime.cli_context import jsonl_size_bytes, read_jsonl_delta_text
from voice_realtime.rolling_recap import (
    TerminalRecapState,
    maybe_inject_terminal_delta,
    wrap_terminal_delta,
)


def _write_record(p: Path, kind: str, text: str) -> None:
    """Append one Claude Code-style event."""
    record = {
        "type": kind,
        "message": {"role": kind, "content": [{"type": "text", "text": text}]},
    }
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_size_returns_zero_for_nonexistent(tmp_path: Path) -> None:
    assert jsonl_size_bytes(tmp_path / "ghost.jsonl") == 0


def test_size_returns_actual_size(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    p.write_text("hello", encoding="utf-8")
    assert jsonl_size_bytes(p) == 5


def test_delta_empty_when_no_new_content(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "first turn")
    size = jsonl_size_bytes(p)
    text, new_offset = read_jsonl_delta_text(p, size)
    assert text == ""
    assert new_offset == size


def test_delta_reads_new_content_only(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "old turn")
    _write_record(p, "assistant", "old response")
    initial_size = jsonl_size_bytes(p)

    _write_record(p, "user", "new question")
    _write_record(p, "assistant", "new answer")

    text, new_offset = read_jsonl_delta_text(p, initial_size)
    assert "new question" in text
    assert "new answer" in text
    assert "old turn" not in text
    assert "old response" not in text
    assert new_offset > initial_size


def test_delta_strips_system_reminders(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "<system-reminder>internal</system-reminder>")
    _write_record(p, "user", "real question")
    text, _ = read_jsonl_delta_text(p, 0)
    assert "internal" not in text
    assert "real question" in text


def test_delta_labels_speakers(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "salut")
    _write_record(p, "assistant", "bonjour")
    text, _ = read_jsonl_delta_text(p, 0)
    assert "Stéphane: salut" in text
    assert "Claude: bonjour" in text


def test_delta_skips_partial_first_line(tmp_path: Path) -> None:
    """If start_offset lands mid-line, the partial first line is discarded."""
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "complete record one")
    _write_record(p, "user", "complete record two")
    # Pick an offset in the middle of the first record
    text, _ = read_jsonl_delta_text(p, 10)
    # Should not include "complete record one" (we landed mid-line)
    # Should include "complete record two"
    assert "complete record two" in text


def test_wrap_terminal_delta() -> None:
    out = wrap_terminal_delta("Stéphane: hello\n\nClaude: hi")
    assert out.startswith("[Note système")
    assert "NE RÉPONDS PAS" in out
    assert "hello" in out


@pytest.mark.asyncio
async def test_maybe_inject_returns_none_without_handle() -> None:
    state = TerminalRecapState(source_handle=None)
    result = await maybe_inject_terminal_delta(state, interval_seconds=60.0)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_inject_respects_min_chars(tmp_path: Path) -> None:
    """Tiny deltas are skipped but offset still advances."""
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "hi")  # very short — under min_delta_chars
    state = TerminalRecapState(source_handle=p, last_offset_bytes=0, last_check_at=0.0)
    result = await maybe_inject_terminal_delta(state, interval_seconds=0.0)
    assert result is None
    assert state.last_offset_bytes > 0  # advanced past the tiny delta


@pytest.mark.asyncio
async def test_maybe_inject_emits_when_enough_content(tmp_path: Path) -> None:
    p = tmp_path / "session.jsonl"
    _write_record(p, "user", "x" * 800)
    state = TerminalRecapState(source_handle=p, last_offset_bytes=0, last_check_at=0.0)
    result = await maybe_inject_terminal_delta(state, interval_seconds=0.0)
    assert result is not None
    assert "Stéphane: " in result
    assert state.injection_count == 1
