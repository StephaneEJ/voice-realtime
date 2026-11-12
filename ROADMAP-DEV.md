# ROADMAP-DEV

## Où j'en suis — 12/11 01:35
Résultat : N — voix duplex multi-fournisseurs, cliente de l'orchestrateur vocal, hors apps Claude et ChatGPT
Lot : 1/6 — reprise du dépôt selon le système de développement (livré la nuit du 12/11 ; suivant : 2/6 N1)
Terminé quand : depuis le téléphone, en marchant, Stéphane pilote ses sessions cmux à la voix par ce dépôt ; fournisseur par défaut et repli choisis sur preuves
Jalons : [x] reprise [ ] N1 client MCP [ ] N2 mode chaîne [ ] N4 page téléphone [ ] N3 banc d'essai [ ] N5 essais réels
Dernier acquis : commit 637132a — dernier état de `main` avant la reprise ; 232 tests verts sans réseau
Prochaine action : lot 2/6 N1 — client MCP des 5 outils de l'orchestrateur, jeton local par `headersHelper`, branche `nuit/B2`
Bloqué : rien ; N3 payant et N5 exigent Stéphane (budget, clés, essais en balade)

## Objectif final

**Résultat utilisateur :** en marchant, depuis le téléphone, Stéphane converse en duplex (coupure de parole, mot d'arrêt) avec une interface vocale qui appelle les outils de l'orchestrateur vocal du Cockpit Jarvis. Il pilote ainsi ses sessions Claude Code, OpenCode et Codex dans cmux sans écran obligatoire. Le garde-fou, la liste blanche et la confirmation en deux temps restent côté serveur. Les fournisseurs sont comparés sur un banc d'essai ; un fournisseur par défaut et un repli sont choisis sur preuves.

**Source :** résultat N de `../JARVIS COCKPIT/ROADMAP-DEV.md` (ajouté le 12/11/2026). Ce dépôt en porte l'exécution ; le Cockpit en garde la définition et les contrats de nuit.

## Acquis avant la reprise (mai à septembre 2026)

| Bloc | État | Preuve |
|---|---|---|
| Phase 1 — MVP duplex Gemini Live et OpenAI Realtime, audio, contexte, coût, sauvegarde vault | livré | README, `docs/DESIGN.md` |
| Phase 2 — `--cli-context`, récapitulatif glissant, `summarize`, alerte budget, NocoDB, coupure de parole | livré à 95 % ; tests vocaux de la matrice non joués | `docs/TEST_BATTERY_2026-05-24.md` |
| Phase 3 — appels d'outils (`vault_write`, `web_search`), confirmation avant action, personas, interface Tauri, annulation d'écho | livré en partie | commits `0660f63` à `90f2133`, `docs/ROADMAP_V3_MULTI_SESSION.md` |
| Fournisseur local (`providers/local.py`) | ébauche sans dépendances installées | `tests/test_local_provider_stub.py` |
| Maintenance PRISME | livré | commit `637132a` |

Les documents `docs/PHASE_3_ROADMAP.md` et `docs/ROADMAP_V3_MULTI_SESSION.md` sont des archives : cette roadmap les remplace pour toute exécution.

## Résultats

| Résultat | Statut | Terminé quand | Preuves |
|---|---|---|---|
| N — voix duplex cliente de l'orchestrateur | en_cours | Les lots 1 à 6 ci-dessous sont faits et l'usage réel en balade est accepté par Stéphane | Tests N1 et N2 sans réseau ; essai local N4 ; rapport du banc N3 dans le budget validé ; usage N5 |

## Lots du résultat N

| Lot | Étape de nuit | Contenu | Statut |
|---|---|---|---|
| 1/6 | B1 | Reprise du dépôt selon le système de développement : `AGENTS.md`, `CLAUDE.md`, cette roadmap, journal, test de format | livré (12/11) |
| 2/6 | B2 | N1 — client MCP des 5 outils de l'orchestrateur (`list_sessions`, `get_state_summary`, `get_last_response`, `send_instruction`, `get_instruction_status`), jeton local par `headersHelper`, garde-fou côté serveur, exposés au modèle comme `ToolSpec` | à_faire |
| 3/6 | B3 | N2 — mode chaîne (reconnaissance vocale, modèle API au choix, synthèse vocale) derrière le protocole `providers`, testé sur enregistrements, sans réseau | à_faire |
| 4/6 | B4 | N4 — page téléphone WebRTC : code et essai local ; exposition derrière Cloudflare Access selon l'autorisation 1 du 12/11 | à_faire |
| 5/6 | B5 | N3 — banc d'essai : harnais, métriques (latence de première réponse, français, coupure, appels d'outils, coût à l'heure) et rapport à blanc, sans appel payant ; passage réel sur budget validé | à_faire |
| 6/6 | — | N5 — essais réels en balade, choix du fournisseur par défaut et du repli | à_faire, exige Stéphane |

## Lot courant

**Résultat :** N, lots 1 à 5 en nuit autonome du 12/11/2026 (conducteur B, espace cmux « NUIT VOICE », worktree `../voice-realtime.nuit`).
**Statut :** en_cours
**Mode d'exécution :** autonome sur contrat
**Contrat :** section « Lot courant » de `../JARVIS COCKPIT/ROADMAP-DEV.md` (inclus, exclus, interdits, destination, contrôles). Il n'est pas recopié ici.

**Critère par étape :** `scripts/nuit/verifier_etape.py <étape>` du clone d'exécution du Cockpit, lancé à la racine de ce dépôt : preuve `docs/preuves/nuit-2026-11-12/<étape>.md` commençant par `Statut : livré`, `uv run --frozen pytest -q` vert, arbre propre, commit contenu dans `origin/main`.

**Destination :** une branche `nuit/<étape>` par étape, PR et fusion dans `main` avec l'autorisation Git permanente.

## Décisions

- 2026-11-12 — Le dépôt adopte le système de développement : `ROADMAP-DEV.md` unique, bloc « Où j'en suis », journal en ajout seul ; les roadmaps de mai deviennent des archives.
- 2026-11-12 — Les outils de l'orchestrateur sont consommés comme client MCP ; aucune copie du garde-fou ni de la liste blanche.

## Risques ouverts

- Les tests vocaux de la phase 2 (matrice 9 dimensions) n'ont jamais été joués : la qualité réelle en français n'est pas mesurée.
- `pyaec` et `sounddevice` exigent des bibliothèques natives : un poste neuf peut échouer à l'installation.
- Le banc N3 dépend d'appels payants : sans budget validé, il reste à blanc.
