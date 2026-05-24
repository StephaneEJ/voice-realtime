/* global React, PERSONAS, Kbd */
// Vue 3 — Settings (modal au-dessus popup, ~500x700)
// 3 variantes : Vertical tabs (brief default), Top tabs, Inline sections

function TabRow({ tabs, active }) {
  return (
    <div className="col" style={{ gap: 4, width: 130, flex:'0 0 auto' }}>
      {tabs.map((t) => (
        <div key={t.k} className={`tab ${active === t.k ? 'active' : ''}`}>
          <span style={{ marginRight: 6 }}>{t.ico}</span>{t.label}
        </div>
      ))}
    </div>
  );
}

const TABS = [
  { k:'keys',     ico:'🔑', label:'API keys' },
  { k:'models',   ico:'◇',  label:'Models' },
  { k:'budget',   ico:'$',  label:'Budget' },
  { k:'personas', ico:'☺',  label:'Personas' },
];

// Reusable panel bodies, parameterized by tab
function KeysBody() {
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="h h2">API keys</div>
      <span className="lbl dim">stored in macOS keychain · never logged</span>

      {[
        { label: 'OpenAI', status: 'ok',   text: '✓ valid · sk-…f3a2', mono:'sk-•••••••••••••••••••••••••••f3a2' },
        { label: 'Gemini', status: 'warn', text: '⚠ untested',           mono:'AIza•••••••••••••••••••••••aB' },
        { label: 'Telegram (alerts)', status: 'danger', text: '✗ missing', mono: '— — —' },
      ].map((row) => (
        <div key={row.label} className="col" style={{ gap: 6 }}>
          <div className="between">
            <span className="lbl">{row.label}</span>
            <span className={`chip ${row.status}`}>{row.text}</span>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <div className="box" style={{ flex:1, padding:'7px 9px', fontFamily:'var(--mono)', fontSize:11 }}>
              {row.mono}
            </div>
            <button className="btn ghost">test</button>
          </div>
        </div>
      ))}

      <div className="divider" />
      <div className="callout">
        <span className="num">i</span>
        keys round-trip to backend on ws connect — never persisted in JS heap.
      </div>
    </div>
  );
}

function ModelsBody() {
  const rows = [
    { id: 'gemini-2.5-flash-native-audio', price:'$0.09/h', tag:'fast · cheap', sel:true  },
    { id: 'gpt-realtime-2',                price:'$0.42/h', tag:'best quality' },
    { id: 'gpt-realtime-mini',             price:'$0.18/h', tag:'balanced' },
    { id: 'gpt-realtime-translate',        price:'$0.24/h', tag:'i18n' },
  ];
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="h h2">Models</div>
      <span className="lbl dim">default for new sessions · per-persona override available</span>

      <div className="col" style={{ gap: 6 }}>
        {rows.map((r) => (
          <div key={r.id} className={`box ${r.sel?'acc':''}`}
               style={{ padding:'9px 12px', display:'flex', alignItems:'center', gap: 10 }}>
            <span className="icn sm" style={{
              borderColor: r.sel ? 'var(--accent)':'var(--line-dim)',
              background: r.sel ? 'var(--accent)' : 'transparent',
            }}>{r.sel ? '●' : ''}</span>
            <div className="col" style={{ gap: 1, flex:1 }}>
              <span className="mono" style={{ fontSize:12 }}>{r.id}</span>
              <span className="tiny dim">{r.tag}</span>
            </div>
            <span className="chip">{r.price}</span>
          </div>
        ))}
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 4 }}>
        <span className="lbl">audio</span>
        <div className="row" style={{ gap: 6 }}>
          <span className="chip acc">opus · 24kHz</span>
          <span className="chip">pcm16</span>
          <span className="chip">echo cancel ✓</span>
        </div>
      </div>
    </div>
  );
}

