"""vault.write tool — write/append a markdown file inside the vault.

Scope: paths MUST resolve under `~/OBSIDIAN/2ND_CERVEAU/`. Symlink/`..`
traversal is rejected by comparing the resolved path against the resolved
vault root.

Modes:
- "append" (default): create file if absent, append content with a leading
  newline if the file already has trailing content.
- "create": refuse if file exists. Use when the model wants to author a
  new note and would otherwise clobber an existing one.

Returns the absolute path written + the number of bytes appended so the
model can verbalize what happened ("3.2k written to <path>").
"""

from __future__ import annotations

from pathlib import Path

from .registry import ToolResult, ToolSafetyLevel, ToolSpec


VAULT_ROOT = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"


def vault_write(path: str, content: str, mode: str = "append") -> ToolResult:
    """Write `content` to `path` (vault-scoped). Returns ToolResult with
    {path, bytes_written, mode} on success.
    """
    if not path or not path.strip():
        return ToolResult(ok=False, error="empty path")
    if content is None:
        return ToolResult(ok=False, error="content is null")
    if mode not in ("append", "create"):
        return ToolResult(ok=False, error=f"mode must be 'append' or 'create', got {mode!r}")

    try:
        vault = VAULT_ROOT.resolve()
    except OSError as exc:
        return ToolResult(ok=False, error=f"vault resolve: {exc}")

    target = Path(path).expanduser()
    if not target.is_absolute():
        # Treat relative paths as vault-relative — gentler API than forcing
        # the model to always say "OBSIDIAN/2ND_CERVEAU/...".
        target = VAULT_ROOT / target

    try:
        target_resolved = target.resolve()
    except OSError as exc:
        return ToolResult(ok=False, error=f"path resolve: {exc}")

    try:
        target_resolved.relative_to(vault)
    except ValueError:
        return ToolResult(ok=False, error="path must live under the vault")

    if mode == "create" and target_resolved.exists():
        return ToolResult(ok=False, error="file already exists (mode=create)")

    try:
        target_resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ToolResult(ok=False, error=f"mkdir parent: {exc}")

    payload = content
    if mode == "append" and target_resolved.exists():
        # Add a newline separator if the existing file doesn't end with one,
        # so consecutive appends don't fuse into one line.
        try:
            existing = target_resolved.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return ToolResult(ok=False, error=f"read existing: {exc}")
        if existing and not existing.endswith("\n"):
            payload = "\n" + payload

    try:
        with target_resolved.open("a" if mode == "append" else "w", encoding="utf-8") as fh:
            written = fh.write(payload)
    except OSError as exc:
        return ToolResult(ok=False, error=f"write: {exc}")

    return ToolResult(ok=True, data={
        "path": str(target_resolved),
        "bytes_written": written,
        "mode": mode,
    })


VAULT_WRITE_SPEC = ToolSpec(
    name="vault_write",
    description=(
        "Écrit ou ajoute du markdown dans un fichier du vault Obsidian. "
        "Chemins relatifs résolus depuis OBSIDIAN/2ND_CERVEAU. "
        "mode='append' (défaut) ajoute, mode='create' refuse si le fichier existe."
    ),
    safety=ToolSafetyLevel.WRITE_USER_SCOPE,
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin relatif ou absolu sous le vault"},
            "content": {"type": "string", "description": "Contenu markdown à écrire"},
            "mode": {
                "type": "string",
                "enum": ["append", "create"],
                "default": "append",
                "description": "append = ajoute en fin de fichier, create = refuse si existe",
            },
        },
        "required": ["path", "content"],
    },
    handler=vault_write,
)
