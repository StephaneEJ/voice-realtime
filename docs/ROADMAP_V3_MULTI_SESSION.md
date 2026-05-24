# Roadmap voice-realtime V3 — exécution multi-session parallèle

**Date** : 2026-05-24 (post-sprint 7 chantiers Phase 3 V2 + 3.F.1 backend WS).
**État** : voir [[Voice Realtime Skill]] section "Sprint 24/05".

## Contexte de cette roadmap

Tout le scope Phase 3 V2 hors UX macOS (P0.1 → 3.H) a été livré dans une session unique avec 138 → 150 pytest verts. Reste **3.F — UX macOS native SwiftUI** qui est :
1. Plus gros que tout ce qui a été livré (~14-16 jours dev)
2. Bloqué par 2 pré-requis (cleanup disque + install Xcode)
3. **Parallélisable** : 5 vues UI + 3 services + tokens + animations peuvent être attaqués en concurrence par plusieurs sessions Claude Code une fois le scaffold posé.

L'idée : poser un scaffold partagé + définir des contrats internes stables (types Swift, signatures de protocoles, design tokens), puis dispatcher les sous-parties à des sessions parallèles. Chacune travaille sur sa branche + son scope clos, sans risque de conflit majeur.

## Ce qui est livré (24/05)

✅ **3.F.1 backend Python** (`voice_realtime/control_server.py` + tests). 150 pytest verts.

WS server `ws://127.0.0.1:7711` conforme schema `design/README.md`. Toutes les ops (session.start / audio.frame / mute / session.stop) + events (session.opened / audio.user.frame / audio.model.frame / transcript.delta+final / model.interrupted / ttfa / ttfi / cost.tick / error / session.closed) sont câblées. Testable seul via `voice-realtime serve` + `websocat`.

## Pré-requis blocant pour la suite

| Sub-step | Bloqué par |
|---|---|
| **3.F.2** scaffold SwiftUI | [[Nettoyage MacBook]] → install Xcode (15 GB) |
| **3.F.3-8** vues / services / anims | 3.F.2 + tokens partagés posés |

## Plan multi-session parallèle (post-3.F.2)

Une fois le scaffold SwiftUI posé (Session 0), **6 sessions Claude Code peuvent tourner en parallèle**.

### Session 0 — Scaffold + contrats partagés (séquentielle, ~1 jour)

**À faire en premier, par une seule session, avant tout fork.**

- Créer `ui-macos/` (Swift Package + Xcode project)
- Structure dossiers stable (Views/ / Models/ / Services/ / Resources/ / Components/)
- Poser les **design tokens** (`Resources/Tokens.swift`) ports de `midfi.css` :
  - Couleurs (`MfBg`, `MfPanel`, `MfAcc`, persona tints…)
  - Typo (SF Pro, JetBrains Mono, sizes display/title/body/caption)
  - Spacing scale, radii, shadows
- Poser les **modèles Swift** (`Models/Persona.swift`, `SessionState.swift`, `Metrics.swift`) — figés
- Poser le **WebSocketClient** stub (`Services/WebSocketClient.swift`) — protocole observé + signatures
- Build "hello menubar" qui ouvre une icône menubar vide qui se branche au WS (mais sans UI utile)
- Commit "Phase 3.F.2 scaffold + tokens + ws client stub"

**Livrable** : repo `ui-macos/` qui build, icône menubar visible, WS client connecté.

### Branches parallèles (post-Session 0)

Chaque session ci-dessous travaille sur une branche dédiée, sur son scope clos. Pas de chevauchement de fichiers entre sessions sauf rebase final.

#### Session A — Audio engine
- **Fichiers** : `Services/AudioEngine.swift` (AVAudioEngine + AVAudioConverter), `Services/AudioPlayback.swift`
- **Scope** : capture mic 16/24 kHz selon provider, conversion vers PCM16 little-endian, envoi via `WebSocketClient.sendAudioFrame()`. Réception `audio.model.frame` → AVAudioPlayerNode.
- **Référence** : `voice_realtime/audio/microphone.py` + `playback.py` (équivalent Python existant)
- **Tests** : capture silencieuse (vérifier no-crash + bytes attendus), playback PCM16 (vérifier audible)
- **Effort** : 2-3 jours
- **Branche** : `3.f.audio`

#### Session B — Welcome popover
- **Fichiers** : `Views/WelcomePopover.swift`, `Views/Components/PersonaRow.swift`, `Views/Components/PrimaryCTA.swift`
- **Scope** : popover 400×600, liste personas (lit `_System/voice-personas/*.md` via le backend Python WS `personas.list` à ajouter), shortcuts ⌘1-6, ⌘N pour nouveau persona, ⌘↵ démarrer
- **Référence** : `design/midfi-main.jsx` → `MfWelcome` + `midfi.css`
- **Effort** : 2 jours
- **Branche** : `3.f.welcome`

#### Session C — Active session popover
- **Fichiers** : `Views/ActiveSession.swift`, `Views/Components/RadialSpectrum.swift`, `Views/Components/TranscriptBubble.swift`, `Views/Components/ControlTrio.swift`, `Views/Components/MetricsStrip.swift`
- **Scope** : popover 400×600 état live, radial spectrum 48 SVG lines + avatar pulse 1600ms, transcript bubbles (user droite accent / model gauche panel-2), trio mute/stop/expand, métriques `mm:ss · $cost · TTFI Xms`
- **Référence** : `design/midfi-main.jsx` → `MfActive`
- **Dépendance** : Session A (audio engine pour bytes mic + playback), Session 0 (WS client)
- **Effort** : 3 jours
- **Branche** : `3.f.active`

