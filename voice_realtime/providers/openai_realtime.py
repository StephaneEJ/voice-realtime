"""OpenAI Realtime provider — minimal text I/O for Milestone 1.

Uses `AsyncOpenAI.realtime.connect()` async context manager.
Audio I/O wiring lands in Milestone 2.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

from openai import AsyncOpenAI

_DEBUG = os.environ.get("VOICE_REALTIME_DEBUG") == "1"

from .base import ProviderConfig, RealtimeEvent

DEFAULT_MODEL = "gpt-realtime-2"
# 2026-05-21 NOTE: gpt-realtime-2 confirmed available via client.models.list().
# Alternatives: gpt-realtime (latest alias), gpt-realtime-mini (cheaper), gpt-realtime-1.5 (legacy).


class OpenAIRealtimeProvider:
    """Minimal OpenAI Realtime wrapper. Text-in/text-out for Milestone 1."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._conn = None  # type: ignore[assignment]  # AsyncRealtimeConnection
        self._conn_cm = None
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._receiver_task: asyncio.Task[None] | None = None
        self._closed: bool = False

    async def connect(self, config: ProviderConfig, system_prompt: str) -> None:
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._conn_cm = self._client.realtime.connect(model=config.model or DEFAULT_MODEL)
        self._conn = await self._conn_cm.__aenter__()

        # Configure session — text-only output, system instructions.
        # Realtime-2 API: `output_modalities` replaces older `modalities`.
        await self._conn.session.update(
            session={
                "type": "realtime",
                "output_modalities": ["text"],
                "instructions": system_prompt,
            }
        )

        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._conn is not None
        try:
            async for event in self._conn:
                etype = getattr(event, "type", "")
                if _DEBUG:
                    print(f"[debug openai event] {etype}", flush=True)
                # Realtime-2 event names — output_text.* replace older text.*
                if etype in ("response.text.delta", "response.output_text.delta"):
                    delta = getattr(event, "delta", "")
                    await self._events.put(
                        RealtimeEvent(kind="partial_transcript_model", data={"text": delta})
                    )
                elif etype in ("response.text.done", "response.output_text.done"):
                    text = getattr(event, "text", "")
                    await self._events.put(
                        RealtimeEvent(kind="final_transcript_model", data={"text": text})
                    )
                elif etype == "response.done":
                    await self._events.put(RealtimeEvent(kind="session_closed", data={"reason": "response_done"}))
                elif etype == "error":
                    err = getattr(event, "error", None)
                    await self._events.put(RealtimeEvent(kind="error", data={"error": repr(err)}))
        except Exception as exc:
            await self._events.put(RealtimeEvent(kind="error", data={"exception": repr(exc)}))

    async def send_text(self, text: str) -> None:
        assert self._conn is not None
        await self._conn.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
        )
        await self._conn.response.create()

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        raise NotImplementedError("Audio I/O lands in Milestone 2")

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        while not self._closed:
            event = await self._events.get()
            yield event
            if event.kind == "session_closed":
                return

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receiver_task is not None:
            self._receiver_task.cancel()
        if self._conn_cm is not None:
            try:
                await self._conn_cm.__aexit__(None, None, None)
            except Exception:
                pass
