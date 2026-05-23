"""Claude Code session context — injects the active CLI conversation.

Strategy : the latest `~/.claude/projects/<encoded-cwd>/*.jsonl` file is the
session that just spawned us. We strip tool_use / tool_result / thinking blocks
and keep only user/assistant text turns. If the result blows the budget,
`claude -p` Sonnet compacts it (preserves topic, decisions, blockers).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# When the raw transcript exceeds this, summarize with claude -p instead.
COMPACT_THRESHOLD_CHARS = 8000
COMPACT_TARGET_CHARS = 2500

COMPACT_PROMPT = """Tu reçois la transcription d'une conversation Claude Code (CLI) entre Stéphane
et un assistant. Résume-la en français en ~2000 caractères en gardant strictement :

- Le sujet actif (ce sur quoi ils travaillent en ce moment)
- Les décisions prises (technique, scope, priorité)
- Les blocages ou questions ouvertes
- Les fichiers / commits / chemins concrets mentionnés
- Ce que Stéphane vient de demander en dernier

Style direct, fragments OK, pas de bla-bla. Aucune introduction du genre
"voici un résumé". Commence direct par le sujet actif.

Transcription :
---
"""


def _encode_cwd_to_project_dir(cwd: Path) -> str:
    """Claude Code encodes /a/b/c → -a-b-c for the projects subdir name."""
    return "-" + str(cwd).strip("/").replace("/", "-")


def find_latest_session_jsonl(cwd: Path | None = None) -> Path | None:
    """Locate the jsonl backing the currently active Claude Code session.

    Resolution order :
    1. `$CLAUDE_CODE_SESSION_ID` — set by Claude Code when it spawns subprocesses.
       Most reliable since `uv run`'s cwd is the repo dir, not the session's cwd.
    2. cwd → parents walk → match against `<encoded>` project dirs.
    3. Global mtime fallback — latest jsonl across all projects.
    """
    # 1. Session ID env var — direct hit, no cwd guessing.
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        matches = list(CLAUDE_PROJECTS_ROOT.glob(f"*/{session_id}.jsonl"))
        if matches:
            return matches[0]

    # 2. cwd walk.
    cwd = cwd or Path(os.getcwd())
    for candidate in [cwd, *cwd.parents]:
        project_dir = CLAUDE_PROJECTS_ROOT / _encode_cwd_to_project_dir(candidate)
        if not project_dir.exists():
            continue
        jsonls = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if jsonls:
            return jsonls[0]

    # 3. Global mtime fallback — last resort if both above miss.
    all_jsonls = sorted(
        CLAUDE_PROJECTS_ROOT.glob("*/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return all_jsonls[0] if all_jsonls else None


def _extract_text_from_content(content: object) -> str:
    """Pull text out of a message.content (either str or list of content blocks)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def read_conversation_text(jsonl_path: Path, max_chars: int = 50000) -> str:
    """Reconstruct a clean user/assistant transcript from a Claude Code jsonl.

    Walks the file end-to-start (most recent first), accumulating turns until
    `max_chars` is reached, then reverses to chronological order.
    """
    try:
        lines = jsonl_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""

    turns: list[str] = []
    used = 0
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type not in ("user", "assistant"):
            continue
        msg = event.get("message", {}) or {}
        text = _extract_text_from_content(msg.get("content"))
        text = text.strip()
        if not text:
            continue
        # Skip empty user tool_result wrappers and system-reminder noise.
        if text.startswith("<system-reminder>") and text.endswith("</system-reminder>"):
            continue
        label = "Stéphane" if event_type == "user" else "Claude"
        turn = f"{label}: {text}"
        if used + len(turn) > max_chars:
            break
        turns.append(turn)
        used += len(turn) + 2
    turns.reverse()
    return "\n\n".join(turns)


def compact_with_claude_p(text: str, timeout_seconds: int = 60) -> str | None:
    """Use `claude -p` Sonnet to compact a long transcript. Returns None on failure."""
    if not text.strip():
        return None
    prompt = COMPACT_PROMPT + text + "\n---\n"
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


def find_git_repo(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default: cwd) until a `.git` directory is found."""
    start = start or Path(os.getcwd())
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def get_recent_git_log(repo: Path | None = None, count: int = 8) -> str | None:
    """Return `git log -<count> --oneline` for the detected repo, or None.

    Surfaces what actions the CLI session took that don't appear in the
    user/assistant text turns (tool_use blocks are stripped). The model
    otherwise has no way to know "we just shipped commit c834367".
    """
    repo = repo or find_git_repo()
    if repo is None:
        return None
    try:
        log_out = subprocess.run(
            ["git", "-C", str(repo), "log", f"-{count}", "--oneline", "--no-decorate"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if log_out.returncode != 0:
        return None
    log_lines = (log_out.stdout or "").strip()
    if not log_lines:
        return None
    # Also include short status to flag uncommitted in-flight work.
    try:
        status_out = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        status = (status_out.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        status = ""
    parts = [f"Repo : {repo.name}", "", "Derniers commits :", log_lines]
    if status:
        parts.extend(["", "Modifs non commitées :", status])
    return "\n".join(parts)


def build_claude_code_context(
    cwd: Path | None = None,
    compact_threshold: int = COMPACT_THRESHOLD_CHARS,
    compact_target: int = COMPACT_TARGET_CHARS,
) -> str | None:
    """Public entrypoint — find session, extract text, compact if needed.

    Returns a ready-to-inject block or None if no session was found / file empty.
    Includes a `git log` summary of the current repo so the model sees actions
    that happened via tool_use (commits, file edits) — not just text turns.
    """
    jsonl_path = find_latest_session_jsonl(cwd)
    if jsonl_path is None:
        return None
    raw = read_conversation_text(jsonl_path, max_chars=50000)
    if not raw:
        return None
    if len(raw) > compact_threshold:
        compacted = compact_with_claude_p(raw)
        body = compacted or raw[:compact_target]
    else:
        body = raw

    git_block = get_recent_git_log()
    sections = ["## Conversation Claude Code en cours", body]
    if git_block:
        sections += ["", "### État git du repo de travail", git_block]
    return "\n".join(sections)
