"""Mode chaîne (N2) — adaptateurs d'étages, sans réseau ni clé réelle.

Les API sont simulées par `httpx.MockTransport` rejouant des flux au format
documenté (`tests/fixtures/chain/*.sse`) ; whisper.cpp et `say` sont
remplacés par de faux binaires. Un essai avec le vrai `say` de macOS (local,
gratuit) tourne quand il est présent.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import wave
from pathlib import Path

import httpx
import pytest

from voice_realtime.providers.base import ToolSpec
from voice_realtime.providers.chain import ChainProvider, ChainStageError, ModelChunk, ToolCall
from voice_realtime.providers.chain_audio import pcm16_to_wav, resample_pcm16, wav_to_pcm16
from voice_realtime.providers.chain_replay import replay
from voice_realtime.providers.chain_stages import (
    AnthropicChat,
    ChainConfigError,
    EchoChat,
    MacSayTTS,
    OpenAICompatibleChat,
    OpenAICompatibleSTT,
    OpenAICompatibleTTS,
    ScriptedSTT,
    WhisperCppSTT,
    build_chain_provider,
    build_llm,
    build_stt,
    build_tts,
    parse_spec,
    to_anthropic_messages,
    to_openai_messages,
)

FIX = Path(__file__).parent / "fixtures" / "chain"
TOOL = ToolSpec(
    name="get_last_response",
    description="Dernier retour d'une session",
    parameters={"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]},
)
FAKE_KEY = "cle-de-test-0000"
HISTORY = [
    {"role": "user", "content": "Où en est le cockpit ?"},
    {"role": "assistant", "content": "Je regarde.", "tool_calls": [ToolCall(id="t1", name="get_last_response", args={"session_id": "cockpit"})]},
    {"role": "tool", "tool_call_id": "t1", "name": "get_last_response", "content": "{\"result\": \"revue finie\"}"},
    {"role": "user", "content": "[Note système] récap"},
    {"role": "user", "content": "Et la voix ?"},
]


def sse_response(name: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(FIX / name).read_bytes())


async def collect(stream) -> list[ModelChunk]:
    return [c async for c in stream]


# ---------------------------------------------------------------------------
# Spécifications et fabrique


def test_parse_spec() -> None:
    s = parse_spec("openai:llama-3.3-70b@https://api.groq.com/openai/v1")
    assert (s.kind, s.args, s.base_url) == ("openai", ("llama-3.3-70b",), "https://api.groq.com/openai/v1")
    assert parse_spec("say:Thomas").args == ("Thomas",)
    assert parse_spec("openai:gpt-4o-mini-tts:coral").args == ("gpt-4o-mini-tts", "coral")
    assert parse_spec("script:Bonjour : ça va ?|Au revoir").args == ("Bonjour : ça va ?|Au revoir",)
    with pytest.raises(ChainConfigError):
        parse_spec(" ")


def test_fabrique_exige_les_trois_etages_sans_choix_par_defaut() -> None:
    with pytest.raises(ChainConfigError) as exc:
        build_chain_provider("", "", "say", env={})
    assert "--chain-stt" in str(exc.value) and "--chain-llm" in str(exc.value)


def test_fabrique_cle_absente_nommee_sans_valeur() -> None:
    with pytest.raises(ChainConfigError) as exc:
        build_llm("anthropic:modele-test", env={})
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    with pytest.raises(ChainConfigError):
        build_stt("openai:modele-stt", env={})


def test_fabrique_modele_requis_et_genre_inconnu() -> None:
    with pytest.raises(ChainConfigError, match="modèle requis"):
        build_llm("openai", env={"OPENAI_API_KEY": FAKE_KEY})
    with pytest.raises(ChainConfigError, match="inconnu"):
        build_tts("piper", env={})
    with pytest.raises(ChainConfigError, match="inconnu"):
        build_stt("vosk", env={})


def test_fabrique_api_compatible_sans_cle_officielle() -> None:
    llm = build_llm("openai:qwen2.5:3b@http://127.0.0.1:11434/v1", env={})
    assert isinstance(llm, OpenAICompatibleChat)
    assert llm.model == "qwen2.5" and llm.base_url == "http://127.0.0.1:11434/v1"
    llm2 = build_llm("openai:modele@http://127.0.0.1:1/v1", env={"VOICE_REALTIME_CHAIN_COMPAT_API_KEY": FAKE_KEY})
    assert FAKE_KEY not in repr(llm2)


def test_fabrique_construit_une_chaine_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"x")
    fake_bin = tmp_path / "whisper-cli"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    say_bin = tmp_path / "say"
    if shutil.which("say") is None:
        say_bin.write_text("#!/bin/sh\n")
        say_bin.chmod(0o755)
    p = build_chain_provider(f"whisper-cpp:{model}", "echo", "say:Thomas", env={})
    assert isinstance(p, ChainProvider)
    assert p.label == "whisper-cpp → echo → say:Thomas"
    assert p.output_sample_rate == 24000
    with pytest.raises(ChainConfigError, match="modèle whisper introuvable"):
        build_stt(f"whisper-cpp:{tmp_path / 'absent.bin'}", env={})


# ---------------------------------------------------------------------------
# Conversions d'historique


def test_historique_vers_openai() -> None:
    msgs = to_openai_messages("Tu es Jarvis.", HISTORY)
    assert msgs[0] == {"role": "system", "content": "Tu es Jarvis."}
    assert msgs[2]["tool_calls"][0] == {
        "id": "t1", "type": "function",
        "function": {"name": "get_last_response", "arguments": "{\"session_id\": \"cockpit\"}"},
    }
    assert msgs[3] == {"role": "tool", "tool_call_id": "t1", "content": "{\"result\": \"revue finie\"}"}
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "user", "user"]


def test_historique_vers_anthropic_fusionne_les_roles() -> None:
    msgs = to_anthropic_messages(HISTORY + [{"role": "assistant", "content": "", "tool_calls": []}])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"][1] == {"type": "tool_use", "id": "t1", "name": "get_last_response", "input": {"session_id": "cockpit"}}
    third = msgs[2]["content"]
    assert third[0]["type"] == "tool_result" and third[0]["tool_use_id"] == "t1"
    assert [b.get("text") for b in third[1:]] == ["[Note système] récap", "Et la voix ?"]


# ---------------------------------------------------------------------------
# Modèles sur flux enregistrés


async def test_openai_chat_en_flux() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return sse_response("openai_chat_stream.sse")

    chat = OpenAICompatibleChat(
        model="modele-test", api_key=FAKE_KEY, base_url="https://api.exemple.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    chunks = await collect(chat.stream("Tu es Jarvis.", HISTORY[:1], [TOOL]))
    assert "".join(c.text for c in chunks) == "Je regarde tes sessions."
    calls = [c.tool_call for c in chunks if c.tool_call]
    assert calls == [ToolCall(id="call_abc", name="get_last_response", args={"session_id": "cockpit"})]
    assert sum(c.tokens_in for c in chunks) == 412 and sum(c.tokens_out for c in chunks) == 23
    assert seen["url"] == "https://api.exemple.test/v1/chat/completions"
    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    body = seen["body"]
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["tools"][0]["function"]["name"] == "get_last_response"
    assert body["messages"][0]["role"] == "system"


async def test_openai_chat_erreur_sans_fuite_de_cle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}})

    chat = OpenAICompatibleChat(model="m", api_key=FAKE_KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ChainStageError) as exc:
        await collect(chat.stream("", HISTORY[:1], []))
    assert FAKE_KEY not in str(exc.value)


async def test_anthropic_en_flux() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return sse_response("anthropic_messages_stream.sse")

    chat = AnthropicChat(model="modele-test", api_key=FAKE_KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    chunks = await collect(chat.stream("Tu es Jarvis.", HISTORY, [TOOL]))
    assert "".join(c.text for c in chunks) == "Je regarde tes sessions."
    assert [c.tool_call for c in chunks if c.tool_call] == [
        ToolCall(id="toolu_01", name="get_last_response", args={"session_id": "cockpit"})
    ]
    assert sum(c.tokens_in for c in chunks) == 388 and sum(c.tokens_out for c in chunks) == 41
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == FAKE_KEY
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    body = seen["body"]
    assert body["system"] == "Tu es Jarvis." and body["stream"] is True
    assert body["tools"] == [{"name": TOOL.name, "description": TOOL.description, "input_schema": TOOL.parameters}]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]


async def test_anthropic_erreur_http_sans_fuite_de_cle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    chat = AnthropicChat(model="m", api_key=FAKE_KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ChainStageError) as exc:
        await collect(chat.stream("", HISTORY[:1], []))
    assert "401" in str(exc.value) and "invalid x-api-key" in str(exc.value)
    assert FAKE_KEY not in str(exc.value) and FAKE_KEY not in repr(chat)


async def test_echo() -> None:
    chunks = await collect(EchoChat().stream("", HISTORY, []))
    assert chunks[0].text == "Tu as dit : Et la voix ?"


# ---------------------------------------------------------------------------
# Reconnaissance vocale


async def test_openai_stt_envoie_un_wav() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " Liste mes sessions en cours. "})

    pcm, rate = wav_to_pcm16((FIX / "coupure.wav").read_bytes())
    stt = OpenAICompatibleSTT(model="modele-stt", api_key=FAKE_KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await stt.transcribe(pcm, rate) == "Liste mes sessions en cours."
    assert seen["url"].endswith("/audio/transcriptions")
    assert b'name="model"' in seen["body"] and b"modele-stt" in seen["body"]
    assert b'name="language"' in seen["body"] and b"RIFF" in seen["body"]


def _fake_bin(tmp_path: Path, body: str) -> Path:
    """Faux binaire : enveloppe shell (le chemin de Python peut contenir une espace)."""
    code = tmp_path / "faux.py"
    code.write_text(body)
    script = tmp_path / "faux-binaire"
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{code}" "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


async def test_whisper_cpp_sur_enregistrement(tmp_path: Path) -> None:
    log = tmp_path / "args.json"
    script = _fake_bin(tmp_path, f"""
