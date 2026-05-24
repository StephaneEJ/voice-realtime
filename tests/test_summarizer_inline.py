"""Tests for the post-session synthesis inlining into voice-session notes (3.G)."""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_realtime.summarizer import SummaryResult, _replace_placeholder_in_transcript


PLACEHOLDER_NOTE = """---
date: 2026-05-24
time: 12:34
provider: gemini
---

# Voice Session — 2026-05-24 12:34

## Stats
- Provider : `gemini`

## Transcript

### Toi
> bonjour

### Modèle
> salut

## Notes post-session

_(à compléter manuellement ou via skill /summarize-voice à venir)_
"""


def _summary(**kwargs) -> SummaryResult:
    return SummaryResult(
        topic_summary=kwargs.get("topic_summary", "Sujet test"),
        decisions=kwargs.get("decisions", ["Décision A"]),
        actions=kwargs.get("actions", [{"what": "Action 1", "when": "today", "owner": "stephane"}]),
        insights=kwargs.get("insights", ["Insight Z"]),
        unresolved_questions=kwargs.get("unresolved_questions", []),
        transcript_path=Path("/dev/null"),
        project_note_path=None,
        appended=False,
    )


def test_replaces_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "session.md"
    p.write_text(PLACEHOLDER_NOTE, encoding="utf-8")
    summary = _summary()
    modified = _replace_placeholder_in_transcript(p, summary)
    assert modified is True
    text = p.read_text(encoding="utf-8")
    assert "Synthèse auto" in text
    assert "Sujet test" in text
    assert "Décision A" in text
    assert "Action 1" in text
    assert "Insight Z" in text
    # Placeholder gone
    assert "à compléter manuellement" not in text


def test_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "session.md"
    p.write_text(PLACEHOLDER_NOTE, encoding="utf-8")
    summary = _summary()
    first = _replace_placeholder_in_transcript(p, summary)
    assert first is True
    # Second call should detect existing synthesis and skip
    second = _replace_placeholder_in_transcript(p, summary)
    assert second is False
    # Only one Synthèse section
    text = p.read_text(encoding="utf-8")
    assert text.count("Synthèse auto") == 1


def test_appends_when_no_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "session.md"
    p.write_text("# Session\n\n## Transcript\n\nstuff\n", encoding="utf-8")
    summary = _summary()
    modified = _replace_placeholder_in_transcript(p, summary)
    assert modified is True
    assert "Synthèse auto" in p.read_text(encoding="utf-8")


def test_handles_no_decisions(tmp_path: Path) -> None:
    p = tmp_path / "session.md"
    p.write_text(PLACEHOLDER_NOTE, encoding="utf-8")
    summary = _summary(decisions=[], actions=[], insights=[], unresolved_questions=[])
    _replace_placeholder_in_transcript(p, summary)
    text = p.read_text(encoding="utf-8")
    assert text.count("_(aucune)_") >= 2  # décisions + actions + questions
    assert "_(aucun)_" in text  # insights


def test_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "ghost.md"
    summary = _summary()
    assert _replace_placeholder_in_transcript(p, summary) is False
