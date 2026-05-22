"""voice-realtime CLI — Typer entry point.

Commands:
    voice-realtime status                  # config sanity check
    voice-realtime hello [--provider]      # M1 smoke test text I/O
    voice-realtime talk [--provider]       # M2-M4 duplex audio session with context + cost + save
"""

from __future__ import annotations

import asyncio
import signal
import sys
import warnings
from pathlib import Path

# Suppress google-genai SDK chatty warnings about non-text/non-data parts —
# these fire on every audio response when modality=AUDIO + output_audio_transcription
# is enabled. Inoffensifs but pollute the transcript display.
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*non-data parts.*")

import typer
from rich.console import Console
from rich.panel import Panel

from .config import SECRETS_PATH, load_config
from .context_loader import build_context
from .cost_tracker import CostTracker, monthly_total_usd
from .log import get_logger, setup_logging
from .providers.base import ProviderConfig
from .providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL, GEMINI_INPUT_SAMPLE_RATE, GEMINI_OUTPUT_SAMPLE_RATE, GeminiProvider
from .providers.openai_realtime import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
    OPENAI_AUDIO_SAMPLE_RATE,
    OpenAIRealtimeProvider,
)
from .session_saver import save_session_note

app = typer.Typer(
    add_completion=False,
    help="Duplex realtime voice skill. Multi-provider (Gemini Live + OpenAI Realtime-2).",
)
console = Console()


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
) -> None:
    """M2-M4: duplex audio session with context injection, cost tracking, vault save."""
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

    # Build context-injected system prompt
    base_prompt = (
        "Tu es Jarvis voice — un partenaire de brainstorming pour Stéphane Dufresne. "
        "Tu réponds en français, naturellement, comme une conversation. "
        "Tu n'es ni flatteur ni servile. Tu challenges quand c'est utile. "
        "Tu vas droit au but, sans préambule."
    )
    ctx = build_context(project_hint=project or None)
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

    # Sample rates per provider
    if provider_name == "openai":
        input_rate = OPENAI_AUDIO_SAMPLE_RATE
        output_rate = OPENAI_AUDIO_SAMPLE_RATE
        impl = OpenAIRealtimeProvider()
    else:
        input_rate = GEMINI_INPUT_SAMPLE_RATE
        output_rate = GEMINI_OUTPUT_SAMPLE_RATE
        impl = GeminiProvider()  # type: ignore[assignment]

    pcfg = ProviderConfig(model=model, api_key=api_key, thinking_level="low", voice=voice)

    if log_path is not None:
        _info(f"Log file: {log_path}")

    header_text = (
        f"Provider: {provider_name} / {model}\n"
        f"Project context: {project_hint or 'none'}\n"
        f"Mic rate: {input_rate} Hz\n"
        f"Max duration: {max_minutes:.0f} min\n"
        f"Cost cap: ${cost_cap:.2f}\n"
        f"Ctrl+C to stop."
    )
    _panel(header_text, title="voice-realtime talk", border_style="cyan")

    _info(f"Connecting to {provider_name}...")
    try:
        await impl.connect(pcfg, system_prompt=system_prompt, audio=True)
    except Exception as exc:
        logger.exception("Connect failed")
        console.print(f"[red]Connect failed: {exc!r}[/red]")
        return

    tracker = CostTracker(
        provider=provider_name,
        model=model,
        hard_stop_cost_usd=cost_cap,
        max_duration_seconds=max_minutes * 60.0,
    )

    player = AudioPlayer(rate=output_rate)
    player.start()

    transcript_user: list[str] = []
    transcript_model: list[str] = []
    stop_event = asyncio.Event()
    end_reason = "user_stop"

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

    async def _mic_pump() -> None:
        async with MicrophoneStream(rate=input_rate, chunk_ms=200) as mic:
            async for chunk in mic:
                if stop_event.is_set():
                    return
                try:
                    await impl.send_audio_chunk(chunk)
                except Exception as exc:
                    logger.exception("send_audio_chunk failed")
                    console.print(f"[red]send_audio_chunk failed: {exc!r}[/red]")
                    return

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
                        await player.enqueue(pcm)
                elif event.kind == "partial_transcript_model":
                    text = event.data.get("text", "")
                    if text:
                        transcript_model.append(text)
                        if show_partial:
                            console.print(f"[green]<<<[/green] {text}", end="")
                            turn_streamed = True
                elif event.kind == "final_transcript_model":
                    text = event.data.get("text", "")
                    if text:
                        if not turn_streamed:
                            transcript_model.append(text)
                            console.print(f"[green]<<<[/green] {text}")
                        else:
                            console.print()  # close streamed line on its own newline
                        turn_streamed = False
                elif event.kind == "partial_transcript_user":
                    text = event.data.get("text", "")
                    if text:
                        transcript_user.append(text)
                        console.print(f"[cyan]>>>[/cyan] {text}", end="")
                elif event.kind == "final_transcript_user":
                    text = event.data.get("text", "")
                    if text and not transcript_user:
                        transcript_user.append(text)
                        console.print(f"[cyan]>>>[/cyan] {text}")
                elif event.kind == "model_interrupted":
                    # User broke in. Drop any audio already buffered so the model
                    # stops talking immediately rather than continuing for seconds.
                    discarded = player.flush()
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

    mic_task = asyncio.create_task(_mic_pump())
    recv_task = asyncio.create_task(_recv_pump())
    cost_task = asyncio.create_task(_cost_monitor())

    await stop_event.wait()

    for task in (mic_task, recv_task, cost_task):
        task.cancel()
    await asyncio.gather(mic_task, recv_task, cost_task, return_exceptions=True)

    await impl.close()
    await player.drain(timeout=2.0)
    player.stop()

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
    cost_path = tracker.persist(reason=end_reason)
    _info(f"Cost log: {cost_path}")

    if save_note:
        try:
            note_path = save_session_note(
                transcript_user=transcript_user,
                transcript_model=transcript_model,
                provider=provider_name,
                model=model,
                elapsed_seconds=tracker.elapsed_seconds,
                estimated_cost_usd=tracker.estimated_cost_usd,
                project_hint=project_hint,
                end_reason=end_reason,
            )
            _info(f"Vault session note: {note_path}")
        except Exception as exc:
            logger.exception("Save session note failed")
            console.print(f"[red]Save session note failed: {exc!r}[/red]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
