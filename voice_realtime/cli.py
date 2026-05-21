"""voice-realtime CLI — Typer entry point.

Milestone 1 commands:
    voice-realtime hello       # smoke test Gemini Live text I/O
    voice-realtime status      # show config sanity (no network)
"""

from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console
from rich.panel import Panel

from .config import SECRETS_PATH, load_config
from .providers.base import ProviderConfig
from .providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL, GeminiProvider
from .providers.openai_realtime import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
    OpenAIRealtimeProvider,
)

app = typer.Typer(
    add_completion=False,
    help="Duplex realtime voice skill. Multi-provider (Gemini Live primary, OpenAI Realtime-2 secondary).",
)
console = Console()


@app.command()
def status() -> None:
    """Show config status — no network calls."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    lines = [
        f"Secrets file : {SECRETS_PATH}",
        f"OpenAI key   : {'present' if cfg.has_openai else 'MISSING'}",
        f"Gemini key   : {'present' if cfg.has_gemini else 'MISSING'}",
        f"Budget cap   : ${cfg.monthly_budget_usd:.2f}/month",
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
    provider: str = typer.Option(
        "openai",
        "--provider",
        "-p",
        help="Provider: openai | gemini",
    ),
    model: str = typer.Option(
        "",
        "--model",
        help="Model identifier. Defaults: openai=gpt-realtime-2, gemini=gemini-3.1-flash-live-preview.",
    ),
) -> None:
    """Smoke test: connect realtime provider, send text, print response, close."""
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if provider == "openai":
        if not cfg.has_openai:
            console.print("[red]OPENAI_API_KEY missing in ~/.claude/voice-realtime.env[/red]")
            raise typer.Exit(1)
        chosen_model = model or OPENAI_DEFAULT_MODEL
        asyncio.run(_run_hello("openai", cfg.openai_api_key, chosen_model, message))  # type: ignore[arg-type]
    elif provider == "gemini":
        if not cfg.has_gemini:
            console.print("[red]GEMINI_API_KEY missing in ~/.claude/voice-realtime.env[/red]")
            raise typer.Exit(1)
        chosen_model = model or GEMINI_DEFAULT_MODEL
        asyncio.run(_run_hello("gemini", cfg.gemini_api_key, chosen_model, message))  # type: ignore[arg-type]
    else:
        console.print(f"[red]Unknown provider: {provider}. Use openai|gemini.[/red]")
        raise typer.Exit(1)


async def _run_hello(provider_name: str, api_key: str, model: str, message: str) -> None:
    if provider_name == "openai":
        impl = OpenAIRealtimeProvider()
    else:
        impl = GeminiProvider()  # type: ignore[assignment]

    pcfg = ProviderConfig(
        model=model,
        api_key=api_key,
        thinking_level="low",
    )
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
                # If we got partials, full text already streamed. If not, print final.
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
        console.print()  # newline

    if not response_chunks:
        console.print("[yellow]No response received.[/yellow]")
        sys.exit(3)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
