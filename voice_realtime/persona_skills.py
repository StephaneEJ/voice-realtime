"""Persona-as-Filter on Obsidian vault — loads skills and notes referenced by
a persona's frontmatter so the model has the right "active knowledge".

Differentiator vs Kast (which stores all knowledge in localStorage): the vault
remains the source of truth; the persona is a *filter* — a curated subset of
skills/notes that the voice model can lean on.

Inputs:
- `obsidian_skills: [hormozi-offer, offer-audit]` → reads
   `~/.claude/commands/<slug>.md` (slash command files)
- `obsidian_notes: ["3 RESSOURCES/LIVRES/Hormozi/**", "4 GARDEN/Offers.md"]`
   → globs the vault and reads matching .md files

Returns a single concatenated string suitable for appending to the system
prompt. Length-capped to avoid blowing past the realtime model context window.
"""

from __future__ import annotations

import os
from pathlib import Path

from .persona import Persona, get_vault_root

# Project-level Claude Code skills live in `<vault>/.claude/commands/`. The
# user-level `~/.claude/commands/` is checked as a fallback (Stéphane doesn't
# have one today but other users might).
def _default_commands_dirs() -> list[Path]:
    return [
        get_vault_root() / ".claude" / "commands",
        Path.home() / ".claude" / "commands",
    ]


CLAUDE_COMMANDS_DIR = Path.home() / ".claude" / "commands"  # legacy const for tests

# Soft caps to keep the injected knowledge block from dominating the context
# window. The realtime model needs room for the actual conversation.
DEFAULT_MAX_CHARS_PER_FILE = 4000
DEFAULT_MAX_TOTAL_CHARS = 16000


def _read_truncated(path: Path, max_chars: int) -> str:
    """Read a file safely, truncating with a marker if needed."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[…tronqué — {len(text) - max_chars} chars omis]"


def _resolve_skill_path(slug: str, commands_dir: Path | None = None) -> Path | None:
    """Locate a slash-command markdown file for a skill slug.

    Looks in <vault>/.claude/commands/ first (project-level skills), then
    ~/.claude/commands/ (user-level). Each is searched directly and
    recursively. Returns None if not found.

    When `commands_dir` is provided explicitly, only that path is searched
    (used by tests).
    """
    search_dirs: list[Path] = [commands_dir] if commands_dir else _default_commands_dirs()
    for base in search_dirs:
        direct = base / f"{slug}.md"
        if direct.exists():
            return direct
        if base.exists():
            matches = list(base.rglob(f"{slug}.md"))
            if matches:
                matches.sort(key=lambda p: len(p.parts))
                return matches[0]
    return None


def load_skills(slugs: list[str], commands_dir: Path | None = None,
                max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE) -> dict[str, str]:
    """Return {slug: content} for each resolvable skill. Missing skills are
    silently skipped — the caller may want to inform the user separately.
    """
    out: dict[str, str] = {}
    for slug in slugs:
        slug = slug.strip().lstrip("/")
        if not slug:
            continue
        path = _resolve_skill_path(slug, commands_dir)
        if path is None:
            continue
        content = _read_truncated(path, max_chars_per_file)
        if content:
            out[slug] = content
    return out


def load_notes(patterns: list[str], vault_root: Path | None = None,
               max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE) -> dict[str, str]:
    """Glob the vault for notes matching the persona's `obsidian_notes` field.

    Patterns are vault-relative (e.g. "3 RESSOURCES/LIVRES/Hormozi/**").
    Returns {relpath: content}.
    """
    vault = vault_root or get_vault_root()
    if not vault.exists():
        return {}
    out: dict[str, str] = {}
    seen: set[Path] = set()
    for pattern in patterns:
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue
        # Glob both file paths and "**" recursive patterns
        if pattern.endswith("**"):
            base_part = pattern[:-2].strip("/")
            base = vault / base_part if base_part else vault
            if base.exists():
                matches = list(base.rglob("*.md"))
            else:
                matches = []
        elif "*" in pattern:
            matches = list(vault.glob(pattern))
        else:
            target = vault / pattern
            if target.is_file():
                matches = [target]
            elif target.is_dir():
                matches = list(target.rglob("*.md"))
            else:
                matches = []
        for path in matches:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                relpath = path.relative_to(vault)
            except ValueError:
                continue
            content = _read_truncated(path, max_chars_per_file)
            if content:
                out[str(relpath)] = content
    return out


def build_persona_knowledge_block(
    persona: Persona,
    *,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE,
    commands_dir: Path | None = None,
    vault_root: Path | None = None,
) -> str:
    """Assemble the knowledge block to append to a persona's system prompt.

    Format:
        # Connaissances actives (persona <name>)
        ## Skills disponibles
        ### <slug-1>
        <content>
        ...
        ## Notes vault
        ### <relpath-1>
        <content>
        ...

    Total length is capped at `max_total_chars`. When over budget, files are
    included in order until budget is exhausted and the rest are listed by
    title only.
    """
    if not persona.has_obsidian_filter:
        return ""

    skills = load_skills(persona.obsidian_skills, commands_dir, max_chars_per_file)
    notes = load_notes(persona.obsidian_notes, vault_root, max_chars_per_file)

    sections: list[str] = [f"# Connaissances actives (persona {persona.name})"]
    used_chars = len(sections[0])
    truncated_skills: list[str] = []
    truncated_notes: list[str] = []

    if skills:
        sections.append("## Skills disponibles")
        used_chars += len(sections[-1])
        for slug, content in skills.items():
            header = f"### /{slug}"
            block_len = len(header) + len(content) + 2
            if used_chars + block_len > max_total_chars:
                truncated_skills.append(slug)
                continue
            sections.append(header)
            sections.append(content)
            used_chars += block_len

    if notes:
        sections.append("## Notes vault")
        used_chars += len(sections[-1])
        for relpath, content in notes.items():
            header = f"### {relpath}"
            block_len = len(header) + len(content) + 2
            if used_chars + block_len > max_total_chars:
                truncated_notes.append(relpath)
                continue
            sections.append(header)
            sections.append(content)
            used_chars += block_len

    if truncated_skills or truncated_notes:
        sections.append("## Aperçus (non chargés faute de budget contexte)")
        if truncated_skills:
            sections.append("Skills : " + ", ".join(truncated_skills))
        if truncated_notes:
            sections.append("Notes : " + ", ".join(truncated_notes))

    return "\n\n".join(sections)


def report_missing_references(persona: Persona,
                              commands_dir: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (missing_skills, missing_note_patterns) to help the user
    diagnose typos in their persona frontmatter.
    """
    missing_skills: list[str] = []
    for slug in persona.obsidian_skills:
        if _resolve_skill_path(slug.strip().lstrip("/"), commands_dir) is None:
            missing_skills.append(slug)
    missing_notes: list[str] = []
    vault = get_vault_root()
    for pattern in persona.obsidian_notes:
        matches = load_notes([pattern], vault, max_chars_per_file=10)
        if not matches:
            missing_notes.append(pattern)
    return missing_skills, missing_notes
