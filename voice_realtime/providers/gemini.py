"""Gemini Live provider — minimal text I/O for Milestone 1.

Audio I/O wiring lands in Milestone 2. This file proves the SDK + key + connect work.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from google import genai

from .base import ProviderConfig, RealtimeEvent, RealtimeVoiceProvider

DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"
# 2026-05-21 NOTE: native-audio models REQUIRE audio response modality (text-only rejected).
# gemini-3.1-flash-live-preview returns 1011 internal error 2026-05-21 (Google bug).
# Workaround: use native-audio model with AUDIO modality + output_audio_transcription
# to get text transcript of audio response for terminal print.


class GeminiProvider:
    """Minimal Gemini Live wrapper. Text-in/text-out for Milestone 1."""

    def __init__(self) -> None:
        self._client: genai.Client | None = None
        self._session: object | None = None  # Live session context manager
        self._session_cm: object | None = None
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._receiver_task: asyncio.Task[None] | None = None
        self._closed: bool = False

    async def connect(self, config: ProviderConfig, system_prompt: str) -> None:
        self._client = genai.Client(api_key=config.api_key)
        model_id = config.model or DEFAULT_MODEL
        is_native_audio = "native-audio" in model_id

        live_config: dict = {"system_instruction": system_prompt}
        if is_native_audio:
            # native-audio models REQUIRE audio response. Use audio + transcription for terminal.
            live_config["response_modalities"] = ["AUDIO"]
            live_config["speech_config"] = {
                "voice_config": {"prebuilt_voice_config": {"voice_name": config.voice or "Aoede"}}
            }
            live_config["output_audio_transcription"] = {}
        else:
            live_config["response_modalities"] = ["TEXT"]

        self._session_cm = self._client.aio.live.connect(
            model=model_id,
            config=live_config,
        )
        self._session = await self._session_cm.__aenter__()
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._session is not None
        try:
            async for response in self._session.receive():
                # Text mode: response.text
                text = getattr(response, "text", None)
                if text:
                    await self._events.put(
                        RealtimeEvent(kind="partial_transcript_model", data={"text": text})
                    )

                # Audio mode: response.server_content.output_transcription.text
                server_content = getattr(response, "server_content", None)
                if server_content is not None:
                    out_transcript = getattr(server_content, "output_transcription", None)
                    if out_transcript is not None:
                        transcript_text = getattr(out_transcript, "text", None)
                        if transcript_text:
                            await self._events.put(
                                RealtimeEvent(kind="partial_transcript_model", data={"text": transcript_text})
                            )
                    if getattr(server_content, "turn_complete", False):
                        await self._events.put(RealtimeEvent(kind="session_closed", data={"reason": "turn_complete"}))
        except Exception as exc:
            await self._events.put(RealtimeEvent(kind="error", data={"exception": repr(exc)}))

    async def send_text(self, text: str) -> None:
        assert self._session is not None
        await self._session.send_client_content(
            turns={"role": "user", "parts": [{"text": text}]},
            turn_complete=True,
        )

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
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass


_: RealtimeVoiceProvider = GeminiProvider()  # type: ignore[assignment]  # static check
