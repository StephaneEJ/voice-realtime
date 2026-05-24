/* global React, ReactDOM,
   DesignCanvas, DCSection, DCArtboard, DCPostIt,
   TweaksPanel, useTweaks, TweakSection, TweakColor, TweakToggle, TweakRadio,
   WelcomeA, WelcomeB, WelcomeC, WelcomeD,
   ActiveA, ActiveB, ActiveC, ActiveD,
   OverlayA, OverlayB, OverlayC, OverlayD,
   SettingsA, SettingsB, SettingsC, SettingsD, SettingsE,
   PersonaEditorA, PersonaEditorB, PersonaEditorC,
   MfWelcome, MfActive, MfOverlay,
   MfSettingsKeys, MfSettingsModels, MfSettingsBudget, MfSettingsPersonas,
   MfPersonaEditor,
   MfStateNoKey, MfStateWsDown, MfStateBudgetHit, MfStateMicDenied,
   MfStateVaultEmpty, MfStateUnsaved, MfStateOnboarding, MfStateKeyInvalid,
   MfaPulse, MfaTalk, MfaPopover, MfaVU, MfaOverlay,
   Callout, Kbd */

const { useEffect } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "blue",
  "theme": "dark",
  "density": "comfy"
}/*EDITMODE-END*/;

