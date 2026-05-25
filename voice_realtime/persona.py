"""Persona system — Phase 3.A.

A persona = identity + voice + behavioural presets + filter onto Obsidian vault
skills/notes. Stored as Markdown files with YAML frontmatter under
`_System/voice-personas/<slug>.md` in the vault.

A persona supersedes the inline base_prompt in cli.py:talk when --persona
is passed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VAULT_ROOT_DEFAULT = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
PERSONAS_SUBDIR = "_System/voice-personas"


def get_vault_root() -> Path:
    """Allow override via env var for tests; default to standard vault path."""
    env = os.environ.get("VOICE_REALTIME_VAULT_ROOT")
    return Path(env) if env else VAULT_ROOT_DEFAULT


def get_personas_dir() -> Path:
    return get_vault_root() / PERSONAS_SUBDIR


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Persona:
    """A loaded persona definition.

    Required: slug, name, system_prompt.
    All other fields are optional with sensible defaults — the CLI flag values
    or provider defaults take over when a field is not specified.
    """

    slug: str
    name: str
    system_prompt: str
    # Behavioural presets
    description: str = ""
    voice: str | None = None
    model: str | None = None
    provider: str | None = None  # "gemini" | "openai", None = use CLI default
    vad: str | None = None       # reactive | balanced | patient | very-patient
    creativity: str | None = None  # precise | balanced | creative | wild (future)
    greeting_mode: str = "persona"  # "persona" or "user"
    greeting_text: str | None = None
    avatar: str | None = None  # relative vault path
    # Obsidian filter — drives what the persona "knows"
    obsidian_skills: list[str] = field(default_factory=list)
    obsidian_notes: list[str] = field(default_factory=list)
    # Capabilities the persona may invoke (informational; actual tool wiring
    # lives in voice_realtime/tools/)
    tools: list[str] = field(default_factory=list)
    # Sprint 3 — context + safety presets
    project: str | None = None  # vault project hint, equivalent to --project CLI flag
    cli_context: bool = False   # equivalent to --cli-context (inject Claude Code transcript)
    rolling_recap: bool = True  # rolling recap of conversation every N min
    rolling_terminal: bool = False  # silent injection of new terminal content
    web_allowlist: list[str] = field(default_factory=list)  # domains for web_search
    ask_before_acting: bool = False  # gate WRITE_USER_SCOPE+ tool calls behind UI confirm
    aec: bool = False  # enable acoustic echo cancellation (chat without headphones)
    # Phrase → tool call recipes. Each item:
    #   {"trigger": "capture this", "action": "vault_write(path=..., content=...)"}
    # Free-form action string for now; future Sprint may parse into tool chains.
    custom_commands: list[dict] = field(default_factory=list)
    # Provenance — populated by load_persona_file
    source_path: Path | None = None

    @property
    def has_obsidian_filter(self) -> bool:
        return bool(self.obsidian_skills or self.obsidian_notes)


class PersonaError(Exception):
    """Raised when a persona file is malformed or missing required fields."""


def parse_persona_text(text: str, slug_hint: str | None = None) -> tuple[dict[str, Any], str]:
    """Split a persona markdown file into (frontmatter dict, body markdown).

    Pure function — no IO. Used by load_persona_file and tests.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise PersonaError(
            f"Persona file missing YAML frontmatter (---...---) "
            f"[slug={slug_hint!r}]"
        )
    fm_text, body = m.group(1), m.group(2).strip()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        raise PersonaError(f"YAML parse error in persona {slug_hint!r}: {exc}") from exc
    if not isinstance(fm, dict):
        raise PersonaError(f"Persona {slug_hint!r} frontmatter must be a YAML mapping")
    return fm, body


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    raise PersonaError(f"Expected list or string, got {type(value).__name__}")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """YAML bool already True/False; tolerate strings like 'true'/'false' for
    UI roundtrips where the editor wrote a string back.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    return bool(value)


def _coerce_command_list(value: Any) -> list[dict]:
    """custom_commands: each entry must be a dict with 'trigger' and 'action'
    keys. Anything else is dropped silently to avoid blowing up on malformed
    UI writes — the editor is responsible for shape, not the loader.
    """
    if not value:
        return []
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        trigger = str(item.get("trigger", "")).strip()
        action = str(item.get("action", "")).strip()
        if trigger and action:
            out.append({"trigger": trigger, "action": action})
    return out


def load_persona_file(path: Path) -> Persona:
    """Load a single persona from a Markdown+frontmatter file.

    Slug is derived from the filename stem unless overridden in frontmatter.
    """
    if not path.exists():
        raise PersonaError(f"Persona file not found: {path}")
    text = path.read_text(encoding="utf-8")
    slug_hint = path.stem
    fm, body = parse_persona_text(text, slug_hint=slug_hint)

    declared_type = fm.get("type")
    if declared_type is not None and declared_type != "voice-persona":
        raise PersonaError(
            f"Persona {slug_hint!r} has type={declared_type!r}, expected 'voice-persona'"
        )

    slug = str(fm.get("slug") or path.stem).strip()
    name = str(fm.get("name") or slug).strip()
    if not slug or not name:
        raise PersonaError(f"Persona {path} missing required field: slug/name")
    if not body:
        raise PersonaError(f"Persona {slug!r} has empty system prompt body")

    greeting_mode = str(fm.get("greeting_mode") or "persona").strip().lower()
    if greeting_mode not in ("persona", "user"):
        raise PersonaError(
            f"Persona {slug!r} greeting_mode must be 'persona' or 'user', got {greeting_mode!r}"
        )

    return Persona(
        slug=slug,
        name=name,
        system_prompt=body,
        description=str(fm.get("description") or "").strip(),
        voice=(str(fm["voice"]).strip() if fm.get("voice") else None),
        model=(str(fm["model"]).strip() if fm.get("model") else None),
        provider=(str(fm["provider"]).strip() if fm.get("provider") else None),
        vad=(str(fm["vad"]).strip() if fm.get("vad") else None),
        creativity=(str(fm["creativity"]).strip() if fm.get("creativity") else None),
        greeting_mode=greeting_mode,
        greeting_text=(str(fm["greeting_text"]).strip() if fm.get("greeting_text") else None),
        avatar=(str(fm["avatar"]).strip() if fm.get("avatar") else None),
        obsidian_skills=_coerce_list(fm.get("obsidian_skills")),
        obsidian_notes=_coerce_list(fm.get("obsidian_notes")),
        tools=_coerce_list(fm.get("tools")),
        project=(str(fm["project"]).strip() if fm.get("project") else None),
        cli_context=_coerce_bool(fm.get("cli_context"), default=False),
        rolling_recap=_coerce_bool(fm.get("rolling_recap"), default=True),
        rolling_terminal=_coerce_bool(fm.get("rolling_terminal"), default=False),
        web_allowlist=_coerce_list(fm.get("web_allowlist")),
        ask_before_acting=_coerce_bool(fm.get("ask_before_acting"), default=False),
        aec=_coerce_bool(fm.get("aec"), default=False),
        custom_commands=_coerce_command_list(fm.get("custom_commands")),
        source_path=path,
    )


def list_personas(personas_dir: Path | None = None) -> list[Persona]:
    """Discover and load all persona files under the personas directory.

    Errored files are skipped silently (one bad file shouldn't hide the rest)
    but the count of failures is logged at the warning level when caller asks.
    """
    personas_dir = personas_dir or get_personas_dir()
    if not personas_dir.exists():
        return []
    personas: list[Persona] = []
    for md_path in sorted(personas_dir.glob("*.md")):
        try:
            personas.append(load_persona_file(md_path))
        except PersonaError:
            continue
    return personas


def load_persona_by_slug(slug: str, personas_dir: Path | None = None) -> Persona:
    """Load a persona by its slug. Raises PersonaError if not found."""
    slug = slug.strip().lower()
    personas_dir = personas_dir or get_personas_dir()
    candidate = personas_dir / f"{slug}.md"
    if candidate.exists():
        return load_persona_file(candidate)
    # Try matching by frontmatter slug field if file name differs
    for p in list_personas(personas_dir):
        if p.slug.lower() == slug:
            return p
    available = ", ".join(p.slug for p in list_personas(personas_dir)) or "(none)"
    raise PersonaError(
        f"Persona {slug!r} not found in {personas_dir}. Available: {available}"
    )
