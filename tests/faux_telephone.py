"""Faux partagés par les tests de la page téléphone (N4) : fournisseur,
transport, registre d'outils et jetons Access signés par une clé locale."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any, AsyncIterator

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from voice_realtime.providers.base import ProviderConfig, RealtimeEvent
from voice_realtime.telephone.pont import Appel
from voice_realtime.tools.registry import ToolRegistry, ToolResult, ToolSafetyLevel, ToolSpec


class FauxFournisseur:
    """Fournisseur scripté : enregistre ce qu'il reçoit, émet ce qu'on lui pousse."""

    def __init__(self, echec_connexion: bool = False) -> None:
        self.echec_connexion = echec_connexion
        self.audio: list[bytes] = []
        self.textes: list[str] = []
        self.reponses_outils: list[tuple[str, str, dict[str, Any]]] = []
        self.outils: list[Any] | None = None
        self.consigne = ""
        self.config: ProviderConfig | None = None
        self.ferme = False
        self.file: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue()
        self.reponse_outil_recue = asyncio.Event()

    async def connect(self, config: ProviderConfig, system_prompt: str, audio: bool = True, tools=None) -> None:
        if self.echec_connexion:
            raise ConnectionError("refus")
        self.config = config
        self.consigne = system_prompt
        self.outils = tools

    async def send_audio_chunk(self, pcm16: bytes) -> None:
        self.audio.append(pcm16)

    async def send_text(self, text: str) -> None:
        self.textes.append(text)

    async def send_silent_note(self, text: str) -> None:
        pass

    async def send_function_response(self, call_id: str, name: str, response: dict[str, Any]) -> None:
        self.reponses_outils.append((call_id, name, response))
        self.reponse_outil_recue.set()

    async def receive_events(self) -> AsyncIterator[RealtimeEvent]:
        while True:
            ev = await self.file.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        self.ferme = True
        await self.file.put(None)

    async def pousser(self, kind: str, **data: Any) -> None:
        await self.file.put(RealtimeEvent(kind=kind, data=data))  # type: ignore[arg-type]


class FauxTransport:
    def __init__(self) -> None:
        self.json: list[dict[str, Any]] = []
        self.audio: list[bytes] = []
        self.nouveau = asyncio.Event()

    async def envoyer_json(self, message: dict[str, Any]) -> None:
        self.json.append(message)
        self.nouveau.set()

    async def envoyer_audio(self, pcm16: bytes) -> None:
        self.audio.append(pcm16)
        self.nouveau.set()

    def evenements(self, ev: str) -> list[dict[str, Any]]:
        return [m for m in self.json if m.get("ev") == ev]

    async def attendre(self, predicat, delai: float = 2.0) -> None:
        async def boucle() -> None:
            while not predicat():
                self.nouveau.clear()
                await self.nouveau.wait()

        await asyncio.wait_for(boucle(), delai)


def registre_essai(appels: list[dict[str, Any]] | None = None) -> ToolRegistry:
    """Deux outils : une lecture qui rend une liste, une écriture qui demande confirmation."""
    journal = appels if appels is not None else []

    def lister(**args: Any) -> ToolResult:
        journal.append({"nom": "lister", **args})
        return ToolResult(ok=True, data={"sessions": ["PILOTE JARVIS"]})

    def ecrire(texte: str) -> ToolResult:
        journal.append({"nom": "ecrire", "texte": texte})
        return ToolResult(ok=True, data={"ok": True})

    def casser() -> ToolResult:
        raise RuntimeError("panne")

    r = ToolRegistry()
    r.register(ToolSpec("lister", "Liste les sessions", ToolSafetyLevel.READ_ONLY,
                        {"type": "object", "properties": {}, "required": []}, lister))
    r.register(ToolSpec("ecrire", "Envoie une consigne", ToolSafetyLevel.WRITE_USER_SCOPE,
                        {"type": "object", "properties": {"texte": {"type": "string"}}, "required": ["texte"]}, ecrire))
    r.register(ToolSpec("casser", "Échoue", ToolSafetyLevel.READ_ONLY,
                        {"type": "object", "properties": {}, "required": []}, casser))
    return r


def appel_essai(fournisseur: Any, **kwargs: Any) -> Appel:
    valeurs: dict[str, Any] = dict(
        fournisseur=fournisseur,
        config=ProviderConfig(model="faux", api_key="", input_sample_rate=16000),
        nom_fournisseur="chain",
        libelle="faux fournisseur",
        consigne_systeme="Consigne d'essai.",
        entree=16000,
        sortie=24000,
        registre=None,
        salutation=False,
    )
    valeurs.update(kwargs)
    return Appel(**valeurs)


# -- Cloudflare Access -------------------------------------------------------

EQUIPE = "essai.cloudflareaccess.com"
EMETTEUR = f"https://{EQUIPE}"
AUD = "aud-essai-0123456789"
ADRESSE = "stephane@example.org"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class CleAccess:
    def __init__(self, kid: str = "cle-1") -> None:
        self.kid = kid
        self.privee = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwk(self) -> dict[str, Any]:
        nums = self.privee.public_key().public_numbers()
        taille = (nums.n.bit_length() + 7) // 8
        return {
            "kid": self.kid, "kty": "RSA", "alg": "RS256", "use": "sig",
            "e": _b64(nums.e.to_bytes(3, "big")), "n": _b64(nums.n.to_bytes(taille, "big")),
        }

    def jeton(self, *, entete: dict[str, Any] | None = None, **charge: Any) -> str:
        maintenant = int(time.time())
        corps = {
            "aud": [AUD], "email": ADRESSE, "exp": maintenant + 600, "iat": maintenant,
            "nbf": maintenant, "iss": EMETTEUR, "type": "app", "sub": "id",
        }
        corps.update(charge)
        tete = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        tete.update(entete or {})
        signe = f"{_b64(json.dumps(tete).encode())}.{_b64(json.dumps(corps).encode())}"
        signature = self.privee.sign(signe.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{signe}.{_b64(signature)}"
