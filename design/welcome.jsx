/* global React, PERSONAS, Menubar, Kbd */
// Vue 1a — Welcome (popup inactif, ~400x600)
// 4 variantes : Hero carousel, Grid, List, Hero-single

function WelcomeA() { // Hero carousel — persona center stage + dots
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret center" />

      <div className="between" style={{ marginBottom: 10 }}>
        <span className="lbl">voice · idle</span>
        <span className="icn sm dim">⚙</span>
      </div>

      <div className="col" style={{ alignItems: 'center', gap: 14, marginTop: 18 }}>
        <span className="lbl dim">choose a persona</span>
        <div className="row" style={{ gap: 24 }}>
          <span className="av md dim">A</span>
          <span className="av xxl acc tilt-1">K</span>
          <span className="av md dim">M</span>
        </div>
        <div className="h h1 tilt-2">Koda</div>
        <span className="lbl">code coach</span>
        <div className="row" style={{ gap: 6 }}>
          <span className="chip">repos</span>
          <span className="chip">docs</span>
          <span className="chip">stack</span>
        </div>

        <div className="row" style={{ gap: 5, marginTop: 4 }}>
          <i style={{ width:6, height:6, borderRadius:'50%', background:'var(--fg-mute)'}} />
          <i style={{ width:8, height:8, borderRadius:'50%', background:'var(--accent)'}} />
          <i style={{ width:6, height:6, borderRadius:'50%', background:'var(--fg-mute)'}} />
          <i style={{ width:6, height:6, borderRadius:'50%', background:'var(--fg-mute)'}} />
          <i style={{ width:6, height:6, borderRadius:'50%', background:'var(--fg-mute)'}} />
          <i style={{ width:6, height:6, borderRadius:'50%', background:'var(--fg-mute)'}} />
        </div>

        <button className="btn primary huge tilt-1" style={{ marginTop: 14 }}>
          ▶ start with Koda
        </button>

        <div className="row tiny dim" style={{ gap: 10, marginTop: 6 }}>
          <span>swipe ←→</span>
          <span>·</span>
          <Kbd>⌘</Kbd><Kbd>P</Kbd>
          <span>switch</span>
        </div>
      </div>

      <div className="between tiny mute" style={{ position:'absolute', bottom:10, left:14, right:14 }}>
        <span className="mono">budget · $12 / $30</span>
        <span className="mono">v0.4 · local :7711</span>
      </div>
    </div>
  );
}

function WelcomeB() { // Grid — 2x3 tappable, then start CTA
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret center" />

      <div className="between" style={{ marginBottom: 12 }}>
        <div className="row" style={{ gap:7 }}>
          <span className="av sm">A</span>
          <span className="lbl">aria  ▾</span>
        </div>
        <span className="icn sm dim">⚙</span>
      </div>

      <div className="h h2" style={{ marginBottom: 4 }}>Hey — pick someone.</div>
      <span className="lbl dim">6 personas · tap to select</span>

      <div style={{
        display:'grid', gridTemplateColumns:'1fr 1fr 1fr',
        gap: 10, marginTop: 12,
      }}>
        {PERSONAS.map((p, i) => (
          <div key={p.id} className={`box ${i===0?'acc':''}`}
               style={{ display:'flex', flexDirection:'column', alignItems:'center', padding:'10px 4px', gap:4 }}>
            <span className={`av md ${i===0?'acc':''}`}>{p.mono}</span>
            <span className="h h3" style={{ fontSize:16 }}>{p.name}</span>
            <span className="tiny dim" style={{ textAlign:'center' }}>{p.role}</span>
          </div>
        ))}
      </div>

      <div className="divider" style={{ marginTop: 14 }} />

      <div className="col" style={{ gap: 4, marginTop: 4 }}>
        <span className="lbl">aria · daily ops</span>
        <span className="tiny dim">inbox · calendar · notes</span>
      </div>

      <button className="btn primary big" style={{ width:'100%', marginTop: 12 }}>
        ▶ start session
      </button>

      <div className="between tiny mute" style={{ marginTop: 10 }}>
        <span><Kbd>⌘</Kbd><Kbd>↵</Kbd> start</span>
        <span><Kbd>⌘</Kbd><Kbd>,</Kbd> settings</span>
      </div>
    </div>
  );
}

