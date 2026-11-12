"""N4 — pont d'appel : page ↔ fournisseur, sans réseau ni navigateur."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.faux_telephone import FauxFournisseur, FauxTransport, appel_essai, registre_essai
from voice_realtime.providers.chain import ChainProvider, ModelChunk, ToolCall
from voice_realtime.providers.chain_audio import wav_to_pcm16
from voice_realtime.providers.chain_stages import EchoChat, ScriptedSTT
from voice_realtime.telephone.pont import TAILLE_MAX_TRAME, PontAppel

FIX = Path(__file__).parent / "fixtures" / "chain"


async def ouvrir(**kwargs) -> tuple[PontAppel, FauxFournisseur, FauxTransport]:
    f = kwargs.pop("fournisseur", None) or FauxFournisseur()
    t = FauxTransport()
    pont = PontAppel(appel_essai(f, **kwargs), t, intervalle_controle_s=0.05)
    await pont.demarrer()
    return pont, f, t


async def test_ouverture_annonce_les_frequences_et_les_outils() -> None:
    pont, f, t = await ouvrir(registre=registre_essai(), salutation=True)
    pret = t.evenements("pret")[0]
    assert pret["entree"] == 16000 and pret["sortie"] == 24000
    assert pret["outils"] == ["lister", "ecrire", "casser"]
    assert [o.name for o in f.outils] == ["lister", "ecrire", "casser"]
    assert f.consigne == "Consigne d'essai."
    assert f.textes == ["Démarre."]
    await pont.terminer("raccroche")


async def test_sans_salutation_ni_outils() -> None:
    pont, f, t = await ouvrir()
    assert f.textes == [] and f.outils is None
    assert t.evenements("pret")[0]["outils"] == []
    await pont.terminer("raccroche")


async def test_audio_transmis_sauf_en_muet_et_trames_invalides_refusees() -> None:
    pont, f, t = await ouvrir()
    await pont.recevoir_audio(b"\x01\x00" * 320)
    await pont.recevoir_commande({"op": "muet", "actif": True})
    await pont.recevoir_audio(b"\x02\x00" * 320)
    await pont.recevoir_commande({"op": "muet", "actif": False})
    await pont.recevoir_audio(b"\x01")  # longueur impaire
    await pont.recevoir_audio(b"\x00" * (TAILLE_MAX_TRAME + 2))
    await pont.recevoir_audio(b"\x03\x00" * 320)
    assert f.audio == [b"\x01\x00" * 320, b"\x03\x00" * 320]
    assert [m["actif"] for m in t.evenements("muet")] == [True, False]
    assert [m["code"] for m in t.evenements("erreur")] == ["trame_invalide", "trame_invalide"]
    assert pont.octets_recus == 1280
    await pont.terminer("raccroche")


async def test_evenements_du_fournisseur_vers_la_page() -> None:
    pont, f, t = await ouvrir()
    await f.pousser("final_transcript_user", text="Liste mes sessions.")
    await f.pousser("partial_transcript_model", text="Une ")
    await f.pousser("audio_chunk_out", pcm16=b"\x05\x00" * 100)
    await f.pousser("model_interrupted")
    await f.pousser("final_transcript_model", text="Une session.")
    await f.pousser("cost_update", tokens_in=10, tokens_out=4, mode="delta")
    await t.attendre(lambda: len(t.evenements("transcription")) == 3)
    assert [(m["role"], m["texte"], m["final"]) for m in t.evenements("transcription")] == [
        ("utilisateur", "Liste mes sessions.", True),
        ("modele", "Une ", False),
        ("modele", "Une session.", True),
    ]
    assert t.audio == [b"\x05\x00" * 100]
    assert len(t.evenements("interrompu")) == 1
    await t.attendre(lambda: pont.tracker.real_tokens_in == 10)
    await pont.terminer("raccroche")
    assert t.evenements("fin") == [{"ev": "fin", "motif": "raccroche"}]
    assert f.ferme


async def test_mot_arret_final_termine_l_appel() -> None:
    pont, f, t = await ouvrir()
    await f.pousser("final_transcript_user", text="Termine la session.")
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "mot_arret"
    assert f.ferme


async def test_mot_arret_reconstitue_depuis_les_partiels() -> None:
    pont, f, t = await ouvrir()
    for morceau in ("fin ", "jar", "vis"):
        await f.pousser("partial_transcript_user", text=morceau)
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "mot_arret"


async def test_partiels_reinitialises_quand_le_modele_parle() -> None:
    pont, f, t = await ouvrir()
    await f.pousser("partial_transcript_user", text="fin ")
    await f.pousser("audio_chunk_out", pcm16=b"\x00\x00" * 10)
    await f.pousser("partial_transcript_user", text="jarvis")
    await t.attendre(lambda: len(t.evenements("transcription")) == 2)
    await asyncio.sleep(0.05)
    assert not pont.termine
    await pont.terminer("raccroche")


async def test_texte_saisi_et_mot_arret_saisi() -> None:
    pont, f, t = await ouvrir()
    await pont.recevoir_commande({"op": "texte", "texte": "  Quel est le dernier retour ?  "})
    assert f.textes == ["Quel est le dernier retour ?"]
    assert t.evenements("transcription")[-1]["role"] == "utilisateur"
    await pont.recevoir_commande({"op": "ping"})
    await pont.recevoir_commande({"op": "inconnue"})
    await pont.recevoir_commande("pas un objet")
    assert t.evenements("pong") and t.evenements("erreur")[0]["code"] == "commande_inconnue"
    await pont.recevoir_commande({"op": "texte", "texte": "stop session"})
    assert pont.motif_fin == "mot_arret"
    assert f.textes == ["Quel est le dernier retour ?"]


async def test_raccrocher_est_idempotent() -> None:
    pont, f, t = await ouvrir()
    await pont.recevoir_commande({"op": "raccrocher"})
    await pont.terminer("deconnexion")
    await pont.recevoir_audio(b"\x00\x00" * 10)
    assert pont.motif_fin == "raccroche"
    assert len(t.evenements("fin")) == 1
    assert f.audio == []


async def test_appel_d_outil_execute_et_resultat_rendu() -> None:
    journal: list[dict] = []
    pont, f, t = await ouvrir(registre=registre_essai(journal))
    await f.pousser("tool_call", call_id="c1", name="lister", args={})
    await asyncio.wait_for(f.reponse_outil_recue.wait(), 2)
    assert f.reponses_outils == [("c1", "lister", {"result": {"sessions": ["PILOTE JARVIS"]}})]
    await t.attendre(lambda: len(t.evenements("outil")) == 2)
    appel, resultat = t.evenements("outil")
    assert appel == {"ev": "outil", "nom": "lister", "etape": "appel"}
    assert resultat["ok"] is True and resultat["etape"] == "resultat"
    # La page ne reçoit ni arguments ni résultat des outils.
    assert "PILOTE" not in str(t.json)
    await pont.terminer("raccroche")


@pytest.mark.parametrize(
    ("nom", "args", "options", "erreur"),
    [
        ("inexistant", {}, {}, "outil inconnu : inexistant"),
        ("casser", {}, {}, "RuntimeError: panne"),
        ("ecrire", {"texte": "go"}, {"demander_avant_agir": True}, "user_confirmation_required_but_no_ui"),
    ],
)
async def test_outils_refuses_ou_en_echec(nom: str, args: dict, options: dict, erreur: str) -> None:
    journal: list[dict] = []
    pont, f, t = await ouvrir(registre=registre_essai(journal), **options)
    await f.pousser("tool_call", call_id="c9", name=nom, args=args)
    await asyncio.wait_for(f.reponse_outil_recue.wait(), 2)
    assert f.reponses_outils == [("c9", nom, {"error": erreur})]
    await t.attendre(lambda: len(t.evenements("outil")) == 2)
    assert t.evenements("outil")[-1]["ok"] is False
    assert journal == []
    await pont.terminer("raccroche")


async def test_ecriture_permise_sans_demande_prealable() -> None:
    journal: list[dict] = []
    pont, f, t = await ouvrir(registre=registre_essai(journal))
    await f.pousser("tool_call", call_id="c2", name="ecrire", args={"texte": "lance les tests"})
    await asyncio.wait_for(f.reponse_outil_recue.wait(), 2)
    assert journal == [{"nom": "ecrire", "texte": "lance les tests"}]
    await pont.terminer("raccroche")


async def test_erreur_du_fournisseur_termine() -> None:
    pont, f, t = await ouvrir()
    await f.pousser("error", exception="boom")
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "erreur_fournisseur"
    assert t.evenements("erreur")[0]["code"] == "fournisseur"
    assert "boom" not in str(t.json)


async def test_fournisseur_qui_ferme_son_flux() -> None:
    pont, f, t = await ouvrir()
    await f.file.put(None)
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "fournisseur_ferme"


async def test_connexion_impossible() -> None:
    f = FauxFournisseur(echec_connexion=True)
    t = FauxTransport()
    pont = PontAppel(appel_essai(f), t)
    await pont.demarrer()
    assert pont.termine and pont.motif_fin == "erreur_fournisseur"
    assert t.evenements("erreur")[0] == {"ev": "erreur", "code": "connexion_fournisseur", "message": "ConnectionError"}
    assert not t.evenements("pret")
    assert not f.ferme  # jamais connecté : rien à fermer


async def test_duree_maximale() -> None:
    pont, f, t = await ouvrir(max_minutes=0.1 / 60)
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "duree_max"


async def test_cout_maximal() -> None:
    pont, f, t = await ouvrir(cout_max_usd=0.0)
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "cout_max"


async def test_transport_coupe_pendant_l_audio() -> None:
    class TransportCasse(FauxTransport):
        async def envoyer_audio(self, pcm16: bytes) -> None:
            raise ConnectionError("fermé")

    f = FauxFournisseur()
    t = TransportCasse()
    pont = PontAppel(appel_essai(f), t)
    await pont.demarrer()
    await f.pousser("audio_chunk_out", pcm16=b"\x00\x00")
    assert await asyncio.wait_for(pont.attendre_fin(), 2) == "deconnexion"


# -- avec le vrai mode chaîne (N2) -------------------------------------------


class TTSCourt:
    name = "tts-court"
    sample_rate = 24000

    async def synthesize(self, text: str):
        yield b"\x01\x00" * 2400


class ChatOutil:
    """Premier tour : appelle `lister` ; ensuite : répond avec le résultat."""

    name = "chat-outil"

    async def stream(self, system, messages, tools):
        if messages[-1]["role"] == "user":
            yield ModelChunk(tool_call=ToolCall(id="t1", name="lister", args={}))
        else:
            yield ModelChunk(text=f"Résultat : {messages[-1]['content']}.")


async def pousser_wav(pont: PontAppel, nom: str) -> None:
    pcm, rate = wav_to_pcm16((FIX / nom).read_bytes())
    assert rate == 16000
    trame = 640  # 20 ms à 16 kHz, comme la page
    for i in range(0, len(pcm), trame):
        await pont.recevoir_audio(pcm[i : i + trame])
        await asyncio.sleep(0)


async def test_chaine_reelle_sur_enregistrement() -> None:
    impl = ChainProvider(ScriptedSTT(["Bonjour Jarvis.", "Liste mes sessions."]), EchoChat(), TTSCourt())
    pont, _, t = await ouvrir(fournisseur=impl)
    await pousser_wav(pont, "deux_phrases.wav")
    await impl.end_of_audio()
    await asyncio.wait_for(impl.wait_idle(), 5)
    await t.attendre(lambda: len([m for m in t.evenements("transcription") if m["role"] == "modele" and m["final"]]) >= 1, 5)
    utilisateur = [m["texte"] for m in t.evenements("transcription") if m["role"] == "utilisateur"]
    assert utilisateur == ["Bonjour Jarvis.", "Liste mes sessions."]
    assert t.audio and all(len(b) % 2 == 0 for b in t.audio)
    await pont.terminer("raccroche")


async def test_chaine_reelle_avec_outil() -> None:
    journal: list[dict] = []
    impl = ChainProvider(ScriptedSTT(["Liste mes sessions."]), ChatOutil(), TTSCourt())
    pont, _, t = await ouvrir(fournisseur=impl, registre=registre_essai(journal))
    await pont.recevoir_commande({"op": "texte", "texte": "Liste mes sessions."})
    await t.attendre(lambda: any(m["role"] == "modele" and m["final"] for m in t.evenements("transcription")), 5)
    final = [m["texte"] for m in t.evenements("transcription") if m["role"] == "modele" and m["final"]]
    assert "PILOTE JARVIS" in final[0]
    assert journal == [{"nom": "lister"}]
    assert [m["etape"] for m in t.evenements("outil")] == ["appel", "resultat"]
    await pont.terminer("raccroche")
