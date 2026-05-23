"""CLI session context — injects the active coding-CLI conversation.

Supports both Claude Code (jsonl per session under ~/.claude/projects/) and
OpenCode (SQLite db at ~/.local/share/opencode/opencode.db). Auto-detects
which one launched us via env vars, with mtime fallbacks. Tool_use blocks
are stripped (the model gets a `git log` summary for that signal instead);
text turns are concatenated. Result is compacted via `claude -p` Sonnet
when it exceeds the budget.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
OPENCODE_DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# When the raw transcript exceeds this, summarize with claude -p instead.
COMPACT_THRESHOLD_CHARS = 8000
COMPACT_TARGET_CHARS = 2500

COMPACT_PROMPT = """Tu reçois la transcription d'une conversation CLI (Claude Code ou OpenCode)
entre Stéphane et un assistant. Résume-la en français en ~2000 caractères en
gardant strictement :

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


# ─── Source abstraction ────────────────────────────────────────────────


class ConversationSource(ABC):
    """A CLI agent whose session transcripts we know how to read."""

    name: str

    @abstractmethod
    def find_active_session(self, cwd: Path | None = None) -> object | None:
        """Return a source-specific session handle (Path, id, ...) or None."""

    @abstractmethod
    def read_transcript(self, handle: object, max_chars: int = 50000) -> str:
        """Extract a clean user/assistant text transcript for the session."""

    @abstractmethod
    def last_activity_ts(self, handle: object) -> float:
        """Unix timestamp of most recent activity — used for cross-source picking."""


def _encode_cwd_to_claude_project_dir(cwd: Path) -> str:
    """Claude Code encodes /a/b/c → -a-b-c for the projects subdir name."""
    return "-" + str(cwd).strip("/").replace("/", "-")


