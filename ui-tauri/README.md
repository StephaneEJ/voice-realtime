# ui-tauri — voice-realtime UI

Tauri 2 + React-TS menubar app that observes and controls the CLI's live voice session.

## Architecture

```
┌────────────────────────────────┐         ws://127.0.0.1:7711        ┌──────────────────────┐
│  voice-realtime talk --ui      │ ─────────────────────────────────► │  ui-tauri (this app) │
│  ─────────────────────────     │                                    │  ──────────────────  │
│  • mic capture (sounddevice)   │  events:                           │  • menubar tray icon │
│  • Gemini/OpenAI direct        │   - session.opened/closed          │  • borderless popover│
│  • playback (PortAudio)        │   - transcript.delta/final         │  • personas list     │
│  • CostTracker / LatencyTracker│   - audio.user/model.frame {rms}   │  • active session    │
│  • spawns control_server       │   - ttfa / ttfi / cost.tick        │  • settings modal    │
│                                │   - mute.state                     │  • global ⌘⇧M mute   │
│                                │                                    │                      │
│                                │ ◄─────────────────────────────────  │                      │
│                                │  commands:                         │                      │
│                                │   - personas.list / settings.get   │                      │
│                                │   - mute / session.stop            │                      │
└────────────────────────────────┘                                    └──────────────────────┘
```

**Audio never crosses the WebSocket.** The CLI owns the mic + playback. The UI is a viewer + light controller — it animates VU bars from RMS-only events, sends mute/stop commands, and can spawn a fresh CLI session via the `spawn_cli_session` Tauri command.

## Develop

```bash
cd ui-tauri
export PATH="/opt/homebrew/opt/rustup/bin:$PATH"  # if rust not on PATH
npm install        # one-time
npm run tauri dev  # opens the menubar app + hot-reload Vite
```

A tray icon appears in the macOS menubar. Click it to toggle the popover. Right-click for the context menu (Show/Hide, Quit).

## Build

```bash
npm run tauri build
```

Produces `src-tauri/target/release/bundle/macos/voice-realtime.app` (10-15 MB).

## Project layout

```
src/
  App.tsx                   orchestrator: WS state, view routing, shortcuts
  lib/
    models.ts               TypeScript wire contracts (mirror of control_server.py)
    ws-client.ts            typed WebSocket client with expo-backoff reconnect
    vault.ts                Obsidian Advanced URI helpers
  components/               Avatar, Bubble, ControlTrio, Kbd, MetricsStrip,
                            RadialSpectrum, StatusChip
  views/
    WelcomeView.tsx         persona list + ⌘1-9 + ⌘↵ to launch
    ActiveSessionView.tsx   live session: radial spectrum, bubbles, controls
    SettingsModal.tsx       Keys / Models / Budget / Personas tabs (read-only)
    StatusBanner.tsx        WS connection state
    EdgeStateBanners.tsx    no-key / budget warn / kill switch banners
  styles/
    midfi.css               design tokens + .mf-* class system (from design/)
    animations.css          custom keyframes (bubble-in, spring-in, slide-up)

src-tauri/
  src/lib.rs                Rust entrypoint: tray, ActivationPolicy::Accessory,
                            spawn_cli_session command, global shortcut plugin
  Cargo.toml                tauri features: tray-icon, image-png
  capabilities/default.json opener + global-shortcut permissions
  tauri.conf.json           decorations:false, transparent:true, visible:false
```

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Click tray icon | Toggle popover |
| ⌘1 – ⌘9 | Select persona (in Welcome) |
| ⌘↵ | Start session with selected persona |
| ⌘M | Mute / unmute (in active session) |
| ⌘. | Stop session (in active session) |
| ⌘, | Open Settings |
| ⌘⇧M | **Global** mute toggle (works app-unfocused) |
| Esc | Close Settings |
| ⌘Q | Quit (right-click tray → Quit) |

## How a session flows

1. **User clicks tray icon** → popover appears showing personas
2. **User picks a persona + ⌘↵** → Rust spawns `voice-realtime talk --ui --persona <slug>`
3. **CLI connects to provider** → emits `session.opened` to its embedded WS server
4. **UI receives `session.opened`** → flips from WelcomeView to ActiveSessionView
5. **CLI mic_pump** emits `audio.user.frame {rms}` per chunk → UI animates VU bar
6. **CLI recv_pump** emits transcripts + `audio.model.frame {rms}` + ttfa/ttfi → UI updates bubbles + radial spectrum
7. **User clicks Stop (or ⌘.)** → UI sends `op: session.stop` → CLI runs farewell + summary + vault save → emits `session.closed`
8. **UI receives `session.closed`** → flips back to WelcomeView with close-reason banner

## What's still ahead

- **Split overlay window** (terminal + voice metrics side-by-side, ⌘⇧E expand button is a placeholder). Wireframe in `design/midfi-main.jsx::MfOverlay`. Deferred — secondary feature.
- **Real-time in-app persona editor** (currently delegates to Obsidian via Advanced URI). Adding tauri-plugin-fs scoped to the vault would let us edit frontmatter in the modal. ~4-6h of work for a workflow the user already has.
- **API key invalid probe** — would need a backend op that hits the provider's /v1/models endpoint and reports back. Currently we only report present/absent based on config presence.
- **Window position pinned under tray icon** — Tauri 2 doesn't yet expose tray pixel coords cross-platform. Window opens centered horizontally at y=32 for now.
- **Persisted settings** — for window position, last-used persona, etc. Use tauri-plugin-store when needed.
