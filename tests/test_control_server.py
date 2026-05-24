"""Tests for control_server (post-pivot 2026-05-24).

The control server is now an OBSERVER/CONTROLLER of the CLI's live session,
not an audio bridge. These tests exercise the WS protocol surface:

- `personas.list` op (no session required)
- `mute` / `session.stop` ops dispatched to CLI-registered handlers
- WS clients receive replayed `session.opened` on late connect
- Multiple observers see the same event stream
- `attach_session` is single-tenant (CLI is single-process)
- Unknown op / bad JSON / no-session error envelopes
"""

from __future__ import annotations

import asyncio
import json
import socket

import pytest
import websockets

from voice_realtime import control_server as cs
from voice_realtime.persona import Persona


# ─── Helpers ───────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def server() -> cs.ControlServer:
    """Spin up a fresh ControlServer on a random port for one test."""
    port = _free_port()
    srv, task = await cs.start_server_task(host="127.0.0.1", port=port)
    yield srv
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def _ws_uri(server: cs.ControlServer) -> str:
    return f"ws://{server.host}:{server.port}"


async def _connect(server: cs.ControlServer):
    return await websockets.connect(_ws_uri(server))


# ─── Pure-function tests ───────────────────────────────────────────────────


def test_pcm16_rms_empty() -> None:
    assert cs._pcm16_rms(b"") == 0.0


def test_pcm16_rms_nonzero() -> None:
    # 16-bit samples at amplitude 16384 → RMS ≈ 0.5 normalized
    pcm = (16384).to_bytes(2, "little", signed=True) * 100
    rms = cs._pcm16_rms(pcm)
    assert 0.4 < rms < 0.6


def test_err_envelope_shape() -> None:
    err = cs._err("API_KEY_MISSING", "no key")
    assert err == {"ev": "error", "code": "API_KEY_MISSING", "msg": "no key"}


def test_persona_to_dict_drops_system_prompt() -> None:
    p = Persona(slug="jarvis", name="Jarvis", system_prompt="secret body", voice="Charon")
    d = cs._persona_to_dict(p)
    assert d["id"] == "jarvis"
    assert d["name"] == "Jarvis"
    assert d["voice"] == "Charon"
    assert "system_prompt" not in d


# ─── WS protocol tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_json_returns_error(server: cs.ControlServer) -> None:
    async with await _connect(server) as ws:
        await ws.send("not json at all")
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "BAD_JSON"


