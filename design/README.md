# Handoff: Voice Realtime — native macOS app

## Overview

Native macOS menubar app that replaces an existing Python CLI for real-time voice
conversations with **Gemini Live** and **OpenAI Realtime** APIs. Speaks to a
**local Python backend** over WebSocket (`ws://127.0.0.1:7711`) that handles the
actual model calls, audio streaming, and tool execution. The UI only renders
events and lets the user drive sessions.

Centerpiece concept: **personas**. A persona = identity (name + avatar) + voice
(model voice preset) + behaviour rules + a slice of context (terminal tail
and/or pinned vault files) + a set of enabled skills/commands.

The app has three primary surfaces:

1. **Popover** anchored under the macOS menubar icon — for quick sessions and
   persona switching.
2. **Split-screen overlay** — when running alongside a terminal, the popover
   transforms into a fixed right-side sidebar (~20% width) so the terminal stays
   in view.
3. **Settings + Persona editor** — modal over the popover for keys, models,
   budget, and per-persona configuration.

---

## About the design files

The files in this bundle are **HTML design references** — prototypes showing
intended look and behaviour. They are not production code to copy directly.

The task is to **recreate the designs in the target codebase's environment**.
The brief proposed **SwiftUI** (preferred) or **Tauri** as fallback. Pick the
environment that fits, then implement each screen using that environment's
established patterns (`NSPopover` + `NSStatusItem` for SwiftUI; `tray-icon` +
custom window for Tauri).

Two fidelity passes are included — see below.

---

## Fidelity

**Mixed.** Two parallel passes live in the canvas:

### Low-fi (wireframes)

Hand-drawn, Caveat/Patrick Hand fonts, sketchy borders. Use these for
**structure, hierarchy, flow** decisions. Multiple variants per screen — only
the ★ kept ones matter for implementation:

- 1a · **C** (list with ⌘1-6 shortcuts)
- 1b · **E** (bubbles + radial halo + trio mute/stop/expand)
- 2 · **C** (radial spectrum sidebar)
- 3 · **vtabs** (vertical tabs, classic macOS Settings)
- 3b · **B** (sub-tabs · 3 onglets: profile / context / skills)

### Mid-fi (final visual reference) — `midfi-*.{css,jsx}`

**Pixel-fidelity reference for implementation.** SF Pro / JetBrains Mono,
warm-dark palette, accent `#4fc3f7`, real icons (inline SVG), real shadows.
Implement against these.

> **Use the mid-fi pass as the source of truth for colors, type, spacing, and
> the layout of each screen.**

---

## Screens / Views

All screens covered in mid-fi unless noted. Reference file in parentheses.

### 1. Welcome popover — *idle state* (`midfi-main.jsx` → `MfWelcome`)

- **Frame**: 400 × 600, anchored under menubar icon. Border-radius 14px,
  warm-dark gradient bg, drop shadow `0 16px 50px rgba(0,0,0,0.55)`.
- **Header**: 12px padding · "Personas" title (SF Pro Display 15px/600) on the
  left, settings cog icon (28×28 button, 7px radius) on the right · 1px border
  underneath.
- **Body**: scrollable list of persona rows. Each row:
  - 32px circular avatar with persona tint (see Design Tokens).
  - Name (SF Pro Text 14px/600), role + tag (11px/dim) ellipsised.
  - `⌘N` keyboard hint chip on the right (mini-kbd: 18px tall, 4px radius,
    monospace).
  - Hover: bg `var(--mf-panel-3)`; selected row: bg `var(--mf-acc-soft)` +
    1px accent border.
- **Footer (fixed bottom)**: gradient fade from transparent to `--mf-bg`, 1px
  border-top. Shows selected persona's name + hourly cost in monospace. Primary
  CTA button (full width, 38px tall, accent fill) labelled
  `▶ Start with Koda · ⌘↵`.

### 2. Active session popover — *live state* (`midfi-main.jsx` → `MfActive`)

- **Frame**: same 400 × 600.
- **Header**: small persona avatar (22×22) + name + live `chip` (mf-chip.live —
  pulsing green dot + `mm:ss`).
- **Hero block**: 168×168 area, persona avatar XXL (112×112) centred, with a
  **radial spectrum** drawn around it — 48 SVG lines, accent-tinted, radius 56,
  inner 26px each, every 3rd line uses `var(--mf-fg-2)` for the user-voice
  layer. Avatar uses `live` modifier → expanding ring + subtle scale pulse
  (see Animation specs §1).
