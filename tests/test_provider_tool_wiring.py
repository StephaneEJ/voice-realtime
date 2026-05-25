"""Sprint 1 — function calling foundation wiring tests.

Covers:
- ToolRegistry.provider_specs() returns base.ToolSpec instances ready for connect
- ToolRegistry.subset() filters by persona allowlist
- ToolRegistry.requires_confirmation() reflects safety levels
- Gemini live_config injects tools shape when tools passed
- OpenAI session payload injects tools + tool_choice when tools passed
- OpenAI function_call_arguments delta/done sequence emits one tool_call event
- LocalProvider.send_function_response stub raises NotImplementedError cleanly

No live providers — everything is stubbed/monkeypatched.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from voice_realtime.providers.base import ProviderConfig, ToolSpec
from voice_realtime.providers.gemini import GeminiProvider
from voice_realtime.providers.local import LocalProvider
from voice_realtime.providers.openai_realtime import OpenAIRealtimeProvider
from voice_realtime.tools import ToolSafetyLevel, default_registry
from voice_realtime.tools.registry import ToolRegistry


# ─── ToolRegistry helpers ──────────────────────────────────────────────────


def test_provider_specs_returns_base_ToolSpec_instances() -> None:
    r = default_registry()
    specs = r.provider_specs()
    assert len(specs) == 3
    assert all(isinstance(s, ToolSpec) for s in specs)
    names = {s.name for s in specs}
    assert names == {"search_vault", "read_file", "note_action"}


def test_subset_filters_by_name() -> None:
    r = default_registry()
    sub = r.subset(["search_vault", "ghost_tool"])  # ghost_tool ignored
    assert sub.names() == ["search_vault"]


def test_subset_empty_when_no_match() -> None:
    r = default_registry()
    sub = r.subset(["nope"])
    assert sub.names() == []


def test_requires_confirmation_matches_safety() -> None:
    r = default_registry()
    assert r.requires_confirmation("search_vault") is False
    assert r.requires_confirmation("read_file") is False
    assert r.requires_confirmation("note_action") is True
    # Unknown tool defaults to False (no confirmation flow)
    assert r.requires_confirmation("ghost") is False


# ─── Gemini config injection ───────────────────────────────────────────────


def test_gemini_live_config_includes_tools_when_set() -> None:
    p = GeminiProvider()
    p._provider_config = ProviderConfig(model="gemini-2.5-flash-native-audio-latest", api_key="x")
    p._system_prompt = "test prompt"
    p._model_id = "gemini-2.5-flash-native-audio-latest"
    p._audio_mode = True
    p._tools = [
        ToolSpec(name="search_vault", description="search", parameters={"type": "object"})
    ]
    cfg = p._build_live_config()
    assert "tools" in cfg
    declarations = cfg["tools"][0]["function_declarations"]
    assert len(declarations) == 1
    assert declarations[0]["name"] == "search_vault"
    assert declarations[0]["description"] == "search"
    assert declarations[0]["parameters"] == {"type": "object"}


def test_gemini_live_config_omits_tools_when_none() -> None:
    p = GeminiProvider()
    p._provider_config = ProviderConfig(model="gemini-2.5-flash-native-audio-latest", api_key="x")
    p._system_prompt = "test"
    p._model_id = "gemini-2.5-flash-native-audio-latest"
    p._audio_mode = False
    p._tools = []
    cfg = p._build_live_config()
    assert "tools" not in cfg


# ─── OpenAI tools wiring at connect ────────────────────────────────────────


class _StubOpenAIConn:
    """Just enough of AsyncRealtimeConnection to capture session.update calls."""

    def __init__(self) -> None:
        self.session_payload: dict | None = None
        self.created_outputs: list[dict] = []
        self.response_create_calls = 0
        # nested namespaces — `self.session`, `self.conversation.item`,
        # `self.response`, `self.input_audio_buffer`
        outer = self

        class _Session:
            async def update(_self, *, session: dict) -> None:
                outer.session_payload = session

        class _Item:
            async def create(_self, *, item: dict) -> None:
                outer.created_outputs.append(item)

        class _Conversation:
            item = _Item()

        class _Response:
            async def create(_self) -> None:
                outer.response_create_calls += 1

        self.session = _Session()
        self.conversation = _Conversation()
        self.response = _Response()


class _StubOpenAIConnCM:
    def __init__(self) -> None:
        self.conn = _StubOpenAIConn()

    async def __aenter__(self) -> _StubOpenAIConn:
        return self.conn

    async def __aexit__(self, *a: object) -> None:
        return None


class _StubAsyncOpenAI:
    def __init__(self, captured: dict) -> None:
        self.captured = captured

        class _Realtime:
            def connect(_self, *, model: str) -> _StubOpenAIConnCM:
                captured["cm"] = _StubOpenAIConnCM()
                captured["model"] = model
                return captured["cm"]

        self.realtime = _Realtime()


@pytest.mark.asyncio
async def test_openai_connect_injects_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        "voice_realtime.providers.openai_realtime.AsyncOpenAI",
        lambda api_key: _StubAsyncOpenAI(captured),
    )
    p = OpenAIRealtimeProvider()
    tools = [
        ToolSpec(name="search_vault", description="search", parameters={"type": "object"}),
        ToolSpec(name="note_action", description="note", parameters={"type": "object"}),
    ]
    await p.connect(
        ProviderConfig(model="gpt-realtime-2", api_key="sk-x"),
        system_prompt="prompt",
        audio=False,
        tools=tools,
    )
    # Stop the receive_loop task so it doesn't leak — _conn is a stub.
    if p._receiver_task is not None:
        p._receiver_task.cancel()
    payload = captured["cm"].conn.session_payload
    assert payload is not None
    assert "tools" in payload
    assert payload["tool_choice"] == "auto"
    assert {t["name"] for t in payload["tools"]} == {"search_vault", "note_action"}
    assert all(t["type"] == "function" for t in payload["tools"])


@pytest.mark.asyncio
async def test_openai_connect_no_tools_omits_field(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        "voice_realtime.providers.openai_realtime.AsyncOpenAI",
        lambda api_key: _StubAsyncOpenAI(captured),
    )
    p = OpenAIRealtimeProvider()
    await p.connect(
        ProviderConfig(model="gpt-realtime-2", api_key="sk-x"),
        system_prompt="prompt",
        audio=False,
        tools=None,
    )
    if p._receiver_task is not None:
        p._receiver_task.cancel()
    payload = captured["cm"].conn.session_payload
    assert "tools" not in payload
    assert "tool_choice" not in payload


# ─── OpenAI function_call_arguments parsing ────────────────────────────────


class _Evt:
    """Minimal event shape: attributes mirror SDK events."""

    def __init__(self, **kw: object) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


class _StubItem:
    def __init__(self, type: str, call_id: str, name: str) -> None:
        self.type = type
        self.call_id = call_id
        self.name = name


@pytest.mark.asyncio
async def test_openai_receive_emits_tool_call_on_done() -> None:
    """Pump 3 events (added, delta, done) through _receive_loop and assert
    exactly one `tool_call` RealtimeEvent comes out with parsed args.
    """
    p = OpenAIRealtimeProvider()

    # Async iterable conn yielding our synthetic events.
    events = [
        _Evt(type="response.output_item.added",
             item=_StubItem("function_call", "call_abc", "search_vault")),
        _Evt(type="response.function_call_arguments.delta",
             call_id="call_abc", delta='{"query":"foo"}'),
        _Evt(type="response.function_call_arguments.done",
             call_id="call_abc", arguments='{"query":"foo"}', name="search_vault"),
    ]

    class _AsyncConn:
        def __aiter__(self):
            async def gen():
                for e in events:
                    yield e
            return gen()

    p._conn = _AsyncConn()  # type: ignore[assignment]
    await p._receive_loop()
    # Drain the queue
    out: list = []
    while not p._events.empty():
        out.append(p._events.get_nowait())
    tool_calls = [e for e in out if e.kind == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].data["call_id"] == "call_abc"
    assert tool_calls[0].data["name"] == "search_vault"
    assert tool_calls[0].data["args"] == {"query": "foo"}


@pytest.mark.asyncio
async def test_openai_send_function_response_fires_create() -> None:
    """`send_function_response` must push function_call_output AND
    call response.create() — without it the model stays silent.
    """
    p = OpenAIRealtimeProvider()
    p._conn = _StubOpenAIConn()  # type: ignore[assignment]
    await p.send_function_response("call_abc", "search_vault", {"result": {"hit": 1}})
    assert len(p._conn.created_outputs) == 1
    item = p._conn.created_outputs[0]
    assert item["type"] == "function_call_output"
    assert item["call_id"] == "call_abc"
    assert json.loads(item["output"]) == {"result": {"hit": 1}}
    assert p._conn.response_create_calls == 1


# ─── LocalProvider stub conformance ────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_send_function_response_stub_raises() -> None:
    p = LocalProvider()
    with pytest.raises(NotImplementedError):
        await p.send_function_response("id", "name", {"result": 1})


@pytest.mark.asyncio
async def test_local_connect_accepts_tools_kw() -> None:
    """Even though the stub raises later, the signature must accept tools=
    so the CLI doesn't TypeError when picking the local provider.
    """
    p = LocalProvider()
    # Force the binary check to "ok" with a tools list — must not TypeError
    # on the tools kwarg.
    p._deps.all_present = lambda: (True, [])  # type: ignore[method-assign]
    with pytest.raises(NotImplementedError):
        await p.connect(
            ProviderConfig(model="local", api_key=""),
            system_prompt="x",
            tools=[ToolSpec(name="search_vault", description="", parameters={})],
        )
