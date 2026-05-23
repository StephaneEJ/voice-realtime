"""Context detector — reads active project context for system prompt injection.

Strategy : a naive `text[:N]` slice on long project notes truncates the most
recent and operationally-relevant sections (Road Map status, Bilan livraison,
Reste à faire). Instead, we parse the markdown by H2/H3 headings, score each
section by priority keywords, and concatenate them in priority order until the
char budget is exhausted. Frontmatter always kept first.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

VAULT_ROOT = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
LIFE_PHASES_DIR = VAULT_ROOT / "2 CASQUETTES" / "Life Phases"
PROJECTS_DIR = VAULT_ROOT / "1 PROJETS"

DEFAULT_MAX_CHARS = 12000

# Keywords that boost section priority — order matters (first match wins).
# "sprint" and "conclusion session" sit at the top because they are written
# AFTER each session and carry the freshest delivery + decision state. Without
# this boost the project note's older "Bilan" sections would win and the model
# would suggest features already shipped.
SECTION_PRIORITY_KEYWORDS = [
    ("sprint", 105),         # latest sprint log — freshest
    ("conclusion session", 102),
    ("bilan", 100),          # earlier delivery summary
    ("reste à faire", 95),
    ("reste a faire", 95),
    ("road map", 90),
    ("roadmap", 90),
    ("actions stéphane", 85),
    ("actions stephane", 85),
    ("statut", 80),
    ("status", 80),
    ("phase 1", 75),
    ("phase 2", 75),
    ("phase 3", 70),
    ("matrice", 65),
    ("tests", 60),
    ("feature requests", 55),
    ("décisions", 50),
    ("decisions", 50),
    ("description", 45),
    ("contexte", 40),
    ("code & infra", 35),
    ("tensions", 20),         # discussion sections — useful but not load-bearing
    ("questions ouvertes", 15),
    ("key notes", 10),
]


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
            main_note = project_dir / f"{project_dir.name}.md"
            if main_note.exists():
                return main_note
            md_files = list(project_dir.glob("*.md"))
            if md_files:
                return md_files[0]
    return None


def _score_heading(heading: str) -> int:
    """Return the priority score for a section heading. Default 30 if no match."""
    h = heading.lower()
    for needle, score in SECTION_PRIORITY_KEYWORDS:
        if needle in h:
            return score
    return 30


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, rest). Empty frontmatter if absent."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :]


def extract_prioritized_sections(text: str, budget: int) -> str:
    """Split markdown by H2/H3, sort by priority, concatenate to budget.

    Always keeps frontmatter and any preamble before the first H2. Then walks
    sections in priority order (descending score, ties keep document order),
    appending until the char budget would be exceeded.
    """
    frontmatter, body = _split_frontmatter(text)

    # Find H2/H3 boundaries; preserve preamble (text before first heading).
    heading_re = re.compile(r"^(#{2,3}) (.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(body))
    if not matches:
        return (frontmatter + body)[:budget]

    preamble = body[: matches[0].start()]

    sections: list[tuple[int, int, str]] = []  # (score, doc_order, content)
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        heading_text = m.group(2)
        content = body[start:end]
        score = _score_heading(heading_text)
        sections.append((score, i, content))

    # Sort by descending score, then by document order (stable for ties).
    sections.sort(key=lambda s: (-s[0], s[1]))

    out_parts = [frontmatter, preamble]
    used = len(frontmatter) + len(preamble)
    for _, _, content in sections:
        if used + len(content) > budget:
            # Try to fit a truncated version if there's meaningful room left.
            remaining = budget - used
            if remaining > 200:
                out_parts.append(content[:remaining])
                used = budget
            break
        out_parts.append(content)
        used += len(content)

    return "".join(out_parts)


def build_context(
    project_hint: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    include_cli: bool = False,
) -> str:
    """Build a compact context string suitable for system_instruction injection.

    Budget split when `include_cli=False` : 70% project / 30% daily.
    When `include_cli=True` : 50% project / 20% daily / 30% active CLI
    transcript (Claude Code OR OpenCode, auto-detected ; compacted via
    `claude -p` if it exceeds the threshold).
    """
    parts: list[str] = []

    if include_cli:
        project_budget = int(max_chars * 0.50)
        daily_budget = int(max_chars * 0.20)
        cli_budget = max_chars - project_budget - daily_budget
    else:
        project_budget = int(max_chars * 0.70)
        daily_budget = max_chars - project_budget
        cli_budget = 0

    if project_hint:
        project_note = find_project_note(project_hint)
        if project_note is not None:
            text = project_note.read_text(encoding="utf-8", errors="ignore")
            extracted = extract_prioritized_sections(text, project_budget)
            parts.append(f"## Projet actif\n{extracted}")

    phase_dir = find_active_phase()
    if phase_dir is not None:
        daily = read_daily_note(phase_dir)
        if daily:
            parts.append(f"## Daily note du jour ({phase_dir.name})\n{daily[:daily_budget]}")

    if include_cli and cli_budget > 0:
        # Imported lazily so users without claude CLI don't pay the import cost.
        from voice_realtime.cli_context import build_cli_context
        cc_block = build_cli_context(
            compact_threshold=cli_budget,
            compact_target=cli_budget - 200,
        )
        if cc_block:
            parts.append(cc_block[:cli_budget])

    text = "\n\n".join(parts)
    return text[:max_chars]
