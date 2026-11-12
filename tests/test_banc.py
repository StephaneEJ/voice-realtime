"""Banc d'essai N3 — harnais, métriques, garde-fous et rapport, sans réseau ni coût."""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from typer.testing import CliRunner

from voice_realtime.banc import garde, harnais
from voice_realtime.banc.garde import AutorisationPayante, ConnexionInterdite, PassageRefuse
from voice_realtime.banc.harnais import (
    Candidat,
    CandidatErreur,
    ResultatScenario,
    charger_candidats,
    executer_banc,
    jouer_temps_reel,
    synthese,
)
from voice_realtime.banc.metriques import centile, langue_probable, normaliser, part, taux_erreur_mots
from voice_realtime.banc.rapport import ecrire, vers_dict, vers_markdown
from voice_realtime.banc.scenarios import ScenarioErreur, charger_scenarios
from voice_realtime.banc.tarifs import GrilleTarifs, Usage
from voice_realtime.providers.base import ProviderConfig, RealtimeEvent

RACINE = Path(__file__).resolve().parents[1]
CONFIG = RACINE / "config" / "banc"
JOUR = datetime(2026, 11, 12, 14, 0, tzinfo=garde.PARIS)
NUIT = datetime(2026, 11, 12, 3, 0, tzinfo=garde.PARIS)


@pytest.fixture(scope="module")
def jeu():
    return charger_scenarios(CONFIG / "scenarios.json")


@pytest.fixture(scope="module")
def grille():
    return GrilleTarifs.charger(CONFIG / "tarifs.json")


@pytest.fixture(scope="module")
def candidats():
    return charger_candidats(CONFIG / "candidats.json")


def chaine(cid: str, stt: str, llm: str, tts: str) -> Candidat:
    return Candidat(id=cid, genre="chaine", stt=stt, llm=llm, tts=tts)


# ---------------------------------------------------------------------------
# Métriques


def test_normaliser_ignore_casse_ponctuation_accents_et_elisions():
    assert normaliser("L'état ? Très BIEN !") == ["l", "etat", "tres", "bien"]
    assert normaliser("l etat tres bien") == ["l", "etat", "tres", "bien"]


def test_taux_erreur_mots_valeurs_connues():
    assert taux_erreur_mots("Liste mes sessions en cours.", "liste mes sessions en cours") == 0.0
    assert taux_erreur_mots("liste mes sessions en cours", "liste mes sessions cours") == pytest.approx(1 / 5)
    assert taux_erreur_mots("un deux", "trois quatre cinq") == pytest.approx(3 / 2)
    assert taux_erreur_mots("", "") == 0.0
    assert taux_erreur_mots("", "bruit") == 1.0


def test_langue_probable():
    assert langue_probable("Voici le résultat, trois sessions sont ouvertes.") == "fr"
    assert langue_probable("Sure, here is what I found for you.") == "en"
    assert langue_probable("Killchat.") == "?"


def test_centile_et_part():
    assert centile([], 50) is None
    assert centile([10.0], 90) == 10.0
    assert centile([100.0, 200.0, 300.0, 400.0], 50) == pytest.approx(250.0)
    assert centile([100.0, 200.0, 300.0, 400.0], 90) == pytest.approx(370.0)
    assert part([True, False, None, True]) == pytest.approx(2 / 3)
    assert part([None]) is None


# ---------------------------------------------------------------------------
# Scénarios et candidats


def test_scenarios_par_defaut_reprennent_le_manifeste(jeu):
    ids = [s.id for s in jeu]
    assert ids == ["outils-et-coupure", "phrase-courte", "mot-arret", "voix-humaine-en"]
    s = jeu.scenarios[0]
    assert s.enregistrement.is_file()
    assert [e.texte for e in s.enonces] == ["Liste mes sessions en cours.", "Quel est le dernier retour de la session cockpit ?"]
    assert s.enonces[1].debut_ms == 3430 and s.coupure_ms == 3430
    assert s.duree_ms == 6917
    assert jeu.scenarios[2].mot_arret is True