import json, sys, wave
args = sys.argv[1:]
wav = args[args.index('-f') + 1]
with wave.open(wav) as w:
    info = [w.getframerate(), w.getnchannels(), w.getnframes()]
json.dump({{"args": args, "wav": info}}, open({str(log)!r}, "w"))
print(" Liste mes sessions\\n en cours. ")
""")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"x")
    pcm, rate = wav_to_pcm16((FIX / "coupure.wav").read_bytes())
    stt = WhisperCppSTT(model_path=model, binary=str(script))
    stt.check()
    # Audio à 24 kHz : rééchantillonné à 16 kHz pour whisper.
    text = await stt.transcribe(resample_pcm16(pcm, rate, 24000), 24000)
    assert text == "Liste mes sessions en cours."
    seen = json.loads(log.read_text())
    assert seen["wav"][0] == 16000 and seen["wav"][1] == 1
    assert abs(seen["wav"][2] - len(pcm) // 2) < 20
    assert seen["args"][:4] == ["-m", str(model), "-l", "fr"] and "-nt" in seen["args"]


async def test_whisper_cpp_echec_signale(tmp_path: Path) -> None:
    script = _fake_bin(tmp_path, "import sys\nsys.stderr.write('error: failed to initialize whisper context')\nsys.exit(3)")
    stt = WhisperCppSTT(model_path=tmp_path, binary=str(script))
    with pytest.raises(ChainStageError, match="code 3 .*failed to initialize"):
        await stt.transcribe(b"\x00\x00" * 1600, 16000)


# ---------------------------------------------------------------------------
# Synthèse vocale


async def test_openai_tts_pcm_en_blocs_pairs() -> None:
    audio = bytes(range(256)) * 100 + b"\x07"  # longueur impaire : dernier octet orphelin
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "audio/pcm"}, content=audio)

    tts = OpenAICompatibleTTS(model="modele-tts", voice="coral", api_key=FAKE_KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    chunks = [c async for c in tts.synthesize("Bonjour Stéphane.")]
    assert all(len(c) % 2 == 0 for c in chunks)
    assert b"".join(chunks) == audio[:-1]
    assert seen["body"] == {"model": "modele-tts", "voice": "coral", "input": "Bonjour Stéphane.", "response_format": "pcm"}
    assert tts.sample_rate == 24000


async def test_say_par_faux_binaire(tmp_path: Path) -> None:
    script = _fake_bin(tmp_path, """