- **Transcript**: bubbles. User bubbles right-aligned, full accent fill, dark
  text. Model bubbles left-aligned, `mf-panel-2` bg with 1px border. Bubble
  border-radius `12px` except for the "tail" corner (4px). Partial/streaming
  bubble: 65% opacity + italic.
- **Control trio**: 38×38 icon buttons (mute, expand) flanking a 56×56 "stop"
  talk button (danger variant — transparent fill, 2px danger stroke, danger
  glow ring).
- **Metrics strip**: monospace 10.5px, dim color, dot-separated:
  `01:48 · $0.05 · TTFI 140ms` (last number in accent).

### 3. Split overlay — *long session* (`midfi-main.jsx` → `MfOverlay`)

- **Frame**: full height. Left 70% = terminal context (`mf-term` style, fake
  Ghostty output). Right 30% = the actual app sidebar.
- The terminal panel is decorative in the design — in implementation it's
  whatever terminal the user already has on screen; the sidebar docks beside
  it via an `NSWindow` with `.canJoinAllSpaces = true` and right-edge alignment.
- **Sidebar contents** (top to bottom): mini header (caption + collapse/cog
  icons); big avatar + radial halo + persona name + role; metrics list (TTFA,
  TTFI, session, cost, tokens) in monospace right-aligned; flex spacer; control
  trio (mute + stop); monthly budget bar at the very bottom with `$X / $Y`
  caption.

### 4. Settings — *vertical tabs layout* (`midfi-settings.jsx`)

- **Frame**: 500 × 700, modal over the popover (greyed backdrop).
- **Left rail**: 156px wide, `1.5%` white tint bg, 1px right border. Section
  caption "SETTINGS" (10px uppercase mute). 4 tab rows, 28px tall, 6px radius.
  Icon + label. Active tab: `var(--mf-acc-soft)` bg + accent text, 500 weight.
- **Right pane**: 18px padding. Header row: title (16px display) + subtitle +
  close button. Body scrollable.
- **4 tabs**:

  - **API keys** (`MfKeysContent`): per-key row with label + status chip
    (ok/warn/danger), monospace key input, "Test" button. Bottom info banner
    about keychain storage.
  - **Models** (`MfModelsContent`): radio-card list. Each card 10×12 padding,
    monospace model ID, role tag, price chip. Selected card: accent border +
    soft accent fill. Below the list: audio chips (codec/echo).
  - **Budget** (`MfBudgetContent`): slider `$5-$50`, progress bar of usage,
    "alert at 80%" toggle (iOS-style switch 36×20), per-persona spend bars
    (each row: avatar + name + colored bar + amount).
  - **Personas** (`MfPersonasContent`): card list with drag handle (`⋮⋮`),
    avatar, name + voice tag, edit/duplicate/delete icon buttons. "+ New
    persona" button top-right.

### 5. Persona editor — *3 sub-tabs* (`midfi-settings.jsx` → `MfPersonaEditor`)

- **Frame**: 520-wide, opens when a personas row is clicked from Settings.
- **Header**: back chevron, persona avatar, name (16px display) — Cancel +
  Save buttons on the right (primary fill for Save).
- **Sub-tabs**: segmented control (`mf-subtabs`) — 3 segments: Profile /
  Context / Skills. Active segment: `--mf-panel-3` fill, white text.
- **Profile tab** (`MfProfileBlock`):
  - **Identity** group: 80×80 avatar + "change…" button + name input + role
    input + voice chip selector (`alloy` active, others outline).
  - **Behavior** group: two row-toggles —
    - `Web search` (ON) with sub-row of allowed-domain chips
      (`arxiv.org`, `docs.* +12`, `+ domain` outline).
    - `Ask before acting` (ON).
- **Context tab** (`MfContextBlock`):
  - **Budget header card**: title, "X% used" in accent, monospace model id,
    stacked horizontal bar (sliding portion in accent + static portion in
    warn), per-segment legend chips.
  - **Sliding card**: title `Sliding · terminal tail` (accent),
    `auto · live` ok chip. Caption: no source picker — the launching
    terminal is the source. Slider for window size (500 → 32k tokens),
    captioned with current value + line count + % of model budget.
  - **Static card**: title `Static · vault pin` (warn), `persisted` caption.
    Filter input. Vault tree (12px monospace, hierarchical indent 14px per
    depth) with custom 12×12 checkboxes per file — on (filled accent),
    off (outline mute), partial (warn dash). "Auto-include linked notes"
    row-toggle at bottom.
