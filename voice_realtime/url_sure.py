"""URL de service acceptées : chiffrées, sauf en boucle locale (N12, revue du 12/11/2026).

L'orchestrateur reçoit le jeton du `headersHelper` ; un modèle compatible OpenAI ou Anthropic
reçoit une clé d'API. Sur `http://` vers un hôte distant, ces en-têtes passeraient en clair.
Seules sont acceptées :

- `https://` vers n'importe quel hôte ;
- `http://` vers la boucle locale (`localhost`, `127.0.0.0/8`, `::1`), cas du serveur MCP du
  Cockpit (`http://127.0.0.1:8765/mcp`) et d'un modèle local (Ollama, llama.cpp).

Tout autre schéma est refusé. Le message d'erreur nomme le schéma et l'hôte, jamais un chemin,
une requête ou des identifiants éventuellement inclus dans l'URL.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


class UrlNonSure(ValueError):
    """URL de service refusée (schéma inconnu, ou `http://` hors boucle locale)."""


def hote_local(hote: str | None) -> bool:
    if not hote:
        return False
    if hote.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(hote.strip("[]")).is_loopback
    except ValueError:
        return False


def verifier_url(url: str, usage: str) -> str:
    """Rend `url` si elle est sûre pour `usage` (« orchestrateur », « llm »…), sinon lève `UrlNonSure`."""
    try:
        parties = urlsplit((url or "").strip())
        hote = parties.hostname
    except ValueError:
        raise UrlNonSure(f"{usage} : URL illisible") from None
    schema = (parties.scheme or "").lower()
    if schema == "https" and hote:
        return url
    if schema == "http" and hote_local(hote):
        return url
    if schema == "http" and hote:
        raise UrlNonSure(
            f"{usage} : http:// vers un hôte distant ({hote}) refusé, l'authentification passerait "
            "en clair ; utiliser https:// ou la boucle locale"
        )
    raise UrlNonSure(f"{usage} : schéma « {schema or 'absent'} » refusé (https://, ou http:// en boucle locale)")
