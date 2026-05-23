"""OpenAI Realtime provider — minimal text I/O for Milestone 1.

Uses `AsyncOpenAI.realtime.connect()` async context manager.
Audio I/O wiring lands in Milestone 2.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import base64

from openai import AsyncOpenAI

from ..log import get_logger

logger = get_logger("voice_realtime.openai")
OPENAI_AUDIO_SAMPLE_RATE = 24000

from .base import ProviderConfig, RealtimeEvent

DEFAULT_MODEL = "gpt-realtime-2"
# 2026-05-21 NOTE: gpt-realtime-2 confirmed available via client.models.list().
# Alternatives: gpt-realtime (latest alias), gpt-realtime-mini (cheaper), gpt-realtime-1.5 (legacy).


class OpenAIRealtimeProvider:
    """OpenAI Realtime wrapper. Supports text-only OR audio I/O depending on `audio` arg."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._conn = None  # type: ignore[assignment]  # AsyncRealtimeConnection
        self._conn_cm = None
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._receiver_task: asyncio.Task[None] | None = None
        self._closed: bool = False
        self._audio_mode: bool = False

    async def connect(self, config: ProviderConfig, system_prompt: str, audio: bool = False) -> None:
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._conn_cm = self._client.realtime.connect(model=config.model or DEFAULT_MODEL)
        self._conn = await self._conn_cm.__aenter__()
        self._audio_mode = audio

        # Realtime-2 API: `output_modalities` replaces older `modalities`.
        session_payload: dict = {
            "type": "realtime",
            "output_modalities": ["audio"] if audio else ["text"],
            "instructions": system_prompt,
        }
        if audio:
            session_payload["audio"] = {
                "input": {
                    "format": {"type": "audio/pcm", "rate": OPENAI_AUDIO_SAMPLE_RATE},
                    # Defaults (threshold=0.5, silence_duration=200ms) were too sensitive:
                    # 2026-05-23 test session = 32 speech_started in 59s, one every 1.8s.
                    # Each false-trigger ran our model_interrupted handler → player.flush()
                    # cut the model's audio mid-sentence before the user could hear it.
                    # Threshold 0.75 + 600ms silence requires a deliberate utterance, not
                    # ambient breathing.
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.75,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 600,
                    },
                    # Enable Whisper-based STT of user audio for terminal transcript
                    "transcription": {"model": "whisper-1"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": OPENAI_AUDIO_SAMPLE_RATE},
                    "voice": config.voice or "alloy",
                },
            }
        await self._conn.session.update(session=session_payload)

        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._conn is not None
        try:
            async for event in self._conn:
                etype = getattr(event, "type", "")
                logger.debug(f"event: {etype}")
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
                elif etype == "response.output_audio.delta":
                    # base64-encoded PCM16 chunk
                    delta_b64 = getattr(event, "delta", "")
                    if delta_b64:
                        pcm16 = base64.b64decode(delta_b64)
                        await self._events.put(
                            RealtimeEvent(kind="audio_chunk_out", data={"pcm16": pcm16})
                        )
                elif etype == "response.output_audio_transcript.delta":
                    # Transcript of audio output (parallel to audio chunks)
                    delta = getattr(event, "delta", "")
                    if delta:
                        await self._events.put(
                            RealtimeEvent(kind="partial_transcript_model", data={"text": delta})
                        )
                elif etype == "conversation.item.input_audio_transcription.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        await self._events.put(
                            RealtimeEvent(kind="partial_transcript_user", data={"text": delta})
                        )
                elif etype == "conversation.item.input_audio_transcription.completed":
                    transcript = getattr(event, "transcript", "")
                    if transcript:
                        await self._events.put(
                            RealtimeEvent(kind="final_transcript_user", data={"text": transcript})
                        )
                elif etype == "input_audio_buffer.speech_started":
                    # Server VAD detected user speech. If a model response was in flight,
                    # the server truncates it — client must flush the audio buffer too,
                    # otherwise the already-received PCM chunks keep playing for several
                    # seconds. Always emit (no-op when no audio is buffered).
                    logger.debug("speech_started — emit model_interrupted")
                    await self._events.put(RealtimeEvent(kind="model_interrupted", data={}))
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

    async def send_silent_note(self, text: str) -> None:
        """Inject a system-role item into the conversation WITHOUT triggering
        a response. OpenAI Realtime accepts role=system messages that the model
        treats as instructions/context. Skipping response.create() means no
        audio is generated — the recap lands in the conversation buffer and
        is consumed at the next user turn.
        """
        if self._conn is None:
            return
        try:
            await self._conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": text}],
                }
            )
        except Exception:
            pass

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        assert self._conn is not None
        audio_b64 = base64.b64encode(pcm16).decode("ascii")
        await self._conn.input_audio_buffer.append(audio=audio_b64)

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        # Generator continues until provider is closed by caller.
        # session_closed events (response.done) are yielded but DO NOT end the iterator —
        # response.done is per-turn, not session-end. Caller decides when to stop.
        while not self._closed:
            event = await self._events.get()
            yield event

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
