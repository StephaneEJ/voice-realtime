# Banc d'essai N3 — rapport à blanc

Début : 2026-11-12T02:41:30+01:00

> **À blanc.** Aucun appel payant, réseau coupé hors boucle locale pendant le jeu. Les valeurs viennent d'étages simulés ou locaux : elles éprouvent le harnais et **ne départagent aucun fournisseur**. Les prix marqués « fictif » sont inventés pour exercer le calcul. Les candidats payants sont seulement chiffrés.

Connexions bloquées par le garde-fou : 0

## Synthèse par candidat

| Candidat | Joué | 1re réponse p50 / p90 (ms) | Erreur de mots | Réponses en français | Coupures vues (délai ms) | Outils corrects | Mot d'arrêt | Coût à l'heure |
|---|---|---|---|---|---|---|---|---|
| `simule-rapide` | oui (4/4) | 1393 / 1505 | 0 % | 100 % | 100 % (210) | 100 % | 100 % | 1.259 $ (fictif)/h |
| `simule-lent` | oui (4/4) | 3249 / 3672 | 0 % | 100 % | 100 % (210) | 100 % | 100 % | 1.259 $ (fictif)/h |
| `simule-degrade` | oui (4/4) | 1939 / 2215 | 11 % | 40 % | 100 % (210) | 0 % | 100 % | 0.932 $ (fictif)/h |
| `local-say` | oui (4/4) | 2370 / 2613 | 0 % | 100 % | 100 % (210) | 100 % | 100 % | 0.377 $ (fictif)/h |
| `gemini-live` | non : payant : non joué à blanc | — | — | — | — | — | — | majorant 1.400 $/h |
| `openai-realtime-mini` | non : payant : non joué à blanc | — | — | — | — | — | — | majorant 1.250 $/h |
| `chaine-api` | non : payant : non joué à blanc | — | — | — | — | — | — | inconnu |

## Détail des latences (moyennes, ms)

| Candidat | Attente fin de parole | Transcription | Premier jeton (depuis le début du tour) |
|---|---|---|---|
| `simule-rapide` | 697 | 152 | 504 |
| `simule-lent` | 697 | 602 | 1865 |
| `simule-degrade` | 697 | 302 | 905 |
| `local-say` | 697 | 152 | 505 |

## Par scénario

### `simule-rapide` — simule:rapide → simule:rapide → simule:rapide

| Scénario | Transcription | Erreur de mots | 1re réponse (ms) | Coupure | Outils appelés | Mot d'arrêt | Erreurs |
|---|---|---|---|---|---|---|---|
| outils-et-coupure | Liste mes sessions en cours. Quel est le dernier retour de la session cockpit ? | 0 % | 1507, 1500 | vue (210) | list_sessions, get_last_response | — | 0 |
| phrase-courte | Attends, arrête-toi. | 0 % | 1276 | — | — | — | 0 |
| mot-arret | Killchat. | 0 % | 1286 | — | — | reconnu | 0 |
| voix-humaine-en | And so my fellow Americans, ask not what your country can do for you, ask what y | 0 % | — | — | — | — | 0 |

### `simule-lent` — simule:lent → simule:lent → simule:lent

| Scénario | Transcription | Erreur de mots | 1re réponse (ms) | Coupure | Outils appelés | Mot d'arrêt | Erreurs |
|---|---|---|---|---|---|---|---|
| outils-et-coupure | Liste mes sessions en cours. Quel est le dernier retour de la session cockpit ? | 0 % | 3675, 3667 | vue (210) | list_sessions, get_last_response | — | 0 |
| phrase-courte | Attends, arrête-toi. | 0 % | 2791 | — | — | — | 0 |
| mot-arret | Killchat. | 0 % | 2831 | — | — | reconnu | 0 |
| voix-humaine-en | And so my fellow Americans, ask not what your country can do for you, ask what y | 0 % | — | — | — | — | 0 |

### `simule-degrade` — simule:degrade → simule:degrade → simule:degrade

| Scénario | Transcription | Erreur de mots | 1re réponse (ms) | Coupure | Outils appelés | Mot d'arrêt | Erreurs |
|---|---|---|---|---|---|---|---|
| outils-et-coupure | Liste mes sessions cours. Quel est le retour de la cockpit ? | 21 % | 2328, 1927 | vue (210) | list_sessions | — | 0 |
| phrase-courte | Attends, arrête-toi. | 0 % | 1952 | — | — | — | 0 |
| mot-arret | Killchat. | 0 % | 1873 | — | — | reconnu | 0 |
| voix-humaine-en | And so my Americans, ask not your country can for you, ask you can do your count | 23 % | — | — | — | — | 0 |

### `local-say` — simule:rapide → simule:rapide → say:Thomas

| Scénario | Transcription | Erreur de mots | 1re réponse (ms) | Coupure | Outils appelés | Mot d'arrêt | Erreurs |
|---|---|---|---|---|---|---|---|
| outils-et-coupure | Liste mes sessions en cours. Quel est le dernier retour de la session cockpit ? | 0 % | 2706, 2397 | vue (210) | list_sessions, get_last_response | — | 0 |
| phrase-courte | Attends, arrête-toi. | 0 % | 2343 | — | — | — | 0 |
| mot-arret | Killchat. | 0 % | 2211 | — | — | reconnu | 0 |
| voix-humaine-en | And so my fellow Americans, ask not what your country can do for you, ask what y | 0 % | — | — | — | — | 0 |

## Méthode

- **Première réponse** : de la fin réelle de l'énoncé (manifeste) au premier bloc audio produit. Mode chaîne : attente de la détection de fin de parole (temps de l'enregistrement) plus le temps réel écoulé entre le début de la transcription et le premier audio. Temps réel : premier audio daté après la fin de l'énoncé.
- **Français** : taux d'erreur de mots de la transcription (minuscules, sans ponctuation ni accents) et langue de chaque réponse estimée par les mots-outils.
- **Coupure** : un événement `model_interrupted` après la reprise de parole attendue, et son délai.
- **Outils** : les outils attendus sont appelés ; ils sont servis par un orchestrateur factice, jamais une session réelle.
- **Coût à l'heure** : coût mesuré (secondes transcrites, jetons, caractères synthétisés, ou tarif horaire temps réel) ramené à la durée de conversation rejouée. Les scénarios sont denses : c'est un majorant d'une conversation réelle.
