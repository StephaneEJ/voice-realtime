"""Serveur de la page téléphone : HTTP pour la page, WebSocket pour l'appel.

Un seul port, une seule dépendance (`websockets`, déjà présente) :

- `GET /`, `/telephone.js`, `/telephone.css`, `/worklets.js`, `/manifest.webmanifest` : la page ;
- `GET /sante` : état minimal en JSON (aucune donnée de session) ;
- `GET /ws` (WebSocket) : un appel ; un seul appel à la fois.

Verrous locaux, en plus de l'application Cloudflare Access en bordure :

1. écoute sur la boucle locale par défaut (le tunnel s'y connecte) ; toute autre
   adresse d'écoute exige Access ou le jeton local, sinon le serveur refuse de partir ;
2. en-tête `Host` dans une liste fermée (contre le rattachement DNS : une page
   tierce qui ferait pointer son nom vers 127.0.0.1 est refusée) ;
3. `Origin` du WebSocket identique à l'hôte servi ou à un nom public déclaré
   (contre le détournement de WebSocket intersite) ;
4. quand la page est exposée (nom public déclaré), au moins un verrou de plus,
   au choix ou cumulés :
   - jeton Access vérifié (signature, audience, adresse), si le tunnel transmet
     `Cf-Access-Jwt-Assertion` ;
   - jeton local `Authorization: Bearer` (fichier 600), si un relais (Worker du
     Cockpit, comme l'écran O5) retire le jeton Access et ajoute le sien.

Un préfixe (`--prefixe /voix`) permet de servir la page sous un chemin public ;
la page n'emploie que des adresses relatives.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import ipaddress
import json
import mimetypes
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from ..log import get_logger
from .acces import ENTETE_JETON, AccesRefuse, VerificateurAcces
from .pont import FabriqueAppel, PontAppel, TAILLE_MAX_TRAME

logger = get_logger("voice_realtime.telephone.serveur")

HOTE_PAR_DEFAUT = "127.0.0.1"
PORT_PAR_DEFAUT = 7720
DOSSIER_STATIQUE = Path(__file__).parent / "static"
FICHIERS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/telephone.js": "telephone.js",
    "/telephone.css": "telephone.css",
    "/worklets.js": "worklets.js",
    "/manifest.webmanifest": "manifest.webmanifest",
    "/icone.svg": "icone.svg",
}
NOMS_LOCAUX = ("localhost", "127.0.0.1", "[::1]")


def est_boucle_locale(hote: str) -> bool:
    """Vrai pour `localhost` et les adresses de bouclage ; `0.0.0.0`, `::` et tout nom sont exclus."""
    nom = (hote or "").strip().strip("[]").lower()
    if nom == "localhost":
        return True
    try:
        return ipaddress.ip_address(nom).is_loopback
    except ValueError:
        return False


def _type_mime(nom: str) -> str:
    if nom.endswith(".webmanifest"):
        return "application/manifest+json"
    if nom.endswith(".js"):
        return "text/javascript; charset=utf-8"
    guess = mimetypes.guess_type(nom)[0] or "application/octet-stream"
    return guess + ("; charset=utf-8" if guess.startswith("text/") else "")


def _politique_contenu(hotes: list[str]) -> str:
    # `connect-src 'self'` couvre ws:/wss: en CSP 3, mais pas sur tous les
    # Safari : les hôtes sont ajoutés explicitement.
    connexions = " ".join(f"wss://{h} ws://{h}" for h in hotes)
    return (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        f"connect-src 'self' {connexions}; worker-src 'self'; manifest-src 'self'; "
        "media-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


def _reponse(statut: HTTPStatus, corps: bytes, type_mime: str, extra: dict[str, str] | None = None) -> Response:
    entetes = Headers()
    entetes["Content-Type"] = type_mime
    entetes["Content-Length"] = str(len(corps))
    entetes["Cache-Control"] = "no-store"
    entetes["X-Content-Type-Options"] = "nosniff"
    entetes["Referrer-Policy"] = "no-referrer"
    entetes["X-Frame-Options"] = "DENY"
    entetes["Connection"] = "close"
    for cle, valeur in (extra or {}).items():
        entetes[cle] = valeur
    return Response(statut.value, statut.phrase, entetes, corps)


def _texte(statut: HTTPStatus, message: str) -> Response:
    return _reponse(statut, (message + "\n").encode(), "text/plain; charset=utf-8")


@dataclass
class ServeurTelephone:
    fabrique: FabriqueAppel
    hote: str = HOTE_PAR_DEFAUT
    port: int = PORT_PAR_DEFAUT
    noms_publics: tuple[str, ...] = ()
    acces: VerificateurAcces | None = None
    jeton: str | None = field(default=None, repr=False)
    prefixe: str = ""
    _serveur: Server | None = field(default=None, init=False, repr=False)
    _pont: PontAppel | None = field(default=None, init=False, repr=False)
    _fichiers: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    appels: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not est_boucle_locale(self.hote) and self.acces is None and not self.jeton:
            # Hors boucle locale, tout appareil du réseau joindrait le port et forgerait
            # Host et Origin : il obtiendrait un appel complet (outils et dépense).
            raise ValueError(
                f"écoute sur {self.hote} hors boucle locale : verrou local exigé, vérification Access "
                "(--access-equipe, --access-aud, --access-adresse) ou jeton local (--jeton-fichier)"
            )
        if self.noms_publics and self.acces is None and not self.jeton:
            raise ValueError(
                "un nom public exige un verrou local : vérification Access "
                "(--access-equipe, --access-aud, --access-adresse) ou jeton local (--jeton-fichier)"
            )
        if self.jeton is not None and len(self.jeton) < 32:
            raise ValueError("jeton local trop court (32 caractères au moins)")
        self.prefixe = self.prefixe.rstrip("/")
        if self.prefixe and not self.prefixe.startswith("/"):
            raise ValueError("le préfixe commence par /")
        self.noms_publics = tuple(n.strip().lower() for n in self.noms_publics if n.strip())
        for chemin, nom in FICHIERS.items():
            self._fichiers[chemin] = (DOSSIER_STATIQUE / nom).read_bytes()

    # -- cycle de vie ------------------------------------------------------

    async def demarrer(self) -> int:
        self._serveur = await serve(
            self._gerer_appel,
            self.hote,
            self.port,
            process_request=self._traiter_requete,
            max_size=TAILLE_MAX_TRAME,
            ping_interval=20,
            ping_timeout=20,
            server_header=None,
        )
        port = self._serveur.sockets[0].getsockname()[1] if self._serveur.sockets else self.port
        self.port = port
        logger.info("page téléphone sur http://%s:%d/", self.hote, port)
        return port

    async def arreter(self) -> None:
        if self._pont is not None:
            await self._pont.terminer("arret_serveur")
        if self._serveur is not None:
            self._serveur.close()
            await self._serveur.wait_closed()

    async def servir(self) -> None:
        if self._serveur is None:
            await self.demarrer()
        assert self._serveur is not None
        await self._serveur.serve_forever()

    @property
    def appel_en_cours(self) -> bool:
        return self._pont is not None and not self._pont.termine

    # -- contrôles ---------------------------------------------------------

    def _hotes_autorises(self) -> set[str]:
        ports = {str(self.port)}
        autorises = {f"{n}:{p}" for n in NOMS_LOCAUX for p in ports}
        autorises |= set(self.noms_publics)
        return autorises

    def _hote_valide(self, requete: Request) -> str | None:
        hote = (requete.headers.get("Host") or "").strip().lower()
        return hote if hote in self._hotes_autorises() else None

    def _verifier_acces(self, requete: Request) -> str | None:
        """Adresse autorisée, ou `None` si Access n'est pas configuré. Lève `AccesRefuse`."""
        if self.acces is None:
            return None
        return self.acces.verifier(requete.headers.get(ENTETE_JETON))

    def _jeton_valide(self, requete: Request) -> bool:
        if self.jeton is None:
            return True
        attendu = f"Bearer {self.jeton}".encode()
        recu = (requete.headers.get("Authorization") or "").encode()
        return hmac.compare_digest(recu, attendu)

    def _chemin_local(self, chemin: str) -> str | None:
        if not self.prefixe:
            return chemin
        if chemin == self.prefixe + "/" or chemin.startswith(self.prefixe + "/"):
            return chemin[len(self.prefixe):]
        return None

    def _traiter_requete(self, connexion: ServerConnection, requete: Request) -> Response | None:
        chemin = self._chemin_local(urlsplit(requete.path).path)
        hote = self._hote_valide(requete)
        if hote is None:
            logger.warning("hôte refusé : %r", (requete.headers.get("Host") or "")[:80])
            return _texte(HTTPStatus.MISDIRECTED_REQUEST, "hôte non reconnu")
        if not self._jeton_valide(requete):
            logger.warning("jeton local absent ou faux")
            return _texte(HTTPStatus.UNAUTHORIZED, "jeton local requis")
        try:
            self._verifier_acces(requete)
        except AccesRefuse as exc:
            logger.warning("accès refusé (%s)", exc.motif)
            return _texte(HTTPStatus.FORBIDDEN, f"accès refusé : {exc.motif}")
        if chemin is None:
            return _texte(HTTPStatus.NOT_FOUND, "introuvable")

        if chemin == "/ws":
            origine = requete.headers.get("Origin") or ""
            parts = urlsplit(origine)
            origines = {hote} | set(self.noms_publics)
            if parts.scheme not in ("http", "https") or parts.netloc.lower() not in origines:
                logger.warning("origine refusée : %r", origine[:80])
                return _texte(HTTPStatus.FORBIDDEN, "origine refusée")
            return None  # poignée de main WebSocket
        if chemin == "/sante":
            corps = json.dumps({"ok": True, "appelEnCours": self.appel_en_cours, "appels": self.appels}).encode()
            return _reponse(HTTPStatus.OK, corps, "application/json")
        nom = FICHIERS.get(chemin)
        if nom is None:
            return _texte(HTTPStatus.NOT_FOUND, "introuvable")
        extra = {}
        if nom == "index.html":
            extra = {
                "Content-Security-Policy": _politique_contenu([hote, *(n for n in self.noms_publics if n != hote)]),
                "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), display-capture=()",
            }
        return _reponse(HTTPStatus.OK, self._fichiers[chemin], _type_mime(nom), extra)

    # -- appel -------------------------------------------------------------

    async def _gerer_appel(self, ws: ServerConnection) -> None:
        if self.appel_en_cours:
            with contextlib.suppress(ConnectionClosed):
                await ws.send(json.dumps({"ev": "erreur", "code": "occupe", "message": "un appel est déjà en cours"}))
                await ws.close(1013, "occupé")
            return

        class _Transport:
            async def envoyer_json(self, message: dict[str, Any]) -> None:
                await ws.send(json.dumps(message, ensure_ascii=False))

            async def envoyer_audio(self, pcm16: bytes) -> None:
                await ws.send(pcm16)

        try:
            appel = self.fabrique()
        except Exception as exc:
            logger.exception("préparation de l'appel impossible")
            with contextlib.suppress(ConnectionClosed):
                await ws.send(json.dumps({"ev": "erreur", "code": "configuration", "message": str(exc)[:200]}))
                await ws.close(1011, "configuration")
            return
        pont = PontAppel(appel, _Transport())
        self._pont = pont
        self.appels += 1
        await pont.demarrer()

        async def lire() -> None:
            async for message in ws:
                if isinstance(message, bytes):
                    await pont.recevoir_audio(message)
                else:
                    try:
                        commande = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    await pont.recevoir_commande(commande)

        lecture = asyncio.create_task(lire(), name="telephone-lecture")
        fin = asyncio.create_task(pont.attendre_fin(), name="telephone-fin")
        try:
            await asyncio.wait({lecture, fin}, return_when=asyncio.FIRST_COMPLETED)
        except ConnectionClosed:
            pass
        finally:
            if not pont.termine:
                await pont.terminer("deconnexion")
            for tache in (lecture, fin):
                tache.cancel()
                with contextlib.suppress(asyncio.CancelledError, ConnectionClosed, Exception):
                    await tache
            with contextlib.suppress(ConnectionClosed):
                await ws.close(1000, pont.motif_fin or "fin")
