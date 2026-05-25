"""Gemini Live provider — minimal text I/O for Milestone 1.

Audio I/O wiring lands in Milestone 2. This file proves the SDK + key + connect work.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from google import genai

from ..log import get_logger
from .base import ProviderConfig, RealtimeEvent, RealtimeVoiceProvider, ToolSpec

logger = get_logger("voice_realtime.gemini")


def _dbg(msg: str) -> None:
    logger.debug(msg)

DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"
# 2026-05-21 NOTE: native-audio models REQUIRE audio response modality (text-only rejected).
# gemini-3.1-flash-live-preview returns 1011 internal error 2026-05-21 (Google bug).
# Workaround: use native-audio model with AUDIO modality + output_audio_transcription
# to get text transcript of audio response for terminal print.

GEMINI_INPUT_SAMPLE_RATE = 16000   # Gemini Live expects 16kHz input
GEMINI_OUTPUT_SAMPLE_RATE = 24000  # outputs 24kHz

# VAD presets — how aggressively the server interrupts the model when it
# detects user speech. Stéphane complained 2026-05-24 that the model stopped
# speaking at the slightest ambient noise (construction sounds outside).
# Picking "patient" or "very-patient" makes the server require a clearer,
# longer utterance before interrupting.
#
# Field semantics (Gemini Live realtime_input_config.automatic_activity_detection):
# - start_of_speech_sensitivity: how easily the server flags speech START
#   (HIGH = trigger on small sounds, LOW = need clear utterance)
# - end_of_speech_sensitivity: how aggressively the server flags speech END
#   (HIGH = ends fast on pause, LOW = waits longer through pauses)
# - silence_duration_ms: how long of a silence terminates a user turn
GEMINI_VAD_PRESETS: dict[str, dict] = {
    "reactive":     {"start": "START_SENSITIVITY_HIGH", "end": "END_SENSITIVITY_HIGH", "silence_duration_ms": 400},
    "balanced":     {"start": "START_SENSITIVITY_HIGH", "end": "END_SENSITIVITY_LOW",  "silence_duration_ms": 700},
    "patient":      {"start": "START_SENSITIVITY_LOW",  "end": "END_SENSITIVITY_LOW",  "silence_duration_ms": 1200},
    "very-patient": {"start": "START_SENSITIVITY_LOW",  "end": "END_SENSITIVITY_LOW",  "silence_duration_ms": 2000},
}
GEMINI_VAD_DEFAULT = "balanced"


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
        self._tools: list[ToolSpec] = []

    def _build_live_config(self) -> dict:
        is_native_audio = "native-audio" in self._model_id
        live_config: dict = {
            "system_instruction": self._system_prompt,
            "context_window_compression": {"sliding_window": {}},
            "session_resumption": {},
        }
        if self._tools:
            # Gemini Live wraps function declarations in a single tools list.
            # `parameters` is JSON-Schema; passed verbatim (Gemini accepts it).
            live_config["tools"] = [{
                "function_declarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in self._tools
                ]
            }]
            _dbg(f"tools wired count={len(self._tools)} names={[t.name for t in self._tools]}")
        if is_native_audio or self._audio_mode:
            live_config["response_modalities"] = ["AUDIO"]
            live_config["speech_config"] = {
                "voice_config": {"prebuilt_voice_config": {"voice_name": (self._provider_config.voice if self._provider_config else None) or "Charon"}}
            }
            live_config["output_audio_transcription"] = {}
            if self._audio_mode:
                live_config["input_audio_transcription"] = {}
                vad_name = (self._provider_config.vad if self._provider_config else None) or GEMINI_VAD_DEFAULT
                vad = GEMINI_VAD_PRESETS.get(vad_name, GEMINI_VAD_PRESETS[GEMINI_VAD_DEFAULT])
                live_config["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "disabled": False,
                        "start_of_speech_sensitivity": vad["start"],
                        "end_of_speech_sensitivity": vad["end"],
                        "silence_duration_ms": vad["silence_duration_ms"],
                    }
                }
                _dbg(f"VAD preset='{vad_name}' silence_duration_ms={vad['silence_duration_ms']} start={vad['start']} end={vad['end']}")
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

    async def connect(
        self,
        config: ProviderConfig,
        system_prompt: str,
        audio: bool = False,
        tools: list[ToolSpec] | None = None,
    ) -> None:
        self._client = genai.Client(api_key=config.api_key)
        self._provider_config = config
        self._system_prompt = system_prompt
        self._audio_mode = audio
        self._model_id = config.model or DEFAULT_MODEL
        self._tools = list(tools or [])
        await self._open_session()
        self._receiver_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Outer loop: re-iterate session.receive() on premature turn_complete.
        Only reconnect when the WebSocket is actually dead (ConnectionClosed).

        Workaround for bug googleapis/python-genai#2117 — native-audio model
        sends turnComplete prematurely after 1-3 sentences (often mid-word),
        and the async for iterator exits even though WebSocket is still alive.
        """
        total_chunks = 0
        turns_reentered = 0
        while not self._closed:
            chunks_this_session, conn_dead = await self._receive_one_session()
            total_chunks += chunks_this_session
            if self._closed:
                break
            if conn_dead:
                # Real disconnect — full reconnect needed
                self._reconnect_count += 1
                _dbg(f"connection died after {chunks_this_session} chunks, full reconnect (count={self._reconnect_count})")
                await self._close_session()
                try:
                    await self._open_session()
                except Exception as exc:
                    _dbg(f"reconnect failed: {exc!r}")
                    await self._events.put(RealtimeEvent(kind="error", data={"exception": repr(exc)}))
                    return
                await asyncio.sleep(0.05)
            else:
                # Iterator exited normally (bug #2117 turnComplete premature).
                # WebSocket still alive — just re-iterate same session, no overhead.
                turns_reentered += 1
                _dbg(f"iterator exited after {chunks_this_session} chunks, re-entering session.receive() (turns_reentered={turns_reentered})")
                await asyncio.sleep(0)
        _dbg(f"reconnect_loop EXIT — total chunks: {total_chunks}, full reconnects: {self._reconnect_count}, soft re-enters: {turns_reentered}")

    async def _receive_one_session(self) -> tuple[int, bool]:
        """Read events from current session until iterator exits.

        Returns (chunk_count, connection_dead). connection_dead=True means
        WebSocket actually closed (need full reconnect). False means iterator
        exited but conn alive (just re-iterate, bug #2117 workaround).
        """
        assert self._session is not None
        # Accumulate model transcript across partials within one turn so we can
        # emit a single final_transcript_model on turn_complete. Without this,
        # clean-terminal mode + Gemini (which never emits final_*) leaves the
        # user staring at a silent terminal even though the model is speaking.
        model_text_buffer = ""
        chunk_count = 0
        conn_dead = False
        try:
            async for response in self._session.receive():
                # 0. Usage metadata (cumulative session totals on LiveServerMessage).
                # When present, replace the running real-tokens totals on the
                # CostTracker via a cost_update event consumed by the CLI.
                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    tokens_in = (
                        getattr(usage, "prompt_token_count", None)
                        or getattr(usage, "input_token_count", None)
                        or 0
                    )
                    tokens_out = (
                        getattr(usage, "response_token_count", None)
                        or getattr(usage, "output_token_count", None)
                        or 0
                    )
                    if tokens_in or tokens_out:
                        await self._events.put(RealtimeEvent(
                            kind="cost_update",
                            data={
                                "tokens_in": int(tokens_in),
                                "tokens_out": int(tokens_out),
                                "mode": "cumulative",
                            },
                        ))

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

                # 2b. tool_call from model — fan out one event per function_call.
                # Gemini bug-mitigation: id is REQUIRED on the FunctionResponse
                # we'll send back; capture it now so the CLI can pair them.
                tool_call = getattr(response, "tool_call", None)
                if tool_call is not None:
                    function_calls = getattr(tool_call, "function_calls", None) or []
                    for fc in function_calls:
                        call_id = getattr(fc, "id", None) or ""
                        fc_name = getattr(fc, "name", "") or ""
                        fc_args = getattr(fc, "args", None) or {}
                        # `args` may arrive as a Mapping-like proto; coerce to plain dict.
                        try:
                            fc_args = dict(fc_args)
                        except Exception:
                            fc_args = {}
                        _dbg(f"tool_call received name={fc_name!r} id={call_id!r} args={fc_args!r}")
                        await self._events.put(RealtimeEvent(
                            kind="tool_call",
                            data={"call_id": call_id, "name": fc_name, "args": fc_args},
                        ))

                # 3. server_content contains transcriptions + model_turn structured data.
                # Skip model_turn.parts[*].inline_data — it duplicates response.data (already emitted above).
                server_content = getattr(response, "server_content", None)
                if server_content is not None:
                    # User interrupted the model mid-turn (server VAD detected speech).
                    # Emit event so client can flush the audio playback buffer.
                    if getattr(server_content, "interrupted", False):
                        _dbg("server_content.interrupted=True — user broke in")
                        await self._events.put(RealtimeEvent(kind="model_interrupted", data={}))
                    # Text transcript parallel to audio (output_audio_transcription)
                    out_transcript = getattr(server_content, "output_transcription", None)
                    if out_transcript is not None:
                        transcript_text = getattr(out_transcript, "text", None)
                        if transcript_text:
                            model_text_buffer += transcript_text
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
                        # Flush accumulated model text as a final transcript so
                        # clean-terminal mode displays one tidy line per model
                        # turn instead of staying silent.
                        if model_text_buffer:
                            await self._events.put(
                                RealtimeEvent(kind="final_transcript_model", data={"text": model_text_buffer})
                            )
                            model_text_buffer = ""
                        await self._events.put(RealtimeEvent(kind="session_closed", data={"reason": "turn_complete"}))
                    # Also flush on user interruption — what the model said up
                    # to the cutoff is still real, the user should see it.
                    elif getattr(server_content, "interrupted", False) and model_text_buffer:
                        await self._events.put(
                            RealtimeEvent(kind="final_transcript_model", data={"text": model_text_buffer})
                        )
                        model_text_buffer = ""
        except Exception as exc:
            _dbg(f"_receive_one_session EXCEPTION after {chunk_count} chunks: {exc!r}")
            # Detect dead websocket (ConnectionClosed-family from `websockets` lib)
            exc_name = type(exc).__name__
            if "ConnectionClosed" in exc_name or "ClosedError" in exc_name:
                conn_dead = True
        return chunk_count, conn_dead

    async def send_text(self, text: str) -> None:
        async with self._session_lock:
            session = self._session
        if session is None:
            raise RuntimeError("Gemini session not active")
        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": text}]},
            turn_complete=True,
        )

    async def send_silent_note(self, text: str) -> None:
        """Inject context with turn_complete=False so Gemini holds the turn
        open — buffer accepts the content but no model response is triggered
        until the next user audio arrives with its own turn_complete=True.
        """
        async with self._session_lock:
            session = self._session
        if session is None:
            return  # mid-reconnect ; recap dropped silently
        try:
            await session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=False,
            )
        except Exception:
            # Don't let a recap failure tear down the session.
            pass

    async def send_function_response(
        self,
        call_id: str,
        name: str,
        response: dict,
    ) -> None:
        """Return a tool result to Gemini. `id` is mandatory — Gemini SDK
        raises `_FUNCTION_RESPONSE_REQUIRES_ID` if missing.

        Survives mid-reconnect: if the session is None during the brief
        reconnect window, drops the response (the model will retry the call
        on the next turn if it still needs the data).
        """
        from google.genai import types as genai_types

        async with self._session_lock:
            session = self._session
        if session is None:
            _dbg(f"send_function_response dropped (mid-reconnect) name={name!r} id={call_id!r}")
            return
        try:
            fr = genai_types.FunctionResponse(
                id=call_id or None,
                name=name,
                response=response,
            )
            await session.send_tool_response(function_responses=[fr])
            _dbg(f"sent function_response name={name!r} id={call_id!r}")
        except Exception as exc:
            _dbg(f"send_function_response failed name={name!r} id={call_id!r}: {exc!r}")

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        # If we're mid-reconnect, session is None — drop chunk silently.
        async with self._session_lock:
            session = self._session
        if session is None:
            return
        try:
            rate = (
                self._provider_config.input_sample_rate
                if self._provider_config and self._provider_config.input_sample_rate
                else GEMINI_INPUT_SAMPLE_RATE
            )
            await session.send_realtime_input(
                audio={"data": pcm16, "mime_type": f"audio/pcm;rate={rate}"}
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
