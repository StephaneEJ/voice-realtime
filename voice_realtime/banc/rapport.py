"""Rapport du banc N3 : JSON complet et Markdown lisible.

Un rapport à blanc le dit en tête, en toutes lettres : ses valeurs viennent
d'étages simulés ou locaux et ne départagent aucun fournisseur.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .harnais import RapportBanc, ResultatCandidat, synthese


def _ms(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f} %"


def _usd(v: float | None, fictif: bool = False) -> str:
    if v is None:
        return "inconnu"
    return f"{v:.3f} $" + (" (fictif)" if fictif else "")


def vers_dict(rapport: RapportBanc) -> dict[str, Any]:
    def candidat(rc: ResultatCandidat) -> dict[str, Any]:
        return {
            "candidat": asdict(rc.candidat),
            "joue": rc.joue,
            "gratuit": rc.gratuit,
            "motif": rc.motif,
            "duree_reelle_s": round(rc.duree_reelle_s, 3),
            "synthese": synthese(rc) if rc.joue else None,
            "chiffrage": asdict(rc.chiffrage) if rc.chiffrage else None,
            "estimation_avant_passage": asdict(rc.estimation) if rc.estimation else None,
            "scenarios": [
                {**asdict(s), "part_francais": s.part_francais} for s in rc.scenarios
            ],
        }

    return {
        "banc": "N3",
        "a_blanc": rapport.a_blanc,
        "debut": rapport.debut,
        "budget_usd": rapport.budget_usd,
        "majorant_payant_usd": rapport.majorant_payant_usd,
        "connexions_bloquees": rapport.connexions_bloquees,
        "scenarios": [
            {"id": s.id, "enregistrement": s.enregistrement.name, "langue": s.langue,
             "outils_attendus": list(s.outils_attendus), "coupure_ms": s.coupure_ms,
             "mot_arret": s.mot_arret, "duree_ms": s.duree_ms, "description": s.description}
            for s in rapport.scenarios
        ],
        "candidats": [candidat(rc) for rc in rapport.candidats],
    }


def vers_markdown(rapport: RapportBanc) -> str:
    l: list[str] = []
    titre = "Banc d'essai N3 — rapport à blanc" if rapport.a_blanc else "Banc d'essai N3 — passage réel"
    l += [f"# {titre}", "", f"Début : {rapport.debut}", ""]
    if rapport.a_blanc:
        l += [
            "> **À blanc.** Aucun appel payant, réseau coupé hors boucle locale pendant le jeu. "
            "Les valeurs viennent d'étages simulés ou locaux : elles éprouvent le harnais et "
            "**ne départagent aucun fournisseur**. Les prix marqués « fictif » sont inventés pour "
            "exercer le calcul. Les candidats payants sont seulement chiffrés.",
            "",
        ]
    else:
        l += [f"Budget validé : {_usd(rapport.budget_usd)} ; majorant estimé avant passage : {_usd(rapport.majorant_payant_usd)}.", ""]
    bloquees = sorted(set(rapport.connexions_bloquees))
    l += [f"Connexions bloquées par le garde-fou : {len(rapport.connexions_bloquees)}"
          + (f" ({', '.join(bloquees)})" if bloquees else ""), ""]

    l += ["## Synthèse par candidat", "",
          "| Candidat | Joué | 1re réponse p50 / p90 (ms) | Erreur de mots | Réponses en français | Coupures vues (délai ms) | Outils corrects | Mot d'arrêt | Coût à l'heure |",
          "|---|---|---|---|---|---|---|---|---|"]
    for rc in rapport.candidats:
        c = rc.candidat
        if not rc.joue:
            est = rc.estimation
            cout = f"majorant {_usd(est.cout_horaire_usd, est.fictif)}/h" if est and est.cout_horaire_usd is not None else "inconnu"
            l.append(f"| `{c.id}` | non : {rc.motif} | — | — | — | — | — | — | {cout} |")
            continue
        s = synthese(rc)
        ch = rc.chiffrage
        cout = _usd(ch.cout_horaire_usd, ch.fictif) + "/h" if ch and ch.cout_horaire_usd is not None else "inconnu"
        l.append(
            f"| `{c.id}` | oui ({s['scenarios_joues']}/{len(rc.scenarios)}) "
            f"| {_ms(s['premiere_reponse_p50_ms'])} / {_ms(s['premiere_reponse_p90_ms'])} "
            f"| {_pct(s['taux_erreur_mots_moyen'])} | {_pct(s['part_reponses_fr'])} "
            f"| {_pct(s['coupures_detectees'])} ({_ms(s['delai_coupure_moyen_ms'])}) "
            f"| {_pct(s['outils_corrects'])} | {_pct(s['mot_arret_reconnu'])} | {cout} |"
        )
    l.append("")

    l += ["## Détail des latences (moyennes, ms)", "",
          "| Candidat | Attente fin de parole | Transcription | Premier jeton (depuis le début du tour) |",
          "|---|---|---|---|"]
    for rc in rapport.candidats:
        if rc.joue:
            s = synthese(rc)
            l.append(f"| `{rc.candidat.id}` | {_ms(s['attente_vad_moyenne_ms'])} | {_ms(s['stt_moyen_ms'])} | {_ms(s['premier_jeton_moyen_ms'])} |")
    l.append("")

    l += ["## Par scénario", ""]
    for rc in rapport.candidats:
        if not rc.joue:
            continue
        l += [f"### `{rc.candidat.id}` — {rc.candidat.libelle}", "",
              "| Scénario | Transcription | Erreur de mots | 1re réponse (ms) | Coupure | Outils appelés | Mot d'arrêt | Erreurs |",
              "|---|---|---|---|---|---|---|---|"]
        for sc in rc.scenarios:
            if not sc.joue:
                l.append(f"| {sc.scenario_id} | non joué : {sc.motif} | | | | | | |")
                continue
            coupure = "—" if not sc.coupure_attendue else ("vue" if sc.coupure_detectee else "manquée") + (
                f" ({_ms(sc.delai_coupure_ms)})" if sc.delai_coupure_ms is not None else "")
            arret = "—" if not sc.mot_arret_attendu else ("reconnu" if sc.mot_arret_reconnu else "manqué")
            transcription = sc.transcription.replace("|", "/")[:80] or "(vide)"
            l.append(
                f"| {sc.scenario_id} | {transcription} | {_pct(sc.taux_erreur_mots)} "
                f"| {', '.join(_ms(v) for v in sc.premieres_reponses_ms) or '—'} | {coupure} "
                f"| {', '.join(sc.outils_appeles) or '—'} | {arret} | {len(sc.erreurs)} |"
            )
        l.append("")

    l += ["## Méthode", "",
          "- **Première réponse** : de la fin réelle de l'énoncé (manifeste) au premier bloc audio produit. "
          "Mode chaîne : attente de la détection de fin de parole (temps de l'enregistrement) plus le temps réel "
          "écoulé entre le début de la transcription et le premier audio. Temps réel : premier audio daté après la fin de l'énoncé.",
          "- **Français** : taux d'erreur de mots de la transcription (minuscules, sans ponctuation ni accents) et "
          "langue de chaque réponse estimée par les mots-outils.",
          "- **Coupure** : un événement `model_interrupted` après la reprise de parole attendue, et son délai.",
          "- **Outils** : les outils attendus sont appelés ; ils sont servis par un orchestrateur factice, jamais une session réelle.",
          "- **Coût à l'heure** : coût mesuré (secondes transcrites, jetons, caractères synthétisés, ou tarif horaire temps réel) "
          "ramené à la durée de conversation rejouée. Les scénarios sont denses : c'est un majorant d'une conversation réelle.",
          ""]
    return "\n".join(l)


def ecrire(rapport: RapportBanc, dossier: Path) -> tuple[Path, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    js = dossier / "rapport.json"
    md = dossier / "rapport.md"
    js.write_text(json.dumps(vers_dict(rapport), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md.write_text(vers_markdown(rapport), encoding="utf-8")
    return md, js
