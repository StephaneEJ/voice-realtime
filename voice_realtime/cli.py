"""voice-realtime CLI — Typer entry point.

Commands:
    voice-realtime status                  # config sanity check
    voice-realtime hello [--provider]      # M1 smoke test text I/O
    voice-realtime talk [--provider]       # M2-M4 duplex audio session with context + cost + save
"""

from __future__ import annotations

import asyncio
import re
import signal
import sys
import warnings
from pathlib import Path

# Voice kill switch : strict isolation across multiple keywords. An utterance
# whose ENTIRE content matches any pattern triggers stop. Mid-phrase mentions
# never match.
#
# Why FR keywords matter (P0.2, 2026-05-24): Gemini STT consistently mishears
# "killchat" in French utterances. Observed transcripts during the 18-min test
# session: "kilk", "kik", "kil chat", and even "24". The legacy EN pattern
# never matched. FR keywords ("termine la session", "fin jarvis", "stop
# session") survive Gemini STT cleanly because they're real French words.
#
# Patterns:
#  - FR primary: "termine la session" — 3 words, robust against STT mishears
#  - FR alt:     "fin jarvis"         — short fallback
#  - EN alt:     "stop session"       — bilingual fallback
#  - Legacy EN:  "kill chat" variants — kept for backwards-compat
#  - Misheard:   "kil[a-zé]* chat"    — accepts "kilk chat", "kik chat",
#                                       "kil chat", "killé chat"
_KILLCHAT_PATTERNS = (
    re.compile(r"^\s*[.,!?]*\s*termine\s+la\s+session\s*[.,!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*[.,!?]*\s*fin\s+jarvis\s*[.,!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*[.,!?]*\s*stop\s+session\s*[.,!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*[.,!?]*\s*kill[\s-]*chat\s*[.,!?]*\s*$", re.IGNORECASE),
    # Misheard tolerance — Gemini STT FR drops or alters consonants of
    # "killchat". Observed live: "kilk", "kik", "kil", "killé". `ki` + 1-4
    # any letter chars + space + `chat`. The anchored ^/$ + the required
    # space-separated `chat` token keeps false positives down ("kilo de chat"
    # has a " de " between, so it doesn't match).
    re.compile(r"^\s*[.,!?]*\s*ki[a-zé]{1,4}\s+chat\s*[.,!?]*\s*$", re.IGNORECASE),
)
# Gemini Live emits inline diarization tags around speech. Strip them so the
# strict isolation regexes above still match when the user said only the
# keyword surrounded by noise markers.
_STT_NOISE_TAGS_RE = re.compile(r"<(?:noise|silence|music|cough|laugh|background)>", re.IGNORECASE)


def _is_killchat_keyword(text: str) -> bool:
    if not text:
        return False
    cleaned = _STT_NOISE_TAGS_RE.sub("", text)
    return any(p.match(cleaned) for p in _KILLCHAT_PATTERNS)


def _say_farewell_edge_tts() -> None:
    """Local fallback farewell when the model voice path failed.

    Uses Edge TTS (same engine as Jarvis) so the user always gets a clear
    closing cue, regardless of whether the realtime websocket survived.
    """
    import subprocess as sp
    tmp = "/tmp/voice-realtime-farewell.mp3"
    try:
        sp.run(
            ["edge-tts", "--voice", "fr-FR-HenriNeural", "--rate", "+25%",
             "--text", "Fin voice realtime.", "--write-media", tmp],
            capture_output=True, timeout=8,
        )
        sp.Popen(["afplay", tmp], stdout=sp.DEVNULL, stderr=sp.DEVNULL).wait(timeout=8)
    except Exception:
        pass

# Suppress google-genai SDK chatty warnings about non-text/non-data parts —
# these fire on every audio response when modality=AUDIO + output_audio_transcription
# is enabled. Inoffensifs but pollute the transcript display.
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*non-data parts.*")

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .config import SECRETS_PATH, load_config
from .context_loader import build_context
from .cost_tracker import CostTracker, monthly_total_usd
from .latency_tracker import LatencyTracker
from .log import get_logger, setup_logging
from .providers.base import ProviderConfig
from .providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL, GEMINI_INPUT_SAMPLE_RATE, GEMINI_OUTPUT_SAMPLE_RATE, GeminiProvider
from .providers.openai_realtime import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
    OPENAI_AUDIO_SAMPLE_RATE,
    OpenAIRealtimeProvider,
)
from .session_saver import save_session_note
from .system_audio import (
    AnotherSessionActive,
    acquire_lock,
    drain_jarvis_queue,
    pause_external_media,
    release_lock,
    resume_external_media,
)

app = typer.Typer(
    add_completion=False,
    help="Duplex realtime voice skill. Multi-provider (Gemini Live + OpenAI Realtime-2).",
)
persona_app = typer.Typer(
    add_completion=False,
    help="Persona management (list, show, new).",
)
app.add_typer(persona_app, name="persona")
console = Console()


@persona_app.command("list")
def persona_list() -> None:
    """List available personas in the vault."""
    from .persona import list_personas, get_personas_dir

    personas = list_personas()
    if not personas:
        console.print(f"[yellow]No personas found in {get_personas_dir()}[/yellow]")
        console.print("[dim]Create one with: voice-realtime persona new <slug>[/dim]")
        raise typer.Exit(0)

    from rich.table import Table
    table = Table(title="Available personas", title_style="cyan", show_lines=False)
    table.add_column("Slug", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Voice")
    table.add_column("VAD")
    table.add_column("Provider")
    table.add_column("Skills")
    table.add_column("Description", style="dim")
    for p in personas:
        skills_n = f"{len(p.obsidian_skills)}+{len(p.obsidian_notes)}" if p.has_obsidian_filter else "—"
        table.add_row(
            p.slug,
            p.name,
            p.voice or "—",
            p.vad or "—",
            p.provider or "—",
            skills_n,
            p.description or "",
        )
    console.print(table)


@persona_app.command("show")
def persona_show(slug: str = typer.Argument(..., help="Persona slug")) -> None:
    """Show a persona's frontmatter + system prompt + resolved knowledge block."""
    from .persona import load_persona_by_slug, PersonaError
    from .persona_skills import build_persona_knowledge_block, report_missing_references

    try:
        p = load_persona_by_slug(slug)
    except PersonaError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold]{p.name}[/bold] ({p.slug})\n"
        f"{p.description}\n\n"
        f"Voice: {p.voice or 'default'}\n"
        f"Model: {p.model or 'default'}\n"
        f"Provider: {p.provider or 'default'}\n"
        f"VAD: {p.vad or 'default'}\n"
        f"Creativity: {p.creativity or 'default'}\n"
        f"Greeting: {p.greeting_mode} ({p.greeting_text or '—'})\n"
        f"Skills: {', '.join(p.obsidian_skills) or 'none'}\n"
        f"Notes: {', '.join(p.obsidian_notes) or 'none'}\n"
        f"Source: {p.source_path}",
        title="Persona", border_style="cyan",
    ))
    console.print(Panel(p.system_prompt, title="System prompt", border_style="dim"))

    if p.has_obsidian_filter:
        missing_skills, missing_notes = report_missing_references(p)
        if missing_skills or missing_notes:
            warn = []
            if missing_skills:
                warn.append(f"Missing skills (typos?): {', '.join(missing_skills)}")
            if missing_notes:
                warn.append(f"No matching notes: {', '.join(missing_notes)}")
            console.print(Panel("\n".join(warn), title="Warnings", border_style="yellow"))
        block = build_persona_knowledge_block(p)
        console.print(Panel(
            f"{len(block)} chars total — preview:\n\n{block[:1500]}{'…' if len(block) > 1500 else ''}",
            title="Knowledge block (vault filter)", border_style="green",
        ))