- **Skills tab** (`MfSkillsBlock`):
  - **Built-in skills** list — each card: monospace skill id (accent if on,
    mute if off), description, iOS-style switch.
  - **Custom commands** list — each card: command name (`/review`) in
    monospace accent, trigger ("when:") and action ("do:") rows below.
    Edit + delete icons. "+ new" button at section head.

### 6. Edge cases (8 states) — `midfi-states.jsx`

All 8 must be implemented before shipping:

| State                 | Component               | Trigger                          |
|-----------------------|-------------------------|----------------------------------|
| First launch          | `MfStateOnboarding`     | No personas in store             |
| No API key            | `MfStateNoKey`          | Both OpenAI + Gemini keys empty  |
| Key invalid (401)     | `MfStateKeyInvalid`     | Test endpoint returns 401        |
| WS backend down       | `MfStateWsDown`         | Cannot connect to `:7711`        |
| Mic permission denied | `MfStateMicDenied`      | `AVCaptureDevice` denied         |
| Budget cap hit        | `MfStateBudgetHit`      | Spend ≥ monthly cap              |
| Vault not linked      | `MfStateVaultEmpty`     | Persona editor → context, vault path null |
| Unsaved changes       | `MfStateUnsaved`        | Cmd+W / back with dirty form     |

Banner system (`.mf-banner`) has 3 severities: `info` (accent), `warn`
(orange), `danger` (red). Use accordingly.

### 7. Animation specs (5 animations) — `midfi-anim.jsx`

Cards document the animations precisely. Implement as listed:

1. **Avatar pulse**: avatar scale 1.000 → 1.035 (ease-in-out 1600ms loop)
   + expanding ring scale 1.00 → 1.32 with fade
   (cubic-bezier(0.16, 1, 0.3, 1), 1600ms iteration).
   Driven by `audio.model.frame` events. Stops 200ms after last frame.
2. **Talk button**: idle (accent fill) → connecting (warn fill + spinner) →
   live (transparent + danger stroke + danger glow). 180ms ease-in-out for
   bg/shadow tween. Spinner = SVG arc 30/90 dasharray rotating 360° in
   900ms linear infinite. Connecting timeout 4000ms → revert + banner.
3. **Popover spring**: open in 240ms with
   `cubic-bezier(0.34, 1.56, 0.64, 1)` (gentle overshoot). Transform
   `translateY(-6px) scale(0.94) → 1`. Close in 140ms ease-out.
4. **VU bars**: RMS over 20ms windows → 32 log-bands. Smoothing
   `h(t) = max(rms, h(t-1) · 0.78)` (22% decay per frame). 50Hz visual
   updates. Floor 3px so silence is still legible.
5. **Overlay slide-in**: popover closes (140ms) then sidebar slides from
   `translateX(100%)` to `0` in 320ms with
   `cubic-bezier(0.32, 0.72, 0, 1)`. 80ms overlap with popover close is OK.

All animations: **respect `prefers-reduced-motion`** — replace
scale/translate with opacity-only, drop loops to static states.

---

## Interactions & navigation

### Keyboard shortcuts (macOS-native, all global within the app)

| Shortcut | Action |
|----------|--------|
| `⌘.`     | Stop current session |
| `⌘,`     | Open Settings |
| `⌘P`     | Open persona switcher (focuses welcome list) |
| `⌘↵`     | Start session from Welcome (with selected persona) |
| `⌘M`     | Toggle mute mic |
| `⌘⇧E`    | Expand popover → split overlay |
| `⌘1`–`⌘6`| Jump to persona N (Welcome) |
| `fn`     | Hold for push-to-talk |
| `Esc`    | Close popover / dismiss modal |
| `⌘S`     | Force-save in persona editor (auto-saves otherwise) |

### Flows

- **Launch a session**: menubar icon click → popover opens → user picks persona
  (click row or ⌘N) → click "Start" or ⌘↵ → state moves to *connecting*
  (talk button warn + spinner) → on first audio frame received → *live* state
  (talk button → stop, transcript starts rendering, VU bars activate).
- **Mid-session expand**: in live popover, click the `⤡` icon (or ⌘⇧E). Popover
  closes; sidebar slides in from right; menubar icon switches to hollow ring
  to indicate "session is in overlay".
