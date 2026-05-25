"""vault.write tool — scope enforcement + append/create semantics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from voice_realtime.tools.vault_write import VAULT_ROOT, vault_write


@pytest.fixture
def fake_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect VAULT_ROOT to a tmp dir so we never touch the real vault."""
    monkeypatch.setattr("voice_realtime.tools.vault_write.VAULT_ROOT", tmp_path)
    return tmp_path


def test_append_creates_then_appends(fake_vault: Path) -> None:
    target = fake_vault / "notes.md"
    r1 = vault_write(str(target), "first line")
    assert r1.ok, r1.error
    assert target.read_text() == "first line"

    r2 = vault_write(str(target), "second line")
    assert r2.ok, r2.error
    # Newline separator added between appends
    assert target.read_text() == "first line\nsecond line"
    assert r2.data["mode"] == "append"
    assert r2.data["path"] == str(target.resolve())


def test_relative_path_resolves_under_vault(fake_vault: Path) -> None:
    r = vault_write("0 INBOX/scratch.md", "hello")
    assert r.ok, r.error
    written = Path(r.data["path"])
    assert written.is_relative_to(fake_vault)
    assert written.name == "scratch.md"


def test_traversal_rejected(fake_vault: Path, tmp_path: Path) -> None:
    """A path that resolves outside the vault must be refused."""
    outside = tmp_path.parent / "outside.md"
    r = vault_write(str(outside), "leak")
    assert not r.ok
    assert "vault" in (r.error or "").lower()
    assert not outside.exists()


def test_dotdot_traversal_rejected(fake_vault: Path) -> None:
    """`..` is reduced by .resolve() — if it escapes the vault, refuse."""
    r = vault_write("../escape.md", "bad")
    assert not r.ok
    assert "vault" in (r.error or "").lower()


def test_create_mode_refuses_existing(fake_vault: Path) -> None:
    target = fake_vault / "exists.md"
    target.write_text("already here")
    r = vault_write(str(target), "new", mode="create")
    assert not r.ok
    assert "exists" in (r.error or "").lower()
    assert target.read_text() == "already here"  # unchanged


def test_create_mode_writes_when_absent(fake_vault: Path) -> None:
    target = fake_vault / "subdir" / "fresh.md"
    r = vault_write(str(target), "brand new", mode="create")
    assert r.ok, r.error
    assert target.read_text() == "brand new"


def test_empty_path_rejected() -> None:
    r = vault_write("", "x")
    assert not r.ok


def test_invalid_mode_rejected(fake_vault: Path) -> None:
    target = fake_vault / "x.md"
    r = vault_write(str(target), "x", mode="overwrite")
    assert not r.ok
    assert "mode" in (r.error or "").lower()


def test_append_to_file_ending_with_newline_no_double_newline(fake_vault: Path) -> None:
    target = fake_vault / "n.md"
    target.write_text("line1\n")
    r = vault_write(str(target), "line2")
    assert r.ok, r.error
    # No extra separator since existing already ended in newline
    assert target.read_text() == "line1\nline2"
