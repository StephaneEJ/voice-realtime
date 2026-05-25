"""Tool registry — minimal, safety-classified, provider-agnostic.

Why classifications matter: voice STT mis-hears, the model sometimes
hallucinates tool calls, and `--cli-context` injects an LLM-generated
recap into the conversation. A typo-able trigger that hits a tool with
side effects (write a note, send a message) MUST require a confirmation
turn. Read-only tools fire instantly.

Safety levels (least → most permissive):
- DANGEROUS — never fires automatically. Provider-side: don't register
  these unless absolutely necessary.
- WRITE_USER_SCOPE — writes inside the vault, owner-scoped. Fires
  immediately during a session but a higher-level dispatcher MAY ask
  for vocal confirmation.
- READ_ONLY — fires immediately, no confirmation needed. The current
  default for everything shipped today.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable


class ToolSafetyLevel(enum.IntEnum):
    READ_ONLY = 0
    WRITE_USER_SCOPE = 1
    DANGEROUS = 2


@dataclass
class ToolResult:
    """Returned by every tool dispatcher. `data` is JSON-serializable."""

    ok: bool
    data: Any = None
    error: str | None = None

    def as_function_response(self, name: str) -> dict[str, Any]:
        """Provider-agnostic shape that adapts to both Gemini + OpenAI
        function-response payloads.
        """
        if self.ok:
            return {"name": name, "response": {"result": self.data}}
        return {"name": name, "response": {"error": self.error or "unknown"}}


@dataclass
class ToolSpec:
    name: str
    description: str
    safety: ToolSafetyLevel
    parameters_schema: dict[str, Any]
    handler: Callable[..., ToolResult]


@dataclass
class ToolRegistry:
    """Holds registered ToolSpec entries + dispatcher."""

    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def dispatch(self, name: str, **kwargs: Any) -> ToolResult:
        spec = self.get(name)
        if spec is None:
            return ToolResult(ok=False, error=f"unknown tool: {name}")
        try:
            return spec.handler(**kwargs)
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    def as_specs(self) -> list[dict[str, Any]]:
        """Provider-shape: shared between Gemini Live `tools` and OpenAI
        Realtime `tools`. Both accept the function-declaration shape.
        """
        return [
            {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters_schema,
            }
            for s in self._tools.values()
        ]

    def provider_specs(self) -> list[Any]:
        """Return registered tools as `base.ToolSpec` instances, ready to hand
        to `provider.connect(tools=...)`. Kept separate from `as_specs()` so
        the dict shape remains stable for any caller that consumed it before.
        """
        from ..providers.base import ToolSpec as ProviderToolSpec
        return [
            ProviderToolSpec(
                name=s.name,
                description=s.description,
                parameters=s.parameters_schema,
            )
            for s in self._tools.values()
        ]

    def subset(self, names: list[str]) -> "ToolRegistry":
        """Return a new registry containing only tools whose name is in
        `names`. Unknown names are silently skipped so a persona referencing
        a future tool doesn't crash the session.
        """
        sub = ToolRegistry()
        wanted = set(names)
        for s in self._tools.values():
            if s.name in wanted:
                sub._tools[s.name] = s
        return sub

    def requires_confirmation(self, name: str) -> bool:
        """True if the named tool's safety level is WRITE_USER_SCOPE or
        DANGEROUS. Used by the CLI when a persona has `ask_before_acting=True`
        to gate dispatch through a UI confirmation.
        """
        spec = self.get(name)
        if spec is None:
            return False
        return spec.safety >= ToolSafetyLevel.WRITE_USER_SCOPE


# ─── Built-in safe read-only tools ────────────────────────────────────


def _tool_search_vault(query: str, limit: int = 3) -> ToolResult:
    """Grep vault for query, return top `limit` matches with path + snippet."""
    import re
    import subprocess
    from pathlib import Path

    if not query.strip():
        return ToolResult(ok=False, error="empty query")
    vault = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
    if not vault.exists():
        return ToolResult(ok=False, error="vault not found")
    try:
        # ripgrep if available, fallback to grep
        rg = subprocess.run(
            ["rg", "-l", "--", query, str(vault)],
            capture_output=True, text=True, timeout=5, check=False,
        )
        paths = [p for p in (rg.stdout or "").splitlines() if p][:limit]
    except FileNotFoundError:
        return ToolResult(ok=False, error="ripgrep not installed")
    matches: list[dict[str, Any]] = []
    for p in paths:
        try:
            content = Path(p).read_text(encoding="utf-8", errors="ignore")
            # First snippet line containing the query, ±60 chars
            line = next((ln for ln in content.splitlines() if query.lower() in ln.lower()), "")
            matches.append({"path": p, "snippet": line.strip()[:200]})
        except OSError:
            continue
    return ToolResult(ok=True, data={"matches": matches, "query": query})


def _tool_read_file(path: str, max_chars: int = 4000) -> ToolResult:
    """Return the first `max_chars` of a file. Vault-scoped."""
    from pathlib import Path

    vault = (Path.home() / "OBSIDIAN" / "2ND_CERVEAU").resolve()
    try:
        target = Path(path).expanduser().resolve()
    except OSError as exc:
        return ToolResult(ok=False, error=f"resolve: {exc}")
    try:
        target.relative_to(vault)
    except ValueError:
        return ToolResult(ok=False, error="path must live under the vault")
    if not target.exists():
        return ToolResult(ok=False, error="file not found")
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError as exc:
        return ToolResult(ok=False, error=f"read: {exc}")
    return ToolResult(ok=True, data={"path": str(target), "content": content})


def _tool_note_action(text: str) -> ToolResult:
    """Append a bullet to today's daily note. WRITE_USER_SCOPE."""
    from datetime import date
    from pathlib import Path

    if not text.strip():
        return ToolResult(ok=False, error="empty text")
    vault = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
    life_phases = vault / "2 CASQUETTES" / "Life Phases"
    if not life_phases.exists():
        return ToolResult(ok=False, error="life phases dir not found")
    # Find active phase by `status: active` in *Intention*.md
    import re
    active_phase = None
    for phase_dir in life_phases.iterdir():
        if not phase_dir.is_dir():
            continue
        for intent in phase_dir.glob("*Intention*.md"):
            try:
                txt = intent.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"^status:\s*active", txt, re.MULTILINE):
                active_phase = phase_dir
                break
        if active_phase:
            break
    if active_phase is None:
        return ToolResult(ok=False, error="no active phase found")
    today = date.today().isoformat()
    daily_note = active_phase / f"{today}.md"
    if not daily_note.exists():
        return ToolResult(ok=False, error=f"daily note for {today} not found ; create it first")
    try:
        with daily_note.open("a", encoding="utf-8") as fh:
            fh.write(f"\n- {text} (via voice tool)\n")
    except OSError as exc:
        return ToolResult(ok=False, error=f"write: {exc}")
    return ToolResult(ok=True, data={"appended_to": str(daily_note), "text": text})