import sys, wave
args = sys.argv[1:]
out = args[args.index('-o') + 1]
text = sys.stdin.read()
assert args[args.index('-v') + 1] == 'Thomas' and '--data-format=LEI16@24000' in args
with wave.open(out, 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
    w.writeframes(b'\\x10\\x00' * (240 * len(text)))
""")
    tts = MacSayTTS(binary=str(script))
    chunks = [c async for c in tts.synthesize("Bonjour.")]
    assert sum(len(c) for c in chunks) == 2 * 240 * len("Bonjour.")
    assert all(len(c) <= 4800 for c in chunks)


@pytest.mark.skipif(shutil.which("say") is None, reason="say absent (macOS uniquement)")
async def test_chaine_locale_avec_le_vrai_say() -> None:
    """Enregistrement → transcription imposée → écho → vraie voix `say`, sans réseau."""
    pcm, rate = wav_to_pcm16((FIX / "coupure.wav").read_bytes())
    provider = ChainProvider(ScriptedSTT(["Attends, arrête-toi."]), EchoChat(), MacSayTTS(voice="Thomas"))
    res = await replay(provider, pcm, rate)
    assert res.texts("final_transcript_model") == ["Tu as dit : Attends, arrête-toi."]
    seconds = len(res.audio_out) / (2 * 24000)
    assert 1.0 < seconds < 6.0
    # La voix produite est audible et se relit comme un WAV valide.
    wav = pcm16_to_wav(res.audio_out, 24000)
    assert wav_to_pcm16(wav)[1] == 24000
    assert max(abs(int.from_bytes(res.audio_out[i:i + 2], "little", signed=True)) for i in range(0, len(res.audio_out), 200)) > 1000


# ---------------------------------------------------------------------------
# Commande `chain-rejouer`


def test_commande_chain_rejouer_sans_specification() -> None:
    from typer.testing import CliRunner

    from voice_realtime.cli import app

    res = CliRunner().invoke(app, ["chain-rejouer", str(FIX / "coupure.wav"), "--chain-llm", "echo"],
                             env={"VOICE_REALTIME_CHAIN_STT": "", "VOICE_REALTIME_CHAIN_TTS": ""})
    assert res.exit_code == 1
    assert "--chain-stt" in res.output


@pytest.mark.skipif(shutil.which("say") is None, reason="say absent (macOS uniquement)")
def test_commande_chain_rejouer_locale(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from voice_realtime.cli import app

    out = tmp_path / "sortie.wav"
    res = CliRunner().invoke(app, [
        "chain-rejouer", str(FIX / "deux_phrases.wav"),
        "--chain-stt", "script:Liste mes sessions en cours.|Quel est le dernier retour ?",
        "--chain-llm", "echo", "--chain-tts", "say:Thomas", "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    assert "Utilisateur : Liste mes sessions en cours." in res.output
    assert "Modèle : Tu as dit : Quel est le dernier retour ?" in res.output
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnframes() > 24000
