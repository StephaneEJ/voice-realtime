"""Garde-fous du banc N3 : rien de payant à blanc, budget tenu sinon, jamais la nuit.

Trois verrous indépendants :

1. **Liste fermée des étages gratuits.** À blanc, seuls des étages qui ne
   sortent pas de la machine sont joués (simulés, scripts, `whisper-cpp`,
   `echo`, `say`, ou une API compatible servie en boucle locale, par exemple
   Ollama). Le verdict dépend du genre de l'étage, pas de la grille de prix :
   une erreur de grille ne rend rien payant gratuit.
2. **Réseau coupé.** Pendant un passage à blanc, toute connexion vers une
   adresse hors boucle locale lève `ConnexionInterdite`, même si un étage
   oubliait sa nature.
3. **Passage payant encadré.** Il exige une autorisation explicite, un budget
   strictement positif, un prix connu pour chaque étage, un majorant estimé
   sous le budget, et une heure hors de la plage de nuit (22:00 à 07:00, heure
   de Paris).
"""

from __future__ import annotations

import contextlib
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterator
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..providers.chain_stages import parse_spec
from ..url_sure import hote_local

PARIS = ZoneInfo("Europe/Paris")
NUIT_DEBUT_H = 22
NUIT_FIN_H = 7

ETAGES_GRATUITS = {
    "stt": frozenset({"simule", "script", "whisper-cpp"}),
    "llm": frozenset({"simule", "echo"}),
    "tts": frozenset({"simule", "say"}),
}
GENRES_COMPATIBLES = frozenset({"openai"})  # API compatible, gratuite seulement en boucle locale


class ConnexionInterdite(ConnectionError):
    """Connexion réseau tentée pendant un passage à blanc."""


class PassageRefuse(RuntimeError):
    """Passage du banc refusé par un garde-fou (motif lisible, sans secret)."""


_hote_local = hote_local  # un seul test d'hôte local pour le banc et les URL de service (N12)


def etage_gratuit(etage: str, spec: str) -> bool:
    """Vrai si l'étage ne peut rien facturer : genre local, ou API compatible en boucle locale."""
    try:
        s = parse_spec(spec)
    except ValueError:
        return False
    if s.kind in ETAGES_GRATUITS.get(etage, frozenset()):
        return s.base_url is None
    if s.kind in GENRES_COMPATIBLES and s.base_url:
        return _hote_local(urlparse(s.base_url).hostname)
    return False


def candidat_gratuit(candidat: Any) -> bool:
    if candidat.genre != "chaine":
        return False  # fournisseurs temps réel : toujours payants
    return all(
        etage_gratuit(etage, spec)
        for etage, spec in (("stt", candidat.stt), ("llm", candidat.llm), ("tts", candidat.tts))
    )


def _adresse_locale(famille: int, adresse: Any) -> bool:
    if famille == getattr(socket, "AF_UNIX", object()):
        return True
    if isinstance(adresse, tuple) and adresse:
        return _hote_local(str(adresse[0]))
    return False


@contextlib.contextmanager
def reseau_coupe() -> Iterator[list[str]]:
    """Refuse toute connexion hors boucle locale ; rend la liste des tentatives bloquées."""
    tentatives: list[str] = []
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def garde(sock: socket.socket, adresse: Any) -> None:
        if not _adresse_locale(sock.family, adresse):
            hote = adresse[0] if isinstance(adresse, tuple) and adresse else "?"
            tentatives.append(str(hote))
            raise ConnexionInterdite(f"banc à blanc : connexion vers {hote} refusée")

    def connect_garde(sock: socket.socket, adresse: Any) -> Any:
        garde(sock, adresse)
        return connect(sock, adresse)

    def connect_ex_garde(sock: socket.socket, adresse: Any) -> Any:
        garde(sock, adresse)
        return connect_ex(sock, adresse)

    def getaddrinfo_garde(hote: Any, *args: Any, **kwargs: Any) -> Any:
        if hote is not None and not _hote_local(hote.decode() if isinstance(hote, bytes) else str(hote)):
            tentatives.append(str(hote))
            raise ConnexionInterdite(f"banc à blanc : résolution de {hote} refusée")
        return getaddrinfo(hote, *args, **kwargs)

    socket.socket.connect = connect_garde  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex_garde  # type: ignore[method-assign]
    socket.getaddrinfo = getaddrinfo_garde  # type: ignore[assignment]
    try:
        yield tentatives
    finally:
        socket.socket.connect = connect  # type: ignore[method-assign]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
        socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def est_la_nuit(maintenant: datetime) -> bool:
    heure = maintenant.astimezone(PARIS).hour
    return heure >= NUIT_DEBUT_H or heure < NUIT_FIN_H


@dataclass(frozen=True)
class AutorisationPayante:
    budget_usd: float
    autorise: bool = False


def verifier_passage_payant(
    candidats: list[Any],
    autorisation: AutorisationPayante | None,
    estimer: Callable[[Any], Any],
    *,
    maintenant: datetime | None = None,
) -> float:
    """Lève `PassageRefuse` si un candidat payant ne peut pas être joué ; rend le majorant total."""
    payants = [c for c in candidats if not candidat_gratuit(c)]
    if not payants:
        return 0.0
    noms = ", ".join(c.id for c in payants)
    if autorisation is None or not autorisation.autorise:
        raise PassageRefuse(f"candidats payants sans autorisation explicite : {noms}")
    if autorisation.budget_usd <= 0:
        raise PassageRefuse("budget payant absent ou nul : passage refusé")
    if est_la_nuit(maintenant or datetime.now(PARIS)):
        raise PassageRefuse("passage payant refusé la nuit (22:00 à 07:00, heure de Paris)")
    total = 0.0
    for c in payants:
        chiffrage = estimer(c)
        if chiffrage.cout_usd is None:
            raise PassageRefuse(f"{c.id} : prix inconnu ({'; '.join(chiffrage.inconnus)}), budget intenable")
        total += chiffrage.cout_usd
    if total > autorisation.budget_usd:
        raise PassageRefuse(
            f"majorant estimé {total:.2f} $ au-dessus du budget {autorisation.budget_usd:.2f} $"
        )
    return total
