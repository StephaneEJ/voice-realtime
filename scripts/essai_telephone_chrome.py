#!/usr/bin/env python3
"""Essai local N4 : la vraie page téléphone dans un vrai Chrome, sans réseau.

- serveur `ServeurTelephone` lancé dans ce processus, sur 127.0.0.1 (port éphémère) ;
- fournisseur : le vrai mode chaîne (N2) — VAD locale sur l'audio reçu du
  navigateur, transcription imposée (`ScriptedSTT`), modèle scripté qui appelle
  un outil factice au second énoncé, synthèse réelle `say` de macOS ;
- Chrome sans interface, profil temporaire jetable, micro simulé par un WAV
  (`--use-file-for-fake-audio-capture`), écran de téléphone émulé (390×844),
  piloté par le protocole DevTools (bibliothèque `websockets` déjà présente).

Le chemin audio éprouvé est donc le vrai : getUserMedia (annulation d'écho,
réduction de bruit, gain auto) → worklet de capture (rééchantillonnage) →
WebSocket → découpage en énoncés → … → synthèse → WebSocket → worklet de
lecture. Seuls la transcription et le modèle sont scriptés.

Usage :
    uv run --frozen python scripts/essai_telephone_chrome.py --sortie docs/preuves/nuit-2026-11-12
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from voice_realtime.providers.base import ProviderConfig  # noqa: E402
from voice_realtime.providers.chain import ChainProvider, ModelChunk, ToolCall  # noqa: E402
from voice_realtime.providers.chain_stages import MacSayTTS, ScriptedSTT  # noqa: E402
from voice_realtime.telephone.pont import Appel  # noqa: E402
from voice_realtime.telephone.serveur import ServeurTelephone  # noqa: E402
from voice_realtime.tools.registry import ToolRegistry, ToolResult, ToolSafetyLevel, ToolSpec  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FIX = RACINE / "tests" / "fixtures" / "chain"
PHRASES = ["Bonjour Jarvis.", "Attends.", "Où en est la session pilote ?"]
REPONSE_LONGUE = (
    "Bonjour Stéphane. Je suis connecté et je t'écoute. "
    "Dis-moi ce que tu veux savoir sur tes sessions en cours ce matin"
)


def scenario_micro(dossier: Path) -> tuple[Path, list[tuple[float, float]]]:
    """WAV 16 kHz composé à partir des enregistrements de N2 :

    0,0 s  « Liste mes sessions… » (transcrit « Bonjour Jarvis. ») → longue réponse parlée ;
    5,0 s  « Attends, arrête-toi. » pendant que la réponse sonne → coupure de parole ;
    11,5 s « Quel est le dernier retour… » (transcrit « Où en est la session pilote ? ») → outil.
    """
    from voice_realtime.providers.chain_audio import pcm16_to_wav, wav_to_pcm16

    deux, r = wav_to_pcm16((FIX / "deux_phrases.wav").read_bytes())
    coupure, _ = wav_to_pcm16((FIX / "coupure.wav").read_bytes())

    def tranche(pcm: bytes, debut_s: float, fin_s: float) -> bytes:
        return pcm[int(debut_s * r) * 2 : int(fin_s * r) * 2]

    def silence(s: float) -> bytes:
        return b"\x00\x00" * int(s * r)

    morceaux = [
        tranche(deux, 0.0, 2.6), silence(2.4), coupure, silence(4.0),
        tranche(deux, 3.0, 6.917), silence(6.0),
    ]
    chemin = dossier / "micro-essai.wav"
    chemin.write_bytes(pcm16_to_wav(b"".join(morceaux), r))
    return chemin, [(0.6, 2.23), (5.4, 6.59), (11.43, 13.92)]


class ChatEssai:
    """Modèle scripté : salutation longue, « j'attends » après la coupure, outil pour la session pilote."""

    name = "chat-essai"

    async def stream(self, system, messages, tools):
        dernier = messages[-1]
        if dernier["role"] == "tool":
            yield ModelChunk(text=f"La session pilote répond : {json.loads(dernier['content'])['result']['etat']}.")
            return
        if "pilote" in dernier["content"]:
            yield ModelChunk(tool_call=ToolCall(id="essai-1", name="sessions_essai", args={}))
            return
        if "Attends" in dernier["content"]:
            yield ModelChunk(text="D'accord, j'attends.")
            return
        yield ModelChunk(text=REPONSE_LONGUE + ".")