def test_scenarios_invalides(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"scenarios": [{"id": "a", "enregistrement": "absent.wav"}]}))
    with pytest.raises(ScenarioErreur, match="introuvable"):
        charger_scenarios(tmp_path / "s.json")
    wav = RACINE / "tests/fixtures/chain/killchat.wav"
    (tmp_path / "d.json").write_text(json.dumps({"scenarios": [
        {"id": "a", "enregistrement": str(wav), "enonces": [{"texte": "x"}]},
        {"id": "a", "enregistrement": str(wav), "enonces": [{"texte": "x"}]},
    ]}))
    with pytest.raises(ScenarioErreur, match="double"):
        charger_scenarios(tmp_path / "d.json")
    (tmp_path / "v.json").write_text(json.dumps({"scenarios": [{"id": "a", "enregistrement": str(wav)}]}))
    with pytest.raises(ScenarioErreur, match="aucun énoncé"):
        charger_scenarios(tmp_path / "v.json")


def test_candidats_par_defaut_et_validation(tmp_path, candidats):
    par_id = {c.id: c for c in candidats}
    assert {"simule-rapide", "simule-lent", "simule-degrade", "gemini-live", "openai-realtime-mini", "chaine-api"} <= set(par_id)
    assert par_id["gemini-live"].genre == "temps_reel"
    for contenu, motif in (
        ({"candidats": [{"id": "x", "genre": "chaine", "stt": "simule"}]}, "requis"),
        ({"candidats": [{"id": "x", "genre": "temps_reel", "fournisseur": "autre", "modele": "m"}]}, "fournisseur"),
        ({"candidats": [{"id": "x", "genre": "bizarre"}]}, "genre inconnu"),
        ({"candidats": []}, "aucun candidat"),
    ):
        (tmp_path / "c.json").write_text(json.dumps(contenu))
        with pytest.raises(CandidatErreur, match=motif):
            charger_candidats(tmp_path / "c.json")


# ---------------------------------------------------------------------------
# Garde-fous


@pytest.mark.parametrize(
    "etage,spec,attendu",
    [
        ("stt", "simule:rapide", True),
        ("stt", "script:bonjour", True),
        ("stt", "whisper-cpp", True),
        ("llm", "echo", True),
        ("tts", "say:Thomas", True),
        ("llm", "openai:llama3@http://127.0.0.1:11434/v1", True),
        ("llm", "openai:llama3@http://localhost:11434/v1", True),
        ("llm", "openai:gpt-x", False),
        ("llm", "openai:gpt-x@https://api.openai.com/v1", False),
        ("llm", "openai:x@http://127.0.0.1.evil.example/v1", False),
        ("llm", "anthropic:claude-haiku-5-5", False),
        ("stt", "simule@https://exemple.test", False),
        ("tts", "openai:gpt-4o-mini-tts", False),
        ("llm", "inconnu", False),
    ],
)
def test_etage_gratuit(etage, spec, attendu):
    assert garde.etage_gratuit(etage, spec) is attendu


def test_temps_reel_jamais_gratuit(candidats):
    par_id = {c.id: c for c in candidats}
    assert garde.candidat_gratuit(par_id["simule-rapide"])
    assert not garde.candidat_gratuit(par_id["gemini-live"])
    assert not garde.candidat_gratuit(par_id["chaine-api"])


def test_reseau_coupe_bloque_le_distant_et_laisse_la_boucle_locale():
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]
    try:
        with garde.reseau_coupe() as bloquees:
            with socket.socket() as s:
                s.connect(("127.0.0.1", port))  # boucle locale : permise
            with socket.socket() as s, pytest.raises(ConnexionInterdite):
                s.connect(("203.0.113.7", 443))
            with pytest.raises(ConnexionInterdite):
                socket.getaddrinfo("api.openai.com", 443)
        assert bloquees == ["203.0.113.7", "api.openai.com"]
    finally:
        serveur.close()
    # Hors du garde, les fonctions d'origine sont rendues.
    assert socket.socket.connect.__name__ == "connect"


def test_nuit():
    assert garde.est_la_nuit(NUIT)
    assert garde.est_la_nuit(datetime(2026, 11, 12, 22, 30, tzinfo=garde.PARIS))
    assert not garde.est_la_nuit(JOUR)
    assert not garde.est_la_nuit(datetime(2026, 11, 12, 7, 0, tzinfo=garde.PARIS))


