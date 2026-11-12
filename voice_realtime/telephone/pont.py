"""Pont d'un appel téléphonique : page du téléphone ↔ fournisseur vocal.

Le pont ne connaît ni le navigateur ni le fournisseur : il reçoit des trames
PCM16 mono et des commandes JSON d'un `Transport`, les pousse dans un
`RealtimeVoiceProvider` (Gemini Live, OpenAI Realtime ou mode chaîne), et
renvoie au transport l'audio produit et des événements courts.

Protocole vers la page (JSON, sauf l'audio en binaire PCM16 à `sortie` Hz) :

    {"ev": "pret", "entree": 16000, "sortie": 24000, "fournisseur": "...", "outils": [...], "maxMinutes": 15}
    {"ev": "transcription", "role": "utilisateur"|"modele", "texte": "...", "final": true}
    {"ev": "interrompu"}                       # vider la lecture en cours
    {"ev": "outil", "nom": "...", "etape": "appel"|"resultat", "ok": true, "dureeMs": 12.0}
    {"ev": "cout", "totalUsd": 0.01, "ecouleS": 12.3}
    {"ev": "muet", "actif": true}
    {"ev": "erreur", "code": "...", "message": "..."}
    {"ev": "fin", "motif": "raccroche"|"mot_arret"|"duree_max"|"cout_max"|"deconnexion"|"erreur_fournisseur"}

Depuis la page : trames binaires PCM16 à `entree` Hz, et

    {"op": "muet", "actif": true} · {"op": "raccrocher"} · {"op": "texte", "texte": "..."} · {"op": "ping"}

Sécurité : le garde-fou, la liste blanche et la confirmation en deux temps de
l'orchestrateur restent côté serveur MCP. Le pont n'envoie à la page que le
nom des outils et leur succès, jamais leurs arguments ni leurs résultats
(textes de sessions = données non fiables).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..cost_tracker import CostTracker
from ..log import get_logger
from ..providers.base import ProviderConfig
from ..tools.registry import ToolRegistry

logger = get_logger("voice_realtime.telephone")

TAILLE_MAX_TRAME = 64 * 1024  # 1 s à 32 kHz ; une page envoie des trames de 20 ms
LONGUEUR_MAX_TEXTE = 2000
TAMPON_MOT_ARRET = 240


class Transport(Protocol):
    async def envoyer_json(self, message: dict[str, Any]) -> None: ...

    async def envoyer_audio(self, pcm16: bytes) -> None: ...


@dataclass
class Appel:
    """Ce qu'il faut pour ouvrir un appel : un fournisseur neuf et sa configuration."""

    fournisseur: Any  # RealtimeVoiceProvider
    config: ProviderConfig
    nom_fournisseur: str
    libelle: str
    consigne_systeme: str
    entree: int
    sortie: int
    registre: ToolRegistry | None = None
    salutation: bool = True
    demander_avant_agir: bool = False
    max_minutes: float = 15.0
    cout_max_usd: float = 3.0


FabriqueAppel = Callable[[], Appel]


def _mot_arret(texte: str) -> bool:
    from ..cli import _is_killchat_keyword

    return _is_killchat_keyword(texte)


