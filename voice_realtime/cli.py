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

import typer
from rich.console import Console
from rich.panel import Panel

from .config import SECRETS_PATH, load_config
from .context_loader import build_context
from .cost_tracker import CostTracker, monthly_total_usd
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
    project: str = typer.Option("", "--project", help="Inject project context from vault (partial name match)."),
    max_minutes: float = typer.Option(15.0, "--max-minutes", help="Hard duration cap (kill switch)."),
    cost_cap: float = typer.Option(3.0, "--cost-cap", help="Hard cost cap USD (kill switch)."),
    no_save: bool = typer.Option(False, "--no-save", help="Skip saving session note to vault."),
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
) -> None:
    # Lazy import audio to avoid PortAudio errors at module load
    from .audio.microphone import MicrophoneStream
    from .audio.playback import AudioPlayer

    # Sample rates per provider
    if provider_name == "openai":
        input_rate = OPENAI_AUDIO_SAMPLE_RATE
        output_rate = OPENAI_AUDIO_SAMPLE_RATE
        impl = OpenAIRealtimeProvider()
    else:
        input_rate = GEMINI_INPUT_SAMPLE_RATE
        output_rate = GEMINI_OUTPUT_SAMPLE_RATE
        impl = GeminiProvider()  # type: ignore[assignment]

    pcfg = ProviderConfig(model=model, api_key=api_key, thinking_level="low")

    console.print(
        Panel(
            f"[cyan]Provider:[/cyan] {provider_name} / {model}\n"
            f"[cyan]Project context:[/cyan] {project_hint or 'none'}\n"
            f"[cyan]Mic rate:[/cyan] {input_rate} Hz\n"
            f"[cyan]Max duration:[/cyan] {max_minutes:.0f} min\n"
            f"[cyan]Cost cap:[/cyan] ${cost_cap:.2f}\n"
            f"[dim]Ctrl+C to stop.[/dim]",
            title="voice-realtime talk",
            border_style="cyan",
        )
    )

    console.print(f"[dim]Connecting to {provider_name}...[/dim]")
    try:
        await impl.connect(pcfg, system_prompt=system_prompt, audio=True)
    except Exception as exc:
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
                    console.print(f"[red]send_audio_chunk failed: {exc!r}[/red]")
                    return

    async def _recv_pump() -> None:
        nonlocal end_reason
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
                        console.print(f"[green]<<<[/green] {text}", end="")
                elif event.kind == "final_transcript_model":
                    text = event.data.get("text", "")
                    if text and not transcript_model:
                        transcript_model.append(text)
                        console.print(f"[green]<<<[/green] {text}")
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
                elif event.kind == "error":
                    console.print(f"\n[red]Server error: {event.data}[/red]")
                    end_reason = "server_error"
                    stop_event.set()
                    return
                # session_closed is per-turn end, don't stop the whole session
        except Exception as exc:
            console.print(f"\n[red]recv_pump exception: {exc!r}[/red]")
            end_reason = "recv_exception"
            stop_event.set()

    async def _cost_monitor() -> None:
        nonlocal end_reason
        while not stop_event.is_set():
            await asyncio.sleep(2.0)
            if tracker.should_warn():
                console.print(
                    f"\n[yellow]⚠ Cost warning: ${tracker.estimated_cost_usd:.2f} reached[/yellow]"
                )
            kill, reason = tracker.should_kill()
            if kill:
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
    console.print()
    console.print(
        Panel(
            f"Durée : {tracker.elapsed_seconds:.0f}s\n"
            f"Coût estimé : ${tracker.estimated_cost_usd:.4f}\n"
            f"User transcripts : {len(transcript_user)} chunks\n"
            f"Model transcripts : {len(transcript_model)} chunks\n"
            f"Fin : {end_reason}",
            title="Session terminée",
            border_style="green",
        )
    )
    cost_path = tracker.persist(reason=end_reason)
    console.print(f"[dim]Cost log: {cost_path}[/dim]")

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
            console.print(f"[dim]Vault session note: {note_path}[/dim]")
        except Exception as exc:
            console.print(f"[red]Save session note failed: {exc!r}[/red]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