def test_passage_payant_refuse_sans_autorisation_budget_jour_ou_prix(candidats, grille, jeu):
    par_id = {c.id: c for c in candidats}
    duree = sum(s.duree_ms or 0 for s in jeu) / 1000

    def estimer(c):
        from voice_realtime.banc.tarifs import estimer_avant_passage

        return estimer_avant_passage(grille, c, duree)

    gemini, api, rapide = par_id["gemini-live"], par_id["chaine-api"], par_id["simule-rapide"]
    assert garde.verifier_passage_payant([rapide], None, estimer, maintenant=NUIT) == 0.0
    cas = [
        ([gemini], None, JOUR, "sans autorisation"),
        ([gemini], AutorisationPayante(5.0, autorise=False), JOUR, "sans autorisation"),
        ([gemini], AutorisationPayante(0.0, autorise=True), JOUR, "budget"),
        ([gemini], AutorisationPayante(5.0, autorise=True), NUIT, "nuit"),
        ([api], AutorisationPayante(5.0, autorise=True), JOUR, "prix inconnu"),
        ([gemini], AutorisationPayante(0.001, autorise=True), JOUR, "au-dessus du budget"),
    ]
    for liste, autorisation, quand, motif in cas:
        with pytest.raises(PassageRefuse, match=motif):
            garde.verifier_passage_payant(liste, autorisation, estimer, maintenant=quand)
    total = garde.verifier_passage_payant([gemini], AutorisationPayante(1.0, autorise=True), estimer, maintenant=JOUR)
    assert total == pytest.approx(1.40 * duree / 3600)


# ---------------------------------------------------------------------------
# Tarifs


def test_chiffrage_chaine_et_temps_reel(grille):
    u = Usage(duree_s=60, audio_entree_s=30, jetons_entree=1_000_000, jetons_sortie=200_000, caracteres_synthese=100_000)
    ch = grille.chiffrer_chaine("simule:rapide", "simule:rapide", "simule:rapide", u)
    attendu = 0.006 * 0.5 + 0.25 + 1.25 * 0.2 + 15 * 0.1
    assert ch.fictif and ch.cout_usd == pytest.approx(attendu)
    assert ch.cout_horaire_usd == pytest.approx(attendu * 60)
    gratuit = grille.chiffrer_chaine("whisper-cpp", "echo", "say:Thomas", u)
    assert gratuit.cout_usd == 0.0 and not gratuit.fictif
    inconnu = grille.chiffrer_chaine("openai:gpt-4o-mini-transcribe", "echo", "say", u)
    assert inconnu.cout_usd is None and "stt" in inconnu.inconnus[0]
    rt = grille.chiffrer_temps_reel("gpt-realtime-mini", Usage(duree_s=1800))
    assert rt.cout_horaire_usd == 1.25 and rt.cout_usd == pytest.approx(0.625)
    assert grille.chiffrer_temps_reel("modele-inconnu", Usage(duree_s=10)).cout_usd is None


# ---------------------------------------------------------------------------
# Harnais de bout en bout, à blanc


@pytest.fixture(scope="module")
def rapport_a_blanc(candidats, jeu, grille):
    def interdit(*_a, **_k):
        raise AssertionError("un fournisseur payant a été construit à blanc")

    origine = harnais._construire_temps_reel
    harnais._construire_temps_reel = interdit
    try:
        retenus = [c for c in candidats if c.id != "local-say"]  # `say` n'existe que sur macOS
        return asyncio.run(executer_banc(retenus, jeu, grille, facteur=0.02, maintenant=NUIT))
    finally:
        harnais._construire_temps_reel = origine


def test_banc_a_blanc_ne_joue_que_le_gratuit(rapport_a_blanc):
    r = rapport_a_blanc
    assert r.a_blanc and r.connexions_bloquees == []
    par_id = {rc.candidat.id: rc for rc in r.candidats}
    for cid in ("gemini-live", "openai-realtime-mini", "chaine-api"):
        rc = par_id[cid]
        assert not rc.joue and not rc.gratuit and rc.motif.startswith("payant")
        assert rc.scenarios == []
    assert par_id["gemini-live"].estimation.cout_horaire_usd == 1.40
    assert par_id["chaine-api"].estimation.cout_usd is None
    for cid in ("simule-rapide", "simule-lent", "simule-degrade"):
        assert par_id[cid].joue and len(par_id[cid].scenarios) == 4


