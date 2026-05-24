/* global React, MfAvatar, MfPERSONAS, MfKbd, MfSwitch, MfRowToggle */

// ════════════════════════════════════════════════════════════
// VUE 3 · Settings (Layout 1 — vertical tabs)
// ════════════════════════════════════════════════════════════

const MF_TABS = [
  { k: 'keys',     label: 'API keys', ico: '🔑' },
  { k: 'models',   label: 'Models',   ico: '◇'  },
  { k: 'budget',   label: 'Budget',   ico: '$'  },
  { k: 'personas', label: 'Personas', ico: '☺'  },
];

function MfTabs({ active }) {
  return (
    <div className="mf-tabs">
      <div className="mf-cap" style={{ padding: '4px 9px', textTransform: 'uppercase', fontSize: 10, color: 'var(--mf-mute)', letterSpacing: '0.05em' }}>
        Settings
      </div>
      {MF_TABS.map(t => (
        <div key={t.k} className={`mf-tab ${active === t.k ? 'active' : ''}`}>
          <span className="mf-tab-ico">{t.ico}</span>
          <span>{t.label}</span>
        </div>
      ))}
    </div>
  );
}

function MfSettingsShell({ active, title, sub, children }) {
  return (
    <div className="mf" style={{ display: 'flex', borderRadius: 12 }}>
      <MfTabs active={active} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div className="mf-between" style={{ padding: '12px 18px 10px', borderBottom: '1px solid var(--mf-border)' }}>
          <div className="mf-col" style={{ gap: 1 }}>
            <span className="mf-display" style={{ fontSize: 16 }}>{title}</span>
            {sub && <span className="mf-cap">{sub}</span>}
          </div>
          <button className="mf-icn sm" title="close (esc)">×</button>
        </div>
        <div style={{ padding: 18, overflow: 'auto', flex: 1 }}>{children}</div>
      </div>
    </div>
  );
}

// ── Tab content: API keys ──────────────────────────────────
function MfKeysContent() {
  const rows = [
    { label: 'OpenAI',           v: 'sk-•••••••••••••••••••••••••••f3a2', s: 'ok'     },
    { label: 'Gemini',           v: 'AIza•••••••••••••••••••••••aB',       s: 'warn'   },
    { label: 'Telegram (alerts)',v: '— — —',                                s: 'danger' },
  ];
  return (
    <div className="mf-col" style={{ gap: 16 }}>
      {rows.map(r => (
        <div key={r.label} className="mf-col" style={{ gap: 6 }}>
          <div className="mf-between">
            <span className="mf-title" style={{ fontSize: 13 }}>{r.label}</span>
            <span className={`mf-chip ${r.s}`}>
              {r.s === 'ok'     && '✓ valid'}
              {r.s === 'warn'   && '⚠ untested'}
              {r.s === 'danger' && '✗ missing'}
            </span>
          </div>
          <div className="mf-row" style={{ gap: 6 }}>
            <div className="mf-input mono" style={{ flex: 1 }}>{r.v}</div>
            <button className="mf-btn ghost">Test</button>
          </div>
        </div>
      ))}

      <div className="mf-banner info" style={{ marginTop: 4 }}>
        <span className="mf-banner-icn">ⓘ</span>
        <span>Keys are stored in the macOS keychain — never in the app's memory or on disk.</span>
      </div>
    </div>
  );
}