function App() {
  const [t, setT] = useTweaks(TWEAK_DEFAULTS);

  // Reflect tweaks on <html> so CSS vars pick them up everywhere (including
  // every artboard).
  useEffect(() => {
    document.documentElement.dataset.accent  = t.accent === 'orange' ? 'orange' : 'blue';
    document.documentElement.dataset.theme   = t.theme  === 'light'  ? 'light'  : 'dark';
    document.documentElement.dataset.density = t.density === 'compact' ? 'compact' : 'comfy';
  }, [t.accent, t.theme, t.density]);

  return (
    <>
      <DesignCanvas>
        {/* ── INTRO post-it cluster ────────────────────────────── */}
        <DCSection id="intro" title="voice realtime — macOS wireframes"
                   subtitle="3 vues · 4 variantes chacune · low-fi · shortcuts macOS natifs">
          <DCArtboard id="legend" label="legend" width={400} height={300}>
            <div className="wf" style={{ padding: 18 }}>
              <div className="h h2" style={{ marginBottom: 6 }}>How to read these.</div>
              <div className="col" style={{ gap: 8 }}>
                <div className="row" style={{ gap: 10 }}>
                  <span className="av md acc">K</span>
                  <span className="lbl dim">hatched circle = avatar placeholder</span>
                </div>
                <div className="row" style={{ gap: 10 }}>
                  <div className="box dash" style={{ width:70, height:24 }} />
                  <span className="lbl dim">dashed border = partial / streaming / placeholder</span>
                </div>
                <div className="row" style={{ gap: 10 }}>
                  <span className="chip acc">accent</span>
                  <span className="chip ok">ok</span>
                  <span className="chip warn">warn</span>
                  <span className="chip danger">err</span>
                </div>
                <div className="row" style={{ gap: 10 }}>
                  <Kbd>⌘</Kbd><Kbd>P</Kbd>
                  <span className="lbl dim">= macOS keyboard shortcut</span>
                </div>
                <div className="row" style={{ gap: 10 }}>
                  <span className="callout"><span className="num">1</span></span>
                  <span className="lbl dim">= numbered callout, see notes</span>
                </div>
              </div>
            </div>
          </DCArtboard>

          <DCArtboard id="shortcuts" label="shortcuts" width={400} height={300}>
            <div className="wf" style={{ padding: 18 }}>
              <div className="h h2" style={{ marginBottom: 8 }}>Keyboard.</div>
              <div className="col" style={{ gap: 6, fontSize: 13 }}>
                {[
                  [['⌘','.'],       'stop session'],
                  [['⌘',','],       'open settings'],
                  [['⌘','P'],       'persona switcher'],
                  [['⌘','↵'],       'start session (welcome)'],
                  [['⌘','M'],       'toggle mute'],
                  [['⌘','⇧','E'],   'expand to split-overlay'],
                  [['fn'],          'push-to-talk (hold)'],
                  [['esc'],         'close popover'],
                  [['⌘','1-6'],     'jump to persona N'],
                ].map(([keys, label]) => (
                  <div key={label} className="between">
                    <span className="dim">{label}</span>
                    <span className="row" style={{ gap: 3 }}>
                      {keys.map((k,i) => <Kbd key={i}>{k}</Kbd>)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </DCArtboard>

          <DCArtboard id="state-machine" label="states" width={400} height={300}>
            <div className="wf" style={{ padding: 18 }}>
              <div className="h h2" style={{ marginBottom: 10 }}>Session states.</div>
              <div className="col" style={{ gap: 10, fontFamily: 'var(--hand)' }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="chip">idle</span>
                  <span className="dim">→</span>
                  <span className="chip warn">connecting</span>
                  <span className="dim">→</span>
                  <span className="chip ok">live</span>
                </div>
                <div className="row" style={{ gap: 8, marginLeft: 64 }}>
                  <span className="dim">↳</span>
                  <span className="chip">muted</span>
                  <span className="dim">⇄ live</span>
                </div>
                <div className="row" style={{ gap: 8, marginLeft: 64 }}>
                  <span className="dim">↳</span>
                  <span className="chip danger">stopping</span>
                  <span className="dim">→</span>
                  <span className="chip">post-session</span>
                </div>
                <div className="divider" />
                <span className="tiny dim">
                  Backend WS at <span className="mono">ws://127.0.0.1:7711</span> emits
                  events (transcript, audio_frame, ttfa, cost_tick).
                  UI never polls — drives off the event stream.
                </span>
              </div>
            </div>
          </DCArtboard>
        </DCSection>

        {/* ── VUE 1a · Welcome (popup inactif) ─────────────────── */}
        <DCSection id="welcome"
                   title="Vue 1a · Welcome popover (inactive)"
                   subtitle="popover 400×600 ancré sous l'icône menubar · état par défaut">
          <DCArtboard id="welcome-a" label="A · hero carousel" width={400} height={600}>
            <WelcomeA />
          </DCArtboard>
          <DCArtboard id="welcome-b" label="B · grid 2×3" width={400} height={600}>
            <WelcomeB />
          </DCArtboard>
          <DCArtboard id="welcome-c" label="C · list ⌘1–6  ★ kept" width={400} height={600}>
            <WelcomeC />
          </DCArtboard>
          <DCArtboard id="welcome-d" label="D · hero single" width={400} height={600}>
            <WelcomeD />
          </DCArtboard>

          <DCPostIt top={-110} left={1700} rotate={2} width={210}>
            <strong>★ retenu : C</strong> (list ⌘1–6)
            <br/>Le plus rapide pour le usage quotidien : 1 raccourci = 1 persona,
            pas de hover/scroll. Les autres restent en archive
            visuelle (carrousel / grid / hero).
          </DCPostIt>
        </DCSection>

        {/* ── VUE 1b · Active session (popup) ──────────────────── */}
        <DCSection id="active"
                   title="Vue 1b · Active session (popover)"
                   subtitle="même popover 400×600, état live · transcript + talk button">
          <DCArtboard id="active-a" label="A · 2-col split" width={400} height={600}>
            <ActiveA />
          </DCArtboard>
          <DCArtboard id="active-b" label="B · terminal stream" width={400} height={600}>
            <ActiveB />
          </DCArtboard>
          <DCArtboard id="active-c" label="C · bubbles + VU" width={400} height={600}>
            <ActiveC />
          </DCArtboard>
          <DCArtboard id="active-d" label="D · viz-first" width={400} height={600}>
            <ActiveD />
          </DCArtboard>
          <DCArtboard id="active-e" label="E · bubbles+radial+trio  ★ new" width={400} height={600}>
            <ActiveE />
          </DCArtboard>

          <DCPostIt top={-100} left={2150} rotate={-3} width={220}>
            <strong>★ nouvelle E</strong> : bubbles (C) + grand avatar
            + spectre radial (signature "vivante" de la session)
            + trio mute/stop/expand (D).
            <br/>Combine l'aspect lisible des bubbles avec
            le feedback visuel fort du radial.
          </DCPostIt>
        </DCSection>

        {/* ── VUE 2 · Split overlay sidebar ────────────────────── */}
        <DCSection id="overlay"
                   title="Vue 2 · Split-screen overlay (80/20)"
                   subtitle="sidebar verticale fixe 20% droite · ghostty à 80% gauche · session longue">
          <DCArtboard id="overlay-a" label="A · EQ bars (brief)" width={900} height={620}>
            <OverlayA />
          </DCArtboard>
          <DCArtboard id="overlay-b" label="B · waveform + skills" width={900} height={620}>
            <OverlayB />
          </DCArtboard>
          <DCArtboard id="overlay-c" label="C · radial spectrum  ★ kept" width={900} height={620}>
            <OverlayC />
          </DCArtboard>
          <DCArtboard id="overlay-d" label="D · ultra-compact" width={900} height={620}>
            <OverlayD />
          </DCArtboard>
          <DCArtboard id="overlay-e" label="E · radial + you-wave  ★ new" width={900} height={620}>
            <OverlayE />
          </DCArtboard>
          <DCArtboard id="overlay-f" label="F · side radial + you-wave/bars  ★ new" width={900} height={620}>
            <OverlayF />
          </DCArtboard>
          <DCArtboard id="overlay-g" label="G · radial halo + dual you-spectrum  ★ new" width={900} height={620}>
            <OverlayG />
          </DCArtboard>

          <DCPostIt top={-110} left={6500} rotate={1.5} width={250}>
            <strong>C, E, F, G</strong> partagent le spectre radial
            autour de l'avatar (model) + <strong>spectre horizontal "toi"</strong>
            séparé en bas.
            <br/>E garde C strict + adds wave.
            <br/>F = radial badge à droite, plus de place pour ta voix.
            <br/>G = radial halo + double-spectre (wave + EQ bars).
          </DCPostIt>
          <DCPostIt top={400} left={6500} rotate={-2} width={230}>
            <strong>Transparence :</strong> bg sidebar 92% opacity sur
            <span style={{fontFamily:'monospace'}}> NSVisualEffectView</span>.
            <br/><br/>
            <strong>Pulse avatar :</strong> scale(1.0 → 1.04) sur event
            <span style={{fontFamily:'monospace'}}> audio.model.frame</span>,
            180ms ease-out (jamais &gt; 200ms).
          </DCPostIt>
        </DCSection>

        {/* ── VUE 3 · Settings ────────────────────────────────── */}
        <DCSection id="settings"
                   title="Vue 3 · Settings panel — 3 layouts"
                   subtitle="modal 500×700 par-dessus le popover · 4 sections (keys / models / budget / personas)">
          <DCArtboard id="settings-vtabs" label="Layout 1 · vertical tabs" width={500} height={700}>
            <SettingsA />
          </DCArtboard>
          <DCArtboard id="settings-toptabs" label="Layout 2 · top tabs" width={500} height={700}>
            <SettingsD />
          </DCArtboard>
          <DCArtboard id="settings-inline" label="Layout 3 · inline (no tabs)" width={500} height={700}>
            <SettingsE />
          </DCArtboard>

          <DCPostIt top={-110} left={1700} rotate={-2.5} width={250}>
            <strong>3 layouts à départager.</strong>
            <br/><br/>
            <em>vtabs</em> = le plus "settings classique macOS",
            scannable, naturel pour 4 sections.
            <br/><br/>
            <em>top-tabs</em> = plus compact, comme une nav web.
            <br/><br/>
            <em>inline</em> = tout visible scrollable, pas de navigation.
            Bon pour 4 sections courtes.
          </DCPostIt>
        </DCSection>

        {/* ── VUE 3 · Settings · contenu par section (layout vtabs) ── */}
        <DCSection id="settings-content"
                   title="Vue 3 · Settings · tour des 4 sections"
                   subtitle="contenu détaillé · présenté ici en layout vtabs">
          <DCArtboard id="settings-keys" label="🔑 API keys" width={500} height={700}>
            <SettingsA />
          </DCArtboard>
          <DCArtboard id="settings-models" label="◇ Models" width={500} height={700}>
            <SettingsD />
          </DCArtboard>
          <DCArtboard id="settings-budget" label="$ Budget" width={500} height={700}>
            <SettingsB />
          </DCArtboard>
          <DCArtboard id="settings-personas" label="☺ Personas" width={500} height={700}>
            <SettingsC />
          </DCArtboard>
        </DCSection>

        {/* ── INTERACTIONS · flows ────────────────────────────── */}
        {/* ── VUE 3b · Persona editor ───────────────── */}
        <DCSection id="persona-editor"
                   title="Vue 3b · Persona editor"
                   subtitle="Settings → Personas → click row · profile / context / skills">
          <DCArtboard id="pe-a" label="A · single-scroll" width={520} height={900}>
            <PersonaEditorA />
          </DCArtboard>
          <DCArtboard id="pe-b" label="B · sub-tabs (3) · context  ★ kept" width={520} height={900}>
            <PersonaEditorB />
          </DCArtboard>
          <DCArtboard id="pe-c" label="C · collapsibles" width={520} height={900}>
            <PersonaEditorC />
          </DCArtboard>

          <DCPostIt top={-110} left={1700} rotate={-2.5} width={250}>
            <strong>★ nouveau</strong> — éditeur ouvert depuis Settings C.
            <br/>4 sections :
            <br/>• <em>identity</em> — nom, voix, avatar
            <br/>• <em>behavior</em> — toggle web search + 3 autres
            <br/>• <em>context window</em> — sliding (terminal pane + slider 500–32k) ou static (arbre vault)
            <br/>• <em>skills/commands</em> — built-in + commandes custom
          </DCPostIt>
          <DCPostIt top={400} left={1700} rotate={1.5} width={240}>
            <strong>Sliding + Static :</strong>
            <br/>Sliding = auto si lancé depuis terminal (ghostty/tmux/prism), pas de picker source.
            <br/>Static = pin vault, sauvegardé par persona.
            <br/>Les deux <em>cohabitent</em> dans le budget context %.
          </DCPostIt>
        </DCSection>

        {/* ── VUE 3b·B walkthrough — each sub-tab of the kept variant ─── */}
        <DCSection id="pe-b-walkthrough"
                   title="Vue 3b·B · sub-tab walkthrough"
                   subtitle="la variante retenue, onglet par onglet · profile → context → skills">
          <DCArtboard id="pe-b-profile" label="1 · profile (identity + behavior)" width={520} height={820}>
            <PersonaEditorB tab="profile" />
          </DCArtboard>
          <DCArtboard id="pe-b-context" label="2 · context (sliding + static)" width={520} height={900}>
            <PersonaEditorB tab="context" />
          </DCArtboard>
          <DCArtboard id="pe-b-skills" label="3 · skills + commands" width={520} height={820}>
            <PersonaEditorB tab="skills" />
          </DCArtboard>

          <DCPostIt top={-110} left={1700} rotate={2} width={250}>
            <strong>Flow type :</strong>
            <br/>1. profile (identité + web search + ask-before-acting)
            <br/>2. context (le plus dense — sliding & static cohabitent)
            <br/>3. skills (built-ins toggleables + commandes custom)
            <br/><br/>auto-save sur change, ⌘S pour forcer.
          </DCPostIt>
          <DCPostIt top={400} left={1700} rotate={-1.5} width={250}>
            <strong>Context budget :</strong>
            <br/>tout est exprimé en % du modèle (ici 500k pour gemini).
            <br/>Sliding (accent) + Static (orange) = 4.1% utilisé.
            <br/>Le reste reste libre pour la conversation elle-même.
          </DCPostIt>
        </DCSection>

        <DCSection id="flows"
                   title="Interactions · flows clés"
                   subtitle="micro-storyboards · les transitions principales">
          <DCArtboard id="flow-launch" label="flow · launch" width={1100} height={420}>
            <div className="wf" style={{ padding: 18, display:'flex', alignItems:'center', gap: 18 }}>
              {[
                { t:'idle', sub:'menubar icon · grey', body:<span className="av md dim">●</span> },
                { t:'click', sub:'icon → popover ouvre', body:<><span className="av md acc">●</span><span className="lbl">click</span></> },
                { t:'welcome', sub:'persona switcher', body:<div className="box" style={{ width:120, height:80 }}/> },
                { t:'start', sub:'⌘↵ ou ▶', body:<button className="talk sm">go</button> },
                { t:'connecting', sub:'~300ms', body:<span className="chip warn">connecting</span> },
                { t:'live', sub:'transcript flows', body:<span className="chip ok">● live</span> },
              ].map((s, i, arr) => (
                <React.Fragment key={s.t}>
                  <div className="col" style={{ alignItems:'center', gap:6, minWidth:110 }}>
                    {s.body}
                    <span className="h h3" style={{ fontSize:16 }}>{s.t}</span>
                    <span className="tiny dim" style={{ textAlign:'center' }}>{s.sub}</span>
                  </div>
                  {i < arr.length-1 && <span className="dim h h2">→</span>}
                </React.Fragment>
              ))}
            </div>
          </DCArtboard>

          <DCArtboard id="flow-expand" label="flow · expand to overlay" width={1100} height={420}>
            <div className="wf" style={{ padding: 18, display:'flex', alignItems:'center', gap: 14 }}>
              <div className="col" style={{ alignItems:'center', gap:6 }}>
                <div className="box" style={{ width:130, height:200, padding:8 }}>
                  <div className="lbl tiny">popover · live</div>
                  <div className="divider"/>
                  <div className="tx-line user"><span className="pfx">{'>'}</span>…</div>
                  <div className="tx-line model"><span className="pfx">{'<'}</span>…</div>
                </div>
                <span className="h h3" style={{ fontSize:16 }}>1. live popover</span>
              </div>

              <div className="col" style={{ alignItems:'center', gap: 6 }}>
                <span className="callout">
                  <span className="num">1</span>
                </span>
                <span className="dim h h2">→</span>
                <span className="tiny dim">click ⤡<br/>or ⌘⇧E</span>
              </div>

              <div className="col" style={{ alignItems:'center', gap:6 }}>
                <div className="row" style={{ width:380, height:200, border:'1.5px solid var(--line)', borderRadius:8, overflow:'hidden' }}>
                  <div style={{ flex:'0 0 70%', background:'var(--paper-hi)', padding:6 }}>
                    <span className="tiny mono mute">$ ghostty (untouched)</span>
                  </div>
                  <div style={{ flex:1, borderLeft:'1.5px solid var(--line)', padding:6 }}>
                    <span className="av md acc">K</span>
                    <div className="tiny dim" style={{ marginTop:4 }}>session<br/>moves here</div>
                  </div>
                </div>
                <span className="h h3" style={{ fontSize:16 }}>2. overlay docked right</span>
              </div>

              <div className="col" style={{ alignItems:'center', gap: 6 }}>
                <span className="callout">
                  <span className="num">2</span>
                </span>
                <span className="dim h h2">→</span>
                <span className="tiny dim">menubar icon<br/>turns hollow</span>
              </div>

              <div className="col" style={{ alignItems:'center', gap:6 }}>
                <div className="box" style={{ width:90, height:60, padding:6 }}>
                  <span className="tiny mute mono">menubar</span>
                  <div className="row" style={{ gap:4, marginTop:6 }}>
                    <span className="av sm dim">○</span>
                    <span className="tiny dim">in overlay</span>
                  </div>
                </div>
                <span className="h h3" style={{ fontSize:16 }}>3. icon state shifts</span>
              </div>
            </div>
          </DCArtboard>
        </DCSection>

        {/* ════════════════════════════════════════════════════ */}
        {/*               MID-FI PASS                            */}
        {/* ════════════════════════════════════════════════════ */}

        <DCSection id="midfi-main"
                   title="◆ MID-FI · main screens"
                   subtitle="SF Pro · JetBrains Mono · #4fc3f7 accent · warm dark · all 5 retained variants">
          <DCArtboard id="mf-welcome" label="1a · Welcome (list ⌘1-6)" width={400} height={600}>
            <MfWelcome />
          </DCArtboard>
          <DCArtboard id="mf-active" label="1b · Active session" width={400} height={600}>
            <MfActive />
          </DCArtboard>
          <DCArtboard id="mf-overlay" label="2 · Split overlay" width={900} height={620}>
            <MfOverlay />
          </DCArtboard>
        </DCSection>

        <DCSection id="midfi-settings"
                   title="◆ MID-FI · Settings (vertical tabs)"
                   subtitle="Layout 1 · les 4 sections du panneau">
          <DCArtboard id="mf-settings-keys"     label="🔑 API keys"  width={500} height={520}>
            <MfSettingsKeys />
          </DCArtboard>
          <DCArtboard id="mf-settings-models"   label="◇ Models"     width={500} height={520}>
            <MfSettingsModels />
          </DCArtboard>
          <DCArtboard id="mf-settings-budget"   label="$ Budget"     width={500} height={620}>
            <MfSettingsBudget />
          </DCArtboard>
          <DCArtboard id="mf-settings-personas" label="☺ Personas"   width={500} height={620}>
            <MfSettingsPersonas />
          </DCArtboard>
        </DCSection>

        <DCSection id="midfi-editor"
                   title="◆ MID-FI · Persona editor (3 sub-tabs)"
                   subtitle="Settings → Personas → row · profile / context / skills">
          <DCArtboard id="mf-pe-profile" label="1 · profile" width={520} height={720}>
            <MfPersonaEditor tab="profile" />
          </DCArtboard>
          <DCArtboard id="mf-pe-context" label="2 · context (sliding + static)" width={520} height={900}>
            <MfPersonaEditor tab="context" />
          </DCArtboard>
          <DCArtboard id="mf-pe-skills" label="3 · skills + commands" width={520} height={820}>
            <MfPersonaEditor tab="skills" />
          </DCArtboard>
        </DCSection>

        <DCSection id="midfi-states"
                   title="◆ Edge cases · 8 states à designer avant dev"
                   subtitle="absence de clé, perte réseau, budget, permissions, vault vide, unsaved, première utilisation, clé invalide">
          <DCArtboard id="st-onboard"     label="① first launch (no personas)" width={400} height={600}>
            <MfStateOnboarding />
          </DCArtboard>
          <DCArtboard id="st-no-key"      label="② no API key" width={400} height={600}>
            <MfStateNoKey />
          </DCArtboard>
          <DCArtboard id="st-key-bad"     label="③ key invalid (401)" width={500} height={620}>
            <MfStateKeyInvalid />
          </DCArtboard>
          <DCArtboard id="st-ws-down"     label="④ WS backend down" width={400} height={600}>
            <MfStateWsDown />
          </DCArtboard>
          <DCArtboard id="st-mic-denied"  label="⑤ mic permission denied" width={400} height={600}>
            <MfStateMicDenied />
          </DCArtboard>
          <DCArtboard id="st-budget"      label="⑥ budget cap hit" width={400} height={600}>
            <MfStateBudgetHit />
          </DCArtboard>
          <DCArtboard id="st-vault-empty" label="⑦ vault not linked" width={520} height={620}>
            <MfStateVaultEmpty />
          </DCArtboard>
          <DCArtboard id="st-unsaved"     label="⑧ unsaved changes" width={520} height={620}>
            <MfStateUnsaved />
          </DCArtboard>
        </DCSection>

        <DCSection id="midfi-anim"
                   title="◆ Animation specs · 5 animations clés"
                   subtitle="durée · easing · trigger · description par carte — base pour SwiftUI / Tauri">
          <DCArtboard id="an-pulse"    label="① avatar pulse"     width={520} height={600}>
            <MfaPulse />
          </DCArtboard>
          <DCArtboard id="an-talk"     label="② talk button"      width={520} height={600}>
            <MfaTalk />
          </DCArtboard>
          <DCArtboard id="an-popover"  label="③ popover spring"   width={520} height={600}>
            <MfaPopover />
          </DCArtboard>
          <DCArtboard id="an-vu"       label="④ VU bars"          width={520} height={600}>
            <MfaVU />
          </DCArtboard>
          <DCArtboard id="an-overlay"  label="⑤ overlay slide-in" width={520} height={600}>
            <MfaOverlay />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Look">
          <TweakRadio
            label="accent"
            value={t.accent}
            onChange={(v) => setT('accent', v)}
            options={[
              { value:'blue',   label:'blue' },
              { value:'orange', label:'orange' },
            ]}
          />
          <TweakRadio
            label="theme"
            value={t.theme}
            onChange={(v) => setT('theme', v)}
            options={[
              { value:'dark',  label:'dark' },
              { value:'light', label:'light' },
            ]}
          />
          <TweakRadio
            label="density"
            value={t.density}
            onChange={(v) => setT('density', v)}
            options={[
              { value:'comfy',   label:'comfy' },
              { value:'compact', label:'compact' },
            ]}
          />
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
