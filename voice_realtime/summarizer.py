"""Post-session summarizer — turns a raw voice transcript into a structured
synthesis (decisions / actions / insights / open questions) and appends it
to the project note. Uses `claude -p` Sonnet, respecting the vault rule
that Jarvis pipelines must never use the Anthropic SDK directly
(see memory feedback_always_claude_cli_not_sdk).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .context_loader import find_project_note

logger = logging.getLogger("voice_realtime.summarizer")

CLAUDE_BIN = "claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
FALLBACK_MODEL = "claude-haiku-4-5"


@dataclass
class SummaryResult:
    topic_summary: str
    decisions: list[str]
    actions: list[dict]
    insights: list[str]
    unresolved_questions: list[str]
    transcript_path: Path
    project_note_path: Path | None
    appended: bool


def _extract_transcript_sections(text: str) -> tuple[str, str, dict]:
    """Return (user_blob, model_blob, frontmatter_dict) from a session note."""
    fm: dict = {}
    body = text
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        body = text[fm_match.end():]

    def _grab(section_header: str) -> str:
        pat = rf"^### {re.escape(section_header)}\s*\n(.*?)(?=^### |\Z)"
        m = re.search(pat, body, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    user = _grab("Toi")
    model = _grab("Modèle")
    # The transcripts are stored as `> chunk` lines — strip the blockquote
    # markers and join the fragmented chunks into readable prose.
    def _clean(blob: str) -> str:
        lines = [re.sub(r"^>\s*", "", ln) for ln in blob.splitlines()]
        joined = " ".join(ln.strip() for ln in lines if ln.strip())
        return re.sub(r"\s+", " ", joined).strip()

    return _clean(user), _clean(model), fm


def _build_prompt(user_blob: str, model_blob: str, project_hint: str | None) -> str:
    return (
        f"Tu reçois le transcript brut d'une session vocale entre Stéphane et un "
        f"modèle IA voice realtime, dans le contexte du projet : {project_hint or 'non précisé'}.\n\n"
        f"Le transcript est très fragmenté en partial chunks STT — tu dois reconstruire "
        f"mentalement les phrases complètes avant d'analyser.\n\n"
        f"=== USER (Stéphane) ===\n{user_blob}\n\n"
        f"=== MODÈLE ===\n{model_blob}\n\n"
        f"Tâche : extraire un JSON strict (rien d'autre, pas de markdown, pas de prose hors JSON).\n\n"
        "Schéma exact :\n"
        "{\n"
        '  "topic_summary": "1-2 phrases sur le sujet principal de la session",\n'
        '  "decisions": ["décision concrète prise, formulée comme une affirmation"],\n'
        '  "actions": [{"what": "action concrète", "when": "today|this-week|later|unspecified", "owner": "stephane|autre"}],\n'
        '  "insights": ["idée non triviale qui mérite d\'être conservée hors du transcript"],\n'
        '  "unresolved_questions": ["question Stéphane à laquelle le modèle n\'a pas répondu correctement ou a esquivé"]\n'
        "}\n\n"
        "Règles :\n"
        "- Décisions = engagements pris, pas hypothèses.\n"
        "- Actions = vérifiables (avec verbe d'action), pas vagues.\n"
        "- Insights = ce qui n'est pas déjà documenté dans le projet.\n"
        "- Unresolved = questions auxquelles le modèle voice a esquivé.\n"
        "- Si une catégorie est vide, retourner [].\n"
        "- Pas de markdown dans les valeurs JSON. Pas de prose hors du JSON.\n"
    )


def _call_claude(prompt: str, model: str) -> str:
    """Invoke `claude -p` CLI and capture stdout. Returns raw text."""
    import os as _os
    quiet_env = dict(_os.environ)
    quiet_env["MallocStackLogging"] = "0"
    quiet_env["MallocStackLoggingNoCompact"] = "0"
    result = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", model, prompt],
        capture_output=True,
        text=True,
        timeout=120,
        env=quiet_env,
        start_new_session=True,
    )
    if result.returncode != 0:
        # `claude` may write errors to stdout under --output-format json — check both.
        err = (result.stderr or "") + "\n" + (result.stdout or "")
        raise RuntimeError(f"claude -p failed (rc={result.returncode}): {err.strip()[:500]}")
    return result.stdout.strip()


def _extract_json_block(raw: str) -> dict:
    """Robustly extract the first JSON object from the LLM output."""
    # Strip optional ```json ... ``` fencing.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    # Find first balanced { ... } block.
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object in LLM output")
    depth = 0
    for i, ch in enumerate(raw[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    raise ValueError("unbalanced JSON braces in LLM output")


def _render_synthesis_section(
    summary: SummaryResult, when: str, provider: str, transcript_filename: str
) -> str:
    lines = [
        f"## Voice session {when} — synthèse ({provider})",
        "",
        f"**Sujet :** {summary.topic_summary or 'non précisé'}",
        "",
        "### Décisions",
    ]
    if summary.decisions:
        lines.extend(f"- {d}" for d in summary.decisions)
    else:
        lines.append("- _(aucune)_")
    lines.extend(["", "### Actions"])
    if summary.actions:
        for a in summary.actions:
            what = a.get("what", "").strip()
            when_v = a.get("when", "unspecified")
            owner = a.get("owner", "stephane")
            lines.append(f"- [ ] {what} — {owner} — {when_v}")
    else:
        lines.append("- _(aucune)_")
    lines.extend(["", "### Insights"])
    if summary.insights:
        lines.extend(f"- {i}" for i in summary.insights)
    else:
        lines.append("- _(aucun)_")
    lines.extend(["", "### Questions ouvertes"])
    if summary.unresolved_questions:
        lines.extend(f"- {q}" for q in summary.unresolved_questions)
    else:
        lines.append("- _(aucune)_")
    lines.extend([
        "",
        f"**Transcript brut :** [[{transcript_filename}]]",
        "",
    ])
    return "\n".join(lines)


def _append_to_project(project_path: Path, section: str) -> None:
    current = project_path.read_text(encoding="utf-8")
    # Append before any final '---' separator or at end-of-file.
    if current.rstrip().endswith("---"):
        new_content = current.rstrip()[:-3].rstrip() + "\n\n" + section + "\n---\n"
    else:
        new_content = current.rstrip() + "\n\n" + section
    project_path.write_text(new_content, encoding="utf-8")


def _replace_placeholder_in_transcript(transcript_path: Path, summary: "SummaryResult") -> bool:
    """Replace the "à compléter manuellement" placeholder in the voice-session
    note with the actual synthesis (decisions / actions / insights / questions).

    Returns True if the file was modified. Idempotent — if the synthesis is
    already in place, leaves the file alone.
    """
    if not transcript_path.exists():
        return False
    current = transcript_path.read_text(encoding="utf-8")
    placeholder = "_(à compléter manuellement ou via skill /summarize-voice à venir)_"
    inline_block_lines = [
        "## Notes post-session — Synthèse auto",
        "",
        f"**Sujet :** {summary.topic_summary or 'non précisé'}",
        "",
        "### Décisions",
    ]
    if summary.decisions:
        inline_block_lines.extend(f"- {d}" for d in summary.decisions)
    else:
        inline_block_lines.append("- _(aucune)_")
    inline_block_lines.extend(["", "### Actions"])
    if summary.actions:
        for a in summary.actions:
            what = a.get("what", "").strip()
            when_v = a.get("when", "unspecified")
            owner = a.get("owner", "stephane")
            inline_block_lines.append(f"- [ ] {what} — {owner} — {when_v}")
    else:
        inline_block_lines.append("- _(aucune)_")
    inline_block_lines.extend(["", "### Insights"])
    if summary.insights:
        inline_block_lines.extend(f"- {i}" for i in summary.insights)
    else:
        inline_block_lines.append("- _(aucun)_")
    inline_block_lines.extend(["", "### Questions ouvertes"])
    if summary.unresolved_questions:
        inline_block_lines.extend(f"- {q}" for q in summary.unresolved_questions)
    else:
        inline_block_lines.append("- _(aucune)_")
    inline_block = "\n".join(inline_block_lines)

    if "## Notes post-session — Synthèse auto" in current:
        return False  # already done — idempotent

    if "## Notes post-session" in current and placeholder in current:
        new = current.replace(
            "## Notes post-session\n\n" + placeholder,
            inline_block,
        )
        if new == current:
            # Fall through to appending
            new = current.rstrip() + "\n\n" + inline_block + "\n"
    else:
        new = current.rstrip() + "\n\n" + inline_block + "\n"
    transcript_path.write_text(new, encoding="utf-8")
    return True


def summarize_session(
    transcript_path: Path,
    project_hint: str | None = None,
    model: str = DEFAULT_MODEL,
) -> SummaryResult:
    if not transcript_path.exists():
        raise FileNotFoundError(transcript_path)

    raw = transcript_path.read_text(encoding="utf-8")
    user_blob, model_blob, fm = _extract_transcript_sections(raw)
    if not (user_blob or model_blob):
        raise ValueError("empty transcript — nothing to summarize")

    prompt = _build_prompt(user_blob, model_blob, project_hint)
    logger.info("Calling claude -p model=%s on %s", model, transcript_path.name)

    try:
        raw_out = _call_claude(prompt, model)
    except (subprocess.TimeoutExpired, RuntimeError) as exc:
        logger.warning("Primary model %s failed (%r) — trying fallback %s", model, exc, FALLBACK_MODEL)
        raw_out = _call_claude(prompt, FALLBACK_MODEL)

    parsed = _extract_json_block(raw_out)

    result = SummaryResult(
        topic_summary=parsed.get("topic_summary", "").strip(),
        decisions=[s.strip() for s in parsed.get("decisions", []) if s.strip()],
        actions=parsed.get("actions", []),
        insights=[s.strip() for s in parsed.get("insights", []) if s.strip()],
        unresolved_questions=[s.strip() for s in parsed.get("unresolved_questions", []) if s.strip()],
        transcript_path=transcript_path,
        project_note_path=None,
        appended=False,
    )

    if project_hint:
        project_note = find_project_note(project_hint)
        if project_note:
            section = _render_synthesis_section(
                result,
                when=f"{fm.get('date', '')} {fm.get('time', '')}".strip(),
                provider=fm.get("provider", "voice"),
                transcript_filename=transcript_path.stem,
            )
            _append_to_project(project_note, section)
            result.project_note_path = project_note
            result.appended = True
            logger.info("Appended synthesis to %s", project_note)

    # Also rewrite the voice-session note: replace the "à compléter
    # manuellement" placeholder with the actual synthesis so the file is
    # self-contained when read directly (no need to bounce to the project
    # note to know what was discussed).
    try:
        modified = _replace_placeholder_in_transcript(transcript_path, result)
        if modified:
            logger.info("Inlined synthesis into transcript note %s", transcript_path.name)
    except Exception as exc:
        logger.warning("Could not inline synthesis into transcript: %r", exc)

    return result
