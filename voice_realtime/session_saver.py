"""Save voice session transcript to Obsidian vault as markdown note."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

VAULT_VOICE_SESSIONS = Path.home() / "OBSIDIAN" / "2ND_CERVEAU" / "_System" / "voice-sessions"


def save_session_note(
    transcript_user: list[str],
    transcript_model: list[str],
    provider: str,
    model: str,
    elapsed_seconds: float,
    estimated_cost_usd: float,
    project_hint: str | None = None,
    end_reason: str = "ended",
) -> Path:
    """Write a markdown session note into the vault. Returns path."""
    VAULT_VOICE_SESSIONS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone()
    fname = ts.strftime("%Y-%m-%d %H-%M") + f" — {provider}.md"
    path = VAULT_VOICE_SESSIONS / fname

    lines: list[str] = [
        "---",
        f"date: {ts.strftime('%Y-%m-%d')}",
        f"time: {ts.strftime('%H:%M')}",
        f"provider: {provider}",
        f"model: {model}",
        f"duration_seconds: {elapsed_seconds:.0f}",
        f"estimated_cost_usd: {estimated_cost_usd:.4f}",
        f"end_reason: {end_reason}",
        "tags: [voice-session, voice-realtime]",
        "---",
        "",
        f"# Voice Session — {ts.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    if project_hint:
        lines.append(f"**Projet :** [[{project_hint}]]")
        lines.append("")
    lines.append("## Stats")
    lines.append(f"- Provider : `{provider}` / `{model}`")
    lines.append(f"- Durée : {elapsed_seconds:.0f}s ({elapsed_seconds / 60:.1f} min)")
    lines.append(f"- Coût estimé : ${estimated_cost_usd:.4f}")
    lines.append(f"- Fin : {end_reason}")
    lines.append("")
    lines.append("## Transcript")
    lines.append("")

    # Interleave best-effort: user blocks, then model blocks (we don't have timestamps M2)
    if transcript_user:
        lines.append("### Toi")
        for chunk in transcript_user:
            lines.append(f"> {chunk}")
        lines.append("")
    if transcript_model:
        lines.append("### Modèle")
        for chunk in transcript_model:
            lines.append(f"> {chunk}")
        lines.append("")

    lines.append("## Notes post-session")
    lines.append("")
    lines.append("_(à compléter manuellement ou via skill /summarize-voice à venir)_")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
