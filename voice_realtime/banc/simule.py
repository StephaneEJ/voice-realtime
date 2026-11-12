"""Étages simulés du banc à blanc : `simule:<profil>` pour la reconnaissance, le modèle et la synthèse.

Ils ne prédisent **aucun** fournisseur réel. Ils servent à éprouver le harnais
et le rapport de bout en bout, sans réseau ni coût : latences réglées par
profil, erreurs de transcription déterministes, réponses en anglais injectées,
appels d'outils de l'orchestrateur déclenchés par mots-clés.

Profils : `rapide`, `lent`, `degrade` (voir `PROFILS`).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..providers.base import ToolSpec
from ..providers.chain import ModelChunk, ToolCall


@dataclass(frozen=True)
class Profil:
    stt_ms: float
    premier_jeton_ms: float
    jeton_ms: float  # entre deux mots
    tts_premier_bloc_ms: float
    mots_omis_tous_les: int = 0  # 0 = transcription exacte
    reponse_anglaise_tous_les: int = 0  # 0 = toujours en français


PROFILS: dict[str, Profil] = {
    "rapide": Profil(stt_ms=150, premier_jeton_ms=250, jeton_ms=12, tts_premier_bloc_ms=120),
    "lent": Profil(stt_ms=600, premier_jeton_ms=900, jeton_ms=40, tts_premier_bloc_ms=450),
    "degrade": Profil(
        stt_ms=300, premier_jeton_ms=500, jeton_ms=25, tts_premier_bloc_ms=250,
        mots_omis_tous_les=4, reponse_anglaise_tous_les=2,
    ),
}


class ProfilInconnu(ValueError):
    pass


def profil(nom: str) -> Profil:
    try:
        return PROFILS[nom or "rapide"]
    except KeyError:
        raise ProfilInconnu(f"profil simulé inconnu : {nom!r} ({' | '.join(PROFILS)})") from None


async def _pause(ms: float, facteur: float) -> None:
    if ms > 0 and facteur > 0:
        await asyncio.sleep(ms * facteur / 1000)


@dataclass
class SttSimule:
    """Rend les énoncés de référence dans l'ordre, éventuellement abîmés ; vide au-delà."""

    profil: Profil
    references: list[str] = field(default_factory=list)
    facteur: float = 1.0
    nom_profil: str = "rapide"

    @property
    def name(self) -> str:
        return f"simule:{self.nom_profil}"

    async def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        await _pause(self.profil.stt_ms, self.facteur)
        if not self.references:
            return ""
        texte = self.references.pop(0)
        n = self.profil.mots_omis_tous_les
        if n:
            mots = texte.split()
            texte = " ".join(m for i, m in enumerate(mots, start=1) if i % n)
        return texte


_REPONSE_OUTIL = "Voici le résultat. Trois sessions sont ouvertes, dont la session cockpit, qui attend ta réponse."
_REPONSE_DEFAUT = "D'accord, je t'écoute. Dis-moi ce que je dois faire pour tes sessions."
_REPONSE_ARRET = "Très bien, je raccroche. À bientôt."
_REPONSE_ANGLAISE = "Sure, here is what I found for you."


@dataclass
class ModeleSimule:
    """Modèle à règles : outils de l'orchestrateur sur mots-clés, réponses en flux mot à mot."""

    profil: Profil
    facteur: float = 1.0
    nom_profil: str = "rapide"
    tours: int = 0

    @property
    def name(self) -> str:
        return f"simule:{self.nom_profil}"

    def _decider(self, messages: list[dict[str, Any]], outils: list[ToolSpec]) -> tuple[str, ToolCall | None]:
        noms = {t.name for t in outils}
        dernier = messages[-1] if messages else {}
        if dernier.get("role") == "tool":
            return _REPONSE_OUTIL, None
        texte = str(dernier.get("content") or "").lower()
        if "killchat" in texte.replace(" ", ""):
            return _REPONSE_ARRET, None
        if "session" in texte and ("liste" in texte or "en cours" in texte) and "list_sessions" in noms:
            return "", ToolCall(id=f"simule-{self.tours}", name="list_sessions", args={})
        if "dernier retour" in texte and "get_last_response" in noms:
            return "", ToolCall(id=f"simule-{self.tours}", name="get_last_response", args={"session": "cockpit"})
        n = self.profil.reponse_anglaise_tous_les
        if n and self.tours % n == 1:
            return _REPONSE_ANGLAISE, None
        return _REPONSE_DEFAUT, None

    async def stream(
        self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelChunk]:
        self.tours += 1
        await _pause(self.profil.premier_jeton_ms, self.facteur)
        texte, appel = self._decider(messages, tools)
        entree = len(system) + sum(len(str(m.get("content") or "")) for m in messages)
        if appel is not None:
            yield ModelChunk(tool_call=appel)
        mots = texte.split(" ") if texte else []
        for i, mot in enumerate(mots):
            if i:
                await _pause(self.profil.jeton_ms, self.facteur)
            yield ModelChunk(text=mot if i == 0 else " " + mot)
        # Usage estimé à 4 caractères par jeton, comme ordre de grandeur.
        yield ModelChunk(tokens_in=max(1, entree // 4), tokens_out=max(1, math.ceil((len(texte) or 8) / 4)))


@dataclass
class TtsSimule:
    """PCM16 24 kHz : 65 ms d'audio par caractère, en blocs de 100 ms, premier bloc après latence."""

    profil: Profil
    facteur: float = 1.0
    nom_profil: str = "rapide"
    sample_rate: int = 24000
    ms_par_caractere: float = 65.0
    caracteres: int = 0

    @property
    def name(self) -> str:
        return f"simule:{self.nom_profil}"

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.caracteres += len(text)
        await _pause(self.profil.tts_premier_bloc_ms, self.facteur)
        total = int(self.sample_rate * len(text) * self.ms_par_caractere / 1000)
        bloc = self.sample_rate // 10
        envoye = 0
        while envoye < total:
            n = min(bloc, total - envoye)
            yield b"\x10\x00" * n
            envoye += n
