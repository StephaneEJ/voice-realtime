"""Rejeu d'un enregistrement dans le mode chaîne, sans micro ni haut-parleur.

Sert aux tests, à la commande `voice-realtime chain-rejouer` et au futur banc
d'essai N3 : l'enregistrement est poussé bloc par bloc comme un micro, les
événements sont collectés, l'audio produit est concaténé.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .base import ProviderConfig, RealtimeEvent, ToolSpec
from .chain import ChainProvider, TurnMetrics

ToolHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ReplayResult:
    events: list[RealtimeEvent] = field(default_factory=list)
    audio_out: bytes = b""
    metrics: list[TurnMetrics] = field(default_factory=list)
    # Pour chaque événement, au même rang : instant dans l'enregistrement
    # (secondes d'audio déjà poussées) et horloge monotone réelle (banc N3).
    instants: list[float] = field(default_factory=list)
    horodatages: list[float] = field(default_factory=list)

    def texts(self, kind: str) -> list[str]:
        return [e.data.get("text", "") for e in self.events if e.kind == kind]

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


async def replay(
    provider: ChainProvider,
    pcm16: bytes,
    sample_rate: int,
    *,
    system_prompt: str = "",
    tools: list[ToolSpec] | None = None,
    tool_handler: ToolHandler | None = None,
    chunk_ms: int = 100,
    realtime: bool = False,
    vad: str | None = None,
    wait_turns: bool = True,
    after_chunk: Callable[[int], Awaitable[None]] | None = None,
) -> ReplayResult:
    """Joue `pcm16` dans `provider` puis attend la fin des tours.

    `tool_handler` tient le rôle de la CLI : il reçoit (nom, arguments) et
    renvoie la charge utile rendue au modèle. `after_chunk(index)` permet aux
    tests d'injecter un geste (coupure, texte) à un instant donné.

    Hors temps réel, l'horloge de lecture devient virtuelle (elle avance d'un
    bloc à chaque envoi) et, si `wait_turns`, chaque tour est traité avant le
    bloc suivant : le rejeu est rapide et déterministe.
    """
    result = ReplayResult()
    vclock = {"t": 0.0}
    debut = time.monotonic()
    if not realtime:
        provider.clock = lambda: vclock["t"]
    await provider.connect(
        ProviderConfig(model=provider.label, api_key="", input_sample_rate=sample_rate, vad=vad),  # type: ignore[arg-type]
        system_prompt=system_prompt,
        audio=True,
        tools=tools,
    )

    async def pump() -> None:
        async for ev in provider.receive_events():
            result.events.append(ev)
            maintenant = time.monotonic()
            result.horodatages.append(maintenant)
            result.instants.append(vclock["t"] if not realtime else maintenant - debut)
            if ev.kind == "audio_chunk_out":
                result.audio_out += ev.data.get("pcm16", b"")
            elif ev.kind == "tool_call":
                payload: dict[str, Any]
                if tool_handler is None:
                    payload = {"error": "aucun outil branché pendant le rejeu"}
                else:
                    payload = await tool_handler(ev.data["name"], ev.data.get("args") or {})
                await provider.send_function_response(ev.data["call_id"], ev.data["name"], payload)

    pump_task = asyncio.create_task(pump())
    step = int(sample_rate * chunk_ms / 1000) * 2
    try:
        for idx, i in enumerate(range(0, len(pcm16), step)):
            await provider.send_audio_chunk(pcm16[i : i + step])
            if after_chunk is not None:
                await after_chunk(idx)
            if realtime:
                await asyncio.sleep(chunk_ms / 1000)
            else:
                vclock["t"] += chunk_ms / 1000
                await asyncio.sleep(0)
                if wait_turns and provider.busy:
                    await provider.wait_idle()
        await provider.end_of_audio()
        await provider.wait_idle()
    finally:
        await provider.close()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(pump_task, timeout=5)
    result.metrics = list(provider.metrics)
    return result
