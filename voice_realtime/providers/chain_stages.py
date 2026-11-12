"""Adaptateurs des étages du mode chaîne et fabrique à partir de « spécifications ».

Reconnaissance vocale (`--chain-stt`) :
  - `whisper-cpp[:chemin_modele]`         local, gratuit (binaire `whisper-cli`)
  - `openai:<modele>[@<base_url>]`        API compatible OpenAI (`/audio/transcriptions`)
  - `script:<phrase 1>|<phrase 2>|...`    transcriptions imposées (essais, rejeu)

Modèle (`--chain-llm`) :
  - `openai:<modele>[@<base_url>]`        Chat Completions en flux (OpenAI, Mistral, Groq, OpenRouter, Ollama…)
  - `anthropic:<modele>`                  Messages API en flux
  - `echo`                                local, répète l'utilisateur (essais)

Synthèse vocale (`--chain-tts`) :
  - `say[:voix]`                          macOS, local, gratuit (défaut de voix : Thomas)
  - `openai:<modele>[:voix][@<base_url>]` API compatible OpenAI (`/audio/speech`, PCM 24 kHz)

Clés : `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` ; pour un `@<base_url>` tiers,
`VOICE_REALTIME_CHAIN_COMPAT_API_KEY` (vide accepté, par exemple pour Ollama).
Aucun étage n'est choisi par défaut : le choix du fournisseur se fera sur le
banc d'essai N3.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Mapping

import httpx

from .base import ToolSpec
from .chain import ChainProvider, ChainStageError, ModelChunk, ToolCall
from .chain_audio import pcm16_to_wav, resample_pcm16, wav_to_pcm16

DEFAULT_WHISPER_MODEL = Path.home() / ".cache" / "whisper.cpp" / "ggml-small.bin"
DEFAULT_SAY_VOICE = "Thomas"
TTS_CHUNK_BYTES = 4800  # 100 ms à 24 kHz


class ChainConfigError(ValueError):
    """Spécification d'étage invalide ou clé manquante (jamais la valeur d'une clé)."""


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------------------
# Reconnaissance vocale


@dataclass
class ScriptedSTT:
    """Renvoie des transcriptions imposées, une par énoncé (essais, rejeu)."""

    phrases: list[str]
    name: str = "script"
    received: list[tuple[int, int]] = field(default_factory=list)  # (octets, fréquence)

    async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        self.received.append((len(pcm16), sample_rate))
        idx = len(self.received) - 1
        return self.phrases[idx] if idx < len(self.phrases) else ""


@dataclass
class WhisperCppSTT:
    """whisper.cpp en sous-processus (`whisper-cli`), sur fichier WAV 16 kHz."""

    model_path: Path = DEFAULT_WHISPER_MODEL
    binary: str = "whisper-cli"
    language: str = "fr"
    threads: int = 4
    timeout_s: float = 60.0
    name: str = "whisper-cpp"

    def check(self) -> None:
        if shutil.which(self.binary) is None:
            raise ChainConfigError(f"binaire introuvable : {self.binary} (brew install whisper-cpp)")
        if not Path(self.model_path).is_file():
            raise ChainConfigError(f"modèle whisper introuvable : {self.model_path}")

    async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        pcm = resample_pcm16(pcm16, sample_rate, 16000)
        with tempfile.TemporaryDirectory(prefix="vr-chain-") as tmp:
            wav_path = Path(tmp) / "enonce.wav"
            wav_path.write_bytes(pcm16_to_wav(pcm, 16000))
            proc = await asyncio.create_subprocess_exec(
                self.binary, "-m", str(self.model_path), "-l", self.language,
                "-t", str(self.threads), "-nt", "-np", "-f", str(wav_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                raise ChainStageError(f"whisper-cli : délai de {self.timeout_s:.0f} s dépassé")
        if proc.returncode != 0:
            lines = err.decode(errors="replace").splitlines()
            errors = [ln for ln in lines if "error" in ln.lower()]
            detail = " / ".join(errors[:3]) if errors else " ".join(lines[-5:])
            raise ChainStageError(f"whisper-cli : code {proc.returncode} — {_short(detail)}")
        return " ".join(out.decode(errors="replace").split())


def _openai_client(api_key: str, base_url: str | None, http_client: httpx.AsyncClient | None):
    from openai import AsyncOpenAI

    kwargs: dict[str, Any] = {"api_key": api_key or "sans-cle", "max_retries": 0}
    if base_url:
        kwargs["base_url"] = base_url
    if http_client is not None:
        kwargs["http_client"] = http_client
    return AsyncOpenAI(**kwargs)


@dataclass
class OpenAICompatibleSTT:
    model: str
    api_key: str = field(repr=False, default="")
    base_url: str | None = None
    language: str = "fr"
    http_client: httpx.AsyncClient | None = field(default=None, repr=False)
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or f"stt:{self.model}"
        self._client = _openai_client(self.api_key, self.base_url, self.http_client)

    async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        wav = pcm16_to_wav(pcm16, sample_rate)
        try:
            res = await self._client.audio.transcriptions.create(
                model=self.model,
                file=("enonce.wav", wav, "audio/wav"),
                language=self.language,
            )
        except Exception as exc:
            raise ChainStageError(f"transcription {self.model} : {type(exc).__name__} {_short(str(exc))}") from None
        return (getattr(res, "text", "") or "").strip()


# ---------------------------------------------------------------------------
# Modèles


def _tool_calls_of(msg: Mapping[str, Any]) -> list[ToolCall]:
    return list(msg.get("tool_calls") or [])


def to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            out.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
            calls = _tool_calls_of(msg)
            if calls:
                item["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)},
                    }
                    for c in calls
                ]
            out.append(item)
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": msg.get("content") or json.dumps({"error": "résultat absent"}),
            })
    return out


def to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tools
    ]


@dataclass
class OpenAICompatibleChat:
    """Chat Completions en flux ; couvre OpenAI et les API compatibles."""

    model: str
    api_key: str = field(repr=False, default="")
    base_url: str | None = None
    max_tokens: int | None = None
    http_client: httpx.AsyncClient | None = field(default=None, repr=False)
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or f"openai:{self.model}"
        self._client = _openai_client(self.api_key, self.base_url, self.http_client)

    async def stream(
        self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelChunk]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(system, messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ChainStageError(f"modèle {self.model} : {type(exc).__name__} {_short(str(exc))}") from None
        pending: dict[int, dict[str, str]] = {}
        async for event in resp:
            usage = getattr(event, "usage", None)
            if usage is not None:
                yield ModelChunk(
                    tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
                    tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
                )
            for choice in getattr(event, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                if getattr(delta, "content", None):
                    yield ModelChunk(text=delta.content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = pending.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if fn.name:
                            slot["name"] += fn.name
                        if fn.arguments:
                            slot["args"] += fn.arguments
        for idx in sorted(pending):
            slot = pending[idx]
            yield ModelChunk(tool_call=ToolCall(
                id=slot["id"] or f"appel-{idx}", name=slot["name"], args=_parse_args(slot["args"])
            ))


def _parse_args(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format neutre → Messages API ; fusionne les rôles consécutifs."""
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for msg in messages:
        role = msg["role"]
        if role == "user":
            push("user", [{"type": "text", "text": msg["content"]}])
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for c in _tool_calls_of(msg):
                blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.args})
            push("assistant", blocks)
        elif role == "tool":
            push("user", [{
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg.get("content") or json.dumps({"error": "résultat absent"}),
            }])
    return out


