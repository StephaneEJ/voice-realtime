"""Garde le format du bloc « Où j'en suis » de ROADMAP-DEV.md (système de développement).

Version autonome, sans réseau ni dépendance au dépôt Cockpit, de l'essentiel de
`JARVIS COCKPIT/scripts/verifier_format_roadmap.py`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CHAMPS = ["Résultat", "Lot", "Terminé quand", "Jalons", "Dernier acquis", "Prochaine action", "Bloqué"]
TITRE = re.compile(r"^## Où j(?:'|’)en suis — (\d{2})/(\d{2}) (\d{2}):(\d{2})\s*$")


def _bloc() -> tuple[str, list[str]]:
    lignes = (RACINE / "ROADMAP-DEV.md").read_text(encoding="utf-8").splitlines()
    titres = [i for i, ligne in enumerate(lignes) if ligne.startswith("## ")]
    assert titres, "aucune section dans ROADMAP-DEV.md"
    debut = titres[0]
    fin = titres[1] if len(titres) > 1 else len(lignes)
    return lignes[debut], [ligne for ligne in lignes[debut + 1:fin] if ligne.strip()]


def test_bloc_en_tete_et_titre_date():
    titre, _ = _bloc()
    trouve = TITRE.match(titre)
    assert trouve, f"titre attendu « ## Où j'en suis — JJ/MM HH:MM », obtenu {titre!r}"
    jour, mois, heure, minute = (int(x) for x in trouve.groups())
    assert 1 <= jour <= 31 and 1 <= mois <= 12 and heure <= 23 and minute <= 59


def test_sept_champs_dans_l_ordre_et_huit_lignes_au_plus():
    _, contenu = _bloc()
    assert len(contenu) <= 8
    cles = [ligne.partition(" : ")[0].strip() for ligne in contenu if " : " in ligne]
    assert [c for c in cles if c in CHAMPS] == CHAMPS
    valeurs = {ligne.partition(" : ")[0].strip(): ligne.partition(" : ")[2].strip() for ligne in contenu}
    assert all(valeurs[c] not in ("", "…", "...") for c in CHAMPS)
    assert re.match(r"^\d+/\d+ — \S", valeurs["Lot"])
    assert re.search(r"\[(x| )\]", valeurs["Jalons"])


def test_dernier_acquis_cite_un_commit_existant():
    _, contenu = _bloc()
    acquis = next(ligne for ligne in contenu if ligne.startswith("Dernier acquis : "))
    trouve = re.search(r"\bcommit `?([0-9a-f]{7,40})\b", acquis)
    assert trouve, "« Dernier acquis » doit citer « commit <empreinte> »"
    resultat = subprocess.run(
        ["git", "-C", str(RACINE), "cat-file", "-e", f"{trouve.group(1)}^{{commit}}"],
        capture_output=True, timeout=10, check=False,
    )
    assert resultat.returncode == 0, f"commit {trouve.group(1)} introuvable"


def test_journal_et_instructions_presents():
    for nom in ("ROADMAP-JOURNAL.md", "AGENTS.md", "CLAUDE.md"):
        assert (RACINE / nom).is_file(), f"{nom} absent"
