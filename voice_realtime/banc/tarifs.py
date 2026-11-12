"""Grille de prix du banc N3 et estimation du coût à l'heure.

Grille JSON (par défaut `config/banc/tarifs.json`) :

    {
      "etages": {
        "stt": {"simule": {"usd_par_minute": 0.006, "fictif": true}, "whisper-cpp": {"usd_par_minute": 0}},
        "llm": {"openai:gpt-x": {"usd_par_million_entree": null, "usd_par_million_sortie": null}},
        "tts": {"say": {"usd_par_million_caracteres": 0}}
      }
    }

Recherche d'un étage : clé exacte « genre:modèle », puis « genre ». Un prix
`null` ou absent vaut « inconnu » : le coût n'est alors pas inventé, et un
passage payant est refusé (impossible de tenir un budget sans prix).

Les fournisseurs temps réel (Gemini Live, OpenAI Realtime) reprennent les
tarifs horaires de `cost_tracker.py`, déjà utilisés par la CLI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..cost_tracker import DEFAULT_HOURLY_RATE_USD_BY_MODEL
from ..providers.chain_stages import parse_spec


@dataclass
class Usage:
    """Consommation mesurée pendant un scénario."""

    duree_s: float = 0.0  # durée de conversation (enregistrement rejoué)
    audio_entree_s: float = 0.0  # audio envoyé à la reconnaissance
    audio_sortie_s: float = 0.0  # audio produit
    jetons_entree: int = 0
    jetons_sortie: int = 0
    caracteres_synthese: int = 0

    def ajouter(self, autre: "Usage") -> None:
        self.duree_s += autre.duree_s
        self.audio_entree_s += autre.audio_entree_s
        self.audio_sortie_s += autre.audio_sortie_s
        self.jetons_entree += autre.jetons_entree
        self.jetons_sortie += autre.jetons_sortie
        self.caracteres_synthese += autre.caracteres_synthese


@dataclass
class Chiffrage:
    cout_usd: float | None
    cout_horaire_usd: float | None
    fictif: bool = False
    inconnus: list[str] = field(default_factory=list)
    detail: dict[str, float | None] = field(default_factory=dict)


def _cle(spec: str) -> tuple[str, str]:
    s = parse_spec(spec)
    exacte = f"{s.kind}:{s.args[0]}" if s.args and s.args[0] and s.kind != "script" else s.kind
    return exacte, s.kind


@dataclass
class GrilleTarifs:
    etages: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    source: Path | None = None

    @classmethod
    def charger(cls, chemin: Path) -> "GrilleTarifs":
        brut = json.loads(Path(chemin).read_text(encoding="utf-8"))
        return cls(etages=brut.get("etages", {}), source=Path(chemin))

    def entree(self, etage: str, spec: str) -> dict[str, Any] | None:
        table = self.etages.get(etage, {})
        exacte, genre = _cle(spec)
        return table.get(exacte) or table.get(genre)

    def chiffrer_chaine(self, stt: str, llm: str, tts: str, usage: Usage) -> Chiffrage:
        inconnus: list[str] = []
        detail: dict[str, float | None] = {}
        fictif = False

        def prix(etage: str, spec: str, champ: str) -> float | None:
            nonlocal fictif
            e = self.entree(etage, spec)
            valeur = None if e is None else e.get(champ)
            if valeur is None:
                inconnus.append(f"{etage} {spec} ({champ})")
                return None
            fictif = fictif or bool(e.get("fictif"))
            return float(valeur)

        p_stt = prix("stt", stt, "usd_par_minute")
        p_in = prix("llm", llm, "usd_par_million_entree")
        p_out = prix("llm", llm, "usd_par_million_sortie")
        p_tts = prix("tts", tts, "usd_par_million_caracteres")
        detail["stt"] = None if p_stt is None else p_stt * usage.audio_entree_s / 60
        detail["llm"] = (
            None if p_in is None or p_out is None
            else (p_in * usage.jetons_entree + p_out * usage.jetons_sortie) / 1e6
        )
        detail["tts"] = None if p_tts is None else p_tts * usage.caracteres_synthese / 1e6
        return _total(detail, usage, fictif, inconnus)

    def chiffrer_temps_reel(self, modele: str, usage: Usage) -> Chiffrage:
        horaire = DEFAULT_HOURLY_RATE_USD_BY_MODEL.get(modele)
        if horaire is None:
            return Chiffrage(None, None, inconnus=[f"temps réel {modele} (usd_par_heure)"])
        cout = horaire * usage.duree_s / 3600
        return Chiffrage(cout, horaire, detail={"temps_reel": cout})


def _total(detail: dict[str, float | None], usage: Usage, fictif: bool, inconnus: list[str]) -> Chiffrage:
    if any(v is None for v in detail.values()):
        return Chiffrage(None, None, fictif=fictif, inconnus=inconnus, detail=detail)
    cout = sum(v for v in detail.values() if v is not None)
    horaire = cout / usage.duree_s * 3600 if usage.duree_s > 0 else None
    return Chiffrage(cout, horaire, fictif=fictif, detail=detail)


def estimer_avant_passage(grille: GrilleTarifs, candidat: Any, duree_totale_s: float) -> Chiffrage:
    """Majorant du coût d'un passage, avant de le jouer (pour tenir un budget).

    Hypothèses prudentes par seconde de conversation : toute la durée part en
    reconnaissance ; 60 jetons d'entrée cumulés (historique renvoyé à chaque
    tour) et 8 jetons de sortie ; 15 caractères synthétisés.
    """
    usage = Usage(
        duree_s=duree_totale_s,
        audio_entree_s=duree_totale_s,
        audio_sortie_s=duree_totale_s,
        jetons_entree=int(60 * duree_totale_s),
        jetons_sortie=int(8 * duree_totale_s),
        caracteres_synthese=int(15 * duree_totale_s),
    )
    if candidat.genre == "temps_reel":
        return grille.chiffrer_temps_reel(candidat.modele, usage)
    return grille.chiffrer_chaine(candidat.stt, candidat.llm, candidat.tts, usage)