function WelcomeC() { // List view — sober, denser
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret left" />

      <div className="between" style={{ marginBottom: 10 }}>
        <div className="row" style={{ gap:6 }}>
          <span className="av sm acc">M</span>
          <span className="lbl">mira  ▾</span>
        </div>
        <span className="icn sm dim">⚙</span>
      </div>

      <div className="h h2 tilt-3">Personas</div>
      <span className="lbl dim">⌘1–6 to jump</span>

      <div className="col" style={{ gap: 6, marginTop: 12 }}>
        {PERSONAS.slice(0,5).map((p, i) => (
          <div key={p.id} className="row between"
               style={{ padding:'7px 9px',
                        border:'1.5px solid', borderColor: i===2 ? 'var(--accent)' : 'transparent',
                        borderRadius: 10 }}>
            <div className="row" style={{ gap:9 }}>
              <span className="av sm">{p.mono}</span>
              <div className="col" style={{ gap: 0 }}>
                <span style={{ fontSize:15, color:'var(--fg)' }}>{p.name}</span>
                <span className="tiny dim">{p.tag}</span>
              </div>
            </div>
            <Kbd>⌘{i+1}</Kbd>
          </div>
        ))}
      </div>

      <div style={{ position:'absolute', left:14, right:14, bottom:50 }}>
        <div className="divider" />
        <div className="between" style={{ marginTop: 8 }}>
          <span className="lbl">mira · writing</span>
          <span className="tiny mono dim">~$0.18 / min</span>
        </div>
      </div>

      <button className="btn primary big" style={{
        position:'absolute', left:14, right:14, bottom:12,
      }}>
        ▶ start with mira
      </button>
    </div>
  );
}

function WelcomeD() { // Hero-single — persona dominates, tiny switcher chips above
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret right" />

      <div className="between" style={{ marginBottom: 6 }}>
        <span className="tiny mute mono">voice · 127.0.0.1:7711</span>
        <span className="icn sm dim">⚙</span>
      </div>

      {/* persona chips inline switcher */}
      <div className="row" style={{ gap: 5, justifyContent:'center', flexWrap:'wrap', marginBottom: 14 }}>
        {PERSONAS.map((p, i) => (
          <span key={p.id} className={`chip ${i===3?'acc':''}`}
                style={ i===3 ? { borderWidth: 2 } : null }>
            {p.name.toLowerCase()}
          </span>
        ))}
      </div>

      <div className="col" style={{ alignItems:'center', gap: 8 }}>
        <span className="av xxl acc">N</span>
        <div className="h h1">Noor.</div>
        <span className="lbl dim" style={{ textAlign:'center', maxWidth:240 }}>
          research partner. arxiv, vault notes,
          live web. asks before it acts.
        </span>

        <div className="row" style={{ gap:6, marginTop: 6 }}>
          <span className="chip">arxiv</span>
          <span className="chip">vault</span>
          <span className="chip">web</span>
        </div>

        <button className="talk lg" style={{ marginTop: 18 }}>
          tap to talk
        </button>

        <span className="tiny dim" style={{ marginTop: 6 }}>
          or hold <Kbd>fn</Kbd> for push-to-talk
        </span>
      </div>

      <div className="between tiny mute" style={{ position:'absolute', bottom:10, left:14, right:14 }}>
        <span className="mono">last · 12m ago · $0.04</span>
        <span className="mono">budget 42% used</span>
      </div>
    </div>
  );
}

Object.assign(window, { WelcomeA, WelcomeB, WelcomeC, WelcomeD });
