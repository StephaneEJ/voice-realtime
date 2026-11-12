"""N4 — serveur de la page téléphone, sur la boucle locale uniquement.

Le serveur écoute sur 127.0.0.1 (port éphémère) ; les clients sont `httpx`
et `websockets`. Aucune connexion sortante.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tests.faux_telephone import ADRESSE, AUD, EQUIPE, CleAccess, FauxFournisseur, appel_essai
from voice_realtime.telephone.acces import VerificateurAcces
from voice_realtime.telephone.configuration import (
    CONSIGNE_TELEPHONE,
    OUTILS_ORCHESTRATEUR,
    ConfigurationTelephoneErreur,
    ReglagesTelephone,
    fabrique_appel,
)
from voice_realtime.telephone.serveur import DOSSIER_STATIQUE, FICHIERS, ServeurTelephone


class Banc:
    """Serveur réel + fournisseurs faux créés à chaque appel."""

    def __init__(self, **options) -> None:
        self.fournisseurs: list[FauxFournisseur] = []

        def fabrique():
            f = FauxFournisseur()
            self.fournisseurs.append(f)
            return appel_essai(f)

        self.serveur = ServeurTelephone(fabrique, port=0, **options)

    async def __aenter__(self) -> "Banc":
        self.port = await self.serveur.demarrer()
        self.base = f"http://localhost:{self.port}"
        return self

    async def __aexit__(self, *exc) -> None:
        await self.serveur.arreter()

    def ws(self, origine: str | None = "auto", **kwargs):
        if origine == "auto":
            origine = self.base
        return connect(f"ws://localhost:{self.port}/ws", origin=origine, **kwargs)


async def lire_json(ws, ev: str, delai: float = 2.0) -> dict:
    async def boucle() -> dict:
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                donnees = json.loads(message)
                if donnees.get("ev") == ev:
                    return donnees

    return await asyncio.wait_for(boucle(), delai)


async def http(banc: Banc, chemin: str, **entetes: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.get(banc.base + chemin, headers=entetes)


async def test_page_et_ressources_servies_avec_entetes_de_securite() -> None:
    async with Banc() as banc:
        page = await http(banc, "/")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        csp = page.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "script-src 'self'" in csp and "unsafe" not in csp
        assert f"wss://localhost:{banc.port}" in csp
        assert page.headers["permissions-policy"].startswith("microphone=(self)")
        assert page.headers["x-frame-options"] == "DENY"
        assert page.headers["cache-control"] == "no-store"
        assert "telephone.js" in page.text and "Appeler" in page.text
        types = {
            "/telephone.js": "text/javascript", "/worklets.js": "text/javascript",
            "/telephone.css": "text/css", "/manifest.webmanifest": "application/manifest+json",
            "/icone.svg": "image/svg+xml",
        }
        for chemin, attendu in types.items():
            r = await http(banc, chemin)
            assert r.status_code == 200 and r.headers["content-type"].startswith(attendu), chemin
        assert (await http(banc, "/../pyproject.toml")).status_code == 404
        assert (await http(banc, "/inconnu")).status_code == 404
        sante = (await http(banc, "/sante")).json()
        assert sante == {"ok": True, "appelEnCours": False, "appels": 0}


async def test_hote_inconnu_refuse_contre_le_rattachement_dns() -> None:
    async with Banc() as banc:
        r = await http(banc, "/", Host=f"piege.example:{banc.port}")
        assert r.status_code == 421
        r = await http(banc, "/", Host=f"127.0.0.1:{banc.port}")
        assert r.status_code == 200


async def test_appel_complet_par_websocket() -> None:
    async with Banc() as banc:
        async with banc.ws() as ws:
            pret = await lire_json(ws, "pret")
            assert pret["entree"] == 16000 and pret["sortie"] == 24000
            f = banc.fournisseurs[0]
            await ws.send(b"\x01\x00" * 320)
            await f.pousser("audio_chunk_out", pcm16=b"\x07\x00" * 50)
            audio = await asyncio.wait_for(ws.recv(), 2)
            assert audio == b"\x07\x00" * 50
            await f.pousser("final_transcript_user", text="Bonjour.")
            assert (await lire_json(ws, "transcription"))["texte"] == "Bonjour."
            assert (await http(banc, "/sante")).json()["appelEnCours"] is True
            await ws.send(json.dumps({"op": "raccrocher"}))
            assert (await lire_json(ws, "fin"))["motif"] == "raccroche"
            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 2)
        assert f.audio == [b"\x01\x00" * 320]
        assert f.ferme
        assert (await http(banc, "/sante")).json() == {"ok": True, "appelEnCours": False, "appels": 1}


async def test_fermeture_de_la_page_termine_l_appel() -> None:
    async with Banc() as banc:
        async with banc.ws() as ws:
            await lire_json(ws, "pret")
        f = banc.fournisseurs[0]
        for _ in range(100):
            if f.ferme:
                break
            await asyncio.sleep(0.02)
        assert f.ferme
        assert banc.serveur._pont.motif_fin == "deconnexion"


async def test_un_seul_appel_a_la_fois() -> None:
    async with Banc() as banc:
        async with banc.ws() as premier:
            await lire_json(premier, "pret")
            async with banc.ws() as second:
                erreur = await lire_json(second, "erreur")
                assert erreur["code"] == "occupe"
                with pytest.raises(ConnectionClosed):
                    await asyncio.wait_for(second.recv(), 2)
            assert len(banc.fournisseurs) == 1
        # le premier fermé, un nouvel appel passe
        for _ in range(100):
            if not banc.serveur.appel_en_cours:
                break
            await asyncio.sleep(0.02)
        async with banc.ws() as troisieme:
            await lire_json(troisieme, "pret")


@pytest.mark.parametrize("origine", [None, "https://piege.example", "null", "http://localhost:1"])
async def test_origine_etrangere_refusee(origine) -> None:
    async with Banc() as banc:
        with pytest.raises(InvalidStatus) as err:
            async with banc.ws(origine=origine):
                pass
        assert err.value.response.status_code == 403
        assert banc.fournisseurs == []


async def test_nom_public_exige_un_verrou_local() -> None:
    with pytest.raises(ValueError, match="Access"):
        ServeurTelephone(lambda: None, noms_publics=("voix.example.org",))
    with pytest.raises(ValueError, match="trop court"):
        ServeurTelephone(lambda: None, jeton="court")
    with pytest.raises(ValueError, match="préfixe"):
        ServeurTelephone(lambda: None, prefixe="voix")


JETON = "j" * 40


async def test_jeton_local_et_prefixe_comme_derriere_le_relais_du_worker() -> None:
    """Relais du Worker : Host réécrit en 127.0.0.1 par le tunnel, Origin public,
    préfixe public, jeton local ajouté par le relais (comme l'écran O5)."""
    async with Banc(jeton=JETON, prefixe="/voix/", noms_publics=("jarvis.example.org",)) as banc:
        hote = f"127.0.0.1:{banc.port}"
        bearer = {"Authorization": f"Bearer {JETON}", "Host": hote}
        assert (await http(banc, "/voix/", Host=hote)).status_code == 401
        assert (await http(banc, "/voix/", Host=hote, Authorization="Bearer " + "x" * 40)).status_code == 401
        page = await http(banc, "/voix/", **bearer)
        assert page.status_code == 200
        assert "wss://jarvis.example.org" in page.headers["content-security-policy"]
        assert (await http(banc, "/voix/worklets.js", **bearer)).status_code == 200
        assert (await http(banc, "/voix/sante", **bearer)).json()["ok"] is True
        for chemin in ("/", "/voix", "/telephone.js", "/voixtelephone.js", "/autre/"):
            assert (await http(banc, chemin, **bearer)).status_code == 404, chemin
        with pytest.raises(InvalidStatus) as err:
            async with connect(f"ws://127.0.0.1:{banc.port}/voix/ws", origin="https://jarvis.example.org"):
                pass
        assert err.value.response.status_code == 401
        async with connect(
            f"ws://127.0.0.1:{banc.port}/voix/ws", origin="https://jarvis.example.org",
            additional_headers={"Authorization": f"Bearer {JETON}"},
        ) as ws:
            await lire_json(ws, "pret")
        with pytest.raises(InvalidStatus) as err:
            async with connect(
                f"ws://127.0.0.1:{banc.port}/voix/ws", origin="https://piege.example",
                additional_headers={"Authorization": f"Bearer {JETON}"},
            ):
                pass
        assert err.value.response.status_code == 403
        assert len(banc.fournisseurs) == 1


@pytest.fixture(scope="module")
def cle() -> CleAccess:
    return CleAccess()


def verificateur(cle: CleAccess) -> VerificateurAcces:
    v = VerificateurAcces.construire(EQUIPE, AUD, [ADRESSE], lire_jwks=lambda: {"keys": [cle.jwk()]})
    v.charger_cles(force=True)
    return v


async def test_access_exige_sur_la_page_et_le_canal(cle: CleAccess) -> None:
    async with Banc(acces=verificateur(cle), noms_publics=("voix.example.org",)) as banc:
        assert (await http(banc, "/")).status_code == 403
        assert (await http(banc, "/sante")).status_code == 403
        intrus = cle.jeton(email="intrus@example.org")
        r = await http(banc, "/", **{"Cf-Access-Jwt-Assertion": intrus})
        assert r.status_code == 403 and "adresse_refusee" in r.text
        bon = cle.jeton()
        assert (await http(banc, "/", **{"Cf-Access-Jwt-Assertion": bon})).status_code == 200
        r = await http(banc, "/", Host="voix.example.org", **{"Cf-Access-Jwt-Assertion": bon})
        assert r.status_code == 200
        assert "wss://voix.example.org" in r.headers["content-security-policy"]
        with pytest.raises(InvalidStatus):
            async with banc.ws():
                pass
        async with banc.ws(additional_headers={"Cf-Access-Jwt-Assertion": bon}) as ws:
            await lire_json(ws, "pret")
        assert len(banc.fournisseurs) == 1


async def test_fabrique_en_echec_rendue_a_la_page() -> None:
    def fabrique():
        raise RuntimeError("clé absente")

    serveur = ServeurTelephone(fabrique, port=0)
    port = await serveur.demarrer()
    try:
        async with connect(f"ws://localhost:{port}/ws", origin=f"http://localhost:{port}") as ws:
            erreur = await lire_json(ws, "erreur")
            assert erreur["code"] == "configuration"
    finally:
        await serveur.arreter()


# -- fichiers statiques ------------------------------------------------------


def test_fichiers_statiques_presents_et_sans_ressource_externe() -> None:
    for nom in set(FICHIERS.values()):
        contenu = (DOSSIER_STATIQUE / nom).read_text(encoding="utf-8")
        assert "http://" not in contenu.replace("http://www.w3.org/2000/svg", "")
        assert "https://" not in contenu
    js = (DOSSIER_STATIQUE / "telephone.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js  # textes du modèle et des sessions : jamais du HTML
    assert "echoCancellation: true" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_javascript_syntaxe_valide() -> None:
    for nom in ("telephone.js", "worklets.js"):
        sortie = subprocess.run(["node", "--check", str(DOSSIER_STATIQUE / nom)], capture_output=True, text=True)
        assert sortie.returncode == 0, sortie.stderr


# -- configuration -----------------------------------------------------------


def test_aucun_fournisseur_par_defaut() -> None:
    with pytest.raises(ConfigurationTelephoneErreur, match="aucun fournisseur par défaut"):
        fabrique_appel(ReglagesTelephone(provider=""), env={})


def test_cles_absentes_nommees_sans_valeur() -> None:
    for fournisseur, cle in (("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY")):
        with pytest.raises(ConfigurationTelephoneErreur, match=cle):
            fabrique_appel(ReglagesTelephone(provider=fournisseur, outils=()), env={})


def test_mode_chaine_incomplet_ou_outil_inconnu() -> None:
    with pytest.raises(ConfigurationTelephoneErreur, match="--chain-stt"):
        fabrique_appel(ReglagesTelephone(provider="chain", outils=()), env={})
    with pytest.raises(ConfigurationTelephoneErreur, match="outils inconnus : rm_rf"):
        fabrique_appel(ReglagesTelephone(provider="chain", outils=("rm_rf",)), env={})
    with pytest.raises(ConfigurationTelephoneErreur, match="--vad"):
        fabrique_appel(ReglagesTelephone(provider="chain", vad="sourd"), env={})


def test_mode_chaine_un_fournisseur_neuf_par_appel() -> None:
    fabrique = fabrique_appel(
        ReglagesTelephone(provider="chain", chain_stt="script:a|b", chain_llm="echo", chain_tts="say:Thomas"),
        env={},
    )
    a, b = fabrique(), fabrique()
    assert a.fournisseur is not b.fournisseur
    assert (a.entree, a.sortie) == (16000, 24000)
    assert a.registre is not None and tuple(a.registre.names()) == OUTILS_ORCHESTRATEUR
    assert a.consigne_systeme.startswith(CONSIGNE_TELEPHONE)
    assert "send_instruction :" in a.consigne_systeme
    assert a.config.input_sample_rate == 16000 and a.config.vad == "balanced"


def test_gemini_et_openai_prepares_sans_connexion() -> None:
    g = fabrique_appel(ReglagesTelephone(provider="gemini", outils=()), env={"GEMINI_API_KEY": "cle-essai"})()
    assert (g.entree, g.sortie, g.nom_fournisseur, g.registre) == (16000, 24000, "gemini", None)
    assert g.consigne_systeme == CONSIGNE_TELEPHONE
    o = fabrique_appel(ReglagesTelephone(provider="openai", outils=()), env={"OPENAI_API_KEY": "cle-essai"})()
    assert (o.entree, o.sortie, o.nom_fournisseur) == (24000, 24000, "openai")
    assert "cle-essai" not in repr(o.libelle)


@pytest.fixture
def cli_isolee(monkeypatch):
    """Ni fichier de secrets lu, ni journal écrit par la commande."""
    import voice_realtime.cli as cli

    def sans_secrets():
        raise FileNotFoundError

    monkeypatch.setattr(cli, "load_config", sans_secrets)
    monkeypatch.setattr(cli, "setup_logging", lambda **_: None)
    return cli.app


def test_commande_sans_fournisseur_echoue_avant_d_ouvrir_le_port(cli_isolee) -> None:
    resultat = CliRunner().invoke(cli_isolee, ["telephone", "--port", "1"])
    assert resultat.exit_code == 1
    assert "--provider requis" in resultat.output


def test_commande_jeton_fichier_trop_ouvert_refuse(cli_isolee, tmp_path) -> None:
    fichier = tmp_path / "jeton"
    fichier.write_text(JETON)
    fichier.chmod(0o644)
    resultat = CliRunner().invoke(cli_isolee, [
        "telephone", "--provider", "chain", "--chain-stt", "script:a", "--chain-llm", "echo",
        "--chain-tts", "say", "--outils", "", "--jeton-fichier", str(fichier),
    ])
    assert resultat.exit_code == 1
    assert "600" in resultat.output
    assert JETON not in resultat.output


def test_commande_nom_public_sans_access_refusee(cli_isolee) -> None:
    resultat = CliRunner().invoke(cli_isolee, [
        "telephone", "--provider", "chain", "--chain-stt", "script:a", "--chain-llm", "echo",
        "--chain-tts", "say", "--outils", "", "--nom-public", "voix.example.org",
    ])
    assert resultat.exit_code == 1
    assert "Access" in resultat.output


def test_page_reference_uniquement_des_fichiers_servis() -> None:
    page = (DOSSIER_STATIQUE / "index.html").read_text(encoding="utf-8")
    import re

    for ref in re.findall(r'(?:href|src)="([^"]+)"', page):
        assert not ref.startswith("/"), f"adresse absolue incompatible avec un préfixe : {ref}"
        assert "/" + ref in FICHIERS, ref
    js = (DOSSIER_STATIQUE / "telephone.js").read_text(encoding="utf-8")
    assert '"/ws"' not in js and '"/worklets.js"' not in js
    assert Path(DOSSIER_STATIQUE / "worklets.js").exists()
