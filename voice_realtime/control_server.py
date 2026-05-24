"""Control server — WebSocket bridge between native UI (SwiftUI/Tauri) and
the existing voice-realtime providers (Phase 3.F.1).

The UI app never calls Gemini/OpenAI directly. It connects to this local
WebSocket server at ws://127.0.0.1:7711 and exchanges JSON messages following
the schema imposed by the Claude Design handoff (see design/README.md).

Architecture:
- One asyncio WS server, multi-client capable (each client = its own session)
- Per-client `Session` object owns a `RealtimeVoiceProvider` instance
- Two pumps: client→provider (forward audio frames) and provider→client
  (translate provider events into WS events)
- `CostTracker` + `LatencyTracker` per session (the same classes used by the CLI)
- Audio capture and playback stay on the CLIENT side (the UI). The server
  receives PCM16 from the client, forwards to the provider, and sends back
  the provider's PCM16 chunks as base64 in `audio.model.frame` events.

WS message schema (echo of design/README.md, kept here for reference):

→ {"op": "session.start", "personaId": "jarvis", "model": "..."}
→ {"op": "audio.frame", "pcm16": "<base64>", "ts": 1234567890}
→ {"op": "mute", "on": true}
→ {"op": "session.stop"}

← {"ev": "session.opened", "sessionId": "...", "model": "...", "voice": "alloy"}
← {"ev": "audio.user.frame", "rms": 0.42, "ts": 123}
← {"ev": "audio.model.frame", "rms": 0.31, "pcm16": "..."}
← {"ev": "transcript.delta", "role": "user|model", "text": "...", "final": false}
← {"ev": "transcript.final", "role": "user|model", "text": "..."}
← {"ev": "ttfa", "ms": 280}
← {"ev": "ttfi", "ms": 140}
← {"ev": "cost.tick", "delta": 0.003, "total": 0.42}
← {"ev": "error", "code": "API_KEY_INVALID", "msg": "..."}
← {"ev": "session.closed", "reason": "user|error|timeout"}
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import websockets
from websockets.server import WebSocketServerProtocol

from .config import load_config
from .cost_tracker import CostTracker
from .latency_tracker import LatencyTracker
from .log import get_logger
from .persona import PersonaError, load_persona_by_slug
from .persona_skills import build_persona_knowledge_block
from .providers.base import ProviderConfig, RealtimeEvent
from .providers.gemini import (
    DEFAULT_MODEL as GEMINI_DEFAULT_MODEL,
    GEMINI_INPUT_SAMPLE_RATE,
    GeminiProvider,
)
from .providers.openai_realtime import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
    OPENAI_AUDIO_SAMPLE_RATE,
    OpenAIRealtimeProvider,
)

logger = get_logger("voice_realtime.control_server")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7711
COST_TICK_INTERVAL_S = 1.0


# ─── Schema helpers ────────────────────────────────────────────────────────


def _err(code: str, msg: str) -> dict[str, Any]:
    return {"ev": "error", "code": code, "msg": msg}


def _pcm16_rms(pcm16: bytes) -> float:
    """Compute normalized RMS [0.0..1.0] of a PCM16 chunk for VU level events.

    Implemented via numpy since the stdlib `audioop` module was removed in
    Python 3.13+. The buffer is interpreted as little-endian int16 samples.
    """
    if not pcm16:
        return 0.0
    try:
        samples = np.frombuffer(pcm16, dtype=np.int16)
    except (ValueError, TypeError):
        return 0.0
    if samples.size == 0:
        return 0.0
    # mean of squares, then sqrt — equivalent to audioop.rms()
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    if math.isnan(rms):
        return 0.0
    return min(1.0, rms / 32768.0)


def _provider_for_model(model: str) -> str:
    """Map a model id to its provider name."""
    return "openai" if model.startswith("gpt-") else "gemini"


# ─── Session ───────────────────────────────────────────────────────────────


@dataclass
class Session:
    """One voice-realtime session driven by one WS client."""

    session_id: str
    ws: WebSocketServerProtocol
    persona_slug: str
    model: str
    provider_name: str
    api_key: str
    voice: str | None = None
    vad: str | None = None
    impl: Any = None  # GeminiProvider | OpenAIRealtimeProvider
    cost_tracker: CostTracker | None = None
    latency: LatencyTracker = field(default_factory=LatencyTracker)
    muted: bool = False
    closed: bool = False
    # internal tasks for clean shutdown
    recv_task: asyncio.Task | None = None
    cost_task: asyncio.Task | None = None

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send a JSON event to the WS client. Swallows transport errors after close."""
        if self.closed:
            return
        try:
            await self.ws.send(json.dumps(event, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            self.closed = True


# ─── Server ────────────────────────────────────────────────────────────────


class ControlServer:
    """WebSocket server that bridges UI clients to voice-realtime providers."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self.sessions: dict[str, Session] = {}
        self._cfg = None  # loaded at start()

    async def start(self) -> None:
        """Start serving forever. Blocks until cancelled."""
        try:
            self._cfg = load_config()
        except FileNotFoundError as exc:
            logger.error("Cannot start without secrets: %s", exc)
            raise
        logger.info("control_server listening on ws://%s:%d", self.host, self.port)
        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()  # run forever

    async def _handle_client(self, ws: WebSocketServerProtocol) -> None:
        client = ws.remote_address
        logger.info("client connected: %s", client)
        session: Session | None = None
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps(_err("BAD_JSON", "message is not valid JSON")))
                    continue
                op = msg.get("op")
                if op == "session.start":
                    if session is not None and not session.closed:
                        await ws.send(json.dumps(_err(
                            "SESSION_ACTIVE",
                            "a session is already running on this connection; stop it first",
                        )))
                        continue
                    session = await self._handle_session_start(ws, msg)
                    if session is not None:
                        self.sessions[session.session_id] = session
                elif op == "audio.frame":
                    if session is None or session.closed:
                        await ws.send(json.dumps(_err("NO_SESSION", "no active session")))
                        continue
                    await self._handle_audio_frame(session, msg)
                elif op == "mute":
                    if session is None or session.closed:
                        await ws.send(json.dumps(_err("NO_SESSION", "no active session")))
                        continue
                    session.muted = bool(msg.get("on"))
                    logger.debug("session %s mute=%s", session.session_id, session.muted)
                elif op == "session.stop":
                    if session is None:
                        continue
                    await self._stop_session(session, reason="user")
                else:
                    await ws.send(json.dumps(_err("UNKNOWN_OP", f"unknown op: {op!r}")))
        except websockets.exceptions.ConnectionClosed:
            logger.info("client %s disconnected", client)
        except Exception:
            logger.exception("client handler crashed")
        finally:
            if session is not None and not session.closed:
                await self._stop_session(session, reason="disconnect")

    async def _handle_session_start(
        self, ws: WebSocketServerProtocol, msg: dict[str, Any]
    ) -> Session | None:
        persona_slug = msg.get("personaId") or "jarvis"
        model = msg.get("model") or ""
        try:
            persona = load_persona_by_slug(persona_slug)
        except PersonaError as exc:
            await ws.send(json.dumps(_err("PERSONA_NOT_FOUND", str(exc))))
            return None

        # Apply persona overrides for fields the client didn't set
        if not model:
            model = persona.model or ""
        provider_name = msg.get("provider") or persona.provider or _provider_for_model(model) or "gemini"
        if not model:
            model = OPENAI_DEFAULT_MODEL if provider_name == "openai" else GEMINI_DEFAULT_MODEL

        # API key resolution
        if provider_name == "openai":
            if not self._cfg or not self._cfg.has_openai:
                await ws.send(json.dumps(_err("API_KEY_MISSING", "OPENAI_API_KEY not configured")))
                return None
            api_key = self._cfg.openai_api_key
            impl = OpenAIRealtimeProvider()
        elif provider_name == "gemini":
            if not self._cfg or not self._cfg.has_gemini:
                await ws.send(json.dumps(_err("API_KEY_MISSING", "GEMINI_API_KEY not configured")))
                return None
            api_key = self._cfg.gemini_api_key
            impl = GeminiProvider()
        else:
            await ws.send(json.dumps(_err("BAD_PROVIDER", f"unknown provider: {provider_name!r}")))
            return None

        voice = msg.get("voice") or persona.voice
        vad = msg.get("vad") or persona.vad
        pcfg = ProviderConfig(model=model, api_key=api_key, voice=voice, vad=vad)  # type: ignore[arg-type]

        # Compose system prompt = persona.system_prompt + persona knowledge block
        system_prompt = persona.system_prompt
        knowledge = build_persona_knowledge_block(persona)
        if knowledge:
            system_prompt = system_prompt + "\n\n" + knowledge

        # Connect provider in audio mode
        try:
            await impl.connect(pcfg, system_prompt=system_prompt, audio=True)
        except Exception as exc:
            logger.exception("provider connect failed")
            await ws.send(json.dumps(_err("PROVIDER_CONNECT_FAILED", repr(exc))))
            return None

        session_id = uuid.uuid4().hex[:12]
        session = Session(
            session_id=session_id,
            ws=ws,
            persona_slug=persona_slug,
            model=model,
            provider_name=provider_name,
            api_key=api_key,
            voice=voice,
            vad=vad,
            impl=impl,
        )
        session.cost_tracker = CostTracker(
            provider=provider_name,
            model=model,
            hard_stop_cost_usd=3.0,
            max_duration_seconds=900.0,
        )

        await session.send_event({
            "ev": "session.opened",
            "sessionId": session_id,
            "personaId": persona_slug,
            "model": model,
            "provider": provider_name,
            "voice": voice or "default",
            "vad": vad or "balanced",
            "expectedSampleRate": (
                OPENAI_AUDIO_SAMPLE_RATE if provider_name == "openai" else GEMINI_INPUT_SAMPLE_RATE
            ),
        })
        logger.info(
            "session %s opened provider=%s model=%s persona=%s",
            session_id, provider_name, model, persona_slug,
        )

        # Start the two pumps for this session.
        session.recv_task = asyncio.create_task(self._provider_pump(session))
        session.cost_task = asyncio.create_task(self._cost_pump(session))
        return session

    async def _handle_audio_frame(self, session: Session, msg: dict[str, Any]) -> None:
        if session.muted:
            return
        b64 = msg.get("pcm16") or ""
        try:
            pcm16 = base64.b64decode(b64) if b64 else b""
        except (ValueError, TypeError):
            await session.send_event(_err("BAD_AUDIO", "pcm16 must be base64-encoded PCM16"))
            return
        if not pcm16:
            return
        # Forward to provider
        try:
            await session.impl.send_audio_chunk(pcm16)
        except Exception as exc:
            logger.warning("send_audio_chunk failed: %r", exc)
            return
        # Update latency + emit user VU event so UI can animate the user side
        # of the spectrum without doing its own RMS pass.
        session.latency.on_user_audio_sent()
        rms = _pcm16_rms(pcm16)
        await session.send_event({
            "ev": "audio.user.frame",
            "rms": round(rms, 4),
            "ts": msg.get("ts", int(time.time() * 1000)),
        })

    async def _provider_pump(self, session: Session) -> None:
        """Translate provider events into WS events for the client."""
        try:
            async for event in session.impl.receive_events():
                if session.closed:
                    break
                await self._translate_event(session, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("provider_pump crashed for session %s", session.session_id)
            await session.send_event(_err("PROVIDER_PUMP_CRASHED", "see server logs"))
        logger.info("provider_pump exiting for session %s", session.session_id)

    async def _translate_event(self, session: Session, event: RealtimeEvent) -> None:
        """Map our internal RealtimeEvent kinds to the WS schema."""
        kind = event.kind
        data = event.data or {}
        if kind == "audio_chunk_out":
            session.latency.on_model_audio_received()
            pcm = data.get("pcm16") or b""
            rms = _pcm16_rms(pcm) if pcm else 0.0
            await session.send_event({
                "ev": "audio.model.frame",
                "rms": round(rms, 4),
                "pcm16": base64.b64encode(pcm).decode("ascii") if pcm else "",
            })
            # Surface TTFA the first time we get audio after a user turn
            ttfa = session.latency.last_ttfa_ms
            if ttfa is not None:
                await session.send_event({"ev": "ttfa", "ms": round(ttfa, 1)})
        elif kind == "partial_transcript_model":
            await session.send_event({
                "ev": "transcript.delta",
                "role": "model",
                "text": data.get("text", ""),
                "final": False,
            })
        elif kind == "final_transcript_model":
            await session.send_event({
                "ev": "transcript.final",
                "role": "model",
                "text": data.get("text", ""),
                "final": True,
            })
            session.latency.on_turn_complete()
        elif kind == "partial_transcript_user":
            await session.send_event({
                "ev": "transcript.delta",
                "role": "user",
                "text": data.get("text", ""),
                "final": False,
            })
        elif kind == "final_transcript_user":
            await session.send_event({
                "ev": "transcript.final",
                "role": "user",
                "text": data.get("text", ""),
                "final": True,
            })
        elif kind == "model_interrupted":
            session.latency.on_interrupt_signal()
            await session.send_event({"ev": "model.interrupted"})
            ttfi = session.latency.last_ttfi_ms
            if ttfi is not None:
                await session.send_event({"ev": "ttfi", "ms": round(ttfi, 1)})
        elif kind == "session_closed":
            # Per-turn close from provider — not a session-end. We swallow it
            # at the server level; the client only sees session.closed when
            # the user explicitly stops.
            return
        elif kind == "error":
            await session.send_event(_err("PROVIDER_ERROR", str(data.get("exception") or data.get("error"))))
        # else: unknown kind — ignore

    async def _cost_pump(self, session: Session) -> None:
        """Emit cost.tick events at a steady cadence and enforce kill switches."""
        try:
            prev_total = 0.0
            while not session.closed:
                await asyncio.sleep(COST_TICK_INTERVAL_S)
                tracker = session.cost_tracker
                if tracker is None:
                    continue
                total = tracker.estimated_cost_usd
                delta = total - prev_total
                prev_total = total
                await session.send_event({
                    "ev": "cost.tick",
                    "delta": round(delta, 6),
                    "total": round(total, 4),
                    "elapsed": round(tracker.elapsed_seconds, 1),
                })
                kill, reason = tracker.should_kill()
                if kill:
                    logger.warning("session %s kill switch: %s", session.session_id, reason)
                    await self._stop_session(session, reason=f"kill_{reason}")
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("cost_pump crashed for session %s", session.session_id)

    async def _stop_session(self, session: Session, *, reason: str) -> None:
        if session.closed:
            return
        # Send the close event BEFORE flipping `closed` so send_event doesn't
        # early-return on its own guard. Then set closed and drop tasks.
        try:
            await session.ws.send(json.dumps({"ev": "session.closed", "reason": reason}))
        except websockets.exceptions.ConnectionClosed:
            pass
        session.closed = True
        if session.cost_tracker is not None:
            try:
                session.cost_tracker.persist(reason=reason)
            except Exception:
                logger.exception("cost tracker persist failed")
        if session.recv_task is not None:
            session.recv_task.cancel()
        if session.cost_task is not None:
            session.cost_task.cancel()
        try:
            await session.impl.close()
        except Exception:
            logger.exception("provider close failed")
        self.sessions.pop(session.session_id, None)
        logger.info("session %s stopped reason=%s", session.session_id, reason)


# ─── Entry point ──────────────────────────────────────────────────────────


async def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the control server (helper for CLI/tests)."""
    server = ControlServer(host=host, port=port)
    await server.start()
