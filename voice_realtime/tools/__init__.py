"""voice-realtime tool calling — registry + safety classifications.

Each tool is a Python callable + a JSON schema description (provider tool-spec)
+ a safety classification.

Wired into the runtime in Sprint 1 (function calling foundation):

    a) cli.py builds a per-session ToolRegistry filtered by the persona's
       `tools:` allowlist and passes `registry.provider_specs()` to
       `provider.connect(tools=...)`.
    b) Provider receives `tool_call` events from the model. cli.py's
       _recv_pump dispatches via asyncio.to_thread, then calls
       `provider.send_function_response(call_id, name, response)`.
    c) control_server emits `tool.call` + `tool.result` events to UI observers.

Tests: tests/test_tool_registry.py (registry behavior) +
tests/test_provider_tool_wiring.py (provider + dispatch loop).
"""

from __future__ import annotations

from .registry import (
    ToolRegistry,
    ToolResult,
    ToolSafetyLevel,
    default_registry,
)

__all__ = [
    "ToolRegistry",
    "ToolResult",
    "ToolSafetyLevel",
    "default_registry",
]
