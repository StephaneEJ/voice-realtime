"""Persona creator — interactive `persona new` (Phase 3.D).

Workflow:
1. CLI prompts for name, description, voice, reactivity, creativity, skills
2. Calls `claude -p` Sonnet with an expert prompt to generate a structured
   markdown system prompt (Identité / Personnalité / Langue / Règles / Outils)
3. Writes <vault>/_System/voice-personas/<slug>.md with YAML frontmatter + body

Avatar generation deferred to Phase 3.F (UI). Frontmatter `avatar:` field is
left empty here; the UI will fill it later.

Conforms to vault rule `feedback_always_claude_cli_not_sdk`: uses `claude -p`
CLI, never the Anthropic SDK.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .persona import get_personas_dir

VALID_VOICES_GEMINI = ["Charon", "Aoede", "Fenrir", "Kore", "Puck"]
VALID_VOICES_OPENAI = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]
VALID_VADS = ["reactive", "balanced", "patient", "very-patient"]
VALID_CREATIVITIES = ["precise", "balanced", "creative", "wild"]
VALID_GREETING_MODES = ["persona", "user"]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,40}$")

CREATOR_SYSTEM_PROMPT = """Tu es un expert prompt engineer spécialisé dans les modèles voice realtime
(Gemini Live et OpenAI Realtime). Tu vas créer un system prompt français
optimisé pour une conversation vocale temps réel.

Tu reçois en entrée :
- Nom du persona
- Description courte (ce qu'il est, son rôle)
- Skills/notes Obsidian que le persona pourra invoquer (liste de slugs)

Tu retournes UNIQUEMENT le body markdown du system prompt (PAS le frontmatter
YAML, le caller s'en occupe). Structure OBLIGATOIRE :

# Identité
[2-4 phrases qui définissent le persona, son rôle, son rapport à Stéphane Dufresne
qui est ingénieur bâtiment devenu DG en transition vers entrepreneuriat]

# Personnalité
- **Ton :** [direct / chaleureux / posé / etc.]
- **Humour :** [rare / léger / sec / etc.]
- **Style :** [conversationnel / chirurgical / contenant / etc.]
- **Énergie :** [calme / haute / variable]

# Langue
Français. Phrases courtes. Accents complets.

# Règles de conversation orale
- 2-3 phrases max par réponse, sauf demande de développement.
- Pas de listes ni de markdown — tu PARLES.
- [autres règles spécifiques au persona]

# Ouverture de session
Quand tu reçois « Démarre. » : dis UNIQUEMENT [phrase courte ouverture]. Puis tu te tais et tu attends.

# Notes de contexte silencieuses
Si tu reçois un message « [Note système — rappel contexte conversation, NE RÉPONDS PAS, absorbe seulement] » : absorbe sans répondre.

# Outils disponibles
[Liste des outils, surtout date/heure. Mentionner les skills Obsidian si présents.]

RÈGLES IMPÉRATIVES :
- Pas d'introduction (pas de "Voici le prompt"). Tu commences DIRECTEMENT par "# Identité".
- Pas de bloc code ```markdown autour. Juste le markdown brut.
- Le contenu est en français, avec tous les accents (é, è, ê, à, â, ù, û, ô, î, ç).
- Adapte le ton et l'énergie à la description fournie.
"""


class PersonaCreatorError(Exception):
    pass


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug))


def _quiet_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["MallocStackLogging"] = "0"
    env["MallocStackLoggingNoCompact"] = "0"
    return env


def generate_system_prompt(
    name: str,
    description: str,
    obsidian_skills: list[str],
    timeout_seconds: int = 90,
) -> str:
    """Call `claude -p` Sonnet to produce the markdown body of a persona.

    Returns the markdown body. Raises PersonaCreatorError on failure.
    """
    user_prompt = f"""Nom du persona : {name}
Description : {description}
Skills Obsidian liés : {', '.join(obsidian_skills) if obsidian_skills else '(aucun)'}

Génère maintenant le markdown body conforme à la structure imposée."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet",
             "--append-system-prompt", CREATOR_SYSTEM_PROMPT,
             user_prompt],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
            env=_quiet_subprocess_env(),
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise PersonaCreatorError(
            "`claude` CLI not found in PATH. Install Claude Code first."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PersonaCreatorError(f"claude -p timed out after {timeout_seconds}s") from exc

    if result.returncode != 0:
        raise PersonaCreatorError(
            f"claude -p failed (exit {result.returncode}). stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
        )
    body = (result.stdout or "").strip()
    # Strip wrapping ```markdown fences if claude added them despite instructions
    if body.startswith("```"):
        lines = body.splitlines()
        # drop first fence line and trailing fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    if not body:
        raise PersonaCreatorError("claude -p returned empty body")
    if not body.startswith("# Identité"):
        # Be lenient: claude might have started with extra preamble; try to
        # find the section anchor and trim.
        idx = body.find("# Identité")
        if idx > 0:
            body = body[idx:].strip()
    return body


def render_persona_file(
    *,
    slug: str,
    name: str,
    description: str,
    voice: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    vad: str | None = None,
    creativity: str | None = None,
    greeting_mode: str = "persona",
    greeting_text: str | None = None,
    avatar: str | None = None,
    obsidian_skills: list[str] | None = None,
    obsidian_notes: list[str] | None = None,
    tools: list[str] | None = None,
    body: str,
) -> str:
    """Compose the full markdown file content (frontmatter + body)."""
    lines = ["---", "type: voice-persona", f"slug: {slug}", f"name: {name}"]
    if description:
        lines.append(f"description: {description}")
    if voice:
        lines.append(f"voice: {voice}")
    if model:
        lines.append(f"model: {model}")
    if provider:
        lines.append(f"provider: {provider}")
    if vad:
        lines.append(f"vad: {vad}")
    if creativity:
        lines.append(f"creativity: {creativity}")
    lines.append(f"greeting_mode: {greeting_mode}")
    if greeting_text:
        lines.append(f'greeting_text: "{greeting_text}"')
    if avatar:
        lines.append(f"avatar: {avatar}")
    if obsidian_skills:
        lines.append("obsidian_skills:")
        for s in obsidian_skills:
            lines.append(f"  - {s}")
    if obsidian_notes:
        lines.append("obsidian_notes:")
        for n in obsidian_notes:
            # Quote if needed (paths with spaces / glob chars)
            if " " in n or "*" in n:
                lines.append(f'  - "{n}"')
            else:
                lines.append(f"  - {n}")
    if tools:
        lines.append("tools:")
        for t in tools:
            lines.append(f"  - {t}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def save_persona(content: str, slug: str, personas_dir: Path | None = None,
                 *, overwrite: bool = False) -> Path:
    """Write the persona file to <vault>/_System/voice-personas/<slug>.md.

    Raises PersonaCreatorError if the file already exists and overwrite=False.
    """
    target_dir = personas_dir or get_personas_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.md"
    if target.exists() and not overwrite:
        raise PersonaCreatorError(
            f"Persona already exists: {target}\nUse --overwrite to replace."
        )
    target.write_text(content, encoding="utf-8")
    return target
