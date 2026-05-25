"""Local provider stub — whisper.cpp + Ollama + Piper pipeline.

This is a SKELETON that implements the RealtimeVoiceProvider protocol but
each external binding raises NotImplementedError. The goal of this file
is to lock in the architecture so that Phase 3 implementation only needs
to fill in the three subprocess managers (whisper.cpp server, Ollama
generate, Piper synthesizer) — no protocol redesign required.

Architecture target
===================

Three concurrent processes form a pseudo-realtime duplex:

    mic PCM16 (16kHz) ──► whisper.cpp /inference  ──► partial transcripts
                                                      │
                                                      ▼
                                            ChatBuffer (rolling)
                                                      │
                                                      ▼
                                          Ollama /api/generate (streaming)
                                                      │
                                                      ▼
                                          tokens ─► Piper TTS ─► PCM16 24kHz playback

Why three separate processes (not one unified runtime):
- whisper.cpp is the only Mac-native streaming STT that runs well on M-series
  CPU (no GPU dep). server mode at port 8081 by default.
- Ollama owns model lifecycle (loaded model stays in RAM) + clean HTTP API.
  Use a small model (qwen2.5:3b or llama3.2:3b) to stay under 5 GB RAM and
  > 30 tok/s on M-series.
- Piper provides natural French voices (`fr_FR-siwis-medium`) at ~50 ms
  per chunk on CPU. Streaming tokens → Piper input via stdin pipe.

Latency target: time-to-first-audio < 1.5 s on M2 Pro. Worse than cloud
realtime providers, but $0/h and offline.

Implementation phases (not in this file)
========================================

3.1.a — whisper.cpp server wrapper (start, stream PCM16, parse partials)
3.1.b — Ollama HTTP streaming client + token buffering
3.1.c — Piper subprocess with stdin streaming + chunked audio out
3.1.d — Wire all three under RealtimeVoiceProvider; preserve the event
        kinds the cli.py recv_pump already handles (no client changes)

Until 3.1.d ships, this file just allows `import voice_realtime.providers.local`
to succeed for type-checking and dependency-injection wiring elsewhere.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import AsyncIterator

from .base import ProviderConfig, RealtimeEvent, RealtimeVoiceProvider, ToolSpec


# Default binary lookups — overridable via ProviderConfig.api_key
# (we reuse api_key as a JSON config blob for local; not pretty but
#  avoids adding fields to base.py before we know the real shape).
DEFAULT_WHISPER_CPP_PATH = "whisper-cli"   # ships in homebrew whisper-cpp
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_PIPER_PATH = "piper"               # homebrew piper
DEFAULT_PIPER_VOICE = "fr_FR-siwis-medium"


@dataclass
class LocalProviderDeps:
    """Resolved paths + endpoints for the three subprocess components."""

    whisper_cli: str = DEFAULT_WHISPER_CPP_PATH
    ollama_host: str = DEFAULT_OLLAMA_HOST
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    piper_cli: str = DEFAULT_PIPER_PATH
    piper_voice: str = DEFAULT_PIPER_VOICE

    def all_present(self) -> tuple[bool, list[str]]:
        """Return (ok, missing_names) for a startup-time check."""
        missing: list[str] = []
        if not shutil.which(self.whisper_cli):
            missing.append(self.whisper_cli)
        if not shutil.which(self.piper_cli):
            missing.append(self.piper_cli)
        # Ollama is checked by hitting the HTTP endpoint at connect()
        return (not missing, missing)


class LocalProvider(RealtimeVoiceProvider):
    """Stub for whisper.cpp + Ollama + Piper local pipeline.

    Currently raises NotImplementedError on every call. Wired into the
    provider registry so a future flag `--provider local` can pick it up
    after Phase 3.1 lands.
    """

    name = "local"

    def __init__(self, deps: LocalProviderDeps | None = None) -> None:
        self._deps = deps or LocalProviderDeps()
        self._closed = False
        # Future: process handles for the three subprocesses
        self._whisper_proc: asyncio.subprocess.Process | None = None
        self._piper_proc: asyncio.subprocess.Process | None = None
        # Future: queues for event fan-out
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=512)

    async def connect(
        self,
        config: ProviderConfig,
        system_prompt: str,
        tools: list[ToolSpec] | None = None,
    ) -> None:
        ok, missing = self._deps.all_present()
        if not ok:
            raise NotImplementedError(
                f"LocalProvider stub — missing binaries: {missing}. "
                "Install via: brew install whisper-cpp ollama piper. "
                "Then a Phase 3.1 implementation must replace this NotImplementedError."
            )
        raise NotImplementedError(
            "LocalProvider.connect — Phase 3.1.a (whisper.cpp server) not yet implemented."
        )

    async def send_text(self, text: str) -> None:
        raise NotImplementedError("LocalProvider.send_text — Phase 3.1.b")

    async def send_function_response(self, call_id: str, name: str, response: dict) -> None:
        # Local Ollama loop has no realtime function-calling protocol; tools
        # would be implemented as a post-generation parse step. Stub no-op so
        # the CLI dispatch path doesn't crash if tools fire during local mode.
        raise NotImplementedError("LocalProvider.send_function_response — Phase 3.1.b")

    async def send_silent_note(self, text: str) -> None:
        # Local model has no API-level system message during streaming;
        # implementation will fold the recap into the conversation buffer
        # directly (prepend before next user turn).
        raise NotImplementedError("LocalProvider.send_silent_note — Phase 3.1.b")

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        raise NotImplementedError("LocalProvider.send_audio_chunk — Phase 3.1.a")

    def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        raise NotImplementedError("LocalProvider.receive_events — Phase 3.1.d")

    async def close(self) -> None:
        self._closed = True
        # Future: terminate whisper + piper subprocesses
