"""Control server — WebSocket bridge between the UI surface (Tauri/Electron)
and the running voice-realtime CLI session.

Architecture pivot (2026-05-24): the server is NO LONGER an audio bridge that
owns its own provider. Instead it observes and controls a session that the
CLI process already runs (the CLI captures the mic via sounddevice, plays
back via portaudio, talks directly to OpenAI/Gemini). The UI just renders
state and sends light commands (mute, stop).

This means:
- The CLI calls `ControlServer.attach_session(...)` when its `talk` command
  has connected the provider. It receives an `AttachedSession` handle to
  emit events on, and registers command handlers (mute, stop) for the WS
  clients to invoke.
- WS clients connect any time, observe the live session if one is attached,
  and can issue commands. Multiple observers are supported — they all see
  the same event stream.
- No audio frames cross the WS. The UI animates VU bars from RMS values
  computed by the CLI on each chunk. The actual PCM stays in the CLI.

WS message schema (echoed in design/README.md):

→ {"op": "personas.list"}
→ {"op": "mute", "on": true}
→ {"op": "session.stop"}

← {"ev": "personas.list", "personas": [{...}]}
← {"ev": "session.opened", "sessionId": "...", "personaId": "...", "model": "...", ...}
← {"ev": "session.closed", "reason": "user|error|kill_switch|disconnect"}
← {"ev": "audio.user.frame", "rms": 0.42, "ts": 1234567890}
← {"ev": "audio.model.frame", "rms": 0.31, "ts": 1234567890}
← {"ev": "transcript.delta", "role": "user|model", "text": "...", "final": false}
← {"ev": "transcript.final", "role": "user|model", "text": "..."}
← {"ev": "ttfa", "ms": 280}
← {"ev": "ttfi", "ms": 140}
← {"ev": "cost.tick", "delta": 0.003, "total": 0.42, "elapsed": 12.3}
← {"ev": "error", "code": "...", "msg": "..."}
← {"ev": "mute.state", "on": true}       # echoed after mute command settles
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import websockets

from .log import get_logger
from .persona import Persona, list_personas

logger = get_logger("voice_realtime.control_server")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7711

# A command handler returns either None or an awaitable. Both shapes are
# supported so the CLI can register sync (state mutation) or async (provider
# call) handlers without ceremony.
CommandHandler = Callable[[dict[str, Any]], Any]


# ─── Schema helpers ────────────────────────────────────────────────────────


def _err(code: str, msg: str) -> dict[str, Any]:
    return {"ev": "error", "code": code, "msg": msg}


def _pcm16_rms(pcm16: bytes) -> float:
    """Compute normalized RMS [0.0..1.0] of a PCM16 chunk for VU level events.

    Used by the CLI's mic_pump and recv_pump before emitting audio.user.frame
    / audio.model.frame events. Lives here so the UI side and the server side
    agree on the exact normalization.
    """
    if not pcm16:
        return 0.0
    try:
        samples = np.frombuffer(pcm16, dtype=np.int16)
    except (ValueError, TypeError):
        return 0.0
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    if math.isnan(rms):
        return 0.0
    return min(1.0, rms / 32768.0)


def _build_settings_payload() -> dict[str, Any]:
    """Snapshot of the user's voice-realtime config + usage for the UI's
    Settings modal. Read-only — writes go through `~/.claude/voice-realtime.env`
    manually for now (Phase B is display-only). Errors degrade gracefully:
    missing config file → keys reported as absent + default budget.
    """
    from .config import SECRETS_PATH, load_config
    from .cost_tracker import daily_total_usd, monthly_total_usd
    from .providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
    from .providers.openai_realtime import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL

    has_openai = False
    has_gemini = False
    budget_cap = 22.0
    try:
        cfg = load_config()
        has_openai = cfg.has_openai
        has_gemini = cfg.has_gemini
        budget_cap = cfg.monthly_budget_usd
    except FileNotFoundError:
        pass  # surfaces as keys absent + default budget

    try:
        monthly = monthly_total_usd()
    except Exception:
        monthly = 0.0
    try:
        daily = daily_total_usd()
    except Exception:
        daily = 0.0

    return {
        "ev": "settings.get",
        "secretsPath": str(SECRETS_PATH),
        "openaiKey": "present" if has_openai else "absent",
        "geminiKey": "present" if has_gemini else "absent",
        "defaultModelOpenai": OPENAI_DEFAULT_MODEL,
        "defaultModelGemini": GEMINI_DEFAULT_MODEL,
        "budgetCapUsd": round(budget_cap, 2),
        "monthlyTotalUsd": round(monthly, 4),
        "dailyTotalUsd": round(daily, 4),
        "monthlyProgressPct": round(min(1.0, monthly / max(0.01, budget_cap)) * 100, 1),
    }


def _persona_to_dict(p: Persona) -> dict[str, Any]:
    """Serialize a Persona for the personas.list WS payload.

    Drops the full `system_prompt` body — the UI only needs identity + presets
    to render the welcome popover.
    """
    return {
        "id": p.slug,
        "name": p.name,
        "description": p.description,
        "voice": p.voice,
        "model": p.model,
        "provider": p.provider,
        "vad": p.vad,
        "avatar": p.avatar,
        "hasObsidianFilter": p.has_obsidian_filter,
    }


# ─── AttachedSession ───────────────────────────────────────────────────────


@dataclass
class AttachedSession:
    """Handle returned to the CLI when it attaches its live session.

    The CLI uses this object to:
      - emit events (transcripts, cost ticks, audio levels) that get
        fanned out to all WS observers
      - register command handlers the WS clients can invoke (mute, stop)
    """

    session_id: str
    persona_slug: str
    model: str
    provider_name: str
    voice: str | None = None
    vad: str | None = None
    _server: ControlServer | None = None
    _command_handlers: dict[str, CommandHandler] = field(default_factory=dict)
    _closed: bool = False

    @property
    def opened_payload(self) -> dict[str, Any]:
        """The session.opened event payload, used on attach + on late client connect."""
        return {
            "ev": "session.opened",
            "sessionId": self.session_id,
            "personaId": self.persona_slug,
            "model": self.model,
            "provider": self.provider_name,
            "voice": self.voice or "default",
            "vad": self.vad or "balanced",
        }

    def on_command(self, op: str, handler: CommandHandler) -> None:
        """Register a handler the WS clients can trigger via `op` messages.

        Currently expected: `mute`, `session.stop`. The handler receives the
        raw message dict and may be sync or async.
        """
        self._command_handlers[op] = handler

    async def dispatch_command(self, op: str, msg: dict[str, Any]) -> bool:
        """Forward a WS-received op to the CLI's registered handler.

        Returns True if a handler ran, False if no handler is registered.
        """
        handler = self._command_handlers.get(op)
        if handler is None:
            return False
        try:
            result = handler(msg)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("command handler for op=%r raised", op)
        return True

    async def emit(self, event: dict[str, Any]) -> None:
        """Broadcast an event to every connected WS observer of this server.

        Called by the CLI's pumps when something happens worth showing in the UI.
        No-op if the session was already detached or no server is bound.
        """
        if self._closed or self._server is None:
            return
        await self._server._broadcast(event)


# ─── Server ────────────────────────────────────────────────────────────────


class ControlServer:
    """WebSocket server that observes + controls the CLI's live voice session.

    Lifecycle:
      1. Start the server (`await server.start()` or run as a task)
      2. CLI calls `server.attach_session(...)` when its session is ready
      3. CLI emits events via the returned AttachedSession
      4. WS clients connect, observe events, send commands
      5. CLI calls `server.detach_session(reason=...)` when the session ends
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self.attached_session: AttachedSession | None = None
        self.clients: set[Any] = set()
        self._server_obj = None  # the websockets.Server instance

    # ── public API the CLI uses ───────────────────────────────────────────

    async def start(self) -> None:
        """Start serving forever. Blocks until cancelled."""
        logger.info("control_server listening on ws://%s:%d", self.host, self.port)
        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()  # run forever

    async def attach_session(
        self,
        *,
        persona_slug: str,
        model: str,
        provider_name: str,
        voice: str | None = None,
        vad: str | None = None,
    ) -> AttachedSession:
        """Register the CLI's current session with the server.

        Raises if a session is already attached — the CLI is single-process,
        a single talk command at a time.
        """
        if self.attached_session is not None and not self.attached_session._closed:
            raise RuntimeError(
                "control_server: a session is already attached "
                f"(session_id={self.attached_session.session_id})"
            )
        session = AttachedSession(
            session_id=uuid.uuid4().hex[:12],
            persona_slug=persona_slug,
            model=model,
            provider_name=provider_name,
            voice=voice,
            vad=vad,
            _server=self,
        )
        self.attached_session = session
        await self._broadcast(session.opened_payload)
        logger.info(
            "session %s attached provider=%s model=%s persona=%s",
            session.session_id, provider_name, model, persona_slug,
        )
        return session

    async def detach_session(self, *, reason: str = "user") -> None:
        """Mark the attached session as closed and notify all observers."""
        session = self.attached_session
        if session is None or session._closed:
            return
        session._closed = True
        self.attached_session = None
        await self._broadcast({"ev": "session.closed", "reason": reason})
        logger.info("session %s detached reason=%s", session.session_id, reason)

    # ── WS internals ──────────────────────────────────────────────────────

    async def _handle_client(self, ws: Any) -> None:
        client = getattr(ws, "remote_address", None)
        logger.info("client connected: %s", client)
        self.clients.add(ws)
        # If a session is already live when this client connects, replay the
        # session.opened so the UI doesn't sit in "idle" until something fires.
        if self.attached_session is not None and not self.attached_session._closed:
            try:
                await ws.send(json.dumps(self.attached_session.opened_payload, ensure_ascii=False))
            except websockets.exceptions.ConnectionClosed:
                self.clients.discard(ws)
                return
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps(_err("BAD_JSON", "message is not valid JSON")))
                    continue
                await self._handle_message(ws, msg)
        except websockets.exceptions.ConnectionClosed:
            logger.info("client %s disconnected", client)
        except Exception:
            logger.exception("client handler crashed")
        finally:
            self.clients.discard(ws)

    async def _handle_message(self, ws: Any, msg: dict[str, Any]) -> None:
        op = msg.get("op")
        if op == "personas.list":
            personas = [_persona_to_dict(p) for p in list_personas()]
            await ws.send(json.dumps(
                {"ev": "personas.list", "personas": personas},
                ensure_ascii=False,
            ))
            return
        if op == "settings.get":
            await ws.send(json.dumps(_build_settings_payload(), ensure_ascii=False))
            return
        if op in ("mute", "session.stop"):
            session = self.attached_session
            if session is None or session._closed:
                await ws.send(json.dumps(_err("NO_SESSION", "no active session attached")))
                return
            dispatched = await session.dispatch_command(op, msg)
            if not dispatched:
                await ws.send(json.dumps(_err(
                    "COMMAND_NOT_HANDLED",
                    f"the CLI did not register a handler for op={op!r}",
                )))
            return
        await ws.send(json.dumps(_err("UNKNOWN_OP", f"unknown op: {op!r}")))

    async def _broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to every connected client. Swallows transport errors."""
        if not self.clients:
            return
        payload = json.dumps(event, ensure_ascii=False)
        dead: list[Any] = []
        for ws in list(self.clients):
            try:
                await ws.send(payload)
            except websockets.exceptions.ConnectionClosed:
                dead.append(ws)
            except Exception:
                logger.exception("send failed on a client; dropping")
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


# ─── Entry point ──────────────────────────────────────────────────────────


async def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ControlServer:
    """Start the control server (helper for the `voice-realtime serve` CLI).

    Returns the server instance so the caller can `attach_session()` on it
    if they want to drive it programmatically.
    """
    server = ControlServer(host=host, port=port)
    await server.start()
    return server


async def start_server_task(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> tuple[ControlServer, asyncio.Task]:
    """Start the server in the background and return (server, task).

    Used by the CLI `talk` command to spin up the WS alongside the audio loop.
    The caller is responsible for cancelling the task on shutdown.
    """
    server = ControlServer(host=host, port=port)
    task = asyncio.create_task(server.start(), name=f"control_server_{port}")
    # Give it a moment to bind so callers can attach right after.
    await asyncio.sleep(0.05)
    return server, task
