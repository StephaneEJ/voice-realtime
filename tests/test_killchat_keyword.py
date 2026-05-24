"""Tests for the killchat keyword regex — anti-false-positive AND noise-tolerant.

P0.2 update (2026-05-24): expanded to cover FR primary keywords + Gemini STT
misheard tolerance. Original bug: during an 18-min FR voice session, the user
said "killchat" several times but Gemini STT wrote "kilk", "kik", "24" — none
matched the strict EN regex. Fix: add FR keywords + lenient "kil*" misheard
pattern.
"""

from __future__ import annotations

import pytest

from voice_realtime.cli import _is_killchat_keyword


@pytest.mark.parametrize(
    "text",
    [
        # Legacy EN — still supported
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
        # FR primary (P0.2 2026-05-24)
        "termine la session",
        "Termine la session.",
        "TERMINE LA SESSION !",
        " termine la session ",
        "termine  la  session",  # multiple spaces (Gemini sometimes inserts)
        "<noise> termine la session <silence>",
        # FR alt
        "fin jarvis",
        "Fin Jarvis.",
        "FIN JARVIS",
        # EN alt
        "stop session",
        "Stop session.",
        # Misheard tolerance (real STT artifacts observed 2026-05-24)
        "kilk chat",
        "Kilk chat.",
        "kik chat",
        "kil chat",
        "killé chat",
        "<noise> kilk chat <silence>",
    ],
)
def test_killchat_matches(text: str) -> None:
    assert _is_killchat_keyword(text), f"expected match: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "",
        # No accidental mid-sentence matches
        "Tu peux killchat ta mère",
        "killchat ça",
        "kill chat ta mère",
        "On va killchat tout ça",
        "explique-moi le killchat",
        # FR keyword as part of a larger sentence must NOT match
        "tu peux termine la session de l'utilisateur",
        "il faut fin jarvis avant de partir",
        "ils ont dit stop session puis ils sont partis",
        # The "24" misheard observed in the 18-min session must NOT match
        # (it's NOT a killchat — just an unrelated number Gemini transcribed)
        "24",
        "vingt-quatre",
        # Short utterances that share a prefix must NOT trigger
        "stop",
        "fin",
        "session",
        "kil",          # too short — no "chat" follows
        "kilk",         # missing " chat"
        "termine",      # missing "la session"
        # Mid-sentence misheards must NOT match
        "tu peux kilk chat avec quelqu'un",
        # Other FR words starting with "kil" mustn't false-positive when
        # followed by "chat" in a longer phrase
        "kilo de chat dans le sac",
    ],
)
def test_killchat_no_match(text: str) -> None:
    assert not _is_killchat_keyword(text), f"expected NO match: {text!r}"


def test_killchat_none_safe() -> None:
    assert _is_killchat_keyword(None) is False  # type: ignore[arg-type]
