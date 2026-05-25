"""Provider Protocol + shared event/config dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol

ThinkingLevel = Literal["minimal", "low", "medium", "high", "very_high"]
VADPreset = Literal["reactive", "balanced", "patient", "very-patient"]
EventKind = Literal[
    "partial_transcript_user",
    "final_transcript_user",
    "partial_transcript_model",
    "final_transcript_model",
    "audio_chunk_out",
    "model_interrupted",
    "tool_call",
    "error",
    "cost_update",
    "session_closed",
]


@dataclass(frozen=True)
class ToolSpec:
    """Provider-agnostic tool declaration the CLI hands to `connect(tools=...)`.

    `parameters` is a JSON-Schema object (`type: object`, `properties`, `required`).
    Both Gemini Live and OpenAI Realtime accept this shape verbatim — only the
    surrounding envelope differs, handled inside each provider.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    api_key: str
    voice: str | None = None
    thinking_level: ThinkingLevel | None = None
    context_tokens: int = 3000
    # Optional override of the mic sample rate sent to the server. Useful for
    # testing whether Gemini Live STT improves at 24kHz vs the default 16kHz
    # on French rapid speech. None = use provider's default constant.
    input_sample_rate: int | None = None
    # VAD preset (server-side voice activity detection sensitivity). Controls
    # how easily the server interrupts the model when ambient noise is picked
    # up. None = providers default to "balanced". Choose "patient" or
    # "very-patient" in noisy environments where the model gets cut off by
    # background sounds.
    vad: VADPreset | None = None


@dataclass(frozen=True)
class RealtimeEvent:
    kind: EventKind
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0


class RealtimeVoiceProvider(Protocol):
    """All voice providers (OpenAI, Gemini, local) implement this."""

    async def connect(
        self,
        config: ProviderConfig,
        system_prompt: str,
        tools: list[ToolSpec] | None = None,
    ) -> None: ...

    async def send_function_response(
        self,
        call_id: str,
        name: str,
        response: dict[str, Any],
    ) -> None:
        """Return a tool call's result to the model so it can resume.

        `response` is the JSON-serializable payload (typically
        `{"result": ...}` or `{"error": "..."}`). Provider impls wrap it in
        the SDK-specific FunctionResponse shape and, for OpenAI, also fire
        `response.create()` so the model speaks the synthesis aloud.
        """
        ...

    async def send_text(self, text: str) -> None: ...

    async def send_silent_note(self, text: str) -> None:
        """Inject text into the conversation history WITHOUT triggering a reply.

        Used by the rolling-context-window feature to top up the model with a
        compacted recap of the last ~7 min, without making the model talk.
        Default fallback: a wrapped send_text — provider impls should override
        with a turn_complete=False (Gemini) or response-less create (OpenAI)
        path so the model truly stays silent.
        """
        await self.send_text(text)

    async def send_audio_chunk(self, pcm16: bytes) -> None: ...

    def receive_events(self) -> AsyncIterator[RealtimeEvent]: ...

    async def close(self) -> None: ...