@app.command()
def status() -> None:
    """Show config status + monthly cost so far. No network."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    monthly = monthly_total_usd()
    pct = (monthly / cfg.monthly_budget_usd * 100.0) if cfg.monthly_budget_usd > 0 else 0.0
    lines = [
        f"Secrets file : {SECRETS_PATH}",
        f"OpenAI key   : {'present' if cfg.has_openai else 'MISSING'}",
        f"Gemini key   : {'present' if cfg.has_gemini else 'MISSING'}",
        f"Budget cap   : ${cfg.monthly_budget_usd:.2f}/month",
        f"Used so far  : ${monthly:.4f} ({pct:.1f}%)",
    ]
    console.print(Panel("\n".join(lines), title="voice-realtime status", border_style="cyan"))


@app.command()
def hello(
    message: str = typer.Option(
        "Bonjour. Réponds en une phrase pour confirmer la connexion.",
        "--message",
        "-m",
        help="Test message to send.",
    ),
    provider: str = typer.Option("openai", "--provider", "-p", help="openai | gemini"),
    model: str = typer.Option("", "--model", help="Override model id."),
) -> None:
    """M1 smoke test: text I/O via WebSocket realtime."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if provider == "openai":
        if not cfg.has_openai:
            console.print("[red]OPENAI_API_KEY missing[/red]")
            raise typer.Exit(1)
        chosen_model = model or OPENAI_DEFAULT_MODEL
        asyncio.run(_run_hello("openai", cfg.openai_api_key, chosen_model, message))  # type: ignore[arg-type]
    elif provider == "gemini":
        if not cfg.has_gemini:
            console.print("[red]GEMINI_API_KEY missing[/red]")
            raise typer.Exit(1)
        chosen_model = model or GEMINI_DEFAULT_MODEL
        asyncio.run(_run_hello("gemini", cfg.gemini_api_key, chosen_model, message))  # type: ignore[arg-type]
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)


async def _run_hello(provider_name: str, api_key: str, model: str, message: str) -> None:
    if provider_name == "openai":
        impl = OpenAIRealtimeProvider()
    else:
        impl = GeminiProvider()  # type: ignore[assignment]

    pcfg = ProviderConfig(model=model, api_key=api_key, thinking_level="low")
    console.print(f"[dim]Connecting to {provider_name} / {model}...[/dim]")
    try:
        await impl.connect(pcfg, system_prompt="Tu es un assistant de test. Sois bref.")
    except Exception as exc:
        console.print(f"[red]Connect failed: {exc!r}[/red]")
        raise typer.Exit(2)

    console.print(f"[cyan]>>>[/cyan] {message}")
    await impl.send_text(message)

    response_chunks: list[str] = []
    try:
        async for event in impl.receive_events():
            if event.kind == "partial_transcript_model":
                chunk = event.data.get("text", "")
                response_chunks.append(chunk)
                console.print(chunk, end="")
            elif event.kind == "final_transcript_model":
                if not response_chunks:
                    final_text = event.data.get("text", "")
                    response_chunks.append(final_text)
                    console.print(f"[green]<<<[/green] {final_text}", end="")
            elif event.kind == "error":
                console.print(f"\n[red]Error: {event.data}[/red]")
                break
            elif event.kind == "session_closed":
                break
    finally:
        await impl.close()
        console.print()

    if not response_chunks:
        console.print("[yellow]No response received.[/yellow]")
        sys.exit(3)


# -----------------------------------------------------------------------------
# Summarize — turn a raw voice session note into a structured synthesis
# -----------------------------------------------------------------------------


@app.command()
def summarize(
    transcript: str = typer.Argument(..., help="Path to a voice session note (markdown)."),
    project: str = typer.Option("", "--project", "-p", help="Project hint for context + append target."),
    model: str = typer.Option("claude-sonnet-4-6", "--model", help="claude -p model id."),
) -> None:
    """Synthesize a voice session transcript via `claude -p` and append to project note."""
    from .summarizer import summarize_session

    path = Path(transcript).expanduser()
    if not path.is_absolute():
        # Try relative to vault voice-sessions dir.
        vault_sessions = Path.home() / "OBSIDIAN" / "2ND_CERVEAU" / "_System" / "voice-sessions"
        candidate = vault_sessions / transcript
        if candidate.exists():
            path = candidate
    if not path.exists():
        console.print(f"[red]Transcript not found: {path}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Summarizing {path.name} (model={model}, project={project or '—'})...[/cyan]")
    try:
        result = summarize_session(path, project_hint=project or None, model=model)
    except Exception as exc:
        console.print(f"[red]Summary failed: {exc!r}[/red]")
        raise typer.Exit(1)

    lines = [
        f"Sujet : {result.topic_summary}",
        f"Décisions : {len(result.decisions)}",
        f"Actions : {len(result.actions)}",
        f"Insights : {len(result.insights)}",
        f"Questions ouvertes : {len(result.unresolved_questions)}",
    ]
    if result.appended and result.project_note_path:
        lines.append(f"Appendé à : {result.project_note_path}")
    elif project:
        lines.append(f"Note projet « {project} » introuvable — synthèse non appendée")
    console.print(Panel("\n".join(lines), title="Synthèse", border_style="green"))


# -----------------------------------------------------------------------------
# Voice preview — short audio sample with each available voice (no mic, no save)
# -----------------------------------------------------------------------------


GEMINI_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Puck"]
OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]