class ClaudeCodeSource(ConversationSource):
    name = "claude-code"

    def find_active_session(self, cwd: Path | None = None) -> Path | None:
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if session_id:
            matches = list(CLAUDE_PROJECTS_ROOT.glob(f"*/{session_id}.jsonl"))
            if matches:
                return matches[0]
        cwd = cwd or Path(os.getcwd())
        for candidate in [cwd, *cwd.parents]:
            project_dir = CLAUDE_PROJECTS_ROOT / _encode_cwd_to_claude_project_dir(candidate)
            if not project_dir.exists():
                continue
            jsonls = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if jsonls:
                return jsonls[0]
        if CLAUDE_PROJECTS_ROOT.exists():
            all_jsonls = sorted(
                CLAUDE_PROJECTS_ROOT.glob("*/*.jsonl"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if all_jsonls:
                return all_jsonls[0]
        return None

    @staticmethod
    def _extract_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    def read_transcript(self, handle: object, max_chars: int = 50000) -> str:
        if not isinstance(handle, Path):
            return ""
        try:
            lines = handle.read_text(encoding="utf-8", errors="ignore").splitlines()
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
            t = event.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = event.get("message", {}) or {}
            text = self._extract_text(msg.get("content")).strip()
            if not text:
                continue
            if text.startswith("<system-reminder>") and text.endswith("</system-reminder>"):
                continue
            label = "Stéphane" if t == "user" else "Claude"
            turn = f"{label}: {text}"
            if used + len(turn) > max_chars:
                break
            turns.append(turn)
            used += len(turn) + 2
        turns.reverse()
        return "\n\n".join(turns)

    def last_activity_ts(self, handle: object) -> float:
        if isinstance(handle, Path) and handle.exists():
            return handle.stat().st_mtime
        return 0.0


class OpenCodeSource(ConversationSource):
    name = "opencode"

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if not OPENCODE_DB_PATH.exists():
            return []
        try:
            conn = sqlite3.connect(str(OPENCODE_DB_PATH), timeout=2.0)
            try:
                return conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            return []

    def find_active_session(self, cwd: Path | None = None) -> str | None:
        # OPENCODE_RUN_ID exists but maps to runs not sessions, so pick the
        # most-recently-updated session whose `directory` matches the cwd
        # (or any of its parents). Fall back to globally-newest.
        cwd = cwd or Path(os.getcwd())
        for candidate in [cwd, *cwd.parents]:
            rows = self._query(
                "SELECT id FROM session WHERE directory = ? ORDER BY time_updated DESC LIMIT 1",
                (str(candidate),),
            )
            if rows:
                return rows[0][0]
        rows = self._query("SELECT id FROM session ORDER BY time_updated DESC LIMIT 1")
        return rows[0][0] if rows else None

    def read_transcript(self, handle: object, max_chars: int = 50000) -> str:
        if not isinstance(handle, str):
            return ""
        rows = self._query(
            """
            SELECT m.data, p.data
            FROM message m
            JOIN part p ON p.message_id = m.id
            WHERE m.session_id = ?
            ORDER BY m.time_created ASC, p.time_created ASC
            """,
            (handle,),
        )
        if not rows:
            return ""
        collected: list[str] = []
        used = 0
        for msg_data, part_data in reversed(rows):
            try:
                pdata = json.loads(part_data)
            except json.JSONDecodeError:
                continue
            if pdata.get("type") != "text":
                continue
            text = pdata.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                mdata = json.loads(msg_data)
            except json.JSONDecodeError:
                continue
            role = mdata.get("role")
            label = "Stéphane" if role == "user" else "OpenCode"
            turn = f"{label}: {text.strip()}"
            if used + len(turn) > max_chars:
                break
            collected.append(turn)
            used += len(turn) + 2
        collected.reverse()
        return "\n\n".join(collected)

    def last_activity_ts(self, handle: object) -> float:
        if not isinstance(handle, str):
            return 0.0
        rows = self._query(
            "SELECT time_updated FROM session WHERE id = ? LIMIT 1",
            (handle,),
        )
        if not rows:
            return 0.0
        # OpenCode stores millisecond timestamps.
        try:
            return float(rows[0][0]) / 1000.0
        except (TypeError, ValueError):
            return 0.0


# ─── Auto-detection + public API ──────────────────────────────────────


def detect_source(cwd: Path | None = None) -> tuple[ConversationSource, object] | None:
    """Return the (source, handle) pair for the most recently active CLI.

    Honors env vars first (CLAUDE_CODE_SESSION_ID, OPENCODE_RUN_ID), otherwise
    queries both backends and picks whichever has the freshest activity for
    this cwd.
    """
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        src = ClaudeCodeSource()
        handle = src.find_active_session(cwd)
        if handle is not None:
            return src, handle
    if os.environ.get("OPENCODE_RUN_ID"):
        src = OpenCodeSource()
        handle = src.find_active_session(cwd)
        if handle is not None:
            return src, handle

    candidates: list[tuple[ConversationSource, object, float]] = []
    for src in (ClaudeCodeSource(), OpenCodeSource()):
        handle = src.find_active_session(cwd)
        if handle is None:
            continue
        candidates.append((src, handle, src.last_activity_ts(handle)))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[2], reverse=True)
    src, handle, _ = candidates[0]
    return src, handle


def _quiet_subprocess_env() -> dict[str, str]:
    """Mirror of rolling_recap._quiet_subprocess_env — silences macOS
    MallocStackLogging warnings leaking from claude -p grand-children.
    """
    env = dict(os.environ)
    env["MallocStackLogging"] = "0"
    env["MallocStackLoggingNoCompact"] = "0"
    return env


def compact_with_claude_p(text: str, timeout_seconds: int = 60) -> str | None:
    """Use `claude -p` Sonnet to compact a long transcript. Returns None on failure."""
    if not text.strip():
        return None
    prompt = COMPACT_PROMPT + text + "\n---\n"
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet", prompt],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
            env=_quiet_subprocess_env(),
            start_new_session=True,
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
    """Return `git log -<count> --oneline` + status for the detected repo.

    Surfaces what actions the CLI session took that don't appear in the
    user/assistant text turns (tool_use blocks are stripped).
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


def build_cli_context(
    cwd: Path | None = None,
    compact_threshold: int = COMPACT_THRESHOLD_CHARS,
    compact_target: int = COMPACT_TARGET_CHARS,
) -> str | None:
    """Build the active-CLI conversation block to inject into voice context.

    Auto-detects Claude Code vs OpenCode and reads the right transcript.
    Compacts via `claude -p` Sonnet over budget. Appends `git log` summary
    so the model sees the trajectory of code actions, not just text turns.
    """
    detection = detect_source(cwd)
    if detection is None:
        return None
    source, handle = detection
    raw = source.read_transcript(handle, max_chars=50000)
    if not raw:
        return None
    if len(raw) > compact_threshold:
        compacted = compact_with_claude_p(raw)
        body = compacted or raw[:compact_target]
    else:
        body = raw

    git_block = get_recent_git_log()
    title = f"## Conversation CLI en cours ({source.name})"
    sections = [title, body]
    if git_block:
        sections += ["", "### État git du repo de travail", git_block]
    return "\n".join(sections)


# Back-compat shim so anything importing the old name still works.
build_claude_code_context = build_cli_context
