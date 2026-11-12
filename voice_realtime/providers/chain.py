"""Mode chaîne : reconnaissance vocale → modèle API au choix → synthèse vocale.

`ChainProvider` implémente `RealtimeVoiceProvider` avec trois étages
interchangeables, si bien que `cli.py` le pilote comme Gemini Live ou OpenAI
Realtime, sans connaître les étages :

    micro PCM16 ──► Endpointer (VAD locale) ──► SpeechToText ──► final_transcript_user
                                                       │
                                                       ▼
                                     ChatModel.stream(system, historique, outils)
                                        │ texte par phrases        │ appels d'outils
                                        ▼                          ▼
                              TextToSpeech ──► audio_chunk_out    tool_call ──► cli ──► send_function_response

- Coupure de parole : dès que l'Endpointer détecte une reprise de parole
  pendant une réponse, la réponse en cours est annulée et `model_interrupted`
  est émis ; seul le texte déjà parlé reste dans l'historique.
- Outils : un appel d'outil reste valable même si la réponse est coupée ; son
  résultat est rangé dans l'historique à son arrivée, et le tour suivant
  l'attend avant d'interroger le modèle. Le garde-fou reste côté serveur MCP.
- Le mot d'arrêt (« killchat ») est détecté par la CLI sur les transcriptions
  utilisateur, comme pour les autres fournisseurs.

Les adaptateurs concrets (OpenAI compatible, Anthropic, whisper.cpp, `say`)
vivent dans `chain_stages.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol

from .base import ProviderConfig, RealtimeEvent, ToolSpec
from .chain_audio import EndpointEvent, Endpointer

logger = logging.getLogger("voice_realtime.chain")

DEFAULT_INPUT_SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# Contrats des trois étages


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ModelChunk:
    """Morceau de réponse du modèle : texte, appel d'outil complet ou usage."""

    text: str = ""
    tool_call: ToolCall | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class SpeechToText(Protocol):
    name: str

    async def transcribe(self, pcm16: bytes, sample_rate: int) -> str: ...


