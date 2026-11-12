"""Scénarios du banc N3 : un enregistrement, ses énoncés de référence et les attentes.

Fichier JSON (par défaut `config/banc/scenarios.json`) :

    {
      "manifeste": "tests/fixtures/chain/enregistrements.json",
      "scenarios": [
        {
          "id": "outils-et-coupure",
          "enregistrement": "tests/fixtures/chain/deux_phrases.wav",
          "langue": "fr",
          "outils_attendus": ["list_sessions"],
          "coupure_ms": 3430,
          "mot_arret": false,
          "description": "…"
        }
      ]
    }

Les énoncés de référence (texte, début, fin) viennent du manifeste des
enregistrements, pour ne pas les recopier. Les chemins sont relatifs au
fichier de scénarios, puis à la racine du dépôt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ScenarioErreur(ValueError):
    """Fichier de scénarios invalide ou enregistrement introuvable."""


@dataclass(frozen=True)
class Enonce:
    texte: str
    debut_ms: int | None = None
    fin_ms: int | None = None


@dataclass(frozen=True)
class Scenario:
    id: str
    enregistrement: Path
    enonces: tuple[Enonce, ...]
    langue: str = "fr"
    outils_attendus: tuple[str, ...] = ()
    # Instant (ms, temps de l'enregistrement) où l'utilisateur reprend la
    # parole pendant la réponse : une coupure est attendue peu après.
    coupure_ms: int | None = None
    mot_arret: bool = False
    description: str = ""
    duree_ms: int | None = None

    @property
    def reference(self) -> str:
        return " ".join(e.texte for e in self.enonces)


@dataclass
class JeuScenarios:
    scenarios: list[Scenario] = field(default_factory=list)
    source: Path | None = None

    def __iter__(self):
        return iter(self.scenarios)

    def __len__(self) -> int:
        return len(self.scenarios)


def _resoudre(chemin: str, base: Path, racine: Path) -> Path:
    p = Path(chemin).expanduser()
    if p.is_absolute():
        return p
    for candidat in (base / p, racine / p):
        if candidat.exists():
            return candidat
    return racine / p


def racine_depot() -> Path:
    return Path(__file__).resolve().parents[2]


def charger_scenarios(chemin: Path, *, racine: Path | None = None) -> JeuScenarios:
    racine = racine or racine_depot()
    try:
        brut: dict[str, Any] = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioErreur(f"scénarios illisibles : {chemin} ({exc.__class__.__name__})") from exc
    base = Path(chemin).resolve().parent
    manifeste: dict[str, Any] = {}
    if brut.get("manifeste"):
        mpath = _resoudre(brut["manifeste"], base, racine)
        try:
            manifeste = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScenarioErreur(f"manifeste illisible : {mpath}") from exc

    vus: set[str] = set()
    jeu = JeuScenarios(source=Path(chemin))
    for item in brut.get("scenarios", []):
        sid = str(item.get("id") or "").strip()
        if not sid or sid in vus:
            raise ScenarioErreur(f"identifiant de scénario absent ou en double : {sid!r}")
        vus.add(sid)
        wav = _resoudre(str(item.get("enregistrement") or ""), base, racine)
        if not wav.is_file():
            raise ScenarioErreur(f"{sid} : enregistrement introuvable ({wav.name})")
        info = manifeste.get(wav.name, {})
        segments = item.get("enonces") or info.get("segments") or []
        if not segments:
            raise ScenarioErreur(f"{sid} : aucun énoncé de référence (manifeste ou « enonces »)")
        enonces = tuple(
            Enonce(texte=str(s["texte"]), debut_ms=s.get("debut_ms"), fin_ms=s.get("fin_ms")) for s in segments
        )
        coupure = item.get("coupure_ms")
        jeu.scenarios.append(
            Scenario(
                id=sid,
                enregistrement=wav,
                enonces=enonces,
                langue=str(item.get("langue", "fr")),
                outils_attendus=tuple(item.get("outils_attendus") or ()),
                coupure_ms=int(coupure) if coupure is not None else None,
                mot_arret=bool(item.get("mot_arret", False)),
                description=str(item.get("description", "")),
                duree_ms=info.get("duree_ms"),
            )
        )
    if not jeu.scenarios:
        raise ScenarioErreur(f"aucun scénario dans {chemin}")
    return jeu