@app.command(name="preview-voices")
def preview_voices(
    provider: str = typer.Option("gemini", "--provider", "-p", help="openai | gemini"),
    seconds_per_voice: float = typer.Option(6.0, "--seconds", help="Audio capture window per voice."),
) -> None:
    """Play a short sample with each available voice for the provider."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if provider == "gemini":
        if not cfg.has_gemini:
            console.print("[red]GEMINI_API_KEY missing[/red]")
            raise typer.Exit(1)
        voices = GEMINI_VOICES
        api_key = cfg.gemini_api_key
        model = GEMINI_DEFAULT_MODEL
        rate = GEMINI_OUTPUT_SAMPLE_RATE
    elif provider == "openai":
        if not cfg.has_openai:
            console.print("[red]OPENAI_API_KEY missing[/red]")
            raise typer.Exit(1)
        voices = OPENAI_VOICES
        api_key = cfg.openai_api_key
        model = OPENAI_DEFAULT_MODEL
        rate = OPENAI_AUDIO_SAMPLE_RATE
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_preview_voices(provider, voices, api_key, model, rate, seconds_per_voice))


async def _preview_one_voice(
    provider_name: str,
    voice: str,
    api_key: str,
    model: str,
    rate: int,
    capture_seconds: float,
) -> None:
    from .audio.playback import AudioPlayer

    impl = GeminiProvider() if provider_name == "gemini" else OpenAIRealtimeProvider()
    pcfg = ProviderConfig(model=model, api_key=api_key, thinking_level="low", voice=voice)
    player = AudioPlayer(rate=rate)
    player.start()

    async def _recv() -> None:
        try:
            async for event in impl.receive_events():
                if event.kind == "audio_chunk_out":
                    pcm = event.data.get("pcm16", b"")
                    if pcm:
                        await player.enqueue(pcm)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    recv_task: asyncio.Task | None = None
    try:
        await impl.connect(
            pcfg,
            system_prompt="Tu es un échantillon de voix. Réponds très brièvement.",
            audio=True,
        )
        recv_task = asyncio.create_task(_recv())
        await impl.send_text(
            f"Dis exactement et uniquement la phrase : « Bonjour Stéphane, je suis la voix {voice}. » Rien d'autre."
        )
        await asyncio.sleep(capture_seconds)
    except Exception as exc:
        console.print(f"[red]Voice {voice} failed: {exc!r}[/red]")
    finally:
        if recv_task is not None:
            recv_task.cancel()
            await asyncio.gather(recv_task, return_exceptions=True)
        try:
            await impl.close()
        except Exception:
            pass
        await player.drain(timeout=3.0)
        player.stop()


async def _run_preview_voices(
    provider_name: str,
    voices: list[str],
    api_key: str,
    model: str,
    rate: int,
    capture_seconds: float,
) -> None:
    console.print(Panel(
        f"Provider: {provider_name}\nVoices: {', '.join(voices)}\nCapture per voice: {capture_seconds}s",
        title="voice-realtime preview-voices",
        border_style="cyan",
    ))
    for voice in voices:
        console.print(f"\n[cyan bold]>>> Voix : {voice}[/cyan bold]")
        await _preview_one_voice(provider_name, voice, api_key, model, rate, capture_seconds)
        # Small gap so the audio drains and the next voice doesn't overlap.
        await asyncio.sleep(1.5)
    console.print("\n[green]Preview terminé.[/green]")


# -----------------------------------------------------------------------------
# M2-M4 talk command — full duplex audio session with context + cost + save
# -----------------------------------------------------------------------------


@app.command()
def talk(
    provider: str = typer.Option("gemini", "--provider", "-p", help="openai | gemini"),
    model: str = typer.Option("", "--model", help="Override model id."),
    voice: str = typer.Option("", "--voice", help="Override voice. OpenAI: alloy|ash|ballad|coral|echo|sage|shimmer|verse. Gemini: Aoede|Charon|Fenrir|Kore|Puck."),
    project: str = typer.Option("", "--project", help="Inject project context from vault (partial name match)."),
    max_minutes: float = typer.Option(15.0, "--max-minutes", help="Hard duration cap (kill switch)."),
    cost_cap: float = typer.Option(3.0, "--cost-cap", help="Hard cost cap USD (kill switch)."),
    no_save: bool = typer.Option(False, "--no-save", help="Skip saving session note to vault."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Also print debug logs to stderr (default: file only)."),
    clean_terminal: bool = typer.Option(
        False,
        "--clean-terminal",
        "-c",
        help="Terminal shows STT transcripts only — everything else (status, summary, warnings) goes to log file. Fatal errors still print.",
    ),
    show_partial: bool = typer.Option(
        False,
        "--show-partial",
        help="Display partial model transcripts as they stream (debug). Default: hidden to avoid desync between text and audio playback when interrupting.",
    ),
    auto_summarize: bool = typer.Option(
        True,
        "--summarize/--no-summarize",
        help="Auto-run summarize-voice at session end. Default: on (requires --project for append to work).",
    ),
    cli_context: bool = typer.Option(
        False,
        "--cli-context",
        "--claude-context",  # legacy alias from the 1-day-old name
        "-k",
        help="Inject the active CLI conversation (auto-detects Claude Code or OpenCode, compacts via claude -p Sonnet if over budget). Lets the voice model pick up where the CLI session left off.",
    ),
    rolling_recap: bool = typer.Option(
        True,
        "--rolling-recap/--no-rolling-recap",
        help="Periodically inject a compacted recap (claude -p Sonnet) of the last few minutes so the model stays coherent on long sessions. Default: on.",
    ),
    recap_interval: float = typer.Option(
        420.0,
        "--recap-interval",
        help="Min seconds between rolling recaps (default 420 = 7 min).",
    ),
    recap_user_chars: int = typer.Option(
        2500,
        "--recap-user-chars",
        "--recap-turns",  # legacy alias from the buggy turn-based trigger
        help="Trigger a rolling recap after this many cumulative user transcript chars (default 2500 ≈ 3-4 min of conversation). Char-based instead of turn-based because Gemini emits one partial per syllable.",
    ),
    mic_rate: int = typer.Option(
        0,
        "--mic-rate",
        help="Override mic sample rate (Hz). 0 = provider default (Gemini 16000, OpenAI 24000). Try 24000 on Gemini to see if FR STT improves on rapid speech.",
    ),
    vad: str = typer.Option(
        "balanced",
        "--vad",
        help="VAD sensitivity preset: reactive | balanced | patient | very-patient. Controls how easily the server interrupts the model on ambient noise. Pick 'patient' or 'very-patient' in noisy environments (default: balanced).",
    ),
    persona: str = typer.Option(
        "",
        "--persona",
        help="Persona slug (e.g. 'jarvis', 'hormozi', 'coach-halt'). When set, the persona's system prompt + voice + VAD + model override the inline defaults, and persona.obsidian_skills/notes are merged into the system prompt as 'active knowledge'. List with: voice-realtime persona list",
    ),
) -> None:
    """M2-M4: duplex audio session with context injection, cost tracking, vault save."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    # Resolve persona first — its fields take precedence over CLI defaults
    # for provider/model/voice/vad. Explicit CLI flags (when the user passed
    # them) still win over the persona's frontmatter.
    persona_obj = None
    persona_knowledge = ""
    if persona:
        from .persona import load_persona_by_slug, PersonaError
        from .persona_skills import build_persona_knowledge_block
        try:
            persona_obj = load_persona_by_slug(persona)
        except PersonaError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        # Apply persona overrides only when the CLI value is the default —
        # detect "user didn't pass it" by checking against the typer defaults.
        # `provider` default is "gemini", `voice` is "", `model` is "", `vad`
        # is "balanced". Persona overrides ONLY default values.
        if persona_obj.provider and provider == "gemini":
            provider = persona_obj.provider
        if persona_obj.model and not model:
            model = persona_obj.model
        if persona_obj.voice and not voice:
            voice = persona_obj.voice
        if persona_obj.vad and vad == "balanced":
            vad = persona_obj.vad
        persona_knowledge = build_persona_knowledge_block(persona_obj)

    if provider == "openai":
        if not cfg.has_openai:
            console.print("[red]OPENAI_API_KEY missing[/red]")
            raise typer.Exit(1)
        chosen_model = model or OPENAI_DEFAULT_MODEL
        api_key = cfg.openai_api_key
    elif provider == "gemini":
        if not cfg.has_gemini:
            console.print("[red]GEMINI_API_KEY missing[/red]")
            raise typer.Exit(1)
        chosen_model = model or GEMINI_DEFAULT_MODEL
        api_key = cfg.gemini_api_key
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)

    # Build context-injected system prompt — persona's prompt replaces the
    # inline default when --persona is set.
    if persona_obj is not None:
        base_prompt = persona_obj.system_prompt
        if persona_knowledge:
            base_prompt = base_prompt + "\n\n" + persona_knowledge
    else:
        base_prompt = (
            "Tu es Jarvis voice — un partenaire de brainstorming pour Stéphane Dufresne. "
            "Tu réponds en français, naturellement, comme une conversation. "
            "Tu n'es ni flatteur ni servile. Tu challenges quand c'est utile. "
            "Tu vas droit au but, sans préambule.\n\n"
            "OUVERTURE OBLIGATOIRE : Quand tu reçois le mot-clé « Démarre. » comme premier "
            "message (signal de démarrage de session, ce n'est PAS une vraie question de "
            "Stéphane), tu réponds UNIQUEMENT et EXCLUSIVEMENT par cette phrase courte : "
            "« Salut Stéphane, je suis connecté, je t'écoute. » — RIEN d'autre. Pas de "
            "récap projet, pas de Phase 2, pas de questions, pas de proposition. Tu dis "
            "juste cette phrase puis tu te tais et tu attends sa première vraie question.\n\n"
            "NOTES DE CONTEXTE SILENCIEUSES : Si tu reçois un message commençant par "
            "« [Note système — rappel contexte conversation, NE RÉPONDS PAS, absorbe "
            "seulement] », c'est un récap automatique de ce qui vient d'être dit. Tu "
            "l'absorbes en mémoire SANS répondre. Tu attends que Stéphane parle ensuite."
        )
    ctx = build_context(project_hint=project or None, include_cli=cli_context)
    if ctx:
        system_prompt = base_prompt + "\n\n# Contexte vault (utilise si pertinent)\n\n" + ctx
    else:
        system_prompt = base_prompt

    log_path = setup_logging(provider=provider, verbose=verbose)

    asyncio.run(
        _run_talk(
            provider_name=provider,
            api_key=api_key,  # type: ignore[arg-type]
            model=chosen_model,
            system_prompt=system_prompt,
            max_minutes=max_minutes,
            cost_cap=cost_cap,
            project_hint=project or None,
            save_note=not no_save,
            clean_terminal=clean_terminal,
            log_path=log_path,
            show_partial=show_partial,
            voice=voice or None,
            auto_summarize=auto_summarize,
            rolling_recap=rolling_recap,
            recap_interval=recap_interval,
            recap_user_chars=recap_user_chars,
            mic_rate_override=mic_rate or None,
            vad=vad,
            persona_slug=(persona_obj.slug if persona_obj else None),
            greeting_mode=(persona_obj.greeting_mode if persona_obj else "persona"),
        )
    )