def registre_essai(journal: list[str]) -> ToolRegistry:
    def sessions() -> ToolResult:
        journal.append("sessions_essai")
        return ToolResult(ok=True, data={"etat": "terminée, PILOTE OK"})

    r = ToolRegistry()
    r.register(ToolSpec("sessions_essai", "État factice de la session pilote", ToolSafetyLevel.READ_ONLY,
                        {"type": "object", "properties": {}, "required": []}, sessions))
    return r


class CDP:
    """Client minimal du protocole DevTools : commandes par identifiant."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.n = 0

    async def __call__(self, methode: str, **params: Any) -> dict[str, Any]:
        self.n += 1
        ident = self.n
        await self.ws.send(json.dumps({"id": ident, "method": methode, "params": params}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError(f"{methode} : {message['error']}")
                return message.get("result", {})

    async def evaluer(self, expression: str, geste: bool = False) -> Any:
        r = await self("Runtime.evaluate", expression=expression, returnByValue=True,
                       awaitPromise=True, userGesture=geste)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("text", "exception"))
        return r.get("result", {}).get("value")

    async def capture(self, chemin: Path) -> None:
        r = await self("Page.captureScreenshot", format="png")
        chemin.write_bytes(base64.b64decode(r["data"]))


async def demarrer_chrome(profil: Path, wav: Path) -> tuple[subprocess.Popen, int]:
    proc = subprocess.Popen(
        [
            CHROME, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profil}",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--mute-audio",
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={wav}%noloop",
            # Sans cela, le service audio en bac à sable de macOS ne lit pas le
            # fichier et le micro simulé reste muet (constaté avec Chrome 157).
            "--disable-features=AudioServiceSandbox",
            "--autoplay-policy=no-user-gesture-required", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    fichier = profil / "DevToolsActivePort"
    for _ in range(100):
        if fichier.exists() and fichier.read_text().strip():
            return proc, int(fichier.read_text().splitlines()[0])
        await asyncio.sleep(0.1)
    proc.kill()
    raise RuntimeError("Chrome n'a pas ouvert son port DevTools")


async def essai(sortie: Path | None, delai_s: float) -> dict[str, Any]:
    journal_outils: list[str] = []
    fournisseurs: list[ChainProvider] = []

    micro = bytearray()

    def fabrique() -> Appel:
        impl = ChainProvider(ScriptedSTT(list(PHRASES)), ChatEssai(), MacSayTTS("Thomas"))
        fournisseurs.append(impl)
        recevoir = impl.send_audio_chunk

        async def enregistrer(pcm16: bytes) -> None:  # copie de ce que le serveur reçoit
            micro.extend(pcm16)
            await recevoir(pcm16)

        impl.send_audio_chunk = enregistrer  # type: ignore[method-assign]
        return Appel(
            fournisseur=impl, config=ProviderConfig(model=impl.label, api_key="", input_sample_rate=16000),
            nom_fournisseur="chain", libelle=impl.label, consigne_systeme="Essai.", entree=16000,
            sortie=impl.output_sample_rate, registre=registre_essai(journal_outils), salutation=False,
        )

    serveur = ServeurTelephone(fabrique, port=0)
    port = await serveur.demarrer()
    profil = Path(tempfile.mkdtemp(prefix="vr-essai-chrome-"))
    wav, segments = scenario_micro(profil)
    chrome, port_cdp = await demarrer_chrome(profil, wav)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            pages = (await client.get(f"http://127.0.0.1:{port_cdp}/json/list")).json()
        cible = next(p for p in pages if p.get("type") == "page")
        async with connect(cible["webSocketDebuggerUrl"], max_size=50 * 2**20) as ws:
            cdp = CDP(ws)
            await cdp("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
            await cdp("Page.enable")
            await cdp("Page.navigate", url=f"http://localhost:{port}/")
            for _ in range(50):
                if await cdp.evaluer("document.readyState") == "complete":
                    break
                await asyncio.sleep(0.1)
            if sortie:
                await cdp.capture(sortie / "B4-page-repos.png")
            await cdp.evaluer("document.getElementById('appel').click()", geste=True)

            etat: dict[str, Any] = {}
            fin_attente = time.monotonic() + delai_s
            capture_faite = False
            while time.monotonic() < fin_attente:
                await asyncio.sleep(0.25)
                etat = await cdp.evaluer("JSON.stringify(window.__telephone)")
                etat = json.loads(etat)
                finals = [e for e in etat["evenements"] if e.get("ev") == "transcription"
                          and e.get("role") == "modele" and e.get("final")]
                if sortie and not capture_faite and etat["etat"] == "parle" and len(finals) >= 1:
                    await cdp.capture(sortie / "B4-page-appel.png")
                    capture_faite = True
                outil_fini = any(e.get("ev") == "outil" and e.get("etape") == "resultat" for e in etat["evenements"])
                if outil_fini and any("PILOTE OK" in e["texte"] for e in finals) and etat["etat"] != "parle":
                    break
            if sortie and not capture_faite:
                await cdp.capture(sortie / "B4-page-appel.png")
            await cdp.evaluer("document.getElementById('appel').click()", geste=True)
            await asyncio.sleep(0.5)
            etat = json.loads(await cdp.evaluer("JSON.stringify(window.__telephone)"))
            texte_page = await cdp.evaluer("document.getElementById('journal').innerText")
    finally:
        chrome.terminate()
        with contextlib.suppress(Exception):
            chrome.wait(5)
        shutil.rmtree(profil, ignore_errors=True)
        pont = serveur._pont
        await serveur.arreter()

    impl = fournisseurs[0] if fournisseurs else None
    if sortie and micro:
        from voice_realtime.providers.chain_audio import pcm16_to_wav

        (sortie / "B4-micro-recu.wav").write_bytes(pcm16_to_wav(bytes(micro), 16000))
    evs = etat.get("evenements", [])
    transcriptions = [(e["role"], e["texte"]) for e in evs if e.get("ev") == "transcription" and e.get("final")]
    ratio = (etat.get("frequenceContexte") or 48000) / 24000
    rapport = {
        "duree_essai_s": round(time.monotonic() - t0, 1),
        "scenario_parole_s": segments,
        "frequence_contexte_navigateur": etat.get("frequenceContexte"),
        "page": {
            "octets_micro_envoyes": etat.get("octetsEnvoyes"),
            "echantillons_voix_recus": etat.get("echantillonsRecus"),
            "echantillons_voix_joues": etat.get("echantillonsJoues"),
            "interruptions": etat.get("interruptions"),
            "echantillons_vides_par_la_coupure": round((etat.get("echantillonsRecus") or 0) * ratio)
            - (etat.get("echantillonsJoues") or 0),
            "fin": etat.get("fin"),
            "erreurs": etat.get("erreurs"),
            "transcriptions_finales": transcriptions,
            "outils": [(e["nom"], e["etape"], e.get("ok")) for e in evs if e.get("ev") == "outil"],
            "journal_affiche": texte_page,
        },
        "serveur": {
            "octets_audio_recus": pont.octets_recus if pont else None,
            "secondes_audio_recues": round(pont.octets_recus / 32000, 2) if pont else None,
            "octets_voix_envoyes": pont.octets_envoyes if pont else None,
            "motif_fin": pont.motif_fin if pont else None,
            "enonces_transcrits": [r for r in (impl.stt.received if impl else [])],
            "outils_executes": journal_outils,
            "metriques_tours": [asdict(m) for m in (impl.metrics if impl else [])],
        },
    }
    controles = {
        "micro_du_navigateur_recu": (rapport["serveur"]["secondes_audio_recues"] or 0) >= 5.0,
        "trois_enonces_decoupes": len(rapport["serveur"]["enonces_transcrits"]) == 3,
        "coupure_pendant_la_voix": (etat.get("interruptions") or 0) >= 1
        and rapport["page"]["echantillons_vides_par_la_coupure"] > 0,
        "reponses_apres_coupure": [t for r, t in transcriptions if r == "modele"][-2:]
        == ["D'accord, j'attends.", "La session pilote répond : terminée, PILOTE OK."],
        "voix_jouee_par_la_page": (etat.get("echantillonsJoues") or 0) > 0,
        "outil_appele_et_affiche": journal_outils == ["sessions_essai"]
        and ("sessions_essai", "resultat", True) in rapport["page"]["outils"],
        "raccroche": rapport["serveur"]["motif_fin"] == "raccroche",
    }
    rapport["controles"] = controles
    rapport["reussi"] = all(controles.values())
    return rapport


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sortie", type=Path, help="Dossier où écrire le rapport JSON et les captures")
    parser.add_argument("--delai", type=float, default=40.0, help="Attente maximale de l'appel (s)")
    args = parser.parse_args()
    if not Path(CHROME).exists():
        print(f"Chrome introuvable : {CHROME}", file=sys.stderr)
        return 2
    if args.sortie:
        args.sortie.mkdir(parents=True, exist_ok=True)
    rapport = asyncio.run(essai(args.sortie, args.delai))
    texte = json.dumps(rapport, ensure_ascii=False, indent=2)
    if args.sortie:
        (args.sortie / "B4-essai-chrome.json").write_text(texte + "\n", encoding="utf-8")
    print(texte)
    return 0 if rapport["reussi"] else 1


if __name__ == "__main__":
    sys.exit(main())
