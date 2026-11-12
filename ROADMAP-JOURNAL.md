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