def test_banc_mesure_un_candidat_sain(rapport_a_blanc):
    rc = next(rc for rc in rapport_a_blanc.candidats if rc.candidat.id == "simule-rapide")
    s = synthese(rc)
    assert s["scenarios_joues"] == 4 and s["erreurs"] == 0
    assert s["taux_erreur_mots_moyen"] == 0.0
    assert s["part_reponses_fr"] == 1.0
    assert s["coupures_detectees"] == 1.0 and 0 < s["delai_coupure_moyen_ms"] < 600
    assert s["outils_corrects"] == 1.0 and s["mot_arret_reconnu"] == 1.0
    # Attente de fin de parole (préréglage balanced, 700 ms) dominante, à un bloc près.
    assert 600 <= s["attente_vad_moyenne_ms"] <= 800
    assert s["premiere_reponse_p50_ms"] >= s["attente_vad_moyenne_ms"]
    outils = next(sc for sc in rc.scenarios if sc.scenario_id == "outils-et-coupure")
    assert outils.outils_appeles == ["list_sessions", "get_last_response"]
    assert len(outils.premieres_reponses_ms) == 2
    assert outils.usage.jetons_entree > 0 and outils.usage.caracteres_synthese > 0
    assert rc.chiffrage.fictif and rc.chiffrage.cout_horaire_usd > 0


def test_banc_voit_un_candidat_degrade(rapport_a_blanc):
    par_id = {rc.candidat.id: rc for rc in rapport_a_blanc.candidats}
    sain, degrade = synthese(par_id["simule-rapide"]), synthese(par_id["simule-degrade"])
    assert degrade["taux_erreur_mots_moyen"] > 0.1
    assert degrade["part_reponses_fr"] < 1.0
    assert degrade["outils_corrects"] < 1.0  # « dernier » omis : get_last_response manqué
    assert sain["outils_corrects"] == 1.0


def test_banc_lent_plus_lent_que_rapide(candidats, jeu, grille):
    par_id = {c.id: c for c in candidats}
    sous_jeu = type(jeu)(scenarios=[s for s in jeu if s.id == "phrase-courte"])
    r = asyncio.run(executer_banc([par_id["simule-rapide"], par_id["simule-lent"]], sous_jeu, grille, facteur=0.2))
    rapide, lent = (synthese(rc)["premiere_reponse_p50_ms"] for rc in r.candidats)
    # Écart attendu : (600-150) + (900-250) + (450-120) = 1430 ms × 0,2.
    assert lent - rapide == pytest.approx(286, abs=120)


def test_banc_reseau_coupe_pendant_le_jeu(jeu, grille):
    async def tricheur(candidat, scenario, **_):
        with socket.socket() as s:
            s.connect(("198.51.100.9", 443))
        return ResultatScenario(scenario_id=scenario.id)

    c = chaine("faux-local", "simule", "simule", "simule")
    r = asyncio.run(executer_banc([c], jeu, grille, jouer_chaine_fn=tricheur))
    rc = r.candidats[0]
    assert all(not sc.joue and "ConnexionInterdite" in sc.motif for sc in rc.scenarios)
    assert r.connexions_bloquees == ["198.51.100.9"] * len(jeu)


def test_banc_binaire_absent(jeu, grille):
    c = Candidat(id="x", genre="chaine", stt="simule", llm="simule", tts="simule", requiert=("binaire-qui-n-existe-pas",))
    r = asyncio.run(executer_banc([c], jeu, grille))
    assert not r.candidats[0].joue and "binaire local absent" in r.candidats[0].motif


def test_banc_payant_refuse_avant_tout_jeu(candidats, jeu, grille):
    par_id = {c.id: c for c in candidats}
    with pytest.raises(PassageRefuse, match="nuit"):
        asyncio.run(executer_banc([par_id["gemini-live"]], jeu, grille,
                                  autorisation=AutorisationPayante(10.0, autorise=True), maintenant=NUIT))


# ---------------------------------------------------------------------------
# Pilote temps réel sur un faux fournisseur