function BudgetBody() {
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="h h2">Budget</div>

      <div className="col" style={{ gap: 4 }}>
        <div className="between">
          <span className="lbl">monthly cap</span>
          <span className="mono acc">$30</span>
        </div>
        <div className="slider">
          <div className="track" />
          <div className="knob" style={{ left: 'calc(55% - 7px)' }} />
        </div>
        <div className="between tiny mono dim">
          <span>$5</span><span>$50</span>
        </div>
      </div>

      <div className="col" style={{ gap: 5 }}>
        <div className="between">
          <span className="lbl">this month · march</span>
          <span className="mono">$20.40 / $30</span>
        </div>
        <div className="bar"><i style={{ width:'68%' }} /></div>
        <span className="tiny dim">~9 sessions · avg $2.27 / session</span>
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 6 }}>
        <div className="between">
          <span className="lbl">alert at 80%</span>
          <div className="row" style={{ gap: 6 }}>
            <span className="chip acc">telegram</span>
            <div className="row" style={{ gap: 4 }}>
              <span className="tiny dim">on</span>
              <div style={{
                width: 28, height: 16, borderRadius: 999,
                border:'1.5px solid var(--accent)',
                background:'var(--accent-soft)', position:'relative',
              }}>
                <i style={{ position:'absolute', right:1, top:1, width:12, height:12,
                            borderRadius:'50%', background:'var(--accent)' }} />
              </div>
            </div>
          </div>
        </div>
        <span className="tiny dim">→ sends a single ping to <span className="mono">@vsrt_bot</span></span>
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 4 }}>
        <span className="lbl">cost by persona · this month</span>
        {[
          ['koda',  '$8.20', 0.74],
          ['aria',  '$5.10', 0.45],
          ['mira',  '$3.80', 0.33],
          ['noor',  '$2.10', 0.20],
          ['zen',   '$1.20', 0.10],
        ].map(([n, c, w]) => (
          <div key={n} className="row" style={{ gap: 8, fontSize:13 }}>
            <span className="dim" style={{ width: 46 }}>{n}</span>
            <div className="bar" style={{ flex:1 }}><i style={{ width:`${w*100}%`}}/></div>
            <span className="mono tiny" style={{ width:50, textAlign:'right' }}>{c}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PersonasBody() {
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="between">
        <div className="h h2">Personas</div>
        <button className="btn">+ new</button>
      </div>

      <span className="lbl dim">click row to edit · drag to reorder</span>

      <div className="col" style={{ gap: 6 }}>
        {PERSONAS.map((p, i) => (
          <div key={p.id} className="row"
               style={{ gap: 10, padding:'8px 10px',
                        border:'1.5px solid', borderColor: i===0?'var(--accent)':'var(--line-dim)',
                        borderRadius: 10, alignItems:'center' }}>
            <span className="mono mute" style={{ width: 8 }}>≡</span>
            <span className={`av md ${i===0?'acc':''}`}>{p.mono}</span>
            <div className="col" style={{ gap: 0, flex:1 }}>
              <span style={{ fontSize:15 }}>{p.name}</span>
              <span className="tiny dim">{p.role} · {p.tag}</span>
            </div>
            <div className="row" style={{ gap: 4 }}>
              <span className="icn sm dim" title="edit">✎</span>
              <span className="icn sm dim" title="duplicate">⎘</span>
              <span className="icn sm dim" title="delete">×</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Settings frame variants

function SettingsA() { // Vertical tabs (brief default), keys view shown
  return (
    <div className="wf" style={{ padding: 16 }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="h h2">Settings</div>
        <div className="row" style={{ gap: 6 }}>
          <Kbd>⌘</Kbd><Kbd>,</Kbd>
          <span className="icn sm dim" style={{ marginLeft: 6 }}>×</span>
        </div>
      </div>

      <div className="row" style={{ gap: 14, alignItems:'stretch' }}>
        <TabRow tabs={TABS} active="keys" />
        <div style={{ width: 1, background:'var(--line-dim)', opacity:0.4 }} />
        <div style={{ flex:1 }}>
          <KeysBody />
        </div>
      </div>
    </div>
  );
}

function SettingsB() { // Vertical tabs — budget view
  return (
    <div className="wf" style={{ padding: 16 }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="h h2">Settings</div>
        <span className="icn sm dim">×</span>
      </div>
      <div className="row" style={{ gap: 14, alignItems:'stretch' }}>
        <TabRow tabs={TABS} active="budget" />
        <div style={{ width: 1, background:'var(--line-dim)', opacity:0.4 }} />
        <div style={{ flex:1 }}>
          <BudgetBody />
        </div>
      </div>
    </div>
  );
}

function SettingsC() { // Vertical tabs — personas view
  return (
    <div className="wf" style={{ padding: 16 }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="h h2">Settings</div>
        <span className="icn sm dim">×</span>
      </div>
      <div className="row" style={{ gap: 14, alignItems:'stretch' }}>
        <TabRow tabs={TABS} active="personas" />
        <div style={{ width: 1, background:'var(--line-dim)', opacity:0.4 }} />
        <div style={{ flex:1 }}>
          <PersonasBody />
        </div>
      </div>
    </div>
  );
}

function SettingsD() { // Variant: top-tabs (horizontal) + models view
  return (
    <div className="wf" style={{ padding: 16 }}>
      <div className="between" style={{ marginBottom: 10 }}>
        <div className="h h2">Settings</div>
        <span className="icn sm dim">×</span>
      </div>

      <div className="row" style={{ gap: 6, borderBottom:'1.5px solid var(--line-dim)', paddingBottom: 6 }}>
        {TABS.map((t) => (
          <div key={t.k} className={`tab ${t.k==='models'?'active':''}`}>
            <span style={{ marginRight:6 }}>{t.ico}</span>{t.label}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 14 }}>
        <ModelsBody />
      </div>
    </div>
  );
}

function SettingsE() { // Variant: inline collapsible sections (no tabs)
  return (
    <div className="wf" style={{ padding: 16, overflow:'auto' }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="h h2">Settings</div>
        <span className="icn sm dim">×</span>
      </div>

      {/* collapsed sections list */}
      <div className="col" style={{ gap: 10 }}>
        {/* keys open */}
        <div className="box fill" style={{ padding:'10px 12px' }}>
          <div className="between" style={{ marginBottom: 8 }}>
            <span className="h h3">🔑 API keys</span>
            <span className="dim">▾</span>
          </div>
          <div className="col" style={{ gap: 6 }}>
            <div className="between"><span className="lbl">OpenAI</span><span className="chip ok">✓</span></div>
            <div className="box" style={{ padding:'5px 8px', fontFamily:'var(--mono)', fontSize:10 }}>
              sk-•••••••••••••••••••••••••••f3a2
            </div>
            <div className="between"><span className="lbl">Gemini</span><span className="chip warn">⚠</span></div>
            <div className="box" style={{ padding:'5px 8px', fontFamily:'var(--mono)', fontSize:10 }}>
              AIza•••••••••••••••••••••••aB
            </div>
          </div>
        </div>

        {[
          ['◇ Models', 'gemini-2.5-flash-native-audio · $0.09/h'],
          ['$ Budget', '$20.40 / $30 · alert 80% on'],
          ['☺ Personas', '6 active · koda is default'],
        ].map(([t, sub]) => (
          <div key={t} className="box" style={{ padding:'10px 12px' }}>
            <div className="between">
              <div className="col" style={{ gap: 2 }}>
                <span className="h h3">{t}</span>
                <span className="tiny dim">{sub}</span>
              </div>
              <span className="dim">▸</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { SettingsA, SettingsB, SettingsC, SettingsD, SettingsE });