class ChatModel(Protocol):
    """Historique au format neutre :

    - `{"role": "user", "content": str}`
    - `{"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}`
    - `{"role": "tool", "tool_call_id": str, "name": str, "content": str}`
    """

    name: str

    def stream(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> AsyncIterator[ModelChunk]: ...


class TextToSpeech(Protocol):
    name: str
    sample_rate: int

    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class ChainStageError(RuntimeError):
    """Échec d'un étage (réseau, binaire, réponse invalide). Message sans secret."""


# ---------------------------------------------------------------------------
# Découpage en phrases pour lancer la synthèse au plus tôt

_BOUNDARY = re.compile(r"[.!?…;:](?=\s)|\n")


def pop_sentences(buffer: str, min_chars: int = 8) -> tuple[list[str], str]:
    """Extrait les phrases complètes du tampon ; renvoie (phrases, reste)."""
    out: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(buffer):
        end = m.end()
        candidate = buffer[start:end].strip()
        if len(candidate) >= min_chars:
            out.append(candidate)
            start = end
    return out, buffer[start:]


# ---------------------------------------------------------------------------
# Métriques par tour (reprises par le banc d'essai N3)


@dataclass
class TurnMetrics:
    source: str = "audio"  # audio | text
    utterance_ms: int = 0
    stt_ms: float | None = None
    first_token_ms: float | None = None
    first_audio_ms: float | None = None
    total_ms: float | None = None
    tool_calls: int = 0
    interrupted: bool = False
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class _Turn:
    phase: str = "stt"  # stt | model | done
    superseded: bool = False
    audio_emitted: bool = False
    metrics: TurnMetrics = field(default_factory=TurnMetrics)


# ---------------------------------------------------------------------------


class ChainProvider:
    """Fournisseur « chaîne » : trois étages derrière le protocole `providers`."""

    name = "chain"

    def __init__(
        self,
        stt: SpeechToText,
        model: ChatModel,
        tts: TextToSpeech,
        *,
        endpointer: Endpointer | None = None,
        max_tool_rounds: int = 4,
        tool_result_timeout_s: float = 60.0,
        min_sentence_chars: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stt = stt
        self.model = model
        self.tts = tts
        self._endpointer = endpointer
        self._max_tool_rounds = max_tool_rounds
        self._tool_timeout = tool_result_timeout_s
        self._min_sentence_chars = min_sentence_chars
        self._system = ""
        self._tools: list[ToolSpec] = []
        self._input_rate = DEFAULT_INPUT_SAMPLE_RATE
        self._history: list[dict[str, Any]] = []
        self._notes: list[str] = []
        self._events: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue()
        self._inbox: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._tool_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._worker: asyncio.Task | None = None
        self._turn_task: asyncio.Task | None = None
        self._turn: _Turn | None = None
        self._closed = False
        self._playback_until = 0.0
        # Horloge de lecture (estimation de la fin de l'audio chez l'utilisateur) ;
        # le rejeu accéléré la remplace par une horloge virtuelle.
        self.clock = clock
        self.metrics: list[TurnMetrics] = []

    # -- informations ------------------------------------------------------

    @property
    def label(self) -> str:
        return f"{self.stt.name} → {self.model.name} → {self.tts.name}"

    @property
    def output_sample_rate(self) -> int:
        return self.tts.sample_rate

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._history

    # -- protocole RealtimeVoiceProvider -----------------------------------

    async def connect(
        self,
        config: ProviderConfig,
        system_prompt: str,
        audio: bool = True,
        tools: list[ToolSpec] | None = None,
    ) -> None:
        self._system = system_prompt
        self._tools = list(tools or [])
        self._input_rate = config.input_sample_rate or DEFAULT_INPUT_SAMPLE_RATE
        if self._endpointer is None:
            self._endpointer = Endpointer.for_vad(config.vad, self._input_rate)
        self._closed = False
        self._worker = asyncio.create_task(self._run(), name="chain-worker")
        logger.info("chain connected: %s (outils=%d)", self.label, len(self._tools))

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        if self._closed or self._endpointer is None:
            return
        for ev in self._endpointer.feed(pcm16):
            await self._on_endpoint(ev)

    async def end_of_audio(self) -> None:
        """Fin de flux (rejeu d'un enregistrement) : clôt l'énoncé en cours."""
        if self._endpointer is None:
            return
        for ev in self._endpointer.flush():
            await self._on_endpoint(ev)

    async def send_text(self, text: str) -> None:
        await self._inbox.put(("text", text))

    async def send_silent_note(self, text: str) -> None:
        # Rangé au début du prochain tour : jamais intercalé entre un appel
        # d'outil et son résultat.
        self._notes.append(text)

    async def send_function_response(
        self, call_id: str, name: str, response: dict[str, Any]
    ) -> None:
        fut = self._tool_futures.get(call_id)
        if fut is None:
            logger.warning("résultat d'outil inconnu call_id=%r name=%r — ignoré", call_id, name)
            return
        if not fut.done():
            fut.set_result(response)

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        while True:
            ev = await self._events.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._turn_task, self._worker):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        for fut in self._tool_futures.values():
            if not fut.done():
                fut.cancel()
        await self._events.put(None)

    @property
    def busy(self) -> bool:
        task = self._turn_task
        return not self._inbox.empty() or (task is not None and not task.done())

    async def wait_idle(self) -> None:
        """Attend que les énoncés reçus soient traités (tests et rejeu)."""
        await self._inbox.join()

    # -- interne -----------------------------------------------------------

    async def _emit(self, kind: str, **data: Any) -> None:
        await self._events.put(
            RealtimeEvent(kind=kind, data=data, timestamp_ms=int(time.monotonic() * 1000))  # type: ignore[arg-type]
        )

    async def _on_endpoint(self, ev: EndpointEvent) -> None:
        if ev.kind == "speech_start":
            await self._interrupt()
        else:
            await self._inbox.put(("audio", ev))

    async def _interrupt(self) -> None:
        turn, task = self._turn, self._turn_task
        # La synthèse va plus vite que la lecture : un tour fini peut encore
        # être en train de sonner chez l'utilisateur.
        still_playing = self.clock() < self._playback_until
        running = turn is not None and task is not None and not task.done()
        if running:
            assert turn is not None and task is not None
            turn.metrics.interrupted = True
            if turn.phase == "stt":
                # L'utilisateur reprend avant notre réponse : on garde sa phrase,
                # on renonce seulement à y répondre ; le tour suivant verra les deux.
                turn.superseded = True
            else:
                task.cancel()
                still_playing = still_playing or turn.audio_emitted
        elif turn is not None and still_playing:
            turn.metrics.interrupted = True
        if still_playing:
            self._playback_until = 0.0
            await self._emit("model_interrupted")

    async def _run(self) -> None:
        while True:
            kind, payload = await self._inbox.get()
            try:
                self._turn = _Turn()
                self._turn_task = asyncio.create_task(self._run_turn(kind, payload, self._turn))
                try:
                    await self._turn_task
                except asyncio.CancelledError:
                    # Tour coupé par l'utilisateur : on continue. Worker annulé
                    # (fermeture) : on propage.
                    current = asyncio.current_task()
                    if self._closed or (current is not None and current.cancelling()):
                        raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # jamais de fuite : la conversation continue
                logger.exception("tour en échec")
                await self._emit("error", exception=repr(exc))
            finally:
                self._inbox.task_done()

    async def _run_turn(self, kind: str, payload: Any, turn: _Turn) -> None:
        t0 = time.monotonic()
        m = turn.metrics
        m.source = kind
        self.metrics.append(m)
        try:
            if kind == "audio":
                ev: EndpointEvent = payload
                m.utterance_ms = ev.end_ms - ev.start_ms
                text = (await self.stt.transcribe(ev.pcm16, self._input_rate)).strip()
                m.stt_ms = (time.monotonic() - t0) * 1000
                if not text:
                    return
                await self._emit("final_transcript_user", text=text)
            else:
                text = str(payload)
            self._fold_notes()
            self._history.append({"role": "user", "content": text})
            if turn.superseded:
                return
            turn.phase = "model"
            await self._await_pending_tools()

            spoken_all: list[str] = []
            for round_idx in range(self._max_tool_rounds + 1):
                tools = self._tools if round_idx < self._max_tool_rounds else []
                spoken, calls = await self._model_round(turn, tools, t0, spoken_all)
                if not calls:
                    break
                await self._await_pending_tools()
            final = " ".join(spoken_all).strip()
            if final:
                await self._emit("final_transcript_model", text=final)
            await self._emit("session_closed", reason="turn_complete")
        finally:
            turn.phase = "done"
            m.total_ms = (time.monotonic() - t0) * 1000

    async def _model_round(
        self,
        turn: _Turn,
        tools: list[ToolSpec],
        t0: float,
        spoken_all: list[str],
    ) -> tuple[list[str], list[ToolCall]]:
        """Un aller-retour modèle : texte parlé phrase par phrase, outils émis."""
        m = turn.metrics
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        spoken: list[str] = []
        calls: list[ToolCall] = []

        async def speaker() -> None:
            while True:
                sentence = await sentences.get()
                if sentence is None:
                    return
                spoken.append(sentence)
                spoken_all.append(sentence)
                await self._emit("partial_transcript_model", text=sentence)
                async for chunk in self.tts.synthesize(sentence):
                    if not chunk:
                        continue
                    if not turn.audio_emitted:
                        turn.audio_emitted = True
                        m.first_audio_ms = (time.monotonic() - t0) * 1000
                    duration = len(chunk) / (2 * self.tts.sample_rate)
                    self._playback_until = max(self._playback_until, self.clock()) + duration
                    await self._emit("audio_chunk_out", pcm16=chunk)

        speaker_task = asyncio.create_task(speaker())
        buffer = ""
        completed = False
        try:
            async for chunk in self.model.stream(self._system, list(self._history), tools):
                if chunk.tokens_in or chunk.tokens_out:
                    m.tokens_in += chunk.tokens_in
                    m.tokens_out += chunk.tokens_out
                    await self._emit(
                        "cost_update",
                        tokens_in=chunk.tokens_in,
                        tokens_out=chunk.tokens_out,
                        mode="delta",
                    )
                if chunk.tool_call is not None:
                    calls.append(chunk.tool_call)
                if chunk.text:
                    if m.first_token_ms is None:
                        m.first_token_ms = (time.monotonic() - t0) * 1000
                    buffer += chunk.text
                    ready, buffer = pop_sentences(buffer, self._min_sentence_chars)
                    for s in ready:
                        await sentences.put(s)
            if buffer.strip():
                await sentences.put(buffer.strip())
            await sentences.put(None)
            await speaker_task
            completed = True
        finally:
            if not speaker_task.done():
                speaker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await speaker_task
            # Historique : seul le texte effectivement parlé est gardé ; un
            # appel d'outil n'existe que si la réponse est allée à son terme.
            kept_calls = calls if completed else []
            if spoken or kept_calls:
                self._history.append(
                    {"role": "assistant", "content": " ".join(spoken).strip(), "tool_calls": kept_calls}
                )
            if kept_calls:
                self._register_tool_calls(kept_calls)
                m.tool_calls += len(kept_calls)

        for call in calls:
            await self._emit("tool_call", call_id=call.id, name=call.name, args=call.args)
        return spoken, calls

    def _register_tool_calls(self, calls: list[ToolCall]) -> None:
        loop = asyncio.get_running_loop()
        for call in calls:
            entry: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": None,
            }
            self._history.append(entry)
            fut: asyncio.Future[dict[str, Any]] = loop.create_future()

            def _fill(f: asyncio.Future, entry: dict[str, Any] = entry) -> None:
                if f.cancelled():
                    entry["content"] = json.dumps({"error": "appel annulé"}, ensure_ascii=False)
                else:
                    entry["content"] = json.dumps(f.result(), ensure_ascii=False, default=str)

            fut.add_done_callback(_fill)
            self._tool_futures[call.id] = fut

    async def _await_pending_tools(self) -> None:
        pending = [f for f in self._tool_futures.values() if not f.done()]
        if pending:
            done, still = await asyncio.wait(pending, timeout=self._tool_timeout)
            for f in still:
                f.set_result({"error": "résultat d'outil non reçu dans le délai"})
            await asyncio.sleep(0)  # laisse les callbacks remplir l'historique
        # Les entrées sont remplies : on oublie les futurs résolus.
        for cid in [c for c, f in self._tool_futures.items() if f.done()]:
            del self._tool_futures[cid]

    def _fold_notes(self) -> None:
        for note in self._notes:
            self._history.append({"role": "user", "content": note})
        self._notes.clear()
