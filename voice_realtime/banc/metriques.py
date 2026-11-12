"""Métriques du banc N3 : taux d'erreur de mots, langue de réponse, statistiques.

Tout est pur et sans dépendance : testable sur des chaînes et des listes.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable, Sequence

_PONCTUATION = re.compile(r"[^\w\s']", re.UNICODE)
_APOSTROPHES = re.compile(r"[’'`´]")


def normaliser(texte: str) -> list[str]:
    """Mots comparables : minuscules, sans ponctuation ni accents, élisions séparées.

    « L'état ? » et « l etat » donnent les mêmes mots : le taux d'erreur ne
    pénalise ni la ponctuation ni une graphie d'accent, seulement les mots.
    """
    texte = _APOSTROPHES.sub("' ", texte.lower())
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = _PONCTUATION.sub(" ", texte).replace("'", " ")
    return texte.split()


def distance_mots(reference: Sequence[str], hypothese: Sequence[str]) -> int:
    """Distance d'édition (substitutions, insertions, suppressions) entre deux suites de mots."""
    precedente = list(range(len(hypothese) + 1))
    for i, ref in enumerate(reference, start=1):
        courante = [i] + [0] * len(hypothese)
        for j, hyp in enumerate(hypothese, start=1):
            courante[j] = min(
                precedente[j] + 1,
                courante[j - 1] + 1,
                precedente[j - 1] + (0 if ref == hyp else 1),
            )
        precedente = courante
    return precedente[-1]


def taux_erreur_mots(reference: str, hypothese: str) -> float:
    """Taux d'erreur de mots (WER) ; 0.0 = parfait. Référence vide : 0 si l'hypothèse l'est aussi, sinon 1."""
    ref, hyp = normaliser(reference), normaliser(hypothese)
    if not ref:
        return 0.0 if not hyp else 1.0
    return distance_mots(ref, hyp) / len(ref)


# Mots-outils très fréquents : une réponse française en contient presque
# toujours, une réponse anglaise presque jamais (et inversement).
_MOTS_FR = frozenset(
    "le la les un une des de du et est sont je tu il elle nous vous ils elles on ce cet cette ces "
    "que qui quoi pas ne en au aux pour par sur dans avec mais ou donc car mes tes ses mon ton son "
    "votre vos notre nos leur leurs sa ta ma y a ai as avez avons ont suis es etes fait plus tres "
    "bien oui non voici voila aucune aucun session sessions".split()
)
_MOTS_EN = frozenset(
    "the a an and is are i you he she we they it this that these those what who not no to of in on "
    "for by with but or so my your his her our their be been was were have has had do does did will "
    "would can could here there yes".split()
)


def langue_probable(texte: str) -> str:
    """« fr », « en » ou « ? » selon la proportion de mots-outils (heuristique bornée)."""
    mots = normaliser(texte)
    if not mots:
        return "?"
    fr = sum(1 for m in mots if m in _MOTS_FR)
    en = sum(1 for m in mots if m in _MOTS_EN)
    if fr == en:
        return "?"
    return "fr" if fr > en else "en"


def centile(valeurs: Iterable[float], p: float) -> float | None:
    """Centile `p` (0-100) par interpolation linéaire ; None si aucune valeur."""
    tri = sorted(v for v in valeurs if v is not None and not math.isnan(v))
    if not tri:
        return None
    if len(tri) == 1:
        return tri[0]
    rang = (len(tri) - 1) * p / 100
    bas, haut = math.floor(rang), math.ceil(rang)
    return tri[bas] + (tri[haut] - tri[bas]) * (rang - bas)


def moyenne(valeurs: Iterable[float | None]) -> float | None:
    liste = [v for v in valeurs if v is not None]
    return sum(liste) / len(liste) if liste else None


def part(vrais: Iterable[bool | None]) -> float | None:
    """Proportion de vrais parmi les valeurs connues (None ignorés)."""
    liste = [bool(v) for v in vrais if v is not None]
    return sum(liste) / len(liste) if liste else None
