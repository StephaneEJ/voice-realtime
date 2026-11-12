"""Vérification du jeton Cloudflare Access (`Cf-Access-Jwt-Assertion`).

Second verrou derrière l'application Access : même si une requête atteint le
port local sans passer par le tunnel (autre processus du Mac, erreur de
configuration), la page et le canal audio exigent un jeton RS256 signé par
l'équipe Access, destiné à l'application (`aud`), non expiré, et dont
l'adresse figure dans la liste autorisée.

Les clés publiques (JWKS) sont lues une fois au démarrage depuis
`https://<équipe>/cdn-cgi/access/certs`, puis relues au plus une fois par
minute quand un `kid` inconnu apparaît (rotation des clés par Cloudflare).
Les tests injectent leurs propres clés : aucun réseau.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ENTETE_JETON = "Cf-Access-Jwt-Assertion"
TOLERANCE_HORLOGE_S = 30
INTERVALLE_RELECTURE_CLES_S = 60.0


class AccesRefuse(Exception):
    """Jeton absent ou invalide. `motif` est court et sans donnée du jeton."""

    def __init__(self, motif: str) -> None:
        super().__init__(motif)
        self.motif = motif


def _b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _entier(data: str) -> int:
    return int.from_bytes(_b64url(data), "big")


def cles_depuis_jwks(jwks: dict[str, Any]) -> dict[str, rsa.RSAPublicKey]:
    """`kid` → clé publique RSA, pour les clés de signature RS256 du JWKS."""
    cles: dict[str, rsa.RSAPublicKey] = {}
    for cle in jwks.get("keys", []) or []:
        if cle.get("kty") != "RSA" or cle.get("alg", "RS256") != "RS256":
            continue
        if cle.get("use", "sig") != "sig" or not cle.get("kid"):
            continue
        try:
            cles[cle["kid"]] = rsa.RSAPublicNumbers(_entier(cle["e"]), _entier(cle["n"])).public_key()
        except (KeyError, ValueError):
            continue
    return cles


def normaliser_equipe(equipe: str) -> str:
    """`dufresne` ou `dufresne.cloudflareaccess.com` → `https://dufresne.cloudflareaccess.com`."""
    equipe = equipe.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not equipe:
        raise ValueError("équipe Access vide")
    if "." not in equipe:
        equipe = f"{equipe}.cloudflareaccess.com"
    return f"https://{equipe}"


def lire_jwks_distant(emetteur: str, delai_s: float = 10.0) -> dict[str, Any]:
    import httpx

    reponse = httpx.get(f"{emetteur}/cdn-cgi/access/certs", timeout=delai_s)
    reponse.raise_for_status()
    return reponse.json()


@dataclass
class VerificateurAcces:
    """Valide un jeton Access pour une application et une liste d'adresses."""

    emetteur: str  # https://<équipe>.cloudflareaccess.com
    audience: str  # étiquette AUD de l'application Access
    adresses: frozenset[str]
    lire_jwks: Callable[[], dict[str, Any]] | None = None
    horloge: Callable[[], float] = time.time
    _cles: dict[str, rsa.RSAPublicKey] = field(default_factory=dict, init=False, repr=False)
    _derniere_lecture: float = field(default=float("-inf"), init=False, repr=False)
    _verrou: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def construire(
        cls,
        equipe: str,
        audience: str,
        adresses: Iterable[str],
        lire_jwks: Callable[[], dict[str, Any]] | None = None,
        horloge: Callable[[], float] = time.time,
    ) -> "VerificateurAcces":
        emetteur = normaliser_equipe(equipe)
        adresses_norm = frozenset(a.strip().lower() for a in adresses if a and a.strip())
        if not audience.strip():
            raise ValueError("audience Access (AUD) vide")
        if not adresses_norm:
            raise ValueError("aucune adresse autorisée")
        lecteur = lire_jwks or (lambda: lire_jwks_distant(emetteur))
        return cls(emetteur, audience.strip(), adresses_norm, lecteur, horloge)

    def charger_cles(self, force: bool = False) -> int:
        """Relit le JWKS (au plus une fois par minute sauf `force`). Rend le nombre de clés."""
        with self._verrou:
            maintenant = time.monotonic()
            if not force and maintenant - self._derniere_lecture < INTERVALLE_RELECTURE_CLES_S:
                return len(self._cles)
            self._derniere_lecture = maintenant
            assert self.lire_jwks is not None
            cles = cles_depuis_jwks(self.lire_jwks())
            if cles:
                self._cles = cles
            return len(self._cles)

    def verifier(self, jeton: str | None) -> str:
        """Rend l'adresse autorisée portée par le jeton, sinon lève `AccesRefuse`."""
        if not jeton:
            raise AccesRefuse("jeton_absent")
        morceaux = jeton.split(".")
        if len(morceaux) != 3:
            raise AccesRefuse("jeton_malforme")
        try:
            entete = json.loads(_b64url(morceaux[0]))
            charge = json.loads(_b64url(morceaux[1]))
            signature = _b64url(morceaux[2])
        except (ValueError, json.JSONDecodeError):
            raise AccesRefuse("jeton_malforme") from None
        if not isinstance(entete, dict) or not isinstance(charge, dict):
            raise AccesRefuse("jeton_malforme")
        if entete.get("alg") != "RS256":
            raise AccesRefuse("algorithme_refuse")
        kid = entete.get("kid")
        cle = self._cles.get(kid) if kid else None
        if cle is None and kid:
            try:
                self.charger_cles()
            except Exception:
                raise AccesRefuse("cles_indisponibles") from None
            cle = self._cles.get(kid)
        if cle is None:
            raise AccesRefuse("cle_inconnue")
        try:
            cle.verify(
                signature,
                f"{morceaux[0]}.{morceaux[1]}".encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise AccesRefuse("signature_invalide") from None

        maintenant = self.horloge()
        exp = charge.get("exp")
        if not isinstance(exp, (int, float)) or exp + TOLERANCE_HORLOGE_S < maintenant:
            raise AccesRefuse("jeton_expire")
        nbf = charge.get("nbf")
        if isinstance(nbf, (int, float)) and nbf - TOLERANCE_HORLOGE_S > maintenant:
            raise AccesRefuse("jeton_premature")
        if charge.get("iss") != self.emetteur:
            raise AccesRefuse("emetteur_refuse")
        aud = charge.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if self.audience not in audiences:
            raise AccesRefuse("audience_refusee")
        adresse = str(charge.get("email") or "").strip().lower()
        if not adresse or adresse not in self.adresses:
            raise AccesRefuse("adresse_refusee")
        return adresse