def default_registry() -> ToolRegistry:
    """Return a registry pre-loaded with the built-in tools.

    Sprint 1: search_vault (RO), read_file (RO), note_action (WRITE).
    Sprint 2: vault_write (WRITE), web_search (RO).
    """
    # Imported lazily inside the function so the registry module stays
    # importable even if optional deps for one tool are missing.
    from .vault_write import VAULT_WRITE_SPEC
    from .web_search import WEB_SEARCH_SPEC

    r = ToolRegistry()
    r.register(ToolSpec(
        name="search_vault",
        description="Recherche full-text dans le vault Obsidian, retourne les 3 meilleurs chemins + snippet.",
        safety=ToolSafetyLevel.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Terme ou phrase à chercher"},
                "limit": {"type": "integer", "description": "Nombre max de résultats", "default": 3},
            },
            "required": ["query"],
        },
        handler=_tool_search_vault,
    ))
    r.register(ToolSpec(
        name="read_file",
        description="Lit un fichier markdown du vault et retourne ses 4000 premiers caractères.",
        safety=ToolSafetyLevel.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin absolu sous OBSIDIAN/2ND_CERVEAU"},
                "max_chars": {"type": "integer", "default": 4000},
            },
            "required": ["path"],
        },
        handler=_tool_read_file,
    ))
    r.register(ToolSpec(
        name="note_action",
        description="Ajoute une ligne `- <texte>` à la daily note de la phase active du jour.",
        safety=ToolSafetyLevel.WRITE_USER_SCOPE,
        parameters_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texte à noter"},
            },
            "required": ["text"],
        },
        handler=_tool_note_action,
    ))
    r.register(VAULT_WRITE_SPEC)
    r.register(WEB_SEARCH_SPEC)
    return r