- **Mid-session collapse**: in overlay, click the `⤺` icon. Sidebar slides
  out; popover re-opens with the same live session.
- **Persona switching while live**: not allowed — the user must Stop first.
  (Switching requires a model handshake reset.)

### Session state machine

```
idle ──click▶─▶ connecting ──ws.connected─▶ live ──click⏹/⌘.─▶ stopping ──ws.closed─▶ post-session
                    │
                    └──timeout 4s─▶ error (banner + retry)

live ──┬── click mic/⌘M ──▶ muted (mic suspended, no tokens spent)
       │                      │
       │                      └──click mic/⌘M──▶ live
       │
       └── ws.disconnect ──▶ reconnecting (auto, expo backoff up to 8 tries)
```

---

## State management

### Persisted (user defaults / file)

- `personas: Persona[]` — full list with order. Persisted in
  `~/Library/Application Support/voice-rt/personas.json`.
- `activePersonaId: string` — last used.
- `settings.modelDefault: string`
- `settings.budgetCap: number` — USD/month
- `settings.alertAt80: boolean`
- Per-persona: voice, web-access flag, allowed domains, ask-before-acting,
  sliding-window size, static vault selection (file paths), enabled skills,
  custom commands.

### Keychain (macOS)

- `openai_api_key`
- `gemini_api_key`
- `telegram_token` (optional)

### Ephemeral (in-memory, per session)

- `sessionState: 'idle' | 'connecting' | 'live' | 'muted' | 'stopping' | 'error'`
- `transcript: TurnSegment[]` — accumulator with `partial` flag for the streaming one.
- `metrics: { ttfa, ttfi, durationMs, costUsd, tokensIn, tokensOut }`
- `vuLevels: { user: number[], model: number[] }` — last 32 normalized RMS bands.
- `wsConnection` + reconnect state.

### Data fetching / IPC

The app **does not call model APIs directly** — it talks to the local Python
backend over WebSocket. Suggested message schema (the user can ignore if their
backend is already specified):

```json
// → backend
{"op": "session.start", "personaId": "koda", "model": "gpt-realtime-2"}
{"op": "audio.frame", "pcm16": "<base64>", "ts": 1234567890}
{"op": "mute", "on": true}
{"op": "session.stop"}

// ← backend
{"ev": "session.opened", "sessionId": "...", "model": "...", "voice": "alloy"}
{"ev": "audio.user.frame", "rms": 0.42, "ts": 123}
{"ev": "audio.model.frame", "rms": 0.31, "pcm16": "..."}
{"ev": "transcript.delta", "role": "user|model", "text": "...", "final": false}
{"ev": "transcript.final", "role": "user|model", "text": "..."}
{"ev": "ttfa", "ms": 280}
{"ev": "ttfi", "ms": 140}
{"ev": "skill.call", "id": "vault.search", "args": {}}
{"ev": "skill.result", "id": "vault.search", "ok": true, "tokens": 4200}
{"ev": "cost.tick", "delta": 0.003, "total": 0.42}
{"ev": "error", "code": "API_KEY_INVALID", "msg": "..."}
{"ev": "session.closed", "reason": "user|error|timeout"}
```

---

## Design tokens

All in `midfi.css`. Drop these into your design system / token store.

### Colors

```
--mf-bg:        #14161b   page background (warm dark)
--mf-panel:     #1a1d23   popover / modal surface
--mf-panel-2:   #20242c   nested boxes, cards
--mf-panel-3:   #262b34   inputs, hover, segmented bg

--mf-border:    rgba(255,255,255,0.06)
--mf-border-2:  rgba(255,255,255,0.10)
--mf-stroke:    rgba(255,255,255,0.14)

--mf-fg:        #ecedef   primary text
--mf-fg-2:      #c4c7cd   secondary text
--mf-dim:       #8d929c   muted text / captions
--mf-mute:      #5c6068   placeholders, very dim

--mf-acc:       #4fc3f7   primary accent (live, links, primary CTA fill)
--mf-acc-2:     #29b3f3   hover variant
--mf-acc-soft:  rgba(79,195,247,0.14)
--mf-acc-glow:  rgba(79,195,247,0.35)

--mf-warn:      #ffb74d   cost/budget warnings
--mf-danger:    #ff7676   destructive, stop, errors
--mf-ok:        #80e27e   live indicators
(+ soft variants at 0.14 alpha for each)
```

### Persona accent tints (avatar backgrounds)

