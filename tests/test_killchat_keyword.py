"""Tests for the killchat keyword regex — anti-false-positive AND noise-tolerant."""

from __future__ import annotations

import pytest

from voice_realtime.cli import _is_killchat_keyword


@pytest.mark.parametrize(
    "text",
    [
        "killchat",
        "Kill chat.",
        " kill-chat ! ",
        "KILL CHAT",
        "kill chat",
        " . killchat . ",
        # Gemini STT diarization markers around the utterance (live bug 23/05)
        "<noise> Kill chat. <noise>",
        "<silence>kill-chat<noise>",
        "<music> killchat <silence>",
    ],
)
def test_killchat_matches(text: str) -> None:
    assert _is_killchat_keyword(text), f"expected match: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Tu peux killchat ta mère",
        "killchat ça",
        "kill chat ta mère",
        "On va killchat tout ça",
        "explique-moi le killchat",
    ],
)
def test_killchat_no_match(text: str) -> None:
    assert not _is_killchat_keyword(text), f"expected NO match: {text!r}"


def test_killchat_none_safe() -> None:
    assert _is_killchat_keyword(None) is False  # type: ignore[arg-type]
