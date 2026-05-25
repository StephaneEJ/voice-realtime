"""OpenAI Realtime provider — minimal text I/O for Milestone 1.

Uses `AsyncOpenAI.realtime.connect()` async context manager.
Audio I/O wiring lands in Milestone 2.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import base64

from openai import AsyncOpenAI

from ..log import get_logger

logger = get_logger("voice_realtime.openai")
OPENAI_AUDIO_SAMPLE_RATE = 24000

from .base import ProviderConfig, RealtimeEvent, ToolSpec

DEFAULT_MODEL = "gpt-realtime-2"
# 2026-05-21 NOTE: gpt-realtime-2 confirmed available via client.models.list().
# Alternatives: gpt-realtime (latest alias), gpt-realtime-mini (cheaper), gpt-realtime-1.5 (legacy).

# VAD presets — server_vad turn_detection sensitivity. Matches the Gemini
# preset names so a persona can use the same `vad` field across providers.
# threshold = energy gate (0.5 = sensitive, 0.8 = needs clear voice).
# prefix_padding_ms = audio kept before speech start was detected.
# silence_duration_ms = how long of trailing silence ends a user turn.
OPENAI_VAD_PRESETS: dict[str, dict] = {
    "reactive":     {"threshold": 0.55, "prefix_padding_ms": 250, "silence_duration_ms": 500},
    "balanced":     {"threshold": 0.65, "prefix_padding_ms": 350, "silence_duration_ms": 900},
    "patient":      {"threshold": 0.70, "prefix_padding_ms": 450, "silence_duration_ms": 1400},
    "very-patient": {"threshold": 0.75, "prefix_padding_ms": 550, "silence_duration_ms": 2200},
}
OPENAI_VAD_DEFAULT = "balanced"


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
        # call_id -> {"name": str, "arg_buf": str} — accumulates streamed
        # function_call_arguments.delta chunks until the matching .done event.
        self._pending_calls: dict[str, dict] = {}

    async def connect(
        self,
        config: ProviderConfig,
        system_prompt: str,
        audio: bool = False,
        tools: list[ToolSpec] | None = None,
    ) -> None:
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
        if tools:
            # OpenAI Realtime-2 tools shape: flat objects with explicit type.
            # tool_choice="auto" lets the model decide when to call.
            session_payload["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools
            ]
            session_payload["tool_choice"] = "auto"
            logger.debug(f"tools wired count={len(tools)} names={[t.name for t in tools]}")
        if audio:
            vad_name = config.vad or OPENAI_VAD_DEFAULT
            vad_preset = OPENAI_VAD_PRESETS.get(vad_name, OPENAI_VAD_PRESETS[OPENAI_VAD_DEFAULT])
            logger.debug(
                f"VAD preset='{vad_name}' threshold={vad_preset['threshold']} "
                f"prefix_padding_ms={vad_preset['prefix_padding_ms']} "
                f"silence_duration_ms={vad_preset['silence_duration_ms']}"
            )
            session_payload["audio"] = {
                "input": {
                    "format": {"type": "audio/pcm", "rate": OPENAI_AUDIO_SAMPLE_RATE},
                    # VAD sensitivity controlled by --vad CLI flag or persona frontmatter.
                    # Defaults to "balanced". Pick "patient" / "very-patient" in noisy
                    # environments to stop the server from cutting the model on small
                    # ambient sounds. The previous hardcoded values (0.75 / 600ms) were
                    # added 2026-05-23 against OpenAI's too-sensitive defaults; they now
                    # map to the "very-patient" preset.
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": vad_preset["threshold"],
                        "prefix_padding_ms": vad_preset["prefix_padding_ms"],
                        "silence_duration_ms": vad_preset["silence_duration_ms"],
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
                elif etype == "response.output_item.added":
                    # A function_call item enters the response output. Grab the
                    # call_id + name now so we can collect its streamed args.
                    item = getattr(event, "item", None)
                    if item is not None and getattr(item, "type", None) == "function_call":
                        call_id = getattr(item, "call_id", "") or ""
                        fn_name = getattr(item, "name", "") or ""
                        if call_id:
                            self._pending_calls[call_id] = {"name": fn_name, "arg_buf": ""}
                            logger.debug(f"function_call started call_id={call_id!r} name={fn_name!r}")
                elif etype == "response.function_call_arguments.delta":
                    call_id = getattr(event, "call_id", "") or ""
                    delta = getattr(event, "delta", "") or ""
                    if call_id and call_id in self._pending_calls:
                        self._pending_calls[call_id]["arg_buf"] += delta
                elif etype == "response.function_call_arguments.done":
                    call_id = getattr(event, "call_id", "") or ""
                    pending = self._pending_calls.pop(call_id, None)
                    # `arguments` on .done holds the full JSON string; prefer it
                    # over the accumulated buffer in case any delta was missed.
                    args_str = getattr(event, "arguments", None) or (pending or {}).get("arg_buf", "")
                    fn_name = (pending or {}).get("name") or getattr(event, "name", "") or ""
                    try:
                        fn_args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        logger.warning(f"function_call_arguments JSON decode failed call_id={call_id!r} raw={args_str!r}")
                        fn_args = {}
                    logger.debug(f"function_call done call_id={call_id!r} name={fn_name!r} args={fn_args!r}")
                    await self._events.put(RealtimeEvent(
                        kind="tool_call",
                        data={"call_id": call_id, "name": fn_name, "args": fn_args},
                    ))
                elif etype == "response.done":
                    # Per-response usage block: {"input_tokens", "output_tokens",
                    # "total_tokens"}. Reported once per response.done, so we
                    # add (delta mode) to the running totals on the tracker.
                    resp_obj = getattr(event, "response", None)
                    usage = getattr(resp_obj, "usage", None) if resp_obj is not None else None
                    if usage is not None:
                        tokens_in = getattr(usage, "input_tokens", None) or 0
                        tokens_out = getattr(usage, "output_tokens", None) or 0
                        if tokens_in or tokens_out:
                            await self._events.put(RealtimeEvent(
                                kind="cost_update",
                                data={
                                    "tokens_in": int(tokens_in),
                                    "tokens_out": int(tokens_out),
                                    "mode": "delta",
                                },
                            ))
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

    async def send_function_response(
        self,
        call_id: str,
        name: str,
        response: dict,
    ) -> None:
        """Push a tool result back into the conversation and kick a new response.

        Without the trailing `response.create()` the model would buffer the
        function_call_output but never speak the synthesis aloud — confirmed
        gotcha on Realtime-2 (see masterplan Sprint 1 notes).
        """
        if self._conn is None:
            return
        try:
            output_str = json.dumps(response, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning(f"send_function_response JSON encode failed name={name!r}: {exc!r}")
            output_str = json.dumps({"error": "serialization_failed"})
        try:
            await self._conn.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output_str,
                }
            )
            await self._conn.response.create()
            logger.debug(f"sent function_call_output call_id={call_id!r} name={name!r}")
        except Exception as exc:
            logger.warning(f"send_function_response failed call_id={call_id!r} name={name!r}: {exc!r}")

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