```
aria #ff8a7a · koda #4fc3f7 · mira #c084fc
noor #5eead4 · zen  #a3e635 · fox  #ffb74d
```

### Typography

- **Sans**: SF Pro Text / SF Pro Display (use `-apple-system` on macOS).
- **Mono**: JetBrains Mono (bundle), fallback SF Mono.
- Letter-spacing `-0.005em` on body, `-0.01em` on titles, `-0.018em` on display.
- Sizes: display 22 / title 16 / body 13 / caption 11 / label 11 uppercase /
  mono 11 (12 for prominent values).

### Spacing scale

`4, 6, 8, 10, 12, 14, 16, 18, 22, 28` — most layouts use 8/12/18.

### Radii

- Chips: 6
- Buttons / inputs / icons: 7-9
- Cards: 10
- Popover / modal: 12-14
- Talk button: 50% (full circle)

### Shadows

- Popover:
  `0 1px 0 var(--mf-border-2) inset, 0 16px 50px rgba(0,0,0,0.55), 0 0 0 1px rgba(0,0,0,0.5)`
- Modal: `0 18px 60px rgba(0,0,0,0.6)`
- Primary button:
  `0 1px 0 rgba(255,255,255,0.4) inset, 0 4px 14px var(--mf-acc-glow)`
- Talk button: same + `0 0 0 6px rgba(79,195,247,0.10)` outer ring

---

## Assets

- **No bundled images** — avatars are letters on persona-tinted circles
  (component `MfAvatar`). If the user later wants real avatars, swap with a
  loaded image and keep the persona tint as fallback.
- **Icons are inline SVG** — see the trio (mute/stop/expand) in `MfActive` and
  `MfOverlay`. The implementation should switch to **SF Symbols** in SwiftUI
  (e.g. `mic`, `mic.slash`, `stop.fill`, `arrow.up.left.and.arrow.down.right`),
  or to **Tabler Icons / Lucide** if going Tauri/web.
- **Fonts**: SF Pro is system on macOS. **JetBrains Mono** must be bundled if
  going Tauri; in SwiftUI it can be loaded as a custom font.

---

## Files (in this bundle)

### Mid-fi (the reference)

- `midfi.css` — full token system, every utility class used by mid-fi
- `midfi-primitives.jsx` — `MfAvatar`, `MfHeader`, `MfVuBars`, `MfVuWave`,
  `MfRadial`, `MfSpark`, `MfSwitch`, `MfRowToggle`, `MfMenubar`
- `midfi-main.jsx` — `MfWelcome`, `MfActive`, `MfOverlay`
- `midfi-settings.jsx` — `MfSettingsKeys/Models/Budget/Personas`,
  `MfPersonaEditor`, plus blocks `MfProfileBlock`, `MfContextBlock`,
  `MfSkillsBlock`
- `midfi-states.jsx` — the 8 edge cases
- `midfi-anim.jsx` — animation specs cards

### Wireframes (for context only, not for implementation)

- `sketchy.css` + `primitives.jsx` + `welcome.jsx` + `active.jsx` +
  `overlay.jsx` + `settings.jsx` + `persona-editor.jsx` — kept for reference
  on flow exploration. The mid-fi pass supersedes everything visually.

### Canvas / shell

- `Voice Realtime Wireframes.html` — open this in a browser to navigate every
  artboard. Pan/zoom canvas.
- `app.jsx` + `design-canvas.jsx` + `tweaks-panel.jsx` — host code, ignore.

---

## Implementation suggestions (non-prescriptive)

- **SwiftUI**: use `NSStatusItem` for the menubar, `NSPopover` (transient
  behaviour) for the popover, a separate `NSWindow` aligned to right edge for
  the overlay (set `level = .floating`, `canJoinAllSpaces = true`,
  `styleMask = .borderless`). Audio: `AVAudioEngine` + `AVAudioConverter` for
  PCM16/24kHz capture, `AVAudioPlayerNode` for playback. WS: `URLSessionWebSocketTask`.
- **Tauri**: `tray-icon` for menubar, custom transparent window for popover
  (focused = visible, blur = hidden), second window for overlay with
  `alwaysOnTop`. Audio: `cpal` (Rust) or `Web Audio API` (front-end). WS: native.

Either way: **persist everything per-persona to disk**, keep API keys in
keychain (`security` CLI in Tauri, native APIs in SwiftUI), and never let WS
ride on the JS heap longer than necessary.
