"""Tests for control_server (Phase 3.F.1).

Provider calls are mocked — we test the WS protocol surface only:
- Message routing (session.start / audio.frame / mute / session.stop / unknown op)
- Error envelope shape
- Persona lookup wired in
- Session lifecycle (open → close)
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

from voice_realtime import control_server as cs


@pytest.fixture(autouse=True)
def _silence_persistence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Don't write real cost jsonl files during tests."""
    from voice_realtime import cost_tracker
    monkeypatch.setattr(cost_tracker, "SESSIONS_DIR", tmp_path)


@pytest.fixture
def fake_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch load_config to return a fake config with both keys present."""
    fake = MagicMock()
    fake.has_openai = True
    fake.has_gemini = True
    fake.openai_api_key = "sk-test"
    fake.gemini_api_key = "AIzaTest"
    monkeypatch.setattr(cs, "load_config", lambda: fake)


@pytest.fixture
def fake_personas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch persona loader so we don't need vault personas to exist on disk."""
    def _load(slug: str):
        if slug == "jarvis":
            persona = MagicMock()
            persona.slug = "jarvis"
            persona.system_prompt = "Tu es Jarvis."
            persona.model = "gemini-2.5-flash-native-audio-latest"
            persona.provider = "gemini"
            persona.voice = "Charon"
            persona.vad = "balanced"
            persona.greeting_mode = "persona"
            persona.has_obsidian_filter = False
            persona.obsidian_skills = []
            persona.obsidian_notes = []
            return persona
        if slug == "ghost":
            from voice_realtime.persona import PersonaError
            raise PersonaError(f"Persona 'ghost' not found")
        raise ValueError(f"unexpected slug: {slug}")

    monkeypatch.setattr(cs, "load_persona_by_slug", _load)
    monkeypatch.setattr(cs, "build_persona_knowledge_block", lambda _p: "")


class FakeProvider:
    """Minimal stand-in for GeminiProvider / OpenAIRealtimeProvider."""

    def __init__(self) -> None:
        self.connected_with: tuple | None = None
        self.audio_chunks_sent: list[bytes] = []
        self.closed = False
        self._events: asyncio.Queue = asyncio.Queue()

    async def connect(self, config, system_prompt, audio=False):
        self.connected_with = (config, system_prompt, audio)

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        self.audio_chunks_sent.append(pcm16)

    async def receive_events(self):
        while not self.closed:
            ev = await self._events.get()
            if ev is None:
                break
            yield ev

    async def send_text(self, text: str) -> None:
        pass

    async def send_silent_note(self, text: str) -> None:
        pass

    async def close(self) -> None:
        self.closed = True
        await self._events.put(None)


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    """Replace both GeminiProvider and OpenAIRealtimeProvider with FakeProvider."""
    fp = FakeProvider()
    monkeypatch.setattr(cs, "GeminiProvider", lambda: fp)
    monkeypatch.setattr(cs, "OpenAIRealtimeProvider", lambda: fp)
    return fp


@pytest.fixture
async def server_port(fake_config, fake_personas, fake_provider) -> int:
    """Spin up a fresh ControlServer on a random port for one test."""
    # Find an available port
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = cs.ControlServer(host="127.0.0.1", port=port)
    server._cfg = cs.load_config()
    serve_task = asyncio.create_task(_run_server_for_test(server, port))
    # Give it a moment to bind
    await asyncio.sleep(0.1)
    yield port
    serve_task.cancel()
    try:
        await serve_task
    except asyncio.CancelledError:
        pass


async def _run_server_for_test(server: cs.ControlServer, port: int) -> None:
    async with websockets.serve(server._handle_client, "127.0.0.1", port):
        await asyncio.Future()


# ─── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pcm16_rms_empty() -> None:
    assert cs._pcm16_rms(b"") == 0.0


@pytest.mark.asyncio
async def test_pcm16_rms_nonzero() -> None:
    # 16-bit samples at amplitude 16384 → RMS ≈ 0.5 normalized
    pcm = (16384).to_bytes(2, "little", signed=True) * 100
    rms = cs._pcm16_rms(pcm)
    assert 0.4 < rms < 0.6


def test_provider_for_model_routing() -> None:
    assert cs._provider_for_model("gpt-realtime-2") == "openai"
    assert cs._provider_for_model("gpt-realtime-mini") == "openai"
    assert cs._provider_for_model("gemini-2.5-flash-native-audio-latest") == "gemini"


def test_err_envelope_shape() -> None:
    err = cs._err("API_KEY_MISSING", "no key")
    assert err == {"ev": "error", "code": "API_KEY_MISSING", "msg": "no key"}


@pytest.mark.asyncio
async def test_bad_json_returns_error_envelope(server_port: int) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send("not json at all")
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "BAD_JSON"


@pytest.mark.asyncio
async def test_audio_frame_without_session_errors(server_port: int) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "audio.frame", "pcm16": ""}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "NO_SESSION"