@dataclass
class PontAppel:
    appel: Appel
    transport: Transport
    intervalle_controle_s: float = 1.0
    tracker: CostTracker = field(init=False)
    motif_fin: str | None = field(default=None, init=False)
    muet: bool = field(default=False, init=False)
    octets_recus: int = field(default=0, init=False)
    octets_envoyes: int = field(default=0, init=False)
    _fin: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _taches: set[asyncio.Task] = field(default_factory=set, init=False)
    _tampon_mot_arret: str = field(default="", init=False)
    _connecte: bool = field(default=False, init=False)
    _ferme: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.tracker = CostTracker(
            provider=self.appel.nom_fournisseur,
            model=self.appel.config.model,
            hard_stop_cost_usd=self.appel.cout_max_usd,
            max_duration_seconds=self.appel.max_minutes * 60.0,
        )

    # -- cycle de vie ------------------------------------------------------

    async def demarrer(self) -> None:
        a = self.appel
        outils = a.registre.provider_specs() if a.registre and a.registre.names() else None
        try:
            await a.fournisseur.connect(a.config, system_prompt=a.consigne_systeme, audio=True, tools=outils)
        except Exception as exc:
            logger.exception("connexion au fournisseur impossible")
            await self._envoyer({"ev": "erreur", "code": "connexion_fournisseur", "message": type(exc).__name__})
            await self.terminer("erreur_fournisseur")
            return
        self._connecte = True
        await self._envoyer({
            "ev": "pret",
            "entree": a.entree,
            "sortie": a.sortie,
            "fournisseur": a.libelle,
            "outils": a.registre.names() if a.registre else [],
            "maxMinutes": a.max_minutes,
        })
        self._lancer(self._pompe_evenements(), "telephone-evenements")
        self._lancer(self._surveillance(), "telephone-surveillance")
        if a.salutation:
            try:
                await a.fournisseur.send_text("Démarre.")
            except Exception:
                logger.warning("salutation impossible (non bloquant)", exc_info=True)

    async def attendre_fin(self) -> str:
        await self._fin.wait()
        return self.motif_fin or "inconnu"

    @property
    def termine(self) -> bool:
        return self._fin.is_set()

    async def terminer(self, motif: str) -> None:
        if self._ferme:
            return
        self._ferme = True
        self.motif_fin = motif
        logger.info("fin d'appel : %s (reçu %d o, envoyé %d o)", motif, self.octets_recus, self.octets_envoyes)
        await self._envoyer({"ev": "fin", "motif": motif})
        if self._connecte:
            with contextlib.suppress(Exception):
                await self.appel.fournisseur.close()
        courante = asyncio.current_task()
        for tache in list(self._taches):
            if tache is not courante and not tache.done():
                tache.cancel()
        self._fin.set()

    # -- entrées de la page ------------------------------------------------

    async def recevoir_audio(self, pcm16: bytes) -> None:
        if self._ferme or not self._connecte or self.muet:
            return
        if not pcm16 or len(pcm16) % 2 or len(pcm16) > TAILLE_MAX_TRAME:
            await self._envoyer({"ev": "erreur", "code": "trame_invalide", "message": f"{len(pcm16)} octets"})
            return
        self.octets_recus += len(pcm16)
        try:
            await self.appel.fournisseur.send_audio_chunk(pcm16)
        except Exception:
            logger.exception("envoi audio au fournisseur impossible")
            await self.terminer("erreur_fournisseur")

    async def recevoir_commande(self, message: Any) -> None:
        if self._ferme or not isinstance(message, dict):
            return
        op = message.get("op")
        if op == "muet":
            self.muet = bool(message.get("actif"))
            await self._envoyer({"ev": "muet", "actif": self.muet})
        elif op == "raccrocher":
            await self.terminer("raccroche")
        elif op == "texte":
            texte = str(message.get("texte") or "").strip()[:LONGUEUR_MAX_TEXTE]
            if texte and self._connecte:
                await self._envoyer({"ev": "transcription", "role": "utilisateur", "texte": texte, "final": True})
                if _mot_arret(texte):
                    await self.terminer("mot_arret")
                    return
                await self.appel.fournisseur.send_text(texte)
        elif op == "ping":
            await self._envoyer({"ev": "pong"})
        else:
            await self._envoyer({"ev": "erreur", "code": "commande_inconnue", "message": str(op)[:40]})

    # -- interne -----------------------------------------------------------

    def _lancer(self, coro: Awaitable[Any], nom: str) -> asyncio.Task:
        tache = asyncio.ensure_future(coro)
        tache.set_name(nom)
        self._taches.add(tache)
        tache.add_done_callback(self._taches.discard)
        return tache

    async def _envoyer(self, message: dict[str, Any]) -> None:
        try:
            await self.transport.envoyer_json(message)
        except Exception:
            logger.debug("page injoignable pour %s", message.get("ev"))

    async def _surveillance(self) -> None:
        dernier_cout = 0.0
        while not self._ferme:
            await asyncio.sleep(self.intervalle_controle_s)
            arreter, raison = self.tracker.should_kill()
            if arreter:
                await self.terminer("cout_max" if "cost" in raison else "duree_max")
                return
            maintenant = time.monotonic()
            if maintenant - dernier_cout >= 5.0:
                dernier_cout = maintenant
                await self._envoyer({
                    "ev": "cout",
                    "totalUsd": round(self.tracker.estimated_cost_usd, 4),
                    "ecouleS": round(self.tracker.elapsed_seconds, 1),
                })

    async def _verifier_mot_arret(self, texte: str, *, partiel: bool) -> bool:
        if partiel:
            self._tampon_mot_arret = (self._tampon_mot_arret + texte)[-TAMPON_MOT_ARRET:]
            candidat = self._tampon_mot_arret
        else:
            candidat = texte
        if _mot_arret(candidat):
            logger.info("mot d'arrêt reconnu")
            await self.terminer("mot_arret")
            return True
        return False

    async def _pompe_evenements(self) -> None:
        f = self.appel.fournisseur
        try:
            async for ev in f.receive_events():
                if self._ferme:
                    return
                d = ev.data
                if ev.kind == "audio_chunk_out":
                    pcm = d.get("pcm16", b"")
                    if pcm:
                        self._tampon_mot_arret = ""
                        self.octets_envoyes += len(pcm)
                        try:
                            await self.transport.envoyer_audio(pcm)
                        except Exception:
                            await self.terminer("deconnexion")
                            return
                elif ev.kind in ("partial_transcript_user", "final_transcript_user"):
                    texte = d.get("text", "")
                    if not texte:
                        continue
                    final = ev.kind == "final_transcript_user"
                    await self._envoyer({"ev": "transcription", "role": "utilisateur", "texte": texte, "final": final})
                    if await self._verifier_mot_arret(texte, partiel=not final):
                        return
                elif ev.kind in ("partial_transcript_model", "final_transcript_model"):
                    texte = d.get("text", "")
                    if texte:
                        await self._envoyer({
                            "ev": "transcription", "role": "modele", "texte": texte,
                            "final": ev.kind == "final_transcript_model",
                        })
                elif ev.kind == "model_interrupted":
                    await self._envoyer({"ev": "interrompu"})
                elif ev.kind == "tool_call":
                    self._lancer(self._executer_outil(d), "telephone-outil")
                elif ev.kind == "cost_update":
                    t_in = int(d.get("tokens_in", 0) or 0)
                    t_out = int(d.get("tokens_out", 0) or 0)
                    if d.get("mode", "cumulative") == "delta":
                        self.tracker.update_tokens_delta(t_in, t_out)
                    else:
                        self.tracker.update_tokens_cumulative(t_in, t_out)
                elif ev.kind == "error":
                    logger.error("erreur du fournisseur : %s", d)
                    await self._envoyer({"ev": "erreur", "code": "fournisseur", "message": "erreur du fournisseur"})
                    await self.terminer("erreur_fournisseur")
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("flux d'événements du fournisseur interrompu")
            await self.terminer("erreur_fournisseur")
            return
        if not self._ferme:
            await self.terminer("fournisseur_ferme")

    async def _executer_outil(self, donnees: dict[str, Any]) -> None:
        a = self.appel
        call_id = donnees.get("call_id", "") or ""
        nom = donnees.get("name", "") or ""
        args = donnees.get("args", {}) or {}
        t0 = time.monotonic()
        await self._envoyer({"ev": "outil", "nom": nom, "etape": "appel"})
        ok = False
        if a.registre is None or a.registre.get(nom) is None:
            reponse: dict[str, Any] = {"error": f"outil inconnu : {nom}"}
        elif a.demander_avant_agir and a.registre.requires_confirmation(nom):
            # Même règle que `talk` sans interface : sûreté d'abord, refus.
            reponse = {"error": "user_confirmation_required_but_no_ui"}
        else:
            try:
                resultat = await asyncio.to_thread(a.registre.dispatch, nom, **args)
            except Exception as exc:
                logger.exception("outil %r en échec", nom)
                reponse = {"error": f"{type(exc).__name__}: {exc}"}
            else:
                reponse = resultat.as_function_response(nom).get("response", {})
                ok = resultat.ok
        try:
            await a.fournisseur.send_function_response(call_id, nom, reponse)
        except Exception:
            logger.exception("résultat d'outil non transmis au fournisseur")
        await self._envoyer({
            "ev": "outil", "nom": nom, "etape": "resultat", "ok": ok,
            "dureeMs": round((time.monotonic() - t0) * 1000.0, 1),
        })
