"""Tool registry — basic dispatch + safety + handler error paths."""

from __future__ import annotations

import pytest

from voice_realtime.tools import (
    ToolRegistry,
    ToolResult,
    ToolSafetyLevel,
    default_registry,
)
from voice_realtime.tools.registry import ToolSpec


def test_tool_result_function_response_ok() -> None:
    r = ToolResult(ok=True, data={"x": 1})
    out = r.as_function_response("my_tool")
    assert out == {"name": "my_tool", "response": {"result": {"x": 1}}}


def test_tool_result_function_response_error() -> None:
    r = ToolResult(ok=False, error="boom")
    out = r.as_function_response("my_tool")
    assert out == {"name": "my_tool", "response": {"error": "boom"}}


def test_registry_dispatch_unknown_returns_error() -> None:
    r = ToolRegistry()
    out = r.dispatch("ghost")
    assert not out.ok
    assert "unknown" in (out.error or "")


def test_registry_register_then_dispatch() -> None:
    r = ToolRegistry()
    r.register(ToolSpec(
        name="echo",
        description="echo back",
        safety=ToolSafetyLevel.READ_ONLY,
        parameters_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=lambda msg: ToolResult(ok=True, data={"echo": msg}),
    ))
    out = r.dispatch("echo", msg="hi")
    assert out.ok
    assert out.data == {"echo": "hi"}


def test_registry_dispatch_handler_exception_becomes_result() -> None:
    r = ToolRegistry()
    def _boom(**_: object) -> ToolResult:
        raise ValueError("kaboom")
    r.register(ToolSpec(
        name="boom",
        description="",
        safety=ToolSafetyLevel.READ_ONLY,
        parameters_schema={"type": "object"},
        handler=_boom,
    ))
    out = r.dispatch("boom")
    assert not out.ok
    assert "ValueError" in (out.error or "")
    assert "kaboom" in (out.error or "")


def test_registry_register_duplicate_raises() -> None:
    r = ToolRegistry()
    spec = ToolSpec(
        name="dup", description="", safety=ToolSafetyLevel.READ_ONLY,
        parameters_schema={}, handler=lambda: ToolResult(ok=True),
    )
    r.register(spec)
    with pytest.raises(ValueError):
        r.register(spec)


def test_registry_as_specs_shape() -> None:
    r = default_registry()
    specs = r.as_specs()
    assert isinstance(specs, list)
    assert len(specs) == 5
    names = {s["name"] for s in specs}
    assert names == {"search_vault", "read_file", "note_action", "vault_write", "web_search"}
    for s in specs:
        assert "description" in s
        assert "parameters" in s


def test_default_registry_safety_levels() -> None:
    r = default_registry()
    assert r.get("search_vault").safety == ToolSafetyLevel.READ_ONLY
    assert r.get("read_file").safety == ToolSafetyLevel.READ_ONLY
    assert r.get("note_action").safety == ToolSafetyLevel.WRITE_USER_SCOPE
    assert r.get("vault_write").safety == ToolSafetyLevel.WRITE_USER_SCOPE
    assert r.get("web_search").safety == ToolSafetyLevel.READ_ONLY


def test_read_file_rejects_outside_vault(tmp_path) -> None:
    from voice_realtime.tools.registry import _tool_read_file
    outside = tmp_path / "x.md"
    outside.write_text("secret", encoding="utf-8")
    out = _tool_read_file(str(outside))
    assert not out.ok
    assert "vault" in (out.error or "")


def test_search_vault_empty_query() -> None:
    from voice_realtime.tools.registry import _tool_search_vault
    out = _tool_search_vault("")
    assert not out.ok
