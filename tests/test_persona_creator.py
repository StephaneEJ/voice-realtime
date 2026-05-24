"""Tests for persona_creator (Phase 3.D). The claude -p invocation is mocked."""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_realtime.persona_creator import (
    PersonaCreatorError,
    is_valid_slug,
    render_persona_file,
    save_persona,
)


def test_slug_validation() -> None:
    assert is_valid_slug("hormozi") is True
    assert is_valid_slug("coach-halt") is True
    assert is_valid_slug("test-3") is True
    assert is_valid_slug("9-personas") is True
    # Negative cases
    assert is_valid_slug("") is False
    assert is_valid_slug("Hormozi") is False  # uppercase
    assert is_valid_slug("hormozi/sub") is False
    assert is_valid_slug("-leading-dash") is False
    assert is_valid_slug("with space") is False
    assert is_valid_slug("a" * 50) is False  # too long


def test_render_minimal() -> None:
    content = render_persona_file(
        slug="test",
        name="Test",
        description="",
        body="# Identité\nBody",
    )
    assert "---" in content
    assert "slug: test" in content
    assert "name: Test" in content
    assert "description:" not in content  # empty omitted
    assert "voice:" not in content  # optional omitted (avoid voice-persona match)
    assert "greeting_mode: persona" in content  # default
    assert "# Identité" in content


def test_render_full() -> None:
    content = render_persona_file(
        slug="hormozi",
        name="Alex Hormozi",
        description="Coach offres",
        voice="Charon",
        model="gemini-2.5-flash-native-audio-latest",
        provider="gemini",
        vad="balanced",
        creativity="balanced",
        greeting_mode="persona",
        greeting_text="Salut Stéphane.",
        obsidian_skills=["hormozi-offer", "offer-audit"],
        obsidian_notes=["3 RESSOURCES/LIVRES/Hormozi/**"],
        tools=["get_current_datetime"],
        body="# Identité\nBody content",
    )
    assert "voice: Charon" in content
    assert "provider: gemini" in content
    assert "vad: balanced" in content
    assert 'greeting_text: "Salut Stéphane."' in content
    assert "- hormozi-offer" in content
    assert '- "3 RESSOURCES/LIVRES/Hormozi/**"' in content  # quoted
    assert "- get_current_datetime" in content


def test_save_persona(tmp_path: Path) -> None:
    content = "---\ntype: voice-persona\nslug: x\nname: X\n---\n\n# Identité\nbody"
    target = save_persona(content, "x", personas_dir=tmp_path)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == content


def test_save_persona_no_overwrite(tmp_path: Path) -> None:
    content = "---\ntype: voice-persona\nslug: x\nname: X\n---\n\n# Identité\nbody"
    save_persona(content, "x", personas_dir=tmp_path)
    with pytest.raises(PersonaCreatorError, match="already exists"):
        save_persona(content, "x", personas_dir=tmp_path)


def test_save_persona_overwrite(tmp_path: Path) -> None:
    content_v1 = "---\ntype: voice-persona\nslug: x\nname: X1\n---\n\n# Identité\nv1"
    content_v2 = "---\ntype: voice-persona\nslug: x\nname: X2\n---\n\n# Identité\nv2"
    save_persona(content_v1, "x", personas_dir=tmp_path)
    target = save_persona(content_v2, "x", personas_dir=tmp_path, overwrite=True)
    assert "v2" in target.read_text(encoding="utf-8")


def test_round_trip_with_loader(tmp_path: Path) -> None:
    """A persona created via render_persona_file must load back cleanly."""
    from voice_realtime.persona import load_persona_file

    content = render_persona_file(
        slug="roundtrip",
        name="Round Trip",
        description="Test round trip",
        voice="Charon",
        provider="gemini",
        vad="patient",
        greeting_mode="user",
        greeting_text="Vas-y.",
        obsidian_skills=["a", "b"],
        obsidian_notes=["notes/*.md"],
        body="# Identité\nJe suis testé.",
    )
    p = tmp_path / "roundtrip.md"
    p.write_text(content, encoding="utf-8")
    persona = load_persona_file(p)
    assert persona.slug == "roundtrip"
    assert persona.name == "Round Trip"
    assert persona.voice == "Charon"
    assert persona.vad == "patient"
    assert persona.greeting_mode == "user"
    assert persona.greeting_text == "Vas-y."
    assert persona.obsidian_skills == ["a", "b"]
    assert persona.obsidian_notes == ["notes/*.md"]
