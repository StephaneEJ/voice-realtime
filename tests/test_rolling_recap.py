"""Unit tests for rolling_recap module.

Trigger logic + state mechanics. No network / no claude -p subprocess.
"""

from __future__ import annotations

import pytest

from voice_realtime.rolling_recap import (
    DEFAULT_USER_CHAR_TRIGGER,
    MIN_TRANSCRIPT_CHARS,
    RecapState,
    SILENT_NOTE_PREFIX,
    maybe_run_recap,
    wrap_for_silent_injection,
)


def test_recap_state_initial() -> None:
    s = RecapState()
    assert s.user_chars_since_recap == 0
    assert s.recap_count == 0
    assert s.render_transcript() == ""


def test_recap_state_add_user_counts_chars() -> None:
    s = RecapState()
    s.add_user("Bonjour")
    s.add_user(" Stéphane")
    # add_user strips whitespace before counting; both non-empty after strip.
    assert s.user_chars_since_recap == len("Bonjour") + len("Stéphane")


def test_recap_state_add_user_skips_blank() -> None:
    s = RecapState()
    s.add_user("")
    s.add_user("   ")
    assert s.user_chars_since_recap == 0
    assert s.user_chunks_since_recap == []


def test_recap_state_add_model_does_not_affect_user_chars() -> None:
    s = RecapState()
    s.add_model("Reply from model")
    assert s.user_chars_since_recap == 0
    assert "Reply from model" in s.render_transcript()


def test_recap_state_render_groups_roles() -> None:
    s = RecapState()
    s.add_user("Question 1")
    s.add_user("Question 2")
    s.add_model("Answer 1")
    s.add_model("Answer 2")
    out = s.render_transcript()
    assert "Stéphane (parole) : Question 1 Question 2" in out
    assert "Assistant (réponses) : Answer 1 Answer 2" in out


def test_recap_state_reset_clears_and_increments_count() -> None:
    s = RecapState()
    s.add_user("X" * 100)
    s.add_model("Y" * 50)
    s.reset()
    assert s.user_chars_since_recap == 0
    assert s.user_chunks_since_recap == []
    assert s.model_chunks_since_recap == []
    assert s.recap_count == 1


def test_recap_state_reset_resets_last_recap_timer() -> None:
    s = RecapState()
    before = s.last_recap_at
    s.reset()
    assert s.last_recap_at >= before


def test_wrap_for_silent_injection_uses_marker() -> None:
    wrapped = wrap_for_silent_injection("Recap content")
    assert wrapped.startswith(SILENT_NOTE_PREFIX)
    assert "Recap content" in wrapped


async def test_maybe_run_recap_below_thresholds_returns_none() -> None:
    s = RecapState()
    s.add_user("Short message")
    # Far below char trigger AND just initialized so elapsed ≈ 0
    out = await maybe_run_recap(s, interval_seconds=999_999, char_trigger=999_999)
    assert out is None


async def test_maybe_run_recap_empty_buffer_returns_none() -> None:
    s = RecapState()
    # Force time-trigger by claiming the last recap was very long ago, but
    # there's still no transcript to compact → still returns None.
    s.last_recap_at = 0.0
    out = await maybe_run_recap(s, interval_seconds=0.0, char_trigger=999_999)
    assert out is None


async def test_maybe_run_recap_too_short_transcript_returns_none() -> None:
    s = RecapState()
    s.add_user("Too short")  # well below MIN_TRANSCRIPT_CHARS (=600)
    s.last_recap_at = 0.0
    out = await maybe_run_recap(s, interval_seconds=0.0, char_trigger=0)
    assert out is None


def test_default_trigger_is_char_based() -> None:
    # Anti-regression: 23/05 bug was a turn-based trigger that fired every
    # 25 partials (= every ~2 min on Gemini). Module-level constant must
    # remain char-based.
    assert isinstance(DEFAULT_USER_CHAR_TRIGGER, int)
    assert DEFAULT_USER_CHAR_TRIGGER > MIN_TRANSCRIPT_CHARS