async def _run_talk(
    provider_name: str,
    api_key: str,
    model: str,
    system_prompt: str,
    max_minutes: float,
    cost_cap: float,
    project_hint: str | None,
    save_note: bool,
    clean_terminal: bool = False,
    log_path: Path | None = None,
    show_partial: bool = False,
    voice: str | None = None,
    auto_summarize: bool = True,
    rolling_recap: bool = True,
    recap_interval: float = 420.0,
    recap_user_chars: int = 2500,
    mic_rate_override: int | None = None,
    vad: str = "balanced",
    persona_slug: str | None = None,
    greeting_mode: str = "persona",
) -> None:
    # Lazy import audio to avoid PortAudio errors at module load
    from .audio.microphone import MicrophoneStream
    from .audio.playback import AudioPlayer

    logger = get_logger("voice_realtime.talk")

    def _info(msg: str, *, force: bool = False, style: str = "dim") -> None:
        """Log to file always; print to terminal if !clean_terminal OR force."""
        logger.info(msg)
        if (not clean_terminal) or force:
            if style:
                console.print(f"[{style}]{msg}[/{style}]")
            else:
                console.print(msg)

    def _panel(text: str, title: str, border_style: str = "cyan", *, force: bool = False) -> None:
        """Log textual content; render Panel only if !clean_terminal OR force."""
        logger.info("=== %s ===\n%s", title, text)
        if (not clean_terminal) or force:
            console.print(Panel(text, title=title, border_style=border_style))

    # Sample rates per provider — overridable via --mic-rate to A/B test
    # whether 24kHz capture+upload improves Gemini FR STT on rapid speech.
    if provider_name == "openai":
        input_rate = mic_rate_override or OPENAI_AUDIO_SAMPLE_RATE
        output_rate = OPENAI_AUDIO_SAMPLE_RATE
        impl = OpenAIRealtimeProvider()
    else:
        input_rate = mic_rate_override or GEMINI_INPUT_SAMPLE_RATE
        output_rate = GEMINI_OUTPUT_SAMPLE_RATE
        impl = GeminiProvider()  # type: ignore[assignment]

    valid_vads = {"reactive", "balanced", "patient", "very-patient"}
    if vad not in valid_vads:
        console.print(f"[red]Unknown --vad value: {vad!r}. Use one of: {', '.join(sorted(valid_vads))}[/red]")
        raise typer.Exit(1)

    pcfg = ProviderConfig(
        model=model, api_key=api_key, thinking_level="low", voice=voice,
        input_sample_rate=input_rate, vad=vad,  # type: ignore[arg-type]
    )

    if log_path is not None:
        _info(f"Log file: {log_path}")

    header_text = (
        f"Provider: {provider_name} / {model}\n"
        f"Persona: {persona_slug or 'jarvis (inline default)'}\n"
        f"Project context: {project_hint or 'none'}\n"
        f"Mic rate: {input_rate} Hz\n"
        f"VAD preset: {vad}\n"
        f"Greeting mode: {greeting_mode}\n"
        f"Max duration: {max_minutes:.0f} min\n"
        f"Cost cap: ${cost_cap:.2f}\n"
        f"Ctrl+C / 'termine la session' to stop."
    )
    _panel(header_text, title="voice-realtime talk", border_style="cyan")

    # Pause external media + acquire Jarvis TTS lock BEFORE opening the
    # microphone — anything still playing would pollute the input stream.
    # acquire_lock() refuses if another talk session is already active.
    try:
        acquire_lock()
    except AnotherSessionActive as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)
    media_state = pause_external_media()
    if media_state.deezer_pids or media_state.spotify_was_playing or media_state.music_was_playing:
        paused = []
        if media_state.deezer_pids:
            paused.append(f"Deezer x{len(media_state.deezer_pids)} (SIGSTOP)")
        if media_state.spotify_was_playing:
            paused.append("Spotify")
        if media_state.music_was_playing:
            paused.append("Music")
        _info(f"Paused external media: {', '.join(paused)}")

    _info(f"Connecting to {provider_name}...")
    try:
        await impl.connect(pcfg, system_prompt=system_prompt, audio=True)
    except Exception as exc:
        logger.exception("Connect failed")
        console.print(f"[red]Connect failed: {exc!r}[/red]")
        release_lock()
        resume_external_media(media_state)
        return

    # Greeting kick : Gemini Live native-audio server VAD won't emit a first
    # turn until it detects user speech. We send a tiny text trigger so the
    # model delivers the obligatory greeting immediately, without waiting.
    # Personas with greeting_mode="user" expect to wait silently for Stéphane
    # to speak first (e.g. interview personas) — skip the kick in that case.
    if greeting_mode == "persona":
        try:
            await impl.send_text("Démarre.")
        except Exception as exc:
            logger.warning("greeting kick failed (non-fatal): %r", exc)
    else:
        logger.info("greeting_mode=user — skipping kick, waiting for user to speak first")

    tracker = CostTracker(
        provider=provider_name,
        model=model,
        hard_stop_cost_usd=cost_cap,
        max_duration_seconds=max_minutes * 60.0,
    )

    player = AudioPlayer(rate=output_rate)
    player.start()
    mic_stream = MicrophoneStream(rate=input_rate, chunk_ms=200)
    latency = LatencyTracker()

    transcript_user: list[str] = []
    transcript_model: list[str] = []
    stop_event = asyncio.Event()
    end_reason = "user_stop"
    connected = True  # impl.connect() has returned successfully above

    # Rolling recap : tracks turns + transcripts between auto-injected recaps.
    from .rolling_recap import RecapState, maybe_run_recap
    recap_state = RecapState() if rolling_recap else None

    def _vu_bar(level: float, width: int = 28) -> str:
        scaled = min(1.0, level * 4.5)  # speech RMS ~0.05-0.2 maps to 0.2-0.9 bar
        filled = int(scaled * width)
        return "█" * filled + "░" * (width - filled)

    def _render_status() -> Panel:
        if connected:
            head = f"[green]●[/green] Connecté  [dim]{provider_name} / {model}[/dim]"
            border = "green"
        else:
            head = f"[yellow]○[/yellow] Connexion...  [dim]{provider_name} / {model}[/dim]"
            border = "yellow"
        mic_lvl = mic_stream.level
        out_lvl = player.level

        def _fmt_ms(v: float | None) -> str:
            return f"{v:.0f}ms" if v is not None else "—"

        ttfa_line = (
            f"⏱  TTFA  last [bold]{_fmt_ms(latency.last_ttfa_ms)}[/bold]  "
            f"avg {_fmt_ms(latency.avg_ttfa_ms)}"
        )
        ttfi_line = (
            f"✂  TTFI  last [bold]{_fmt_ms(latency.last_ttfi_ms)}[/bold]  "
            f"avg {_fmt_ms(latency.avg_ttfi_ms)}"
        )
        body = (
            f"{head}\n"
            f"🎤 TOI  [cyan]{_vu_bar(mic_lvl)}[/cyan]  [dim]{mic_lvl*100:4.1f}[/dim]\n"
            f"🔊 IA   [magenta]{_vu_bar(out_lvl)}[/magenta]  [dim]{out_lvl*100:4.1f}[/dim]\n"
            f"{ttfa_line}\n"
            f"{ttfi_line}"
        )
        return Panel(Text.from_markup(body), border_style=border, title="voice-realtime live")

    live = Live(
        _render_status(),
        console=console,
        refresh_per_second=15,
        transient=False,
        auto_refresh=False,
    )
    live.start()

    def _request_stop(_sig=None, _frame=None) -> None:
        if not stop_event.is_set():
            logger.info("Stop requested by user (signal)")
            if not clean_terminal:
                console.print("\n[yellow]Stop requested...[/yellow]")
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, ValueError):
            pass

    # Client-side barge-in: when user starts speaking while model audio is
    # still buffered, flush locally without waiting for server VAD →
    # model_interrupted round-trip (~600ms + buffer ~1-6s on Gemini).
    BARGE_IN_LEVEL = 0.03  # RMS threshold; lowered from 0.08 — AirPods capture peaks ~0.04-0.06
    BARGE_IN_MIN_BUFFER = 4800  # 0.1s of audio @ 24kHz/16bit/mono — guards false positives during model silence
    # Hysteresis: require N consecutive frames above threshold before flushing.
    # Mic chunks land every ~200ms; 2 frames ≈ 400ms of sustained signal —
    # filters out ambient parasites (door, breath, family noise) that hit one
    # frame's RMS but vanish next frame. Live test 23/05 saw 12 flushes in
    # 10 min ; with N=2 most of those single-spike parasites get filtered.
    BARGE_IN_CONSECUTIVE_FRAMES = 2
    _last_level_log = 0.0  # throttle telemetry
    _above_threshold_streak = 0  # hysteresis counter

    async def _mic_pump() -> None:
        nonlocal _last_level_log, _above_threshold_streak
        async with mic_stream as mic:
            async for chunk in mic:
                if stop_event.is_set():
                    return
                try:
                    await impl.send_audio_chunk(chunk)
                    latency.on_user_audio_sent()
                except Exception as exc:
                    logger.exception("send_audio_chunk failed")
                    console.print(f"[red]send_audio_chunk failed: {exc!r}[/red]")
                    return
                # Telemetry: log mic level when model is mid-speech (helps tune threshold).
                buf = player.buffered_bytes()
                lvl = mic_stream.level
                now = asyncio.get_running_loop().time()
                if buf > BARGE_IN_MIN_BUFFER and (now - _last_level_log) > 0.5:
                    logger.info(
                        "barge-in telemetry — mic_level=%.4f buf=%d streak=%d",
                        lvl, buf, _above_threshold_streak,
                    )
                    _last_level_log = now
                # Client-side barge-in with hysteresis: only flush after
                # BARGE_IN_CONSECUTIVE_FRAMES frames above threshold in a row.
                if lvl > BARGE_IN_LEVEL and buf > BARGE_IN_MIN_BUFFER:
                    _above_threshold_streak += 1
                    if _above_threshold_streak >= BARGE_IN_CONSECUTIVE_FRAMES:
                        latency.on_interrupt_signal()
                        discarded = player.flush()
                        latency.on_flush_complete()
                        _above_threshold_streak = 0  # reset after firing
                        if discarded > 0:
                            logger.info(
                                "client barge-in — flushed %d audio bytes (mic level %.4f)",
                                discarded, lvl,
                            )
                            # Visual marker: shows the user WHY model audio
                            # just cut off (otherwise looks like a crash).
                            console.print(
                                f"[magenta]✂[/magenta] [dim]barge-in — {discarded}B flushed[/dim]"
                            )
                else:
                    _above_threshold_streak = 0  # any quiet frame resets streak

    async def _vu_pump() -> None:
        while not stop_event.is_set():
            try:
                live.update(_render_status(), refresh=True)
            except Exception:
                pass
            await asyncio.sleep(0.07)

    # Bug #1 fix : avoid showing partial model transcripts faster than audio playback.
    # Default = hidden (sync with audio at turn end). --show-partial re-enables streaming.
    turn_streamed = False

    async def _recv_pump() -> None:
        nonlocal end_reason, turn_streamed
        try:
            async for event in impl.receive_events():
                if stop_event.is_set():
                    return
                if event.kind == "audio_chunk_out":
                    pcm = event.data.get("pcm16", b"")
                    if pcm:
                        latency.on_model_audio_received()
                        await player.enqueue(pcm)
                elif event.kind == "partial_transcript_model":
                    text = event.data.get("text", "")
                    if text:
                        transcript_model.append(text)
                        if recap_state is not None:
                            recap_state.add_model(text)
                        if show_partial:
                            console.print(f"[green]<<<[/green] {text}", end="")
                            turn_streamed = True
                elif event.kind == "final_transcript_model":
                    text = event.data.get("text", "")
                    if text:
                        if not turn_streamed:
                            transcript_model.append(text)
                            if recap_state is not None:
                                recap_state.add_model(text)
                            console.print(f"[green]<<<[/green] {text}")
                        else:
                            console.print()  # close streamed line on its own newline
                        turn_streamed = False
                    latency.on_turn_complete()
                elif event.kind == "partial_transcript_user":
                    text = event.data.get("text", "")
                    if text:
                        transcript_user.append(text)
                        if recap_state is not None:
                            recap_state.add_user(text)
                        console.print(f"[cyan]>>>[/cyan] {text}", end="")
                        # Voice kill switch — Gemini Live only emits partial_*,
                        # never final_*. Check killchat keyword on each partial.
                        if _is_killchat_keyword(text):
                            logger.info("Voice kill switch — 'killchat' keyword matched: %r", text)
                            console.print("\n[yellow]Voice kill switch: 'killchat' détecté[/yellow]")
                            end_reason = "user_voice_killchat"
                            stop_event.set()
                elif event.kind == "final_transcript_user":
                    text = event.data.get("text", "")
                    if text and not transcript_user:
                        transcript_user.append(text)
                        if recap_state is not None:
                            recap_state.add_user(text)
                        console.print(f"[cyan]>>>[/cyan] {text}")
                    # Voice kill switch : the isolated word "killchat" stops the session.
                    if text and _is_killchat_keyword(text):
                        logger.info("Voice kill switch — 'killchat' keyword matched: %r", text)
                        console.print("[yellow]Voice kill switch: 'killchat' détecté — fin de session[/yellow]")
                        end_reason = "user_voice_killchat"
                        stop_event.set()
                elif event.kind == "model_interrupted":
                    # User broke in. Drop any audio already buffered so the model
                    # stops talking immediately rather than continuing for seconds.
                    latency.on_interrupt_signal()
                    discarded = player.flush()
                    latency.on_flush_complete()
                    logger.info("model_interrupted — flushed %d audio bytes", discarded)
                    turn_streamed = False
                elif event.kind == "error":
                    logger.error("Server error: %s", event.data)
                    console.print(f"\n[red]Server error: {event.data}[/red]")
                    end_reason = "server_error"
                    stop_event.set()
                    return
                # session_closed is per-turn end, don't stop the whole session
        except Exception as exc:
            logger.exception("recv_pump exception")
            console.print(f"\n[red]recv_pump exception: {exc!r}[/red]")
            end_reason = "recv_exception"
            stop_event.set()

    async def _cost_monitor() -> None:
        nonlocal end_reason
        while not stop_event.is_set():
            await asyncio.sleep(2.0)
            if tracker.should_warn():
                warn_msg = f"⚠ Cost warning: ${tracker.estimated_cost_usd:.2f} reached"
                logger.warning(warn_msg)
                if not clean_terminal:
                    console.print(f"\n[yellow]{warn_msg}[/yellow]")
            kill, reason = tracker.should_kill()
            if kill:
                logger.error("Kill switch fired: %s", reason)
                console.print(f"\n[red]Kill switch: {reason}[/red]")
                end_reason = f"kill_switch_{reason}"
                stop_event.set()
                return

    async def _recap_pump() -> None:
        """Periodically compact recent turns and inject as a silent note."""
        if recap_state is None:
            return
        # First check after ~half the interval so even short sessions can recap.
        # Then poll every 30s; the trigger logic inside maybe_run_recap decides.
        await asyncio.sleep(min(60.0, recap_interval / 2.0))
        while not stop_event.is_set():
            try:
                recap = await maybe_run_recap(
                    recap_state,
                    interval_seconds=recap_interval,
                    char_trigger=recap_user_chars,
                )
            except Exception as exc:
                logger.warning("recap compact failed: %r", exc)
                recap = None
            if recap:
                chars_in_recap = recap_state.user_chars_since_recap
                try:
                    await impl.send_silent_note(recap)
                    recap_state.reset()
                    logger.info(
                        "rolling recap #%d injected (%d recap chars, %d user transcript chars consumed)",
                        recap_state.recap_count,
                        len(recap),
                        chars_in_recap,
                    )
                except Exception as exc:
                    logger.warning("send_silent_note failed: %r", exc)
            await asyncio.sleep(30.0)

    mic_task = asyncio.create_task(_mic_pump())
    recv_task = asyncio.create_task(_recv_pump())
    cost_task = asyncio.create_task(_cost_monitor())
    vu_task = asyncio.create_task(_vu_pump())
    recap_task = asyncio.create_task(_recap_pump()) if recap_state is not None else None

    await stop_event.wait()

    # Farewell : ask the model to say a closing phrase BEFORE cancelling any
    # pump. mic_pump's send_audio_chunk stream keeps the websocket alive — if
    # we cancel pumps first, Gemini server can close the connection with
    # 1011 "Internal error" before our send_text trigger lands.
    #
    # Settle window: when killchat triggers stop_event mid-utterance, Gemini's
    # server is often still generating audio for whatever the user just said.
    # Sending the farewell on top of that in-flight turn produces the 1011
    # "Internal error" seen in the 23/05 sessions. 800ms pause lets the
    # current turn settle before we redirect with a fresh request.
    farewell_via_model = False
    try:
        logger.info("farewell: settle window 800ms before send_text")
        await asyncio.sleep(0.8)
        player.flush()  # cut pending model audio so farewell starts on silence
        logger.info("farewell: sending farewell text")
        await impl.send_text("Dis exactement « Fin voice realtime. » et absolument rien d'autre. Pas de commentaire, pas de question, juste cette phrase.")
        logger.info("farewell: waiting 3.5s for model audio")
        # Give the model time to generate + recv_pump time to enqueue PCM.
        await asyncio.sleep(3.5)
        farewell_via_model = player.buffered_bytes() > 0
        logger.info(
            "farewell: model path %s (buffered=%dB)",
            "OK" if farewell_via_model else "FAILED",
            player.buffered_bytes(),
        )
    except Exception as exc:
        logger.warning("Model farewell failed: %r", exc)

    # Now cancel everything
    mic_task.cancel()
    recv_task.cancel()
    cost_task.cancel()
    vu_task.cancel()
    if recap_task is not None:
        recap_task.cancel()
    pending = [mic_task, recv_task, cost_task, vu_task]
    if recap_task is not None:
        pending.append(recap_task)
    await asyncio.gather(*pending, return_exceptions=True)

    await player.drain(timeout=5.0)
    await impl.close()
    player.stop()

    if not farewell_via_model:
        # Fallback: speak via Edge TTS locally so user always gets a closing cue.
        _say_farewell_edge_tts()
    try:
        live.stop()
    except Exception:
        pass

    release_lock()
    resume_external_media(media_state)
    queued = drain_jarvis_queue()
    if queued:
        _info(f"Drained {queued} Jarvis message(s) from queue")

    # Summary + persist
    if not clean_terminal:
        console.print()
    summary_text = (
        f"Durée : {tracker.elapsed_seconds:.0f}s\n"
        f"Coût estimé : ${tracker.estimated_cost_usd:.4f}\n"
        f"User transcripts : {len(transcript_user)} chunks\n"
        f"Model transcripts : {len(transcript_model)} chunks\n"
        f"Fin : {end_reason}"
    )
    _panel(summary_text, title="Session terminée", border_style="green")

    # Save vault note FIRST so we can include its path in the NocoDB record.
    vault_note_path: str | None = None
    if save_note:
        try:
            _vault_note_path = save_session_note(
                transcript_user=transcript_user,
                transcript_model=transcript_model,
                provider=provider_name,
                model=model,
                elapsed_seconds=tracker.elapsed_seconds,
                estimated_cost_usd=tracker.estimated_cost_usd,
                project_hint=project_hint,
                end_reason=end_reason,
            )
            vault_note_path = str(_vault_note_path)
        except Exception as exc:
            logger.warning("Vault session note save failed: %r", exc)

    cost_path = tracker.persist(
        reason=end_reason,
        project_hint=project_hint,
        vault_note_path=vault_note_path,
    )
    _info(f"Cost log: {cost_path}")

    # Budget alert : ping Telegram once per month if we crossed 80% of the cap.
    try:
        from .telegram_alert import maybe_alert_budget
        cfg_for_alert = load_config()
        monthly = monthly_total_usd()
        if maybe_alert_budget(monthly, cfg_for_alert.monthly_budget_usd, threshold_pct=80.0):
            _info(f"Telegram budget alert sent ({100*monthly/cfg_for_alert.monthly_budget_usd:.0f}%)")
    except Exception as exc:
        logger.warning("Budget alert check failed (non-fatal): %r", exc)

    if save_note and vault_note_path is not None:
        try:
            note_path = vault_note_path  # already computed above
            _info(f"Vault session note: {note_path}")

            # Auto-summarize via `claude -p` Sonnet — appends synthesis to project note.
            if auto_summarize and (transcript_user or transcript_model):
                _info("Auto-summarize en cours (claude -p Sonnet)...", force=True)
                try:
                    from .summarizer import summarize_session
                    result = summarize_session(Path(note_path), project_hint=project_hint)
                    head = (
                        f"Sujet : {result.topic_summary[:80]}\n"
                        f"Décisions : {len(result.decisions)}  |  "
                        f"Actions : {len(result.actions)}  |  "
                        f"Insights : {len(result.insights)}  |  "
                        f"Questions ouvertes : {len(result.unresolved_questions)}"
                    )
                    if result.appended and result.project_note_path:
                        head += f"\nAppendé à : {result.project_note_path.name}"
                    elif project_hint:
                        head += f"\nProjet « {project_hint} » introuvable — synthèse non appendée"
                    _panel(head, title="Auto-summarize", border_style="cyan", force=True)
                except Exception as exc:
                    logger.exception("Auto-summarize failed")
                    console.print(f"[yellow]Auto-summarize failed (non-fatal): {exc!r}[/yellow]")
        except Exception as exc:
            logger.exception("Save session note failed")
            console.print(f"[red]Save session note failed: {exc!r}[/red]")