class FauxTempsReel:
    """Répond 300 ms (temps d'enregistrement) après chaque fin d'énoncé ; coupe à la reprise de parole."""

    def __init__(self, fins_ms: list[int], coupure_ms: int | None, rate: int = 16000) -> None:
        self.fins = list(fins_ms)
        self.coupure = coupure_ms
        self.rate = rate
        self.recu_ms = 0.0
        self.file: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue()
        self.reponses: list[dict[str, Any]] = []
        self.outil_demande = False

    async def connect(self, config, system_prompt, audio=False, tools=None):
        self.outils = [t.name for t in tools or []]

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        self.recu_ms += len(pcm16) / 2 / self.rate * 1000
        if self.fins and self.recu_ms >= self.fins[0] + 300:
            self.fins.pop(0)
            if not self.outil_demande:
                self.outil_demande = True
                await self.file.put(RealtimeEvent("tool_call", {"call_id": "c1", "name": "list_sessions", "args": {}}))
            await self.file.put(RealtimeEvent("audio_chunk_out", {"pcm16": b"\x00\x00" * 2400}))
            await self.file.put(RealtimeEvent("final_transcript_model", {"text": "Voici les sessions ouvertes."}))
        if self.coupure is not None and self.recu_ms >= self.coupure + 200:
            self.coupure = None
            await self.file.put(RealtimeEvent("model_interrupted"))

    async def send_function_response(self, call_id, name, response):
        self.reponses.append(response)

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        while (ev := await self.file.get()) is not None:
            yield ev

    async def close(self):
        await self.file.put(None)


def test_pilote_temps_reel_date_les_evenements_en_temps_d_enregistrement(jeu):
    s = jeu.scenarios[0]
    faux = FauxTempsReel([e.fin_ms for e in s.enonces], s.coupure_ms)
    config = ProviderConfig(model="faux", api_key="", input_sample_rate=16000)
    r = asyncio.run(jouer_temps_reel(faux, config, s, vitesse=10, silence_final_s=0.5))
    assert len(r.premieres_reponses_ms) == 2
    for v in r.premieres_reponses_ms:
        assert 250 <= v <= 600
    assert r.coupure_detectee and 150 <= r.delai_coupure_ms <= 500
    assert r.outils_appeles == ["list_sessions"]
    assert faux.reponses and "sessions" in faux.reponses[0]["result"]
    assert "list_sessions" in faux.outils
    assert r.usage.duree_s == pytest.approx(s.duree_ms / 1000 + 0.5, abs=0.05)


# ---------------------------------------------------------------------------
# Rapport et CLI


def test_rapport_dit_a_blanc_et_se_relit(rapport_a_blanc, tmp_path):
    md = vers_markdown(rapport_a_blanc)
    assert md.startswith("# Banc d'essai N3 — rapport à blanc")
    assert "ne départagent aucun fournisseur" in md
    assert "| `gemini-live` | non : payant : non joué à blanc |" in md
    assert "majorant 1.400 $/h" in md
    chemin_md, chemin_js = ecrire(rapport_a_blanc, tmp_path / "r")
    donnees = json.loads(chemin_js.read_text())
    assert donnees["a_blanc"] is True and donnees == json.loads(json.dumps(vers_dict(rapport_a_blanc), default=str))
    assert {c["candidat"]["id"] for c in donnees["candidats"]} >= {"simule-rapide", "gemini-live"}
    assert chemin_md.read_text() == md


def test_cli_banc_a_blanc_et_refus_payant(tmp_path, monkeypatch):
    from voice_realtime import cli

    monkeypatch.setattr(cli, "load_config", lambda *a, **k: None)
    runner = CliRunner()
    res = runner.invoke(cli.app, ["banc", "--seulement", "simule-rapide", "--seulement", "gemini-live",
                                  "--facteur", "0.01", "-o", str(tmp_path / "rapport")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "rapport" / "rapport.md").is_file()
    assert "gemini-live : payant, chiffré seulement" in res.output
    refus = runner.invoke(cli.app, ["banc", "--seulement", "gemini-live", "--payant", "-o", str(tmp_path / "x")])
    assert refus.exit_code == 2 and "Passage refusé" in refus.output and "budget" in refus.output
    assert not (tmp_path / "x").exists()
    inconnu = runner.invoke(cli.app, ["banc", "--seulement", "nimporte"])
    assert inconnu.exit_code == 1 and "inconnus" in inconnu.output