@dataclass
class AnthropicChat:
    """Messages API d'Anthropic en flux SSE, par `httpx` (aucune dépendance ajoutée)."""

    model: str
    api_key: str = field(repr=False, default="")
    base_url: str = "https://api.anthropic.com"
    max_tokens: int = 1024
    timeout_s: float = 60.0
    http_client: httpx.AsyncClient | None = field(default=None, repr=False)
    name: str = ""

    API_VERSION = "2023-06-01"

    def __post_init__(self) -> None:
        self.name = self.name or f"anthropic:{self.model}"

    async def stream(
        self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelChunk]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": to_anthropic_messages(messages),
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_s)
        owns = self.http_client is None
        try:
            async with client.stream(
                "POST", self.base_url.rstrip("/") + "/v1/messages", headers=headers, json=body
            ) as resp:
                if resp.status_code >= 400:
                    raw = (await resp.aread()).decode(errors="replace")
                    try:
                        detail = json.loads(raw).get("error", {}).get("message", raw)
                    except (json.JSONDecodeError, AttributeError):
                        detail = raw
                    raise ChainStageError(f"modèle {self.model} : HTTP {resp.status_code} {_short(str(detail))}")
                async for chunk in _anthropic_events(resp):
                    yield chunk
        except httpx.HTTPError as exc:
            raise ChainStageError(f"modèle {self.model} : {type(exc).__name__}") from None
        finally:
            if owns:
                await client.aclose()