@app.command()
def stats(
    days: int = typer.Option(30, "--days", help="Window of days to report (default 30)."),
    show_sessions: int = typer.Option(10, "--show", help="N most recent sessions to list."),
) -> None:
    """Aggregate stats from local jsonl session logs.

    Local jsonl is the source of truth (cost_tracker.persist always writes
    there; NocoDB is best-effort mirror). This avoids depending on NocoDB
    being reachable to view stats.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone
    from .cost_tracker import SESSIONS_DIR

    if not SESSIONS_DIR.exists():
        console.print(f"[yellow]No sessions dir: {SESSIONS_DIR}[/yellow]")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records: list[dict] = []
    for path in sorted(SESSIONS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            started = rec.get("started_iso", "")
            if not started:
                continue
            try:
                started_dt = datetime.fromisoformat(started)
            except ValueError:
                continue
            if started_dt < cutoff:
                continue
            records.append(rec)

    if not records:
        console.print(f"[yellow]No sessions in the last {days} days.[/yellow]")
        return

    total_cost = sum(float(r.get("estimated_cost_usd", 0.0)) for r in records)
    total_seconds = sum(float(r.get("elapsed_seconds", 0.0)) for r in records)
    by_provider: dict[str, tuple[int, float, float]] = {}  # name → (count, cost, seconds)
    for r in records:
        p = r.get("provider", "?")
        c, cost, secs = by_provider.get(p, (0, 0.0, 0.0))
        by_provider[p] = (
            c + 1,
            cost + float(r.get("estimated_cost_usd", 0.0)),
            secs + float(r.get("elapsed_seconds", 0.0)),
        )

    header = f"Window : last {days} days  |  {len(records)} sessions  |  ${total_cost:.4f}  |  {total_seconds/60:.1f} min"
    console.print(Panel(header, title="voice-realtime stats", border_style="cyan"))

    # Per-provider breakdown
    breakdown_lines = []
    for prov, (c, cost, secs) in sorted(by_provider.items(), key=lambda kv: -kv[1][1]):
        breakdown_lines.append(f"  {prov:10s} : {c:3d} sessions  ${cost:.4f}  {secs/60:.1f} min")
    console.print("\n[bold]Par provider :[/bold]")
    for line in breakdown_lines:
        console.print(line)

    # Recent sessions
    console.print(f"\n[bold]{min(show_sessions, len(records))} sessions récentes :[/bold]")
    for r in sorted(records, key=lambda x: x.get("started_iso", ""), reverse=True)[:show_sessions]:
        started = r.get("started_iso", "")[:16].replace("T", " ")
        prov = r.get("provider", "?")
        secs = float(r.get("elapsed_seconds", 0.0))
        cost = float(r.get("estimated_cost_usd", 0.0))
        reason = r.get("end_reason", "?")
        console.print(f"  {started}  {prov:8s}  {secs/60:5.1f} min  ${cost:.4f}  [{reason}]")


@app.command()
def doctor() -> None:
    """End-to-end sanity check — clés API, vault, mic, NocoDB, claude CLI.

    Run this when something feels off OR on a fresh install before the
    first `talk` to catch missing pieces before they bite mid-session.
    """
    import shutil
    import subprocess as _sp
    from pathlib import Path

    ok = "[green]✓[/green]"
    fail = "[red]✗[/red]"
    warn = "[yellow]⚠[/yellow]"
    checks: list[tuple[str, str, str]] = []  # (label, status, detail)

    # 1. Secrets file + API keys
    try:
        cfg = load_config()
        if cfg.has_gemini:
            checks.append(("Gemini API key", ok, "loaded"))
        else:
            checks.append(("Gemini API key", fail, f"missing in {SECRETS_PATH}"))
        if cfg.has_openai:
            checks.append(("OpenAI API key", ok, "loaded"))
        else:
            checks.append(("OpenAI API key", warn, "missing (Gemini-only is fine)"))
        checks.append(("Monthly budget cap", ok, f"${cfg.monthly_budget_usd:.2f}/month"))
    except FileNotFoundError:
        checks.append(("Secrets file", fail, f"{SECRETS_PATH} not found"))

    # 2. Vault paths
    vault = Path.home() / "OBSIDIAN" / "2ND_CERVEAU"
    if vault.exists():
        checks.append(("Obsidian vault", ok, str(vault)))
    else:
        checks.append(("Obsidian vault", warn, f"{vault} not found — context_loader will return empty"))
    voice_sessions_dir = vault / "_System" / "voice-sessions"
    if voice_sessions_dir.exists():
        n = len(list(voice_sessions_dir.glob("*.md")))
        checks.append(("Vault voice-sessions/", ok, f"{n} notes"))
    else:
        checks.append(("Vault voice-sessions/", warn, "will be created on first session"))

    # 3. CLI dependencies
    for binary in ["claude", "edge-tts", "afplay"]:
        path = shutil.which(binary)
        checks.append((f"Binary `{binary}`", ok if path else fail, path or "not in PATH"))

    # 4. PortAudio / mic access — try to open and close a stream
    try:
        import sounddevice as _sd
        devs = _sd.query_devices()
        input_devs = [d for d in devs if d.get("max_input_channels", 0) > 0]
        if input_devs:
            checks.append(("Microphone (PortAudio)", ok, f"{len(input_devs)} input device(s)"))
        else:
            checks.append(("Microphone (PortAudio)", fail, "no input device"))
    except Exception as exc:
        checks.append(("Microphone (PortAudio)", fail, repr(exc)))

    # 5. NocoDB reachability (best-effort, opt-in)
    try:
        from .nocodb_writer import _config as _nc_config
        nc = _nc_config()
        if nc:
            url, _token, table = nc
            checks.append(("NocoDB config", ok, f"table {table[-8:]} @ {url}"))
        else:
            checks.append(("NocoDB config", warn, "env vars missing in ~/.nocodb.env (mirror disabled)"))
    except Exception as exc:
        checks.append(("NocoDB config", warn, repr(exc)))

    # 6. Sessions log directory + recent count
    from .cost_tracker import SESSIONS_DIR
    if SESSIONS_DIR.exists():
        n = len(list(SESSIONS_DIR.glob("*.jsonl")))
        checks.append(("Sessions log dir", ok, f"{n} jsonl files in {SESSIONS_DIR}"))
    else:
        checks.append(("Sessions log dir", warn, "will be created on first session"))

    # 7. Claude Code project dir (sanity for --cli-context)
    cc_root = Path.home() / ".claude" / "projects"
    if cc_root.exists():
        n = sum(1 for _ in cc_root.glob("*/*.jsonl"))
        checks.append(("Claude Code sessions", ok, f"{n} jsonl across all projects"))
    else:
        checks.append(("Claude Code sessions", warn, f"{cc_root} not found"))

    # 8. OpenCode db (sanity for --cli-context multi-source)
    opencode_db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if opencode_db.exists():
        checks.append(("OpenCode db", ok, str(opencode_db)))
    else:
        checks.append(("OpenCode db", warn, f"{opencode_db} not found — Claude Code source only"))

    # Render
    body = "\n".join(f"  {status}  {label:32s} {detail}" for label, status, detail in checks)
    fails = sum(1 for _, s, _ in checks if s == fail)
    title = "voice-realtime doctor — ALL GOOD" if fails == 0 else f"voice-realtime doctor — {fails} FAILURE(S)"
    border = "green" if fails == 0 else "red"
    console.print(Panel(body, title=title, border_style=border))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