// ── Tab content: Models ────────────────────────────────────
function MfModelsContent() {
  const rows = [
    { id: 'gemini-2.5-flash-native-audio', price: '$0.09/h', tag: 'fast · cheap',    sel: true  },
    { id: 'gpt-realtime-2',                price: '$0.42/h', tag: 'best quality',                },
    { id: 'gpt-realtime-mini',             price: '$0.18/h', tag: 'balanced',                    },
    { id: 'gpt-realtime-translate',        price: '$0.24/h', tag: 'translation',                 },
  ];
  return (
    <div className="mf-col" style={{ gap: 12 }}>
      <span className="mf-cap">Default model for new sessions · personas may override.</span>
      <div className="mf-col" style={{ gap: 6 }}>
        {rows.map(r => (
          <div key={r.id} className={`mf-card ${r.sel ? 'selected' : 'hover'}`}
               style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px' }}>
            <span style={{
              width: 16, height: 16, borderRadius: 50,
              border: `2px solid ${r.sel ? 'var(--mf-acc)' : 'var(--mf-stroke)'}`,
              background: r.sel ? 'var(--mf-acc)' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              {r.sel && <span style={{ width: 6, height: 6, borderRadius: 50, background: '#04131c' }} />}
            </span>
            <div className="mf-col" style={{ gap: 1, flex: 1, minWidth: 0 }}>
              <span className="mf-mono-12" style={{ color: 'var(--mf-fg)' }}>{r.id}</span>
              <span className="mf-cap">{r.tag}</span>
            </div>
            <span className={`mf-chip ${r.sel ? 'acc' : ''}`}>{r.price}</span>
          </div>
        ))}
      </div>

      <div className="mf-divider" style={{ marginTop: 4 }} />

      <span className="mf-label">Audio</span>
      <div className="mf-row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <span className="mf-chip acc">opus · 24 kHz</span>
        <span className="mf-chip outline">pcm16 fallback</span>
        <span className="mf-chip outline">echo cancel ✓</span>
      </div>
    </div>
  );
}

// ── Tab content: Budget ────────────────────────────────────
function MfBudgetContent() {
  return (
    <div className="mf-col" style={{ gap: 16 }}>
      <div className="mf-col" style={{ gap: 6 }}>
        <div className="mf-between">
          <span className="mf-title" style={{ fontSize: 13 }}>Monthly cap</span>
          <span className="mf-mono-12 mf-acc">$30</span>
        </div>
        <div className="mf-slider">
          <div className="track">
            <div className="fill" style={{ width: '55%' }} />
            <div className="knob" style={{ left: '55%' }} />
          </div>
        </div>
        <div className="mf-between mf-cap mf-mono">
          <span>$5</span><span>$50</span>
        </div>
      </div>

      <div className="mf-divider" />

      <div className="mf-col" style={{ gap: 6 }}>
        <div className="mf-between">
          <span className="mf-title" style={{ fontSize: 13 }}>This month · March</span>
          <span className="mf-mono-12">$20.40 / $30</span>
        </div>
        <div className="mf-bar warn"><i style={{ width: '68%' }} /></div>
        <span className="mf-cap">9 sessions · avg $2.27 · 12d left</span>
      </div>

      <div className="mf-divider" />

      <MfRowToggle
        label="Alert me at 80%"
        sub="single telegram ping to @vsrt_bot"
        on
      />

      <div className="mf-divider" />

      <div className="mf-col" style={{ gap: 8 }}>
        <span className="mf-label">By persona · this month</span>
        {[
          ['koda',  '$8.20', 0.74, 'koda'],
          ['aria',  '$5.10', 0.45, 'aria'],
          ['mira',  '$3.80', 0.33, 'mira'],
          ['noor',  '$2.10', 0.20, 'noor'],
          ['zen',   '$1.20', 0.10, 'zen'],
        ].map(([n, c, w, pid]) => (
          <div key={n} className="mf-row" style={{ gap: 9 }}>
            <MfAvatar persona={pid} size="sm" />
            <span style={{ width: 52, fontSize: 12.5 }}>{n}</span>
            <div className="mf-bar" style={{ flex: 1 }}>
              <i style={{ width: `${w*100}%`, background: `var(--pa-${pid})` }} />
            </div>
            <span className="mf-mono" style={{ width: 50, textAlign: 'right' }}>{c}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tab content: Personas ──────────────────────────────────
function MfPersonasContent() {
  return (
    <div className="mf-col" style={{ gap: 10 }}>
      <div className="mf-between">
        <span className="mf-cap">Drag to reorder · click row to edit</span>
        <button className="mf-btn">+ New persona</button>
      </div>

      <div className="mf-col" style={{ gap: 5 }}>
        {MfPERSONAS.map((p, i) => (
          <div key={p.id} className={`mf-card hover ${i === 1 ? 'selected' : ''}`}
               style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px' }}>
            <span className="mf-dim" style={{ width: 10, cursor: 'grab', userSelect: 'none' }}>⋮⋮</span>
            <MfAvatar persona={p.id} size="md" />
            <div className="mf-col" style={{ gap: 0, flex: 1, minWidth: 0 }}>
              <span className="mf-title" style={{ fontSize: 13.5 }}>{p.name}</span>
              <span className="mf-cap" style={{
                overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
              }}>{p.role} · voice: {p.voice}</span>
            </div>
            <div className="mf-row" style={{ gap: 1 }}>
              <button className="mf-icn sm">✎</button>
              <button className="mf-icn sm">⎘</button>
              <button className="mf-icn sm" style={{ color: 'var(--mf-danger)' }}>×</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Settings variant wrappers ─────────────────────────
function MfSettingsKeys() {
  return <MfSettingsShell active="keys" title="API keys" sub="stored in macOS keychain"><MfKeysContent /></MfSettingsShell>;
}
function MfSettingsModels() {
  return <MfSettingsShell active="models" title="Models" sub="default for new sessions"><MfModelsContent /></MfSettingsShell>;
}
function MfSettingsBudget() {
  return <MfSettingsShell active="budget" title="Budget" sub="monthly cap · alerts"><MfBudgetContent /></MfSettingsShell>;
}
function MfSettingsPersonas() {
  return <MfSettingsShell active="personas" title="Personas" sub="6 active · edit, duplicate, reorder"><MfPersonasContent /></MfSettingsShell>;
}

// ════════════════════════════════════════════════════════════
// VUE 3b · Persona editor (Layout B — 3 sub-tabs)
// ════════════════════════════════════════════════════════════

function MfProfileBlock() {
  return (
    <div className="mf-col" style={{ gap: 18 }}>
      <div className="mf-col" style={{ gap: 10 }}>
        <span className="mf-label">Identity</span>
        <div className="mf-row" style={{ gap: 14, alignItems: 'flex-start' }}>
          <div className="mf-col" style={{ alignItems: 'center', gap: 6 }}>
            <MfAvatar persona="koda" size="xl" />
            <button className="mf-btn ghost" style={{ height: 24, padding: '0 8px', fontSize: 11 }}>change…</button>
          </div>
          <div className="mf-col" style={{ flex: 1, gap: 8 }}>
            <div className="mf-col" style={{ gap: 3 }}>
              <span className="mf-cap">Name</span>
              <div className="mf-input">Koda</div>
            </div>
            <div className="mf-col" style={{ gap: 3 }}>
              <span className="mf-cap">Role · one line</span>
              <div className="mf-input">code coach — pair on architecture &amp; reviews</div>
            </div>
            <div className="mf-col" style={{ gap: 3 }}>
              <span className="mf-cap">Voice</span>
              <div className="mf-row" style={{ gap: 5, flexWrap: 'wrap' }}>
                <span className="mf-chip acc">alloy</span>
                <span className="mf-chip outline">echo</span>
                <span className="mf-chip outline">sage</span>
                <span className="mf-chip outline">verse</span>
                <span className="mf-chip outline">+ 4</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mf-divider" />

      <div className="mf-col" style={{ gap: 4 }}>
        <span className="mf-label">Behavior</span>

        <MfRowToggle
          label="Web search"
          sub="let koda call web.fetch / web.search"
          on
        />
        <div className="mf-row" style={{ marginLeft: 0, gap: 6, alignItems: 'center', flexWrap: 'wrap', paddingLeft: 0 }}>
          <span className="mf-cap">Restrict to</span>
          <span className="mf-chip acc">arxiv.org</span>
          <span className="mf-chip acc">docs.* +12</span>
          <span className="mf-chip outline">+ domain</span>
        </div>

        <div className="mf-divider" style={{ margin: '8px 0' }} />

        <MfRowToggle
          label="Ask before acting"
          sub="confirm on file write · send · book"
          on
        />
      </div>
    </div>
  );
}

function MfContextBlock() {
  const MODEL = 'gemini-2.5-flash-native-audio';
  const MODEL_TOK = 500_000;
  const SLIDE = 8_000;
  const STAT = 12_400;
  const slidePct  = (SLIDE / MODEL_TOK) * 100;
  const staticPct = (STAT  / MODEL_TOK) * 100;
  const totalPct  = slidePct + staticPct;

  return (
    <div className="mf-col" style={{ gap: 14 }}>
      {/* Budget header */}
      <div className="mf-card" style={{ background: 'var(--mf-bg)' }}>
        <div className="mf-between">
          <span className="mf-title">Context budget</span>
          <span className="mf-mono-12 mf-acc">{totalPct.toFixed(1)}% used</span>
        </div>
        <span className="mf-cap mf-mono" style={{ display:'block', marginTop: 2 }}>{MODEL} · 500k tokens</span>
        <div className="mf-bar stacked" style={{ marginTop: 9 }}>
          <i style={{ width: `${slidePct}%`, background: 'var(--mf-acc)' }} />
          <i style={{ left: `${slidePct}%`, width: `${staticPct}%`, background: 'var(--mf-warn)' }} />
        </div>
        <div className="mf-row" style={{ gap: 14, marginTop: 6, fontSize: 11 }}>
          <span><span className="mf-acc" style={{ marginRight: 3 }}>▮</span><span className="mf-dim">sliding · </span>8k <span className="mf-mute">({slidePct.toFixed(1)}%)</span></span>
          <span><span className="mf-warn" style={{ marginRight: 3 }}>▮</span><span className="mf-dim">static · </span>12.4k <span className="mf-mute">({staticPct.toFixed(1)}%)</span></span>
          <span className="mf-mute" style={{ marginLeft: 'auto' }}>free · {((MODEL_TOK - SLIDE - STAT)/1000).toFixed(0)}k</span>
        </div>
      </div>

      {/* Sliding section */}
      <div className="mf-card">
        <div className="mf-between">
          <div className="mf-row" style={{ gap: 8 }}>
            <span className="mf-title mf-acc">Sliding · terminal tail</span>
          </div>
          <span className="mf-chip live ok">auto · live</span>
        </div>
        <span className="mf-cap" style={{ display: 'block', marginTop: 4 }}>
          Launched from <span className="mf-mono">ghostty / tmux / prism / iterm</span> → tails the parent pane. No source picker.
        </span>

        <div className="mf-divider" style={{ margin: '10px 0' }} />

        <div className="mf-col" style={{ gap: 4 }}>
          <div className="mf-between">
            <span className="mf-cap">Window size</span>
            <span className="mf-mono-12 mf-acc">8k tokens · ~150 lines · 1.6%</span>
          </div>
          <div className="mf-slider">
            <div className="track">
              <div className="fill" style={{ width: '25%' }} />
              <div className="knob" style={{ left: '25%' }} />
            </div>
          </div>
          <div className="mf-between mf-cap mf-mono">
            <span>500</span><span>32k</span>
          </div>
        </div>
      </div>

      {/* Static section */}
      <div className="mf-card">
        <div className="mf-between">
          <span className="mf-title mf-warn">Static · vault pin</span>
          <span className="mf-mono mf-dim">12.4k · 2.5% · persisted</span>
        </div>
        <span className="mf-cap" style={{ display: 'block', marginTop: 4 }}>
          Selection saved per persona, survives across sessions.
        </span>

        <div className="mf-divider" style={{ margin: '10px 0' }} />

        <div className="mf-input" style={{ height: 28, marginBottom: 8 }}>
          <span style={{ color: 'var(--mf-mute)' }}>🔍</span>
          <span style={{ marginLeft: 6, color: 'var(--mf-mute)' }}>Filter vault…</span>
        </div>

        <div className="mf-col" style={{ gap: 1, fontFamily: 'var(--mf-mono)', fontSize: 11.5 }}>
          {[
            { name:'projects/',         d:0, c:'partial', ico:'📁' },
            { name:'voice-rt/',         d:1, c:'partial', ico:'📁' },
            { name:'spec.md',           d:2, c:'on'                },
            { name:'architecture.md',   d:2, c:'on'                },
            { name:'scratch.md',        d:2, c:'off'               },
            { name:'web-svc/',          d:1, c:'off',    ico:'📁' },
            { name:'daily/',            d:0, c:'off',    ico:'📁' },
            { name:'refs/',             d:0, c:'partial',ico:'📁' },
            { name:'ws-protocol.md',    d:1, c:'on'                },
            { name:'tokens.md',         d:1, c:'on'                },
          ].map((r, i) => (
            <div key={i} className="mf-row" style={{
              gap: 7, padding: '3px 4px', paddingLeft: 4 + r.d * 14,
              borderRadius: 4,
            }}>
              <span style={{
                width: 12, height: 12, borderRadius: 3,
                border: `1.5px solid ${
                  r.c === 'on'      ? 'var(--mf-acc)' :
                  r.c === 'partial' ? 'var(--mf-warn)' :
                                      'var(--mf-stroke)'
                }`,
                background:
                  r.c === 'on'      ? 'var(--mf-acc)' :
                  r.c === 'partial' ? 'rgba(255,183,77,0.3)' :
                                      'transparent',
                display: 'inline-flex', alignItems:'center', justifyContent:'center',
                flexShrink: 0,
              }}>
                {r.c === 'on' && <span style={{ color:'#04131c', fontSize: 9, fontWeight:'bold' }}>✓</span>}
                {r.c === 'partial' && <span style={{ width: 5, height: 1.5, background: 'var(--mf-warn)' }} />}
              </span>
              {r.ico && <span style={{ fontSize: 11 }}>{r.ico}</span>}
              <span style={{
                color: r.c === 'on' ? 'var(--mf-fg)' :
                       r.c === 'partial' ? 'var(--mf-warn)' :
                                           'var(--mf-mute)',
              }}>{r.name}</span>
            </div>
          ))}
          <div className="mf-cap" style={{ paddingLeft: 4, marginTop: 4 }}>… 4 more · 18 total in vault</div>
        </div>

        <div className="mf-divider" style={{ margin: '10px 0' }} />

        <MfRowToggle
          label="Auto-include linked notes"
          sub="follow [[wikilinks]] 1 level deep"
          on
        />
      </div>
    </div>
  );
}

function MfSkillsBlock() {
  const skills = [
    { id:'vault.search',   on: true,  desc:'search the obsidian vault' },
    { id:'vault.write',    on: true,  desc:'append / create notes' },
    { id:'repo.search',    on: true,  desc:'grep across selected repos' },
    { id:'web.search',     on: true,  desc:'duckduckgo · arxiv · docs' },
    { id:'calendar.*',     on: false, desc:'read / schedule events' },
    { id:'inbox.*',        on: false, desc:'gmail · read / draft' },
  ];
  const commands = [
    { name:'/review',  trigger:'review the last commit',  action:'repo.diff → critique' },
    { name:'/notes',   trigger:'capture this',            action:'vault.write(daily/today)' },
  ];

  return (
    <div className="mf-col" style={{ gap: 16 }}>
      <div className="mf-col" style={{ gap: 8 }}>
        <div className="mf-between">
          <span className="mf-label">Skills (built-in)</span>
          <span className="mf-cap">{skills.filter(s=>s.on).length} of {skills.length} on</span>
        </div>
        <div className="mf-col" style={{ gap: 4 }}>
          {skills.map(s => (
            <div key={s.id} className="mf-card hover"
                 style={{ padding: '7px 11px', display: 'flex', alignItems: 'center', gap: 10,
                          background: s.on ? 'var(--mf-panel-2)' : 'var(--mf-bg)',
                          borderColor: s.on ? 'var(--mf-border-2)' : 'var(--mf-border)' }}>
              <div className="mf-col" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                <span className="mf-mono-12" style={{ color: s.on ? 'var(--mf-acc)' : 'var(--mf-mute)' }}>{s.id}</span>
                <span className="mf-cap" style={{ marginTop: 1 }}>{s.desc}</span>
              </div>
              <MfSwitch on={s.on} />
            </div>
          ))}
        </div>
      </div>

      <div className="mf-divider" />

      <div className="mf-col" style={{ gap: 8 }}>
        <div className="mf-between">
          <span className="mf-label">Custom commands</span>
          <button className="mf-btn ghost" style={{ height: 24, padding: '0 9px', fontSize: 11 }}>+ new</button>
        </div>
        <span className="mf-cap" style={{ marginTop: -4 }}>Custom phrases → tool chain.</span>
        <div className="mf-col" style={{ gap: 5 }}>
          {commands.map(c => (
            <div key={c.name} className="mf-card" style={{ padding: '8px 11px' }}>
              <div className="mf-between">
                <span className="mf-mono-12 mf-acc">{c.name}</span>
                <div className="mf-row" style={{ gap: 1 }}>
                  <button className="mf-icn sm">✎</button>
                  <button className="mf-icn sm" style={{ color: 'var(--mf-danger)' }}>×</button>
                </div>
              </div>
              <div className="mf-col" style={{ gap: 1, marginTop: 3 }}>
                <span className="mf-cap">when: <span className="mf-mono">"{c.trigger}"</span></span>
                <span className="mf-cap">do: <span className="mf-mono">{c.action}</span></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MfPersonaEditor({ tab = 'context' }) {
  return (
    <div className="mf" style={{ display:'flex', flexDirection:'column' }}>
      {/* header */}
      <div className="mf-between" style={{ padding: '12px 16px 10px', borderBottom: '1px solid var(--mf-border)' }}>
        <div className="mf-row" style={{ gap: 9 }}>
          <button className="mf-icn sm" title="back">‹</button>
          <MfAvatar persona="koda" size="md" />
          <span className="mf-display" style={{ fontSize: 16 }}>Koda</span>
        </div>
        <div className="mf-row" style={{ gap: 6 }}>
          <button className="mf-btn ghost">Cancel</button>
          <button className="mf-btn primary">Save</button>
        </div>
      </div>

      {/* sub-tabs */}
      <div style={{ padding: '10px 16px 4px' }}>
        <div className="mf-subtabs">
          <div className={`mf-subtab ${tab==='profile'?'active':''}`}>Profile</div>
          <div className={`mf-subtab ${tab==='context'?'active':''}`}>Context</div>
          <div className={`mf-subtab ${tab==='skills' ?'active':''}`}>Skills</div>
        </div>
      </div>

      {/* content */}
      <div style={{ padding: '14px 16px 16px', overflow: 'auto', flex: 1 }}>
        {tab === 'profile' && <MfProfileBlock />}
        {tab === 'context' && <MfContextBlock />}
        {tab === 'skills'  && <MfSkillsBlock />}
      </div>
    </div>
  );
}

Object.assign(window, {
  MfSettingsKeys, MfSettingsModels, MfSettingsBudget, MfSettingsPersonas,
  MfPersonaEditor,
});
