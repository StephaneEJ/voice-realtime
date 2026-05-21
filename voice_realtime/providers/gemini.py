"""Gemini Live provider — minimal text I/O for Milestone 1.

Audio I/O wiring lands in Milestone 2. This file proves the SDK + key + connect work.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncIterator

from google import genai

from .base import ProviderConfig, RealtimeEvent, RealtimeVoiceProvider

_DEBUG = os.environ.get("VOICE_REALTIME_DEBUG") == "1"


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[gemini debug] {msg}", file=sys.stderr, flush=True)

DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"
# 2026-05-21 NOTE: native-audio models REQUIRE audio response modality (text-only rejected).
# gemini-3.1-flash-live-preview returns 1011 internal error 2026-05-21 (Google bug).
# Workaround: use native-audio model with AUDIO modality + output_audio_transcription
# to get text transcript of audio response for terminal print.

GEMINI_INPUT_SAMPLE_RATE = 16000   # Gemini Live expects 16kHz input
GEMINI_OUTPUT_SAMPLE_RATE = 24000  # outputs 24kHz


class GeminiProvider:
    """Gemini Live wrapper with transparent multi-turn reconnect.

    The native-audio model closes session.receive() iterator after each model turn.
    We re-open a session in a loop to keep the conversation alive.
    """

    def __init__(self) -> None:
        self._client: genai.Client | None = None
        self._session = None  # type: ignore[assignment]  # current AsyncSession
        self._session_cm = None
        self._session_lock: asyncio.Lock = asyncio.Lock()
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._receiver_task: asyncio.Task[None] | None = None
        self._closed: bool = False
        # Persisted across reconnects
        self._provider_config: ProviderConfig | None = None
        self._system_prompt: str = ""
        self._audio_mode: bool = False
        self._model_id: str = ""
        self._reconnect_count: int = 0

    def _build_live_config(self) -> dict:
        is_native_audio = "native-audio" in self._model_id
        live_config: dict = {
            "system_instruction": self._system_prompt,
            "context_window_compression": {"sliding_window": {}},
            "session_resumption": {},
        }
        if is_native_audio or self._audio_mode:
            live_config["response_modalities"] = ["AUDIO"]
            live_config["speech_config"] = {
                "voice_config": {"prebuilt_voice_config": {"voice_name": (self._provider_config.voice if self._provider_config else None) or "Aoede"}}
            }
            live_config["output_audio_transcription"] = {}
            if self._audio_mode:
                live_config["input_audio_transcription"] = {}
        else:
            live_config["response_modalities"] = ["TEXT"]
        return live_config

    async def _open_session(self) -> None:
        assert self._client is not None
        async with self._session_lock:
            self._session_cm = self._client.aio.live.connect(
                model=self._model_id,
                config=self._build_live_config(),
            )
            self._session = await self._session_cm.__aenter__()
            _dbg(f"opened session #{self._reconnect_count + 1} model={self._model_id}")

    async def _close_session(self) -> None:
        async with self._session_lock:
            if self._session_cm is not None:
                try:
                    await self._session_cm.__aexit__(None, None, None)
                except Exception as exc:
                    _dbg(f"session __aexit__ failed: {exc!r}")
            self._session_cm = None
            self._session = None

    async def connect(self, config: ProviderConfig, system_prompt: str, audio: bool = False) -> None:
        self._client = genai.Client(api_key=config.api_key)
        self._provider_config = config
        self._system_prompt = system_prompt
        self._audio_mode = audio
        self._model_id = config.model or DEFAULT_MODEL
        await self._open_session()
        self._receiver_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Outer loop: keep reading from session. When session ends, reconnect."""
        total_chunks = 0
        while not self._closed:
            chunks_this_session = await self._receive_one_session()
            total_chunks += chunks_this_session
            if self._closed:
                break
            self._reconnect_count += 1
            _dbg(f"session ended after {chunks_this_session} chunks, reconnecting (total reconnects={self._reconnect_count})")
            await self._close_session()
            try:
                await self._open_session()
            except Exception as exc:
                _dbg(f"reconnect failed: {exc!r}")
                await self._events.put(RealtimeEvent(kind="error", data={"exception": repr(exc)}))
                return
            await asyncio.sleep(0.05)  # brief breath between sessions
        _dbg(f"reconnect_loop EXIT — total chunks: {total_chunks}, reconnects: {self._reconnect_count}")

    async def _receive_one_session(self) -> int:
        """Read events from current session until it closes. Returns chunk count."""
        assert self._session is not None
        chunk_count = 0
        try:
            async for response in self._session.receive():
                # 1. Audio bytes direct via response.data (Gemini Live convention for AUDIO modality)
                audio_data = getattr(response, "data", None)
                if audio_data:
                    chunk_count += 1
                    _dbg(f"audio chunk #{chunk_count} size={len(audio_data)}B")
                    await self._events.put(
                        RealtimeEvent(kind="audio_chunk_out", data={"pcm16": audio_data})
                    )

                # 2. Text accumulated from text parts (only if text mode or transcript)
                text = getattr(response, "text", None)
                if text:
                    await self._events.put(
                        RealtimeEvent(kind="partial_transcript_model", data={"text": text})
                    )

                # 3. server_content contains transcriptions + model_turn structured data.
                # Skip model_turn.parts[*].inline_data — it duplicates response.data (already emitted above).
                server_content = getattr(response, "server_content", None)
                if server_content is not None:
                    # Text transcript parallel to audio (output_audio_transcription)
                    out_transcript = getattr(server_content, "output_transcription", None)
                    if out_transcript is not None:
                        transcript_text = getattr(out_transcript, "text", None)
                        if transcript_text:
                            await self._events.put(
                                RealtimeEvent(kind="partial_transcript_model", data={"text": transcript_text})
                            )
                    # User input transcription (when input_audio_transcription enabled)
                    in_transcript = getattr(server_content, "input_transcription", None)
                    if in_transcript is not None:
                        in_text = getattr(in_transcript, "text", None)
                        if in_text:
                            await self._events.put(
                                RealtimeEvent(kind="partial_transcript_user", data={"text": in_text})
                            )
                    if getattr(server_content, "turn_complete", False):
                        await self._events.put(RealtimeEvent(kind="session_closed", data={"reason": "turn_complete"}))
        except Exception as exc:
            _dbg(f"_receive_one_session EXCEPTION after {chunk_count} chunks: {exc!r}")
            # Don't put error event — reconnect_loop will try to recover
        return chunk_count

    async def send_text(self, text: str) -> None:
        async with self._session_lock:
            session = self._session
        if session is None:
            raise RuntimeError("Gemini session not active")
        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": text}]},
            turn_complete=True,
        )

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        # If we're mid-reconnect, session is None — drop chunk silently.
        async with self._session_lock:
            session = self._session
        if session is None:
            return
        try:
            await session.send_realtime_input(
                audio={"data": pcm16, "mime_type": f"audio/pcm;rate={GEMINI_INPUT_SAMPLE_RATE}"}
            )
        except Exception as exc:
            _dbg(f"send_audio_chunk exception (continuing, reconnect loop will recover): {exc!r}")
            # Don't raise — let mic_pump continue. Reconnect loop will heal.

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        # Generator continues until provider is closed by caller.
        # session_closed events (turn_complete) are yielded but DO NOT end the iterator —
        # turn_complete is per-turn, not session-end. Caller decides when to stop.
        while not self._closed:
            event = await self._events.get()
            yield event

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receiver_task is not None:
            self._receiver_task.cancel()
        await self._close_session()


_: RealtimeVoiceProvider = GeminiProvider()  # type: ignore[assignment]  # static check