#### Session D — Split overlay + animations
- **Fichiers** : `Views/SplitOverlay.swift`, `Resources/Animations.swift`
- **Scope** : NSWindow flottant droite 30% écran, sidebar avatar XXL + halo + métriques + sparkline coût 30j (consume `cost.tick` events). Implémente les 5 animations (avatar pulse, talk button states, popover spring, VU bars smoothing, overlay slide-in).
- **Référence** : `design/midfi-main.jsx` → `MfOverlay` + `design/midfi-anim.jsx`
- **Dépendance** : Session 0 (tokens), Session C (mêmes composants)
- **Effort** : 2 jours
- **Branche** : `3.f.overlay`

#### Session E — Settings modal (4 onglets)
- **Fichiers** : `Views/SettingsModal.swift`, `Views/Settings/KeysTab.swift`, `Views/Settings/ModelsTab.swift`, `Views/Settings/BudgetTab.swift`, `Views/Settings/PersonasTab.swift`, `Services/KeychainStore.swift`
- **Scope** : modal 500×700 + 4 onglets verticaux. Tab Keys = inputs API key + test endpoint (`/v1/models` OpenAI, `/v1beta/models` Gemini). Tab Models = radio cards. Tab Budget = slider $5-$50 + bar + toggle 80%. Tab Personas = liste avec drag handle + edit/duplicate/delete.
- **Référence** : `design/midfi-settings.jsx`
- **Dépendance** : Session 0
- **Effort** : 2 jours
- **Branche** : `3.f.settings`

#### Session F — Persona editor (3 sub-tabs)
- **Fichiers** : `Views/PersonaEditor.swift`, `Views/Settings/ProfileBlock.swift`, `Views/Settings/ContextBlock.swift`, `Views/Settings/SkillsBlock.swift`
- **Scope** : editor 520-wide, segmented control 3 sub-tabs. Profile = identity + behavior toggles + voice selector. Context = budget header card + sliding terminal-tail slider + static vault pin avec tree de fichiers cochables. Skills = built-in toggles + custom commands.
- **Référence** : `design/midfi-settings.jsx` → `MfPersonaEditor`
- **Dépendance** : Session 0, Session E (modèle Settings)
- **Effort** : 2 jours
- **Branche** : `3.f.persona-editor`

#### Session G — Edge cases (8 états)
- **Fichiers** : `Views/States/*.swift` (Onboarding, NoKey, KeyInvalid, WsDown, MicDenied, BudgetHit, VaultEmpty, Unsaved)
- **Scope** : 8 vues edge case + banner system (info/warn/danger). Trigger logic dans `ViewModels` correspondants.
- **Référence** : `design/midfi-states.jsx`
- **Dépendance** : Session 0 (tokens) + sessions correspondantes (chaque edge case habite une view existante)
- **Effort** : 1.5 jour
- **Branche** : `3.f.edge-cases`

### Session de merge final (séquentielle, ~1 jour)

Une fois A-G livrées sur leurs branches respectives :

- Rebase sur main dans l'ordre A → B → C → D → E → F → G
- Résoudre conflits éventuels (probablement minimal vu le découpage par fichiers)
- Run full test suite SwiftUI (XCTest) + Python pytest
- Vérifier flow utilisateur complet end-to-end (lancer l'app, créer persona, faire session, etc.)
- Tagger version

## Total estimé

| Phase | Effort cumul si séquentiel | Effort si en parallèle (6 sessions) |
|---|---|---|
| Session 0 scaffold | 1j | 1j |
| Sessions A-G | 14-15j cumulés | **3j parallel** (max(2-3j) par session) |
| Merge final | 1j | 1j |
| **Total** | **16-17j séquentiel** | **5j parallel** ⚡ |

Économie : **~70 % du temps wall-clock** si 6 sessions parallèles. Effort total reste le même (~17j de dev cumulé), mais répartie sur 5 jours wall-clock.

## Comment lancer une session parallèle

Pour chaque branche A-G, ouvrir un Claude Code session dédié au repo, avec ces consignes :

```
Session 3.F-<lettre> — voice-realtime UI macOS

Repo : ~/OBSIDIAN/PROJETS DEV/voice-realtime/
Branche : 3.f.<scope> (à créer si pas existante)
Référence design : ~/OBSIDIAN/PROJETS DEV/voice-realtime/design/midfi-*.{css,jsx}
Plan global : ~/OBSIDIAN/PROJETS DEV/voice-realtime/docs/ROADMAP_V3_MULTI_SESSION.md
Backend WS schema : design/README.md (section "Data fetching / IPC")

Scope : <copier la section "Session X" du roadmap>
Fichiers à créer : <liste>
Tests : minimum 1 vue scrollable manuellement + 1 état edge case si applicable
À NE PAS toucher : fichiers hors du scope listé (autres branches y travaillent)

Quand tu as livré : commit propre + push sur 3.f.<scope>, puis update ce roadmap.
```

## Pré-requis pour démarrer

1. ✅ Backend Python 3.F.1 livré
2. ✅ Handoff Claude Design importé dans `design/`
3. ⏳ [[Nettoyage MacBook]] terminé (cible ≥ 30 GB libres)
4. ⏳ Xcode installé via App Store
5. ⏳ Session 0 scaffold complétée (1 personne, séquentiel)

Puis : fork des sessions A-G en parallèle.

## Décisions ouvertes

1. **WS reconnect auto** (expo backoff up to 8 tries) — implémenter dans `WebSocketClient.swift` (Session 0) ou différer en post-MVP ?
2. **Push-to-talk fn key global** — handler global system event, faisable mais demande NSEvent.addGlobalMonitorForEvents — vérifier permission Accessibility requise.
3. **Snapshot tests SwiftUI** vs tests manuels uniquement — proposition : tests unitaires Models + Services + ViewModels (XCTest), tests visuels manuels.