async def _anthropic_events(resp: httpx.Response) -> AsyncIterator[ModelChunk]:
    blocks: dict[int, dict[str, Any]] = {}
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        etype = ev.get("type")
        if etype == "message_start":
            usage = (ev.get("message") or {}).get("usage") or {}
            if usage.get("input_tokens"):
                yield ModelChunk(tokens_in=int(usage["input_tokens"]))
        elif etype == "content_block_start":
            cb = ev.get("content_block") or {}
            blocks[ev.get("index", 0)] = {"type": cb.get("type"), "id": cb.get("id", ""),
                                          "name": cb.get("name", ""), "json": ""}
        elif etype == "content_block_delta":
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield ModelChunk(text=delta["text"])
            elif delta.get("type") == "input_json_delta":
                blocks.setdefault(ev.get("index", 0), {"type": "tool_use", "id": "", "name": "", "json": ""})
                blocks[ev.get("index", 0)]["json"] += delta.get("partial_json", "")
        elif etype == "content_block_stop":
            blk = blocks.pop(ev.get("index", 0), None)
            if blk and blk.get("type") == "tool_use":
                yield ModelChunk(tool_call=ToolCall(id=blk["id"], name=blk["name"], args=_parse_args(blk["json"])))
        elif etype == "message_delta":
            usage = ev.get("usage") or {}
            if usage.get("output_tokens"):
                yield ModelChunk(tokens_out=int(usage["output_tokens"]))
        elif etype == "error":
            err = ev.get("error") or {}
            raise ChainStageError(f"modèle : {err.get('type', 'erreur')} {_short(str(err.get('message', '')))}")


@dataclass
class EchoChat:
    """Modèle local d'essai : répète la dernière phrase de l'utilisateur."""

    prefix: str = "Tu as dit : "
    name: str = "echo"

    async def stream(
        self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelChunk]:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        yield ModelChunk(text=f"{self.prefix}{last}")


# ---------------------------------------------------------------------------
# Synthèse vocale


def _even_chunks(data: bytes, size: int = TTS_CHUNK_BYTES) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


