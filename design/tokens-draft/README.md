# tokens-draft/ — Session 0 scaffold reference material

**Status** : draft texte, pas dans un Xcode project, pas compilé.

## Pourquoi ce dossier existe

Bloqué pour démarrer la **Session 0 SwiftUI scaffold** (cf. `docs/ROADMAP_V3_MULTI_SESSION.md`) par :
1. Cleanup MacBook en cours (libérer ≥30 GB)
2. Install Xcode (15 GB depuis App Store)

Pendant l'attente, on prépare les artefacts **texte uniquement** que Session 0 devra produire. Une fois Xcode dispo, ces fichiers sont déplacés vers `ui-macos/Sources/VoiceRTApp/Resources/` (Tokens) et `Models/` (un fichier par type), puis compilés.

## Contenu

| Fichier | Cible Session 0 | Rôle |
|---|---|---|
| `Tokens.swift` | `Resources/Tokens.swift` | Couleurs, typo, spacing, radii, motion — port de `design/midfi.css` |
| `Models.swift` | `Models/Persona.swift`, `Models/SessionState.swift`, `Models/Metrics.swift`, etc. | Contrats partagés entre les 6 sessions parallèles A-G |

## À faire pendant Session 0 (cleanup + repartition)

1. Créer `ui-macos/` Swift Package + Xcode project (cf. roadmap section "Session 0")
2. Copier `Tokens.swift` tel quel dans `Resources/`
3. Split `Models.swift` en un fichier par type (`Persona.swift`, `SessionState.swift`, `SessionMetrics.swift`, `TranscriptTurn.swift`, `VULevels.swift`, `AppSettings.swift`, `WSError.swift`)
4. Vérifier compile + `swift test` minimal (un round-trip Codable sur `Persona`)
5. Supprimer ce dossier `tokens-draft/` une fois absorbé

## Notes de design

- **Namespacing** : tout est sous `enum Mf` (couleurs/typo/spacing) ou structs racine (modèles). Pas de globals.
- **Provider/VAD enums Codable** : matchent les strings du backend Python (`"gemini"`, `"openai"`, `"reactive"`, `"balanced"`, `"patient"`, `"very-patient"`). Si on rename côté Python, casser ici aussi.
- **`Color(hex:)` extension** : duplique CSS hex literals 1:1 pour faciliter audit visuel.
- **VULevels.bufferSize = 32** : aligné avec design/README.md "vuLevels: { user: number[], model: number[] } — last 32 normalized RMS bands".
- **Persona Codable** : la clé `id` mappe au champ `id` du WS payload `personas.list` (qui est lui-même = slug Python). Pas de `CodingKeys` custom nécessaire.

## Décisions ouvertes encore non tranchées

Cf. `docs/ROADMAP_V3_MULTI_SESSION.md` section "Décisions ouvertes" :
1. WS reconnect auto (expo backoff) dans Session 0 ou post-MVP ?
2. Push-to-talk fn key — perm Accessibility requise, à valider
3. Snapshot tests SwiftUI vs tests manuels