@pytest.mark.asyncio
async def test_unknown_op_errors(server: cs.ControlServer) -> None:
    async with await _connect(server) as ws:
        await ws.send(json.dumps({"op": "nonsense"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "UNKNOWN_OP"


@pytest.mark.asyncio
async def test_mute_without_session_errors(server: cs.ControlServer) -> None:
    async with await _connect(server) as ws:
        await ws.send(json.dumps({"op": "mute", "on": True}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "NO_SESSION"


@pytest.mark.asyncio
async def test_session_stop_without_session_errors(server: cs.ControlServer) -> None:
    async with await _connect(server) as ws:
        await ws.send(json.dumps({"op": "session.stop"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "NO_SESSION"


@pytest.mark.asyncio
async def test_personas_list_returns_payload(
    server: cs.ControlServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = [
        Persona(slug="jarvis", name="Jarvis", system_prompt="x", description="assistant"),
        Persona(slug="coach", name="Coach", system_prompt="y", voice="Charon", model="m"),
    ]
    monkeypatch.setattr(cs, "list_personas", lambda: fake)

    async with await _connect(server) as ws:
        await ws.send(json.dumps({"op": "personas.list"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "personas.list"
        assert len(msg["personas"]) == 2
        assert msg["personas"][0]["id"] == "jarvis"
        assert msg["personas"][0]["name"] == "Jarvis"
        assert msg["personas"][1]["voice"] == "Charon"
        # body must NOT leak
        assert "system_prompt" not in msg["personas"][0]


# ─── Attach session tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attach_session_broadcasts_opened(server: cs.ControlServer) -> None:
    """When CLI attaches, all connected clients receive session.opened."""
    async with await _connect(server) as ws:
        # Give the server one event loop tick to register the client
        await asyncio.sleep(0.05)
        session = await server.attach_session(
            persona_slug="jarvis",
            model="gemini-2.5-flash-native-audio-latest",
            provider_name="gemini",
            voice="Charon",
            vad="balanced",
        )
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "session.opened"
        assert msg["personaId"] == "jarvis"
        assert msg["model"] == "gemini-2.5-flash-native-audio-latest"
        assert msg["provider"] == "gemini"
        assert msg["voice"] == "Charon"
        assert "sessionId" in msg
        assert msg["sessionId"] == session.session_id


@pytest.mark.asyncio
async def test_late_client_gets_replayed_session_opened(
    server: cs.ControlServer,
) -> None:
    """Client connecting AFTER attach still sees session.opened immediately."""
    await server.attach_session(
        persona_slug="coach",
        model="gpt-realtime-2",
        provider_name="openai",
    )
    async with await _connect(server) as ws:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "session.opened"
        assert msg["personaId"] == "coach"
        assert msg["provider"] == "openai"


@pytest.mark.asyncio
async def test_attach_twice_raises(server: cs.ControlServer) -> None:
    """CLI is single-process; attaching a second session before detaching is a bug."""
    await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    with pytest.raises(RuntimeError, match="already attached"):
        await server.attach_session(
            persona_slug="coach", model="m2", provider_name="openai",
        )


@pytest.mark.asyncio
async def test_detach_broadcasts_session_closed(server: cs.ControlServer) -> None:
    """Detach fires session.closed with the given reason to all observers."""
    await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    async with await _connect(server) as ws:
        # Drain session.opened replay
        await asyncio.wait_for(ws.recv(), timeout=2.0)
        await server.detach_session(reason="kill_switch_cost")
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "session.closed"
        assert msg["reason"] == "kill_switch_cost"


@pytest.mark.asyncio
async def test_emit_events_reach_all_observers(server: cs.ControlServer) -> None:
    """Multiple WS clients see the same events fanned out from the CLI."""
    session = await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    async with await _connect(server) as ws1, await _connect(server) as ws2:
        # Drain replayed session.opened on both
        await asyncio.wait_for(ws1.recv(), timeout=2.0)
        await asyncio.wait_for(ws2.recv(), timeout=2.0)

        await session.emit({
            "ev": "transcript.final",
            "role": "model",
            "text": "Salut Stéphane.",
        })

        for ws in (ws1, ws2):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert msg["ev"] == "transcript.final"
            assert msg["text"] == "Salut Stéphane."


@pytest.mark.asyncio
async def test_mute_command_dispatched_to_handler(server: cs.ControlServer) -> None:
    """WS mute op → CLI-registered handler is called with the raw message."""
    session = await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    received: list[dict] = []
    session.on_command("mute", lambda msg: received.append(msg))

    async with await _connect(server) as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # drain session.opened
        await ws.send(json.dumps({"op": "mute", "on": True}))
        # Handler runs synchronously — give one tick for the server to dispatch
        await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0]["op"] == "mute"
    assert received[0]["on"] is True


@pytest.mark.asyncio
async def test_session_stop_command_dispatched_async(server: cs.ControlServer) -> None:
    """Async command handlers (e.g. await provider.close()) are awaited correctly."""
    session = await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    stop_called = asyncio.Event()

    async def _on_stop(_msg: dict) -> None:
        await asyncio.sleep(0.01)  # simulate async cleanup
        stop_called.set()

    session.on_command("session.stop", _on_stop)

    async with await _connect(server) as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # drain session.opened
        await ws.send(json.dumps({"op": "session.stop"}))
        await asyncio.wait_for(stop_called.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_command_without_handler_returns_error(server: cs.ControlServer) -> None:
    """CLI didn't register a handler for `mute` → client gets COMMAND_NOT_HANDLED."""
    await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    async with await _connect(server) as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # drain session.opened
        await ws.send(json.dumps({"op": "mute", "on": True}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "COMMAND_NOT_HANDLED"


@pytest.mark.asyncio
async def test_emit_after_detach_is_noop(server: cs.ControlServer) -> None:
    """Late events from the CLI after detach must not crash."""
    session = await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    await server.detach_session(reason="user")
    # Should not raise even though the session is closed
    await session.emit({"ev": "transcript.delta", "role": "user", "text": "ignored", "final": False})


@pytest.mark.asyncio
async def test_personas_list_works_during_active_session(
    server: cs.ControlServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """personas.list is still callable while a session is attached."""
    monkeypatch.setattr(
        cs, "list_personas",
        lambda: [Persona(slug="jarvis", name="Jarvis", system_prompt="x")],
    )
    await server.attach_session(
        persona_slug="jarvis", model="m", provider_name="gemini",
    )
    async with await _connect(server) as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # drain session.opened
        await ws.send(json.dumps({"op": "personas.list"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "personas.list"
        assert msg["personas"][0]["id"] == "jarvis"
