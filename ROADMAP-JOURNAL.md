# ROADMAP-JOURNAL

Historique des clôtures de session (ajout seul). L'historique antérieur au 12/11/2026 est dans le README, `docs/` et l'historique Git.

## 2026-11-12 — reprise du dépôt selon le système de développement (nuit, étape B1)

- **Preuves :** `docs/preuves/nuit-2026-11-12/B1.md` ; 232 tests existants verts sur `637132a`, plus le test de format de la roadmap.
- **Décisions :** `ROADMAP-DEV.md` unique ; roadmaps de mai archivées ; résultat N du Cockpit exécuté ici en six lots.
- **Limites :** aucun code fonctionnel modifié ; aucun essai vocal.

## 2026-11-12 — N1 client MCP des 5 outils de l'orchestrateur (nuit, étape B2)

- **Preuves :** `docs/preuves/nuit-2026-11-12/B2.md` ; 261 tests verts sans réseau (25 nouveaux) ; `list_sessions`, `get_state_summary`, `tools/list` et un refus `session_introuvable` rejoués sur le serveur local réel.
- **Décisions :** client `httpx` sans SDK `mcp` ; `send_instruction` en `WRITE_USER_SCOPE` ; avertissement « donnée non fiable » ajouté aux retours de session.
- **Limites :** `send_instruction` non appelé en réel (pas de session de test dédiée) ; aucun essai vocal ni fournisseur.

## 2026-11-12 — N2 mode chaîne reconnaissance, modèle, synthèse (nuit, étape B3)

- **Preuves :** `docs/preuves/nuit-2026-11-12/B3.md` ; 303 tests verts sans réseau (42 nouveaux, réseau bloqué pour les vérifier) sur enregistrements `say` et `jfk.wav` ; chaîne locale rejouée de bout en bout avec la vraie voix `say`.
- **Décisions :** aucun étage par défaut ; VAD locale par énergie ; modèle compatible OpenAI ou Anthropic en flux ; outil lancé conservé après coupure.
- **Limites :** aucune API réelle appelée (interdit de nuit) ; whisper.cpp réel non joué (modèle local tronqué) ; pas d'essai micro ni en rue.

## 2026-11-12 — N4 page téléphone, code et essai local (nuit, étape B4)

- **Preuves :** `docs/preuves/nuit-2026-11-12/B4.md` ; 369 tests verts (66 nouveaux, réseau limité à la boucle locale) ; essai réel dans Chrome sans interface, micro simulé par un enregistrement, 7/7 contrôles (découpage, coupure pendant la voix, outil, voix jouée, raccroché).
- **Décisions :** capture et lecture WebRTC du navigateur, transport WebSocket (compatible Access et tunnel), sans nouvelle dépendance ; verrous locaux (hôte, origine, Access ou jeton local) ; aucun fournisseur par défaut.
- **Limites :** exposition non faite (pas de portée Access, relais WebSocket du Worker à écrire dans le Cockpit) ; aucun essai sur téléphone ni avec un fournisseur réel.

## 2026-11-12 — N3 banc d'essai à blanc (nuit, étape B5)

- **Preuves :** `docs/preuves/nuit-2026-11-12/B5.md` et `B5-banc/rapport.md` ; 405 tests verts (36 nouveaux) ; passage à blanc réel : 4 candidats gratuits joués sur 4 scénarios, 3 payants chiffrés sans être joués, aucune connexion tentée.
- **Décisions :** à blanc par défaut, trois verrous (étages gratuits par genre, réseau coupé, passage payant sous budget et de jour) ; orchestrateur factice ; prix inconnus jamais inventés.
- **Limites :** aucun fournisseur réel mesuré ; pilote temps réel éprouvé sur un faux seulement ; prix des étages API à relever.
