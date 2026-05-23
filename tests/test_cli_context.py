"""Unit tests for cli_context — Claude Code + OpenCode source abstraction.

We don't touch a real opencode.db here; we use a temporary path injected
via monkeypatch so tests are hermetic.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from voice_realtime import cli_context
from voice_realtime.cli_context import (
    ClaudeCodeSource,
    OpenCodeSource,
    detect_source,
    find_git_repo,
    get_recent_git_log,
)


def test_killchat_noise_strip_unaffected() -> None:
    # sanity — module imports + works in isolation
    src = ClaudeCodeSource()
    assert src.name == "claude-code"


def test_claude_code_extract_text_handles_str_content() -> None:
    src = ClaudeCodeSource()
    assert src._extract_text("plain string") == "plain string"


def test_claude_code_extract_text_handles_list_content() -> None:
    src = ClaudeCodeSource()
    content = [
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "name": "Bash"},
        {"type": "text", "text": "world"},
    ]
    out = src._extract_text(content)
    assert "hello" in out
    assert "world" in out
    assert "Bash" not in out


def test_claude_code_extract_text_handles_garbage() -> None:
    src = ClaudeCodeSource()
    assert src._extract_text(None) == ""
    assert src._extract_text(42) == ""
    assert src._extract_text([{"type": "image"}]) == ""


def test_claude_code_read_transcript_drops_tool_blocks(tmp_path: Path) -> None:
    src = ClaudeCodeSource()
    jsonl = tmp_path / "fake.jsonl"
    events = [
        {"type": "user", "message": {"content": "user msg"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "assistant reply"}]}},
        {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "..."}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "..."}]}},
    ]
    jsonl.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    out = src.read_transcript(jsonl)
    assert "user msg" in out
    assert "assistant reply" in out
    # thinking + tool_result blocks contribute no text
    assert "..." not in out


def test_claude_code_read_transcript_skips_system_reminders(tmp_path: Path) -> None:
    src = ClaudeCodeSource()
    jsonl = tmp_path / "fake.jsonl"
    events = [
        {"type": "user", "message": {"content": "<system-reminder>noise</system-reminder>"}},
        {"type": "user", "message": {"content": "real user text"}},
    ]
    jsonl.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    out = src.read_transcript(jsonl)
    assert "real user text" in out
    assert "noise" not in out


def test_claude_code_read_transcript_missing_file_returns_empty(tmp_path: Path) -> None:
    src = ClaudeCodeSource()
    assert src.read_transcript(tmp_path / "nope.jsonl") == ""
    assert src.read_transcript("not a path") == ""


def test_find_git_repo_returns_voice_realtime_when_in_repo() -> None:
    # Tests live inside the voice-realtime repo — find_git_repo should locate it.
    repo = find_git_repo(Path(__file__).resolve().parent)
    assert repo is not None
    assert (repo / ".git").exists()


def test_get_recent_git_log_returns_lines() -> None:
    out = get_recent_git_log(count=3)
    assert out is not None
    assert "Repo : voice-realtime" in out
    assert "Derniers commits :" in out


def _make_opencode_db(tmp_path: Path, cwd: str = "/somewhere") -> Path:
    """Create a minimal opencode.db with the schema cli_context queries."""
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                time_updated INTEGER NOT NULL
            );
            CREATE TABLE message (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE part (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            """
        )
        now_ms = int(time.time() * 1000)
        conn.execute("INSERT INTO session VALUES (?, ?, ?)", ("ses_test1", cwd, now_ms))
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            ("msg_a", "ses_test1", now_ms, json.dumps({"role": "user"})),
        )
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            ("msg_b", "ses_test1", now_ms + 1, json.dumps({"role": "assistant"})),
        )
        conn.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            ("part_a", "msg_a", "ses_test1", now_ms,
             json.dumps({"type": "text", "text": "Question from user"})),
        )
        conn.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            ("part_b", "msg_b", "ses_test1", now_ms + 1,
             json.dumps({"type": "text", "text": "Answer from opencode"})),
        )
        conn.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            ("part_c", "msg_b", "ses_test1", now_ms + 2,
             json.dumps({"type": "reasoning", "text": "internal thinking should be skipped"})),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_opencode_source_finds_session_by_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _make_opencode_db(tmp_path, cwd=str(tmp_path / "fakeproject"))
    monkeypatch.setattr(cli_context, "OPENCODE_DB_PATH", db)
    src = OpenCodeSource()
    handle = src.find_active_session(tmp_path / "fakeproject")
    assert handle == "ses_test1"


def test_opencode_source_falls_back_to_newest_when_cwd_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_opencode_db(tmp_path, cwd="/totally/different/path")
    monkeypatch.setattr(cli_context, "OPENCODE_DB_PATH", db)
    src = OpenCodeSource()
    handle = src.find_active_session(tmp_path / "elsewhere")
    # No cwd match, but a session exists → fallback returns latest.
    assert handle == "ses_test1"


def test_opencode_source_returns_none_when_db_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_context, "OPENCODE_DB_PATH", tmp_path / "nonexistent.db")
    src = OpenCodeSource()
    assert src.find_active_session() is None


def test_opencode_source_read_transcript_skips_non_text_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_opencode_db(tmp_path, cwd=str(tmp_path / "proj"))
    monkeypatch.setattr(cli_context, "OPENCODE_DB_PATH", db)
    src = OpenCodeSource()
    out = src.read_transcript("ses_test1")
    assert "Question from user" in out
    assert "Answer from opencode" in out
    # reasoning part must NOT leak
    assert "internal thinking" not in out


def test_opencode_source_read_transcript_uses_correct_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_opencode_db(tmp_path, cwd=str(tmp_path / "proj"))
    monkeypatch.setattr(cli_context, "OPENCODE_DB_PATH", db)
    src = OpenCodeSource()
    out = src.read_transcript("ses_test1")
    assert "Stéphane: Question from user" in out
    assert "OpenCode: Answer from opencode" in out
