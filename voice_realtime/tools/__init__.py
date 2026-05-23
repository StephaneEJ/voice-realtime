"""Phase 3.5 — voice-realtime tool calling skeleton.

Public surface kept minimal so providers' tool_call dispatch can light up
without re-architecting. Each tool is a Python callable + a JSON schema
description (provider tool-spec) + a safety classification.

DEFER FROM PHASE 2: this module is loaded but `voice-realtime talk` does
NOT yet wire tools into provider connect(). Phase 3.5 implementation is:

    a) provider.connect(config, system_prompt, tools=ToolRegistry().as_specs())
    b) recv_pump: on event.kind == "tool_call" → ToolRegistry.dispatch(...)
       → provider.send_function_response(result)
    c) Optional: surface tool_call as a terminal marker like ✂ barge-in.

Until then, importing this module gives a working registry but no live
wiring. Tests in tests/test_tool_registry.py exercise it.
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
