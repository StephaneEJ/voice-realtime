"""Context detector — reads active project context for system prompt injection."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

VAULT_ROOT = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
LIFE_PHASES_DIR = VAULT_ROOT / "2 CASQUETTES" / "Life Phases"
PROJECTS_DIR = VAULT_ROOT / "1 PROJETS"


def find_active_phase() -> Path | None:
    """Find phase folder with `status: active` in its Intention.md."""
    if not LIFE_PHASES_DIR.exists():
        return None
    for phase_dir in LIFE_PHASES_DIR.iterdir():
        if not phase_dir.is_dir():
            continue
        for intention in phase_dir.glob("*Intention*.md"):
            try:
                content = intention.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"^status:\s*active", content, re.MULTILINE):
                return phase_dir
    return None


def read_daily_note(phase_dir: Path, on_date: date | None = None) -> str | None:
    """Read today's daily note in the active phase."""
    today = on_date or date.today()
    daily_path = phase_dir / f"{today.isoformat()}.md"
    if not daily_path.exists():
        return None
    try:
        return daily_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def find_project_note(slug_or_name: str) -> Path | None:
    """Find a project note by slug or partial name match."""
    if not PROJECTS_DIR.exists():
        return None
    pattern = slug_or_name.lower()
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        if pattern in project_dir.name.lower():
            # Look for the main note inside (same name as folder, or first .md)
            main_note = project_dir / f"{project_dir.name}.md"
            if main_note.exists():
                return main_note
            md_files = list(project_dir.glob("*.md"))
            if md_files:
                return md_files[0]
    return None


def build_context(project_hint: str | None = None, max_chars: int = 6000) -> str:
    """Build a compact context string suitable for system_instruction injection."""
    parts: list[str] = []

    # 1. Project note if specified
    if project_hint:
        project_note = find_project_note(project_hint)
        if project_note is not None:
            text = project_note.read_text(encoding="utf-8", errors="ignore")
            parts.append(f"## Projet actif\n{text[:max_chars // 2]}")

    # 2. Active phase daily note
    phase_dir = find_active_phase()
    if phase_dir is not None:
        daily = read_daily_note(phase_dir)
        if daily:
            parts.append(f"## Daily note du jour ({phase_dir.name})\n{daily[:max_chars // 3]}")

    text = "\n\n".join(parts)
    return text[:max_chars]
