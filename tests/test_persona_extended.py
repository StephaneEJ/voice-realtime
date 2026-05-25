"""Sprint 3 — persona schema extensions (context + safety + custom commands).

Round-trip tests for new fields:
- project, cli_context, rolling_recap, rolling_terminal
- web_allowlist, ask_before_acting
- custom_commands (list of {trigger, action} dicts)

Coercion edge cases for booleans (YAML true/false vs strings) and command
list shape (drop malformed entries instead of crashing).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_realtime.persona import (
    Persona,
    _coerce_bool,
    _coerce_command_list,
    load_persona_file,
    parse_persona_text,
)


# ─── _coerce_bool ──────────────────────────────────────────────────────────


def test_coerce_bool_native_true() -> None:
    assert _coerce_bool(True) is True


def test_coerce_bool_native_false() -> None:
    assert _coerce_bool(False) is False


def test_coerce_bool_string_true_variants() -> None:
    for s in ("true", "True", "yes", "YES", "1", "on"):
        assert _coerce_bool(s) is True, f"failed on {s!r}"


def test_coerce_bool_string_false_variants() -> None:
    for s in ("false", "no", "0", "off", "n'importe quoi"):
        assert _coerce_bool(s) is False, f"failed on {s!r}"


def test_coerce_bool_none_uses_default() -> None:
    assert _coerce_bool(None, default=True) is True
    assert _coerce_bool(None, default=False) is False


# ─── _coerce_command_list ──────────────────────────────────────────────────


def test_coerce_command_list_valid() -> None:
    items = [
        {"trigger": "capture", "action": "vault_write(...)"},
        {"trigger": "search", "action": "web_search(query=...)"},
    ]
    out = _coerce_command_list(items)
    assert len(out) == 2
    assert out[0] == {"trigger": "capture", "action": "vault_write(...)"}


def test_coerce_command_list_drops_malformed() -> None:
    items = [
        {"trigger": "ok", "action": "valid"},
        "string instead of dict",       # malformed
        {"trigger": "", "action": "x"},  # empty trigger
        {"trigger": "x", "action": ""},  # empty action
        {"only_trigger": "x"},           # missing action
        None,
    ]
    out = _coerce_command_list(items)
    assert len(out) == 1
    assert out[0]["trigger"] == "ok"


def test_coerce_command_list_non_list_returns_empty() -> None:
    assert _coerce_command_list(None) == []
    assert _coerce_command_list({"trigger": "x"}) == []
    assert _coerce_command_list("nope") == []


# ─── Round-trip Persona with new fields ────────────────────────────────────


_PERSONA_EXTENDED = """---
type: voice-persona
slug: test-ext
name: Test Extended
project: Voice Realtime
cli_context: true
rolling_recap: false
rolling_terminal: true
ask_before_acting: true
web_allowlist:
  - claude.ai
  - github.com
custom_commands:
  - trigger: capture this
    action: vault_write(path=daily/today.md)
  - trigger: search docs
    action: web_search(allowlist=docs)
---

# Identité
Persona test sprint 3.
"""


def test_persona_extended_round_trip(tmp_path: Path) -> None:
    f = tmp_path / "test-ext.md"
    f.write_text(_PERSONA_EXTENDED, encoding="utf-8")
    p = load_persona_file(f)
    assert p.project == "Voice Realtime"
    assert p.cli_context is True
    assert p.rolling_recap is False
    assert p.rolling_terminal is True
    assert p.ask_before_acting is True
    assert p.web_allowlist == ["claude.ai", "github.com"]
    assert len(p.custom_commands) == 2
    assert p.custom_commands[0]["trigger"] == "capture this"
    assert p.custom_commands[1]["action"] == "web_search(allowlist=docs)"


def test_persona_defaults_when_extended_fields_absent(tmp_path: Path) -> None:
    """A persona that omits all the new fields must still load with the
    documented defaults — backwards compatible with existing personas.
    """
    minimal = """---
type: voice-persona
slug: bare
name: Bare
---

# Identité
Minimal persona.
"""
    f = tmp_path / "bare.md"
    f.write_text(minimal, encoding="utf-8")
    p = load_persona_file(f)
    assert p.project is None
    assert p.cli_context is False
    assert p.rolling_recap is True  # default ON per docs
    assert p.rolling_terminal is False
    assert p.web_allowlist == []
    assert p.ask_before_acting is False
    assert p.custom_commands == []


def test_persona_malformed_custom_commands_skipped(tmp_path: Path) -> None:
    """A bogus custom_commands entry must not crash load_persona_file."""
    src = """---
type: voice-persona
slug: bad-cmds
name: Bad Cmds
custom_commands:
  - trigger: ok
    action: real
  - "string entry"
  - trigger: empty-action
    action: ""
---

# Identité
Test.
"""
    f = tmp_path / "bad-cmds.md"
    f.write_text(src, encoding="utf-8")
    p = load_persona_file(f)
    assert len(p.custom_commands) == 1
    assert p.custom_commands[0]["trigger"] == "ok"


def test_persona_bool_string_in_yaml(tmp_path: Path) -> None:
    """If the UI editor writes back booleans as strings, parser must still
    coerce them properly (don't crash, don't end up with truthy 'false').
    """
    src = """---
type: voice-persona
slug: stringy
name: Stringy
cli_context: "true"
rolling_recap: "false"
ask_before_acting: "yes"
---

# Identité
Stringy bools.
"""
    f = tmp_path / "stringy.md"
    f.write_text(src, encoding="utf-8")
    p = load_persona_file(f)
    assert p.cli_context is True
    assert p.rolling_recap is False
    assert p.ask_before_acting is True
