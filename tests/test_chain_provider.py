"""Mode chaîne (N2) — ChainProvider rejoué sur enregistrements, sans réseau.

Les enregistrements de `tests/fixtures/chain/` sont de vrais fichiers audio :
voix française de synthèse `say` sur bruit de fond, et `jfk.wav` (voix
humaine, domaine public). Les étages STT, modèle et synthèse sont des faux
déterministes : on teste le découpage, l'ordre des événements, les outils,
la coupure de parole et l'historique.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

from voice_realtime.providers.base import ProviderConfig, RealtimeVoiceProvider, ToolSpec
from voice_realtime.providers.chain import ChainProvider, ChainStageError, ModelChunk, ToolCall, pop_sentences
from voice_realtime.providers.chain_audio import Endpointer, rms, wav_to_pcm16
from voice_realtime.providers.chain_replay import replay
from voice_realtime.providers.chain_stages import ScriptedSTT

FIX = Path(__file__).parent / "fixtures" / "chain"
MANIFEST = json.loads((FIX / "enregistrements.json").read_text())


def load(name: str) -> tuple[bytes, int]:
    return wav_to_pcm16((FIX / name).read_bytes())


class FakeTTS:
    """100 ms de PCM 24 kHz par phrase, avec pause réglable entre blocs."""

    name = "faux-tts"
    sample_rate = 24000

    def __init__(self, chunks_per_sentence: int = 1, delay_s: float = 0.0) -> None:
        self.chunks = chunks_per_sentence
        self.delay = delay_s
        self.said: list[str] = []

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.said.append(text)
        for _ in range(self.chunks):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield b"\x01\x00" * 2400


class ScriptedChat:
    """Chaque appel consomme une réponse scriptée (liste de ModelChunk)."""

    name = "faux-modele"

    def __init__(self, replies: list[list[ModelChunk]], delay_s: float = 0.0) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.delay = delay_s

    async def stream(self, system, messages, tools) -> AsyncIterator[ModelChunk]:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": list(tools)})
        reply = self.replies.pop(0) if self.replies else [ModelChunk(text="Rien à ajouter.")]
        for chunk in reply:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk


def say(text: str) -> list[ModelChunk]:
    # Découpage en petits morceaux, comme un vrai flux.
    return [ModelChunk(text=text[i : i + 7]) for i in range(0, len(text), 7)]


LIST_SESSIONS = ToolSpec(name="list_sessions", description="Liste les sessions", parameters={"type": "object", "properties": {}})


# ---------------------------------------------------------------------------
# Détection de parole sur enregistrements


@pytest.mark.parametrize("vad", ["reactive", "balanced", "patient"])
def test_endpointer_decoupe_deux_phrases_enregistrees(vad: str) -> None:
    pcm, rate = load("deux_phrases.wav")
    ep = Endpointer.for_vad(vad, rate)
    events = []
    for i in range(0, len(pcm), 3200):  # blocs micro de 100 ms
        events += ep.feed(pcm[i : i + 3200])
    events += ep.flush()
    utterances = [e for e in events if e.kind == "utterance"]
    assert [e.kind for e in events] == ["speech_start", "utterance"] * 2
    for utt, seg in zip(utterances, MANIFEST["deux_phrases.wav"]["segments"]):
        # Le préroulage (300 ms) et le silence de fin encadrent la phrase.
        assert utt.start_ms <= seg["debut_ms"] <= utt.start_ms + 400
        assert seg["fin_ms"] <= utt.end_ms <= seg["fin_ms"] + 1500
        assert len(utt.pcm16) == (utt.end_ms - utt.start_ms) * rate // 1000 * 2


def test_endpointer_suit_une_voix_humaine_enregistree() -> None:
    pcm, rate = load("jfk.wav")
    ep = Endpointer.for_vad("balanced", rate)
    events = []
    for i in range(0, len(pcm), 3200):
        events += ep.feed(pcm[i : i + 3200])
    events += ep.flush()
    utterances = [e for e in events if e.kind == "utterance"]
    assert len(utterances) >= 2  # le discours a des pauses
    assert utterances[0].start_ms < 500
    covered = sum(u.end_ms - u.start_ms for u in utterances)
    assert covered >= 0.8 * MANIFEST["jfk.wav"]["duree_ms"]


def test_endpointer_ignore_le_bruit_de_fond_seul() -> None:
    pcm, rate = load("deux_phrases.wav")
    noise_only = pcm[: 500 * rate // 1000 * 2] * 10  # 5 s de bruit de la pièce
    ep = Endpointer(sample_rate=rate)
    assert ep.feed(noise_only) == []
    assert ep.flush() == []
    assert 0.003 < ep.noise_floor < 0.006


def test_endpointer_coupe_un_enonce_trop_long() -> None:
    pcm, rate = load("jfk.wav")
    ep = Endpointer(sample_rate=rate, silence_ms=5000, max_utterance_ms=2000)
    events = ep.feed(pcm)
    utterances = [e for e in events if e.kind == "utterance"]
    assert utterances and all(u.end_ms - u.start_ms <= 2400 for u in utterances)


def test_rms_et_phrases() -> None:
    assert rms(b"") == 0.0
    assert rms(b"\xff\x7f" * 10) == pytest.approx(1.0, abs=1e-3)
    phrases, reste = pop_sentences("Bonjour Stéphane. Trois sessions tournent : cockpit, voix")
    assert phrases == ["Bonjour Stéphane.", "Trois sessions tournent :"]
    assert reste.strip() == "cockpit, voix"
    # Une phrase trop courte reste dans le tampon.
    assert pop_sentences("Oui. ") == ([], "Oui. ")


# ---------------------------------------------------------------------------
# Conversation complète sur enregistrement


def test_chain_provider_respecte_le_protocole() -> None:
    p: RealtimeVoiceProvider = ChainProvider(ScriptedSTT([]), ScriptedChat([]), FakeTTS())
    assert p.name == "chain"
    assert "faux-modele" in p.label


async def test_conversation_sur_deux_phrases_enregistrees() -> None:
    pcm, rate = load("deux_phrases.wav")
    stt = ScriptedSTT(["Liste mes sessions en cours.", "Quel est le dernier retour ?"])
    chat = ScriptedChat([say("Trois sessions tournent. Le cockpit est actif."), say("Le cockpit a fini sa revue.")])
    tts = FakeTTS()
    res = await replay(ChainProvider(stt, chat, tts), pcm, rate, system_prompt="Tu es Jarvis.")

    # Deux énoncés reçus par la reconnaissance, à 16 kHz, de la bonne durée.
    assert [r[1] for r in stt.received] == [16000, 16000]
    for (nbytes, _), seg in zip(stt.received, MANIFEST["deux_phrases.wav"]["segments"]):
        assert nbytes / (2 * rate) * 1000 >= seg["fin_ms"] - seg["debut_ms"]

    assert res.texts("final_transcript_user") == ["Liste mes sessions en cours.", "Quel est le dernier retour ?"]
    assert res.texts("final_transcript_model") == [
        "Trois sessions tournent. Le cockpit est actif.",
        "Le cockpit a fini sa revue.",
    ]
    # Synthèse phrase par phrase, dès qu'une phrase est complète.
    assert tts.said == ["Trois sessions tournent.", "Le cockpit est actif.", "Le cockpit a fini sa revue."]
    assert "model_interrupted" not in res.kinds()  # réponses courtes : finies avant la reprise
    first_turn = res.kinds()[: res.kinds().index("session_closed") + 1]
    assert first_turn[0] == "final_transcript_user"
    assert first_turn.index("partial_transcript_model") < first_turn.index("audio_chunk_out")
    assert first_turn[-2:] == ["final_transcript_model", "session_closed"]
    assert len(res.audio_out) == 3 * 4800
    # Le modèle reçoit la consigne système et l'historique complet.
    assert chat.calls[1]["system"] == "Tu es Jarvis."
    assert [m["role"] for m in chat.calls[1]["messages"]] == ["user", "assistant", "user"]
    assert len(res.metrics) == 2 and res.metrics[0].first_audio_ms is not None


async def test_appel_d_outil_puis_reponse_parlee() -> None:
    pcm, rate = load("coupure.wav")
    stt = ScriptedSTT(["Liste mes sessions."])
    chat = ScriptedChat([
        [ModelChunk(tool_call=ToolCall(id="c1", name="list_sessions", args={})), ModelChunk(tokens_in=120, tokens_out=8)],
        say("Tu as deux sessions : cockpit et voix.") + [ModelChunk(tokens_in=180, tokens_out=12)],
    ])
    seen: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        seen.append((name, args))
        return {"result": {"sessions": ["cockpit", "voix"]}}

    provider = ChainProvider(stt, chat, FakeTTS())
    res = await replay(provider, pcm, rate, tools=[LIST_SESSIONS], tool_handler=handler)

    assert seen == [("list_sessions", {})]
    tool_events = [e for e in res.events if e.kind == "tool_call"]
    assert tool_events[0].data == {"call_id": "c1", "name": "list_sessions", "args": {}}
    # Le second appel au modèle voit l'appel et son résultat, dans l'ordre.
    msgs = chat.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "tool"]
    assert msgs[1]["tool_calls"][0].name == "list_sessions"
    assert json.loads(msgs[2]["content"]) == {"result": {"sessions": ["cockpit", "voix"]}}
    assert chat.calls[0]["tools"] == [LIST_SESSIONS]
    assert res.texts("final_transcript_model") == ["Tu as deux sessions : cockpit et voix."]
    costs = [e.data for e in res.events if e.kind == "cost_update"]
    assert costs == [
        {"tokens_in": 120, "tokens_out": 8, "mode": "delta"},
        {"tokens_in": 180, "tokens_out": 12, "mode": "delta"},
    ]
    assert res.metrics[0].tool_calls == 1


async def test_refus_du_garde_fou_rendu_au_modele() -> None:
    """Le refus serveur (ToolResult d'erreur) est rendu tel quel : rien n'est décidé ici."""
    pcm, rate = load("coupure.wav")
    chat = ScriptedChat([
        [ModelChunk(tool_call=ToolCall(id="c9", name="send_instruction", args={"session_id": "x", "instruction": "rm"}))],
        say("Le serveur a refusé la consigne."),
    ])

    async def handler(name: str, args: dict) -> dict:
        return {"error": "refus garde-fou : consigne sensible, confirmation requise"}

    res = await replay(ChainProvider(ScriptedSTT(["Envoie rm."]), chat, FakeTTS()), pcm, rate, tool_handler=handler)
    tool_msg = chat.calls[1]["messages"][2]
    assert "refus garde-fou" in tool_msg["content"]
    assert res.texts("final_transcript_model") == ["Le serveur a refusé la consigne."]


async def test_limite_des_tours_d_outils() -> None:
    pcm, rate = load("coupure.wav")
    loop_call = [ModelChunk(tool_call=ToolCall(id="", name="list_sessions", args={}))]
    chat = ScriptedChat([loop_call, loop_call, say("Je m'arrête là, voici le point.")])
    calls = 0

    async def handler(name: str, args: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"result": []}

    provider = ChainProvider(ScriptedSTT(["Boucle."]), chat, FakeTTS(), max_tool_rounds=2)
    await replay(provider, pcm, rate, tools=[LIST_SESSIONS], tool_handler=handler)
    assert calls == 2
    assert chat.calls[2]["tools"] == []  # dernier tour : réponse parlée obligatoire


# ---------------------------------------------------------------------------
# Coupure de parole


async def test_coupure_pendant_la_reponse_parlee() -> None:
    """L'utilisateur reprend pendant la synthèse : réponse annulée, seul le parlé reste."""
    first, rate = load("deux_phrases.wav")
    first = first[: 3000 * rate // 1000 * 2]  # première phrase et son silence
    barge, _ = load("coupure.wav")
    stt = ScriptedSTT(["Raconte-moi la nuit.", "Attends, arrête-toi."])
    long_reply = say("Première phrase de la longue réponse. Deuxième phrase. Troisième phrase. Quatrième phrase.")
    chat = ScriptedChat([long_reply, say("D'accord, je t'écoute.")])
    tts = FakeTTS(chunks_per_sentence=5, delay_s=0.02)
    provider = ChainProvider(stt, chat, tts)

    async def barge_in(idx: int) -> None:
        # Dès que la première réponse sonne, l'utilisateur coupe.
        if idx == len(first) // 3200 - 1:
            for _ in range(200):
                if provider._turn is not None and provider._turn.audio_emitted:
                    break
                await asyncio.sleep(0.01)
            await provider.send_audio_chunk(barge)
            await provider.end_of_audio()

    res = await replay(provider, first, rate, wait_turns=False, after_chunk=barge_in)
    kinds = res.kinds()
    assert "model_interrupted" in kinds
    assert res.texts("final_transcript_user") == ["Raconte-moi la nuit.", "Attends, arrête-toi."]
    assert res.texts("final_transcript_model") == ["D'accord, je t'écoute."]
    assistant = [m for m in provider.history if m["role"] == "assistant"]
    assert assistant[0]["content"].startswith("Première phrase")
    assert "Quatrième" not in assistant[0]["content"]
    assert res.metrics[0].interrupted is True


async def test_coupure_quand_l_audio_sonne_encore() -> None:
    """Synthèse finie mais lecture en cours chez l'utilisateur : coupure quand même."""
    provider = ChainProvider(ScriptedSTT(["Salut."]), ScriptedChat([say("Bonjour Stéphane, je t'écoute.")]), FakeTTS(chunks_per_sentence=30))
    t = {"now": 0.0}
    provider.clock = lambda: t["now"]
    await provider.connect(ProviderConfig(model="x", api_key=""), "sys")
    events = []

    async def pump():
        async for ev in provider.receive_events():
            events.append(ev.kind)

    task = asyncio.create_task(pump())
    await provider.send_text("Salut.")
    await provider.wait_idle()
    assert not provider.busy
    t["now"] = 1.0  # 3 s d'audio produits, 1 s écoulée
    barge, rate = load("coupure.wav")
    await provider.send_audio_chunk(barge[: 800 * rate // 1000 * 2])
    await asyncio.sleep(0)
    await provider.close()
    await task
    assert "model_interrupted" in events


async def test_reprise_pendant_la_transcription_regroupe_les_phrases() -> None:
    """Reprise avant toute réponse : on ne répond qu'une fois, aux deux phrases."""

    class SlowSTT(ScriptedSTT):
        async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
            text = await super().transcribe(pcm16, sample_rate)
            await asyncio.sleep(0.05)
            return text

    pcm, rate = load("coupure.wav")
    chat = ScriptedChat([say("Je réponds aux deux.")])
    provider = ChainProvider(SlowSTT(["Je voulais dire", "et aussi ceci."]), chat, FakeTTS())

    async def second_phrase(idx: int) -> None:
        if idx == len(pcm) // 3200 - 1:
            await asyncio.sleep(0.01)  # la première transcription est en cours
            await provider.send_audio_chunk(pcm)
            await provider.end_of_audio()

    res = await replay(provider, pcm, rate, wait_turns=False, after_chunk=second_phrase)
    assert len(chat.calls) == 1
    assert [m["content"] for m in chat.calls[0]["messages"]] == ["Je voulais dire", "et aussi ceci."]
    assert res.texts("final_transcript_model") == ["Je réponds aux deux."]


async def test_resultat_d_outil_tardif_garde_apres_coupure() -> None:
    """Un outil lancé reste valable : son résultat rejoint l'historique du tour suivant."""
    chat = ScriptedChat([
        [ModelChunk(tool_call=ToolCall(id="c1", name="list_sessions", args={}))],
        say("Réponse au premier tour."),
        say("Voici les sessions."),
    ])
    provider = ChainProvider(ScriptedSTT([]), chat, FakeTTS(), tool_result_timeout_s=2)
    await provider.connect(ProviderConfig(model="x", api_key=""), "sys", tools=[LIST_SESSIONS])
    events: list = []

    async def pump():
        async for ev in provider.receive_events():
            events.append(ev)

    task = asyncio.create_task(pump())
    await provider.send_text("Liste les sessions.")
    for _ in range(100):
        if any(e.kind == "tool_call" for e in events):
            break
        await asyncio.sleep(0.01)
    # Coupure pendant l'attente du résultat : le tour est annulé.
    await provider._interrupt()
    await provider.send_text("Alors ?")
    await asyncio.sleep(0.02)
    await provider.send_function_response("c1", "list_sessions", {"result": ["cockpit"]})
    await provider.wait_idle()
    await provider.close()
    await task
    last_call = chat.calls[-1]["messages"]
    tool_msgs = [m for m in last_call if m["role"] == "tool"]
    assert json.loads(tool_msgs[0]["content"]) == {"result": ["cockpit"]}
    assert [m["role"] for m in last_call] == ["user", "assistant", "tool", "user"]


# ---------------------------------------------------------------------------
# Texte, notes silencieuses, erreurs, mot d'arrêt


async def test_texte_de_demarrage_et_note_silencieuse() -> None:
    chat = ScriptedChat([say("Salut Stéphane, je suis connecté, je t'écoute."), say("Noté, on continue.")])
    provider = ChainProvider(ScriptedSTT([]), chat, FakeTTS())
    await provider.connect(ProviderConfig(model="x", api_key=""), "sys")
    events: list = []

    async def pump():
        async for ev in provider.receive_events():
            events.append(ev)

    task = asyncio.create_task(pump())
    await provider.send_text("Démarre.")
    await provider.wait_idle()
    await provider.send_silent_note("[Note système — rappel contexte conversation, NE RÉPONDS PAS] récap")
    await asyncio.sleep(0)
    assert len(chat.calls) == 1  # la note ne déclenche aucune réponse
    await provider.send_text("Et maintenant ?")
    await provider.wait_idle()
    await provider.close()
    await task
    assert [m["content"][:6] for m in chat.calls[1]["messages"] if m["role"] == "user"] == ["Démarr", "[Note ", "Et mai"]
    assert [e.data["text"] for e in events if e.kind == "final_transcript_model"][0].startswith("Salut Stéphane")


async def test_erreur_d_etage_puis_conversation_continue() -> None:
    class FlakySTT:
        name = "instable"

        def __init__(self) -> None:
            self.n = 0

        async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
            self.n += 1
            if self.n == 1:
                raise ChainStageError("transcription : délai dépassé")
            return "Deuxième essai."

    pcm, rate = load("deux_phrases.wav")
    res = await replay(ChainProvider(FlakySTT(), ScriptedChat([say("Bien reçu cette fois.")]), FakeTTS()), pcm, rate)
    errors = [e for e in res.events if e.kind == "error"]
    assert len(errors) == 1 and "délai dépassé" in errors[0].data["exception"]
    assert res.texts("final_transcript_user") == ["Deuxième essai."]
    assert res.texts("final_transcript_model") == ["Bien reçu cette fois."]


async def test_enonce_vide_ignore() -> None:
    pcm, rate = load("coupure.wav")
    chat = ScriptedChat([])
    res = await replay(ChainProvider(ScriptedSTT([""]), chat, FakeTTS()), pcm, rate)
    assert chat.calls == []
    assert "final_transcript_user" not in res.kinds()


async def test_mot_d_arret_enregistre_detecte_par_la_cli() -> None:
    from voice_realtime.cli import _is_killchat_keyword

    pcm, rate = load("killchat.wav")
    res = await replay(ChainProvider(ScriptedSTT(["Killchat."]), ScriptedChat([]), FakeTTS()), pcm, rate)
    users = res.texts("final_transcript_user")
    assert users == ["Killchat."]
    assert _is_killchat_keyword(users[0])


async def test_resultat_d_outil_inconnu_ignore() -> None:
    provider = ChainProvider(ScriptedSTT([]), ScriptedChat([]), FakeTTS())
    await provider.connect(ProviderConfig(model="x", api_key=""), "sys")
    await provider.send_function_response("inconnu", "list_sessions", {"result": 1})
    await provider.close()
    assert provider.history == []
