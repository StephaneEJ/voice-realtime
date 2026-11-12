# ROADMAP-DEV

## Où j'en suis — 12/11 02:55
Résultat : N — voix duplex multi-fournisseurs, cliente de l'orchestrateur vocal, hors apps Claude et ChatGPT
Lot : 5/6 — N3 banc d'essai (livré à blanc la nuit du 12/11 ; suivant : passage réel sur budget, puis 6/6 N5)
Terminé quand : depuis le téléphone, en marchant, Stéphane pilote ses sessions cmux à la voix par ce dépôt ; fournisseur par défaut et repli choisis sur preuves
Jalons : [x] reprise [x] N1 client MCP [x] N2 mode chaîne [x] N4 page téléphone (locale) [x] N3 banc à blanc [ ] N3 passage réel [ ] N5 essais réels
Dernier acquis : commit 0187154 — `voice-realtime banc` (harnais, métriques, rapport, garde-fous anti-paiement), passage à blanc réel sur 4 candidats gratuits, 3 payants chiffrés ; 405 tests verts
Prochaine action : avec Stéphane, de jour — relever les prix de `config/banc/tarifs.json`, confirmer les modèles candidats, valider un budget, puis `voice-realtime banc --payant --budget-usd <X>`
Bloqué : passage N3 réel et N5 exigent Stéphane (budget, de jour) ; exposition N4 (relais du Worker et application Access hors de ce dépôt) ; modèle whisper local tronqué

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
| N — voix duplex cliente de l'orchestrateur | en_cours | Les lots 1 à 6 ci-dessous sont faits et l'usage réel en balade est accepté par Stéphane | Tests N1 et N2 sans réseau ; essai local N4 (`docs/preuves/nuit-2026-11-12/B4.md`) ; banc N3 à blanc (`docs/preuves/nuit-2026-11-12/B5.md`) ; rapport du banc N3 dans le budget validé ; usage N5 |

## Lots du résultat N

| Lot | Étape de nuit | Contenu | Statut |
|---|---|---|---|
| 1/6 | B1 | Reprise du dépôt selon le système de développement : `AGENTS.md`, `CLAUDE.md`, cette roadmap, journal, test de format | livré (12/11) |
| 2/6 | B2 | N1 — client MCP des 5 outils de l'orchestrateur (`list_sessions`, `get_state_summary`, `get_last_response`, `send_instruction`, `get_instruction_status`), jeton local par `headersHelper`, garde-fou côté serveur, exposés au modèle comme `ToolSpec` | livré (12/11) |
| 3/6 | B3 | N2 — mode chaîne (reconnaissance vocale, modèle API au choix, synthèse vocale) derrière le protocole `providers`, testé sur enregistrements, sans réseau | livré (12/11) |
| 4/6 | B4 | N4 — page téléphone WebRTC : code et essai local ; exposition derrière Cloudflare Access selon l'autorisation 1 du 12/11 | livré en local (12/11) ; exposition non faite, préparée |
| 5/6 | B5 | N3 — banc d'essai : harnais, métriques (latence de première réponse, français, coupure, appels d'outils, coût à l'heure) et rapport à blanc, sans appel payant ; passage réel sur budget validé | livré à blanc (12/11) ; passage réel à faire, exige Stéphane |
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
- 2026-11-12 — Client MCP minimal écrit avec `httpx` (déjà présent) plutôt que le SDK `mcp` : pas de nouvelle dépendance ni de verrou à recalculer ; transport HTTP streamable (JSON ou SSE, `Mcp-Session-Id`), jeton relu par le `headersHelper` du Cockpit à chaque ouverture de session. `send_instruction` est classé `WRITE_USER_SCOPE` ; la CLI `voice-realtime orchestrateur` n'expose que les lectures.
- 2026-11-12 — Page téléphone (N4) : micro et haut-parleur par les API WebRTC du navigateur (`getUserMedia` avec annulation d'écho, réduction de bruit, gain auto ; worklets audio), transport PCM16 par WebSocket sur le même port que la page, sans `RTCPeerConnection`. Raison : l'exposition autorisée passe par Cloudflare Access et un tunnel HTTP, où un WebSocket circule ; un flux média UDP exigerait un serveur TURN et contournerait Access. Bonus : aucune nouvelle dépendance (`websockets` déjà présent), alors qu'`aiortc` et `av` sont lourds et natifs. Un seul appel à la fois, un fournisseur neuf par appel.
- 2026-11-12 — Mode chaîne : VAD locale par énergie (pas de dépendance native), synthèse phrase par phrase, aucun étage par défaut (les trois sont à préciser, en attendant N3). Modèle : Chat Completions compatible OpenAI (couvre OpenAI, Mistral, Groq, OpenRouter, Ollama) et Messages API Anthropic par `httpx`, en flux. Un appel d'outil lancé survit à une coupure de parole : son résultat rejoint l'historique du tour suivant.
- 2026-11-12 — Banc N3 : à blanc par défaut, avec trois verrous indépendants (liste fermée d'étages gratuits par genre, réseau coupé hors boucle locale pendant le jeu, passage payant conditionné à autorisation, budget, prix connus, majorant sous budget et heure hors 22:00-07:00). Les outils sont servis par un orchestrateur factice, même en passage réel. Un prix inconnu n'est jamais inventé. Étages simulés pour éprouver le harnais, sans valeur de comparaison.

## Risques ouverts

- Les tests vocaux de la phase 2 (matrice 9 dimensions) n'ont jamais été joués : la qualité réelle en français n'est pas mesurée.
- `pyaec` et `sounddevice` exigent des bibliothèques natives : un poste neuf peut échouer à l'installation.
- Le banc N3 réel dépend d'appels payants : sans budget validé, il reste à blanc. Prix des étages API non relevés (`null` dans `config/banc/tarifs.json`) ; tarifs horaires temps réel de mai non revérifiés. Le pilote temps réel n'a tourné que contre un faux fournisseur.
- Exposition N4 non faite. Le jeton `wrangler` n'a pas la portée Access : aucune application Access ne peut être créée ni modifiée. Le seul chemin protégé disponible est celui de l'écran O5, sous `/authorize/…` via le Worker du Cockpit. Ce Worker ne relaie aujourd'hui que GET et HEAD, sans WebSocket. Il faut ajouter dans le Cockpit une route `/authorize/voix/` qui relaie aussi l'upgrade WebSocket avec le jeton local, puis une règle de tunnel `/voix/` vers `127.0.0.1:7720` et un service lancé (`--prefixe /voix --jeton-fichier … --nom-public jarvis.dufresne-ia.com`). Sinon, Stéphane ajoute un nom d'hôte et une application Access dans le tableau de bord.
- Page téléphone : jamais essayée sur un vrai téléphone. Sur iPhone, Safari coupe le micro quand l'écran se verrouille. L'annulation d'écho du navigateur sur haut-parleur n'est pas mesurée.
- Mode chaîne : la VAD par énergie n'est pas éprouvée en rue ni sans casque (l'écho de la synthèse peut couper la réponse ; `--aec` à essayer) ; aucun étage n'a été appelé sur une API réelle.
