"""Rolling context window — periodic recap injection during long voice sessions.

Providers lock `system_instruction` at connect, so we can't update it mid-flight.
Instead, every ~7 min (or 25 user turns, whichever first) we :
  1. take the accumulated user + model transcripts since the last recap,
  2. compact them via `claude -p` Sonnet into a tight bullet recap,
  3. inject that recap as a silent note (turn_complete=False on Gemini, or
     role=system without response.create on OpenAI) so the model absorbs it
     without speaking.

This keeps the model coherent across long sessions where its own internal
context window or attention drifts away from the early discussion.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field

DEFAULT_INTERVAL_SECONDS = 420.0  # 7 min
# Char-based trigger instead of turn-based : Gemini emits one partial transcript
# per syllable, so counting "turns" by partial events explodes (28 partials in
# 2 min = a recap every 100 seconds, way too often). Characters of accumulated
# user text are a stable proxy across providers.
DEFAULT_USER_CHAR_TRIGGER = 2500   # ≈ 3-4 min of brisk conversation
MIN_TRANSCRIPT_CHARS = 600  # below this, recap not worth it

RECAP_PROMPT = """Tu reçois une portion de conversation vocale entre Stéphane et un assistant
réalisée DEPUIS le dernier point de contexte. Compacte en ≤ 1200 caractères
français, en gardant strictement :
- Sujet courant
- Décisions ou conclusions atteintes
- Points en suspens / questions ouvertes
- Détails techniques saillants (chiffres, noms, fichiers, commits)

Style : fragments OK, pas de bla-bla, pas d'intro. Commence direct par le sujet.

Conversation :
---
"""


@dataclass
class RecapState:
    """Tracks transcript chars between recaps. Char-based — not turn-based —
    because Gemini emits one partial per syllable (turn counts inflate ~30x).
    """

    started_at: float = field(default_factory=time.monotonic)
    last_recap_at: float = field(default_factory=time.monotonic)
    user_chunks_since_recap: list[str] = field(default_factory=list)
    model_chunks_since_recap: list[str] = field(default_factory=list)
    user_chars_since_recap: int = 0
    recap_count: int = 0

    def add_user(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.user_chunks_since_recap.append(text)
            self.user_chars_since_recap += len(text)

    def add_model(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.model_chunks_since_recap.append(text)

    def render_transcript(self) -> str:
        """Render the buffer as a flat dialogue. We don't have strict turn
        boundaries from chunks (Gemini emits partials per syllable), so we
        group all user chunks then all model chunks.
        """
        if not self.user_chunks_since_recap and not self.model_chunks_since_recap:
            return ""
        user_text = " ".join(self.user_chunks_since_recap)
        model_text = " ".join(self.model_chunks_since_recap)
        out: list[str] = []
        if user_text:
            out.append(f"Stéphane (parole) : {user_text}")
        if model_text:
            out.append(f"Assistant (réponses) : {model_text}")
        return "\n\n".join(out)

    def reset(self) -> None:
        self.last_recap_at = time.monotonic()
        self.user_chunks_since_recap.clear()
        self.model_chunks_since_recap.clear()
        self.user_chars_since_recap = 0
        self.recap_count += 1


def compact_recap(transcript: str, timeout_seconds: int = 45) -> str | None:
    """Run `claude -p` Sonnet to compact a rolling-window transcript."""
    if len(transcript) < MIN_TRANSCRIPT_CHARS:
        return None
    prompt = RECAP_PROMPT + transcript + "\n---\n"
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet", prompt],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


SILENT_NOTE_PREFIX = (
    "[Note système — rappel contexte conversation, NE RÉPONDS PAS, absorbe seulement]\n\n"
)


def wrap_for_silent_injection(recap: str) -> str:
    """Wrap the compacted recap with a marker that asks the model not to reply.

    Belt-and-suspenders : both turn_complete=False (Gemini) / no-response.create
    (OpenAI) AND a textual marker the system_prompt teaches the model to ignore.
    """
    return SILENT_NOTE_PREFIX + recap


async def maybe_run_recap(
    state: RecapState,
    interval_seconds: float,
    char_trigger: int,
) -> str | None:
    """Return a compact recap string if the trigger conditions are met, else None.

    Triggers on either:
    - elapsed time since last recap >= interval_seconds, OR
    - accumulated user transcript chars >= char_trigger.

    Runs `compact_recap` in a thread executor so we don't block the asyncio
    event loop while `claude -p` does its 5-30s synchronous work.
    """
    elapsed = time.monotonic() - state.last_recap_at
    time_trigger = elapsed >= interval_seconds
    chars_trigger = state.user_chars_since_recap >= char_trigger
    if not (time_trigger or chars_trigger):
        return None
    transcript = state.render_transcript()
    if not transcript:
        return None
    loop = asyncio.get_running_loop()
    recap = await loop.run_in_executor(None, compact_recap, transcript)
    if recap is None:
        return None
    return wrap_for_silent_injection(recap)