@dataclass
class MacSayTTS:
    """`say` de macOS vers un WAV PCM16, découpé en blocs de 100 ms."""

    voice: str = DEFAULT_SAY_VOICE
    sample_rate: int = 24000
    binary: str = "say"
    timeout_s: float = 30.0
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or f"say:{self.voice}"

    def check(self) -> None:
        if shutil.which(self.binary) is None:
            raise ChainConfigError(f"binaire introuvable : {self.binary} (macOS uniquement)")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        with tempfile.TemporaryDirectory(prefix="vr-chain-") as tmp:
            out_path = Path(tmp) / "phrase.wav"
            proc = await asyncio.create_subprocess_exec(
                self.binary, "-v", self.voice, "--file-format=WAVE",
                f"--data-format=LEI16@{self.sample_rate}", "-o", str(out_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, err = await asyncio.wait_for(proc.communicate(text.encode()), timeout=self.timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                raise ChainStageError(f"say : délai de {self.timeout_s:.0f} s dépassé")
            if proc.returncode != 0:
                raise ChainStageError(f"say : code {proc.returncode} — {_short(err.decode(errors='replace'))}")
            pcm, rate = wav_to_pcm16(out_path.read_bytes())
        pcm = resample_pcm16(pcm, rate, self.sample_rate)
        for chunk in _even_chunks(pcm):
            yield chunk


@dataclass
class OpenAICompatibleTTS:
    """`/audio/speech` en PCM16 24 kHz, lu en flux."""

    model: str
    voice: str = "alloy"
    api_key: str = field(repr=False, default="")
    base_url: str | None = None
    instructions: str | None = None
    http_client: httpx.AsyncClient | None = field(default=None, repr=False)
    sample_rate: int = 24000
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or f"tts:{self.model}:{self.voice}"
        self._client = _openai_client(self.api_key, self.base_url, self.http_client)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        kwargs: dict[str, Any] = {
            "model": self.model, "voice": self.voice, "input": text, "response_format": "pcm",
        }
        if self.instructions:
            kwargs["instructions"] = self.instructions
        carry = b""
        try:
            async with self._client.audio.speech.with_streaming_response.create(**kwargs) as resp:
                async for data in resp.iter_bytes(TTS_CHUNK_BYTES):
                    data = carry + data
                    cut = len(data) - (len(data) % 2)
                    carry = data[cut:]
                    if cut:
                        yield data[:cut]
        except ChainStageError:
            raise
        except Exception as exc:
            raise ChainStageError(f"synthèse {self.model} : {type(exc).__name__} {_short(str(exc))}") from None


# ---------------------------------------------------------------------------
# Fabrique


@dataclass(frozen=True)
class StageSpec:
    kind: str
    args: tuple[str, ...]
    base_url: str | None


def parse_spec(spec: str) -> StageSpec:
    """`genre[:arg1[:arg2]][@base_url]` ; l'URL peut contenir des « : »."""
    spec = (spec or "").strip()
    if not spec:
        raise ChainConfigError("spécification vide")
    base_url = None
    if "@" in spec:
        spec, base_url = spec.split("@", 1)
        base_url = base_url.strip() or None
    if spec.startswith("script:"):
        return StageSpec("script", (spec[len("script:"):],), base_url)
    parts = spec.split(":")
    return StageSpec(parts[0].strip().lower(), tuple(p.strip() for p in parts[1:]), base_url)


def _key(env: Mapping[str, str], name: str, *, compat: bool) -> str:
    if compat:
        return env.get("VOICE_REALTIME_CHAIN_COMPAT_API_KEY", "")
    value = env.get(name, "")
    if not value:
        raise ChainConfigError(f"clé {name} absente (à mettre dans le fichier de secrets)")
    return value


def _need_model(s: StageSpec, stage: str) -> str:
    if not s.args or not s.args[0]:
        raise ChainConfigError(f"{stage} : modèle requis, par exemple « {s.kind}:<modele> »")
    return s.args[0]


def build_stt(spec: str, env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    s = parse_spec(spec)
    if s.kind == "whisper-cpp":
        stt = WhisperCppSTT(model_path=Path(s.args[0]).expanduser() if s.args and s.args[0] else DEFAULT_WHISPER_MODEL)
        stt.check()
        return stt
    if s.kind == "openai":
        return OpenAICompatibleSTT(
            model=_need_model(s, "stt"), base_url=s.base_url,
            api_key=_key(env, "OPENAI_API_KEY", compat=bool(s.base_url)),
        )
    if s.kind == "script":
        return ScriptedSTT(phrases=[p.strip() for p in s.args[0].split("|")])
    raise ChainConfigError(f"stt inconnu : {s.kind} (whisper-cpp | openai | script)")


def build_llm(spec: str, env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    s = parse_spec(spec)
    if s.kind == "openai":
        return OpenAICompatibleChat(
            model=_need_model(s, "llm"), base_url=s.base_url,
            api_key=_key(env, "OPENAI_API_KEY", compat=bool(s.base_url)),
        )
    if s.kind == "anthropic":
        return AnthropicChat(
            model=_need_model(s, "llm"),
            base_url=s.base_url or "https://api.anthropic.com",
            api_key=_key(env, "ANTHROPIC_API_KEY", compat=False),
        )
    if s.kind == "echo":
        return EchoChat()
    raise ChainConfigError(f"llm inconnu : {s.kind} (openai | anthropic | echo)")


def build_tts(spec: str, env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    s = parse_spec(spec)
    if s.kind == "say":
        tts = MacSayTTS(voice=s.args[0] if s.args and s.args[0] else DEFAULT_SAY_VOICE)
        tts.check()
        return tts
    if s.kind == "openai":
        voice = s.args[1] if len(s.args) > 1 and s.args[1] else "alloy"
        return OpenAICompatibleTTS(
            model=_need_model(s, "tts"), voice=voice, base_url=s.base_url,
            api_key=_key(env, "OPENAI_API_KEY", compat=bool(s.base_url)),
        )
    raise ChainConfigError(f"tts inconnu : {s.kind} (say | openai)")


def build_chain_provider(
    stt: str, llm: str, tts: str, env: Mapping[str, str] | None = None, **kwargs: Any
) -> ChainProvider:
    missing = [n for n, v in (("--chain-stt", stt), ("--chain-llm", llm), ("--chain-tts", tts)) if not v]
    if missing:
        raise ChainConfigError(
            "mode chaîne : préciser " + ", ".join(missing)
            + " (ou VOICE_REALTIME_CHAIN_STT / _LLM / _TTS). Exemple : "
            "--chain-stt whisper-cpp --chain-llm anthropic:<modele> --chain-tts say:Thomas"
        )
    return ChainProvider(build_stt(stt, env), build_llm(llm, env), build_tts(tts, env), **kwargs)
