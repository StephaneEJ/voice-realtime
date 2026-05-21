"""Provider Protocol + shared event/config dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol

ThinkingLevel = Literal["minimal", "low", "medium", "high", "very_high"]
EventKind = Literal[
    "partial_transcript_user",
    "final_transcript_user",
    "partial_transcript_model",
    "final_transcript_model",
    "audio_chunk_out",
    "tool_call",
    "error",
    "cost_update",
    "session_closed",
]


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    api_key: str
    voice: str | None = None
    thinking_level: ThinkingLevel | None = None
    context_tokens: int = 3000


@dataclass(frozen=True)
class RealtimeEvent:
    kind: EventKind
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0


class RealtimeVoiceProvider(Protocol):
    """All voice providers (OpenAI, Gemini, local) implement this."""

    async def connect(self, config: ProviderConfig, system_prompt: str) -> None: ...

    async def send_text(self, text: str) -> None: ...

    async def send_audio_chunk(self, pcm16: bytes) -> None: ...

    def receive_events(self) -> AsyncIterator[RealtimeEvent]: ...

    async def close(self) -> None: ...
