"""Tests for the persona system (Phase 3.A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_realtime.persona import (
    Persona,
    PersonaError,
    load_persona_file,
    list_personas,
    load_persona_by_slug,
    parse_persona_text,
)
from voice_realtime.persona_skills import (
    _resolve_skill_path,
    build_persona_knowledge_block,
    load_notes,
    load_skills,
)


PERSONA_MIN = """---
type: voice-persona
slug: test-min
name: Test Min
---

# Identité
Je suis un persona de test minimal.

# Personnalité
- Direct
"""

PERSONA_FULL = """---
type: voice-persona
slug: test-full
name: Test Full
description: Un persona complet de test
voice: Charon
model: gemini-2.5-flash-native-audio-latest
provider: gemini
vad: patient
creativity: creative
greeting_mode: user
greeting_text: "Vas-y, je t'écoute."
avatar: 6 ATTACHMENTS/personas/test.png
obsidian_skills:
  - skill-a
  - skill-b
obsidian_notes:
  - "4 GARDEN/*.md"
tools:
  - get_current_datetime
  - get_weather
---

# Identité
Je suis un persona de test complet.
"""


def test_parse_min_persona(tmp_path: Path) -> None:
    p = tmp_path / "test-min.md"
    p.write_text(PERSONA_MIN, encoding="utf-8")
    persona = load_persona_file(p)
    assert persona.slug == "test-min"
    assert persona.name == "Test Min"
    assert persona.voice is None
    assert persona.vad is None
    assert persona.greeting_mode == "persona"  # default
    assert persona.obsidian_skills == []
    assert persona.obsidian_notes == []
    assert "Je suis un persona de test minimal" in persona.system_prompt
    assert persona.source_path == p


def test_parse_full_persona(tmp_path: Path) -> None:
    p = tmp_path / "test-full.md"
    p.write_text(PERSONA_FULL, encoding="utf-8")
    persona = load_persona_file(p)
    assert persona.slug == "test-full"
    assert persona.name == "Test Full"
    assert persona.voice == "Charon"
    assert persona.model == "gemini-2.5-flash-native-audio-latest"
    assert persona.provider == "gemini"
    assert persona.vad == "patient"
    assert persona.creativity == "creative"
    assert persona.greeting_mode == "user"
    assert persona.greeting_text == "Vas-y, je t'écoute."
    assert persona.avatar == "6 ATTACHMENTS/personas/test.png"
    assert persona.obsidian_skills == ["skill-a", "skill-b"]
    assert persona.obsidian_notes == ["4 GARDEN/*.md"]
    assert persona.tools == ["get_current_datetime", "get_weather"]
    assert persona.has_obsidian_filter is True


def test_missing_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "broken.md"
    p.write_text("# Just markdown, no frontmatter\n\nBody.", encoding="utf-8")
    with pytest.raises(PersonaError, match="missing YAML frontmatter"):
        load_persona_file(p)


def test_wrong_type(tmp_path: Path) -> None:
    p = tmp_path / "wrong.md"
    p.write_text("---\ntype: skill\nslug: x\nname: X\n---\n\nBody", encoding="utf-8")
    with pytest.raises(PersonaError, match="expected 'voice-persona'"):
        load_persona_file(p)


def test_invalid_greeting_mode(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text(
        "---\ntype: voice-persona\nslug: x\nname: X\ngreeting_mode: chuchote\n---\n\nBody",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="greeting_mode"):
        load_persona_file(p)


def test_empty_body(tmp_path: Path) -> None:
    p = tmp_path / "empty.md"
    p.write_text("---\ntype: voice-persona\nslug: x\nname: X\n---\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="empty system prompt"):
        load_persona_file(p)


def test_list_personas(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(PERSONA_MIN.replace("test-min", "a").replace("Test Min", "A"), encoding="utf-8")
    (tmp_path / "b.md").write_text(PERSONA_MIN.replace("test-min", "b").replace("Test Min", "B"), encoding="utf-8")
    (tmp_path / "broken.md").write_text("not valid", encoding="utf-8")
    personas = list_personas(tmp_path)
    slugs = [p.slug for p in personas]
    assert "a" in slugs
    assert "b" in slugs
    assert "broken" not in slugs  # silently skipped


def test_load_by_slug(tmp_path: Path) -> None:
    (tmp_path / "found.md").write_text(PERSONA_MIN.replace("test-min", "found").replace("Test Min", "Found"), encoding="utf-8")
    persona = load_persona_by_slug("found", tmp_path)
    assert persona.slug == "found"


def test_load_by_slug_not_found(tmp_path: Path) -> None:
    with pytest.raises(PersonaError, match="not found"):
        load_persona_by_slug("ghost", tmp_path)


def test_coerce_list_scalar(tmp_path: Path) -> None:
    p = tmp_path / "scalar.md"
    p.write_text(
        '---\ntype: voice-persona\nslug: s\nname: S\nobsidian_skills: solo-skill\n---\nbody',
        encoding="utf-8",
    )
    persona = load_persona_file(p)
    assert persona.obsidian_skills == ["solo-skill"]


def test_skill_path_resolution(tmp_path: Path) -> None:
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "my-skill.md").write_text("Content", encoding="utf-8")
    found = _resolve_skill_path("my-skill", cmd_dir)
    assert found is not None
    assert found.name == "my-skill.md"

    assert _resolve_skill_path("nonexistent", cmd_dir) is None


def test_load_skills(tmp_path: Path) -> None:
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "alpha.md").write_text("Alpha content", encoding="utf-8")
    (cmd_dir / "beta.md").write_text("Beta content", encoding="utf-8")
    out = load_skills(["alpha", "beta", "gamma"], cmd_dir)
    assert "alpha" in out
    assert "beta" in out
    assert "gamma" not in out
    assert out["alpha"] == "Alpha content"


def test_load_skills_truncates_large_files(tmp_path: Path) -> None:
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    huge = "x" * 10000
    (cmd_dir / "big.md").write_text(huge, encoding="utf-8")
    out = load_skills(["big"], cmd_dir, max_chars_per_file=500)
    assert len(out["big"]) < len(huge)
    assert "tronqué" in out["big"]


def test_load_notes_glob(tmp_path: Path) -> None:
    # Simulate vault structure
    (tmp_path / "4 GARDEN").mkdir()
    (tmp_path / "4 GARDEN" / "note-a.md").write_text("A", encoding="utf-8")
    (tmp_path / "4 GARDEN" / "note-b.md").write_text("B", encoding="utf-8")
    (tmp_path / "3 RESSOURCES").mkdir()
    (tmp_path / "3 RESSOURCES" / "elsewhere.md").write_text("C", encoding="utf-8")

    out = load_notes(["4 GARDEN/**"], vault_root=tmp_path)
    relpaths = list(out.keys())
    assert any("note-a.md" in p for p in relpaths)
    assert any("note-b.md" in p for p in relpaths)
    assert not any("elsewhere" in p for p in relpaths)


def test_build_knowledge_block_empty_without_filter(tmp_path: Path) -> None:
    persona = Persona(slug="empty", name="Empty", system_prompt="body")
    assert build_persona_knowledge_block(persona) == ""


def test_build_knowledge_block_assembled(tmp_path: Path) -> None:
    cmd_dir = tmp_path / "cmds"
    cmd_dir.mkdir()
    (cmd_dir / "s1.md").write_text("Skill 1", encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "n1.md").write_text("Note 1", encoding="utf-8")
    persona = Persona(
        slug="p", name="P", system_prompt="body",
        obsidian_skills=["s1"],
        obsidian_notes=["notes/**"],
    )
    block = build_persona_knowledge_block(persona, commands_dir=cmd_dir, vault_root=vault)
    assert "Connaissances actives" in block
    assert "/s1" in block
    assert "Skill 1" in block
    assert "n1.md" in block
    assert "Note 1" in block