@pytest.mark.asyncio
async def test_unknown_op_errors(server_port: int) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "nonsense"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "UNKNOWN_OP"


@pytest.mark.asyncio
async def test_session_start_unknown_persona(server_port: int) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "ghost"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "error"
        assert msg["code"] == "PERSONA_NOT_FOUND"


@pytest.mark.asyncio
async def test_session_lifecycle_open_then_stop(server_port: int) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "jarvis"}))
        # Expect session.opened
        opened = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert opened["ev"] == "session.opened"
        assert opened["personaId"] == "jarvis"
        assert opened["model"] == "gemini-2.5-flash-native-audio-latest"
        assert opened["provider"] == "gemini"
        assert "sessionId" in opened

        # Stop
        await ws.send(json.dumps({"op": "session.stop"}))

        # Drain until we see session.closed, with a single bounded deadline.
        # The cost pump may emit a tick or two before the close lands; we
        # don't care about ordering, only that the close eventually arrives.
        async def _wait_close() -> dict:
            while True:
                msg = json.loads(await ws.recv())
                if msg["ev"] == "session.closed":
                    return msg
        closed_msg = await asyncio.wait_for(_wait_close(), timeout=4.0)
        assert closed_msg["reason"] == "user"


@pytest.mark.asyncio
async def test_audio_frame_forwards_to_provider(server_port: int, fake_provider: FakeProvider) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "jarvis"}))
        # Drain session.opened
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        # Send a couple of PCM16 frames (silent audio = zeros, RMS = 0)
        silent = b"\x00\x00" * 480  # 30ms @ 16kHz
        b64 = base64.b64encode(silent).decode("ascii")
        await ws.send(json.dumps({"op": "audio.frame", "pcm16": b64, "ts": 1000}))

        # Expect audio.user.frame echo
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "audio.user.frame"
        assert msg["rms"] == 0.0
        assert msg["ts"] == 1000

        # Verify it landed on the fake provider
        assert len(fake_provider.audio_chunks_sent) == 1
        assert fake_provider.audio_chunks_sent[0] == silent


@pytest.mark.asyncio
async def test_mute_drops_audio(server_port: int, fake_provider: FakeProvider) -> None:
    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "jarvis"}))
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # session.opened

        await ws.send(json.dumps({"op": "mute", "on": True}))
        # No reply for mute, just internal state change. Send audio.
        b64 = base64.b64encode(b"\x00\x00" * 100).decode("ascii")
        await ws.send(json.dumps({"op": "audio.frame", "pcm16": b64}))
        # Provider should NOT receive a chunk while muted
        await asyncio.sleep(0.2)
        assert fake_provider.audio_chunks_sent == []


@pytest.mark.asyncio
async def test_personas_list_returns_payload(
    server_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """personas.list returns a list of persona dicts without requiring a session."""
    from voice_realtime.persona import Persona

    fake = [
        Persona(slug="jarvis", name="Jarvis", system_prompt="x", description="assistant"),
        Persona(slug="coach", name="Coach", system_prompt="y", voice="Charon", model="m"),
    ]
    monkeypatch.setattr(cs, "list_personas", lambda: fake)

    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "personas.list"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["ev"] == "personas.list"
        assert len(msg["personas"]) == 2
        assert msg["personas"][0]["id"] == "jarvis"
        assert msg["personas"][0]["name"] == "Jarvis"
        assert msg["personas"][1]["voice"] == "Charon"
        # system_prompt body must NOT leak in payload
        assert "system_prompt" not in msg["personas"][0]


@pytest.mark.asyncio
async def test_personas_list_works_during_active_session(
    server_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """personas.list is queryable even while a session is running on the same connection."""
    from voice_realtime.persona import Persona

    monkeypatch.setattr(
        cs, "list_personas",
        lambda: [Persona(slug="jarvis", name="Jarvis", system_prompt="x")],
    )

    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "jarvis"}))
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # drain session.opened
        await ws.send(json.dumps({"op": "personas.list"}))
        # Drain until personas.list arrives (cost.tick may interleave)
        for _ in range(10):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            if msg["ev"] == "personas.list":
                assert msg["personas"][0]["id"] == "jarvis"
                return
        pytest.fail("personas.list never received")


@pytest.mark.asyncio
async def test_provider_event_forwards_to_client(server_port: int, fake_provider: FakeProvider) -> None:
    """Inject a fake provider event and verify it surfaces over WS."""
    from voice_realtime.providers.base import RealtimeEvent

    uri = f"ws://127.0.0.1:{server_port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "session.start", "personaId": "jarvis"}))
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # session.opened

        # Inject a transcript event from the "provider"
        await fake_provider._events.put(
            RealtimeEvent(kind="final_transcript_model", data={"text": "Salut Stéphane."})
        )
        # Expect transcript.final to be forwarded
        for _ in range(5):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            if msg["ev"] == "transcript.final":
                assert msg["role"] == "model"
                assert msg["text"] == "Salut Stéphane."
                return
        pytest.fail("transcript.final never received")
