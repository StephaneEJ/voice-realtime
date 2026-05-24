/* global React, Kbd */
// Persona editor — Settings → Personas → click a row.
// Surfaces: identity · voice · web access · skills/commands · context window
// (sliding from a terminal pane OR static from a vault selection).
// 2 variantes : A = single-column scroll, B = nested tabs inside editor.

// ── Shared sub-blocks ───────────────────────────────────────

function Toggle({ on }) {
  return (
    <div style={{
      width: 30, height: 17, borderRadius: 999,
      border: `1.5px solid ${on ? 'var(--accent)' : 'var(--line-dim)'}`,
      background: on ? 'var(--accent-soft)' : 'transparent',
      position: 'relative', flex:'0 0 auto',
    }}>
      <i style={{
        position:'absolute', top: 1, left: on ? 14 : 1,
        width: 12, height: 12, borderRadius:'50%',
        background: on ? 'var(--accent)' : 'var(--line-dim)',
        transition: 'left .12s',
      }} />
    </div>
  );
}

function RowToggle({ label, sub, on }) {
  return (
    <div className="between" style={{ alignItems: 'flex-start' }}>
      <div className="col" style={{ gap: 1, flex:1 }}>
        <span className="lbl">{label}</span>
        {sub && <span className="tiny dim">{sub}</span>}
      </div>
      <Toggle on={on} />
    </div>
  );
}

function ProfileBlock() { // Identity + behavior, fused into a single tab
  return (
    <div className="col" style={{ gap: 12 }}>
      <span className="h h3">Identity</span>
      <div className="row" style={{ gap: 12, alignItems:'flex-start' }}>
        <div className="col" style={{ alignItems:'center', gap: 4 }}>
          <span className="av xl acc">K</span>
          <span className="tiny dim">change…</span>
        </div>
        <div className="col" style={{ flex:1, gap: 6 }}>
          <div className="col" style={{ gap: 2 }}>
            <span className="tiny dim">name</span>
            <div className="box" style={{ padding:'5px 8px' }}>Koda</div>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="tiny dim">role · one-liner</span>
            <div className="box" style={{ padding:'5px 8px' }}>code coach — pair on architecture & reviews</div>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="tiny dim">voice</span>
            <div className="row" style={{ gap: 5, flexWrap:'wrap' }}>
              <span className="chip acc">alloy</span>
              <span className="chip">echo</span>
              <span className="chip">sage</span>
              <span className="chip">verse</span>
              <span className="chip dim">+ 4 more…</span>
            </div>
          </div>
        </div>
      </div>

      <div className="divider" />

      <span className="h h3">Behavior</span>
      <RowToggle label="Web search" sub="let koda call web.fetch / web.search" on />
      <div className="row" style={{ marginLeft: 12, gap: 6, alignItems:'center', flexWrap:'wrap' }}>
        <span className="tiny dim">restrict to</span>
        <span className="chip acc">arxiv.org</span>
        <span className="chip acc">docs.* +12</span>
        <span className="chip ghost dim" style={{ borderStyle:'dashed' }}>+ domain</span>
      </div>
      <RowToggle label="Ask before acting" sub="confirm on file write / send / book" on />
    </div>
  );
}

// Combined context: sliding + static run together, both contribute to the budget.
function ContextBlock() {
  const MODEL = 'gemini-2.5-flash-native-audio';
  const MODEL_TOK = 500_000;   // model context window
  const SLIDE_TOK = 8_000;
  const STATIC_TOK = 12_400;
  const total = SLIDE_TOK + STATIC_TOK;
  const slidePct = (SLIDE_TOK / MODEL_TOK) * 100;
  const staticPct = (STATIC_TOK / MODEL_TOK) * 100;
  const totalPct = (total / MODEL_TOK) * 100;

  return (
    <div className="col" style={{ gap: 12 }}>
      {/* Budget indicator */}
      <div className="box fill" style={{ padding: '10px 12px' }}>
        <div className="between">
          <span className="h h3">Context budget</span>
          <span className="mono acc">{totalPct.toFixed(1)}% used</span>
        </div>
        <span className="tiny dim mono">{MODEL} · 500k tokens</span>

        {/* stacked bar: sliding (accent) + static (warn) + free */}
        <div className="bar" style={{ marginTop: 8, position:'relative', overflow:'hidden' }}>
          <i style={{ width: `${slidePct}%`, background: 'var(--accent)' }} />
          <i style={{ position:'absolute', top:0, height:'100%',
                       left: `${slidePct}%`, width: `${staticPct}%`,
                       background: 'var(--warn)' }} />
        </div>

        <div className="row tiny mono" style={{ gap: 12, marginTop: 5, flexWrap:'wrap' }}>
          <span><span className="acc">▮</span> sliding · 8k <span className="dim">({slidePct.toFixed(1)}%)</span></span>
          <span><span className="warn">▮</span> static · 12.4k <span className="dim">({staticPct.toFixed(1)}%)</span></span>
          <span className="mute">free · {((MODEL_TOK - total)/1000).toFixed(0)}k</span>
        </div>
      </div>

      {/* Sliding — from launching terminal */}
      <div className="box" style={{ padding: '10px 12px' }}>
        <div className="between" style={{ marginBottom: 4 }}>
          <span className="h h3 acc">Sliding · terminal tail</span>
          <span className="chip ok">auto · live</span>
        </div>
        <span className="tiny dim">
          launched from <span className="mono">ghostty / tmux / prism / iterm</span> →
          tails the parent pane automatically. no source picker.
        </span>

        <div className="divider" />

        <div className="col" style={{ gap: 3 }}>
          <div className="between">
            <span className="tiny dim">window size</span>
            <span className="mono acc">8k tokens · ~150 lines · 1.6%</span>
          </div>
          <div className="slider">
            <div className="track" />
            <div className="knob" style={{ left: 'calc(40% - 7px)' }} />
          </div>
          <div className="between tiny mono dim">
            <span>500</span><span>32k</span>
          </div>
        </div>
      </div>

      {/* Static — vault pin, persists */}
      <div className="box" style={{ padding: '10px 12px' }}>
        <div className="between" style={{ marginBottom: 4 }}>
          <span className="h h3" style={{ color:'var(--warn)' }}>Static · vault pin</span>
          <span className="mono tiny dim">12.4k · 2.5% · persists</span>
        </div>
        <span className="tiny dim">selection saved per-persona, survives across sessions.</span>

        {/* vault tree */}
        <div className="col" style={{ gap: 2, fontFamily:'var(--mono)', fontSize:11, marginTop: 8 }}>
          {[
            { name:'📁 projects/',         d:0, c:'partial' },
            { name:'   📁 voice-rt/',      d:1, c:'partial' },
            { name:'      ◉ spec.md',      d:2, c:'on' },
            { name:'      ◉ architecture.md', d:2, c:'on' },
            { name:'      ○ scratch.md',   d:2, c:'off' },
            { name:'   📁 web-svc/',       d:1, c:'off' },
            { name:'📁 daily/',            d:0, c:'off' },
            { name:'📁 refs/',             d:0, c:'partial' },
            { name:'   ◉ ws-protocol.md',  d:1, c:'on' },
            { name:'   ◉ tokens.md',       d:1, c:'on' },
            { name:'… 4 more',             d:0, c:'off' },
          ].map((r, i) => (
            <div key={i} className="row" style={{ gap: 6, paddingLeft: r.d * 10 }}>
              <span style={{
                color: r.c==='on' ? 'var(--accent)' :
                       r.c==='partial' ? 'var(--warn)' :
                       'var(--fg-mute)',
              }}>{r.name}</span>
            </div>
          ))}
        </div>

        <div className="divider" />

        <RowToggle label="auto-include linked notes" sub="follow [[wikilinks]] 1 level deep" on />
      </div>
    </div>
  );
}

function SkillsBlock() {
  const skills = [
    { id:'vault.search',   k:'builtin',  on: true,  desc:'search the obsidian vault' },
    { id:'vault.write',    k:'builtin',  on: true,  desc:'append / create notes' },
    { id:'repo.search',    k:'builtin',  on: true,  desc:'grep across selected repos' },
    { id:'web.search',     k:'builtin',  on: true,  desc:'duckduckgo · arxiv · docs' },
    { id:'calendar.*',     k:'builtin',  on: false, desc:'read / schedule events' },
    { id:'inbox.*',        k:'builtin',  on: false, desc:'gmail · read / draft' },
  ];
  const commands = [
    { name:'/review',  trigger:'review the last commit',  action:'repo.diff → critique' },
    { name:'/notes',   trigger:'capture this',            action:'vault.write(daily/today)' },
  ];

  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="between">
        <span className="h h3">Skills</span>
        <span className="tiny dim">{skills.filter(s=>s.on).length} / {skills.length} on</span>
      </div>
      <div className="col" style={{ gap: 4 }}>
        {skills.map(s => (
          <div key={s.id} className="row between"
               style={{ padding:'5px 8px', border:'1.5px solid var(--line-dim)',
                        borderRadius:8, borderColor: s.on?'var(--accent)':'var(--line-dim)' }}>
            <div className="col" style={{ gap: 0 }}>
              <span className="mono" style={{ fontSize: 12, color: s.on?'var(--accent)':'var(--fg-dim)' }}>
                {s.id}
              </span>
              <span className="tiny dim">{s.desc}</span>
            </div>
            <Toggle on={s.on} />
          </div>
        ))}
      </div>

      <div className="between" style={{ marginTop: 4 }}>
        <span className="h h3">Commands</span>
        <button className="btn ghost" style={{ fontSize:14, padding:'4px 10px' }}>+ new</button>
      </div>
      <span className="tiny dim">custom phrases → tool chain</span>
      <div className="col" style={{ gap: 4 }}>
        {commands.map(c => (
          <div key={c.name} className="box" style={{ padding:'6px 9px' }}>
            <div className="between">
              <span className="mono acc" style={{ fontSize:12 }}>{c.name}</span>
              <span className="row" style={{ gap:4 }}>
                <span className="icn sm dim">✎</span>
                <span className="icn sm dim">×</span>
              </span>
            </div>
            <div className="tiny dim" style={{ marginTop: 2 }}>
              when: <span className="mono" style={{ fontSize: 10 }}>"{c.trigger}"</span>
            </div>
            <div className="tiny dim">
              do:&nbsp; <span className="mono" style={{ fontSize: 10 }}>{c.action}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}



// ── Variants ───────────────────────────────────────────────

function PersonaEditorA() { // Single-column scroll
  return (
    <div className="wf" style={{ padding: 16, overflow:'auto' }}>
      <div className="between" style={{ marginBottom: 14 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="icn sm dim">←</span>
          <span className="h h2">edit · Koda</span>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn ghost" style={{ fontSize:14, padding:'4px 10px' }}>cancel</button>
          <button className="btn primary" style={{ fontSize:14, padding:'4px 12px' }}>save</button>
        </div>
      </div>

      <div className="col" style={{ gap: 16 }}>
        <ProfileBlock />
        <div className="divider" />
        <ContextBlock />
        <div className="divider" />
        <SkillsBlock />
      </div>

      <div className="divider" style={{ marginTop: 14 }} />
      <div className="between tiny dim" style={{ marginTop: 8 }}>
        <span>auto-save · ⌘S to force</span>
        <span className="row" style={{ gap: 4 }}>
          <span>delete persona</span>
          <span className="icn sm" style={{ borderColor:'var(--danger)', color:'var(--danger)' }}>×</span>
        </span>
      </div>
    </div>
  );
}

function PersonaEditorB({ tab = 'context' }) { // Sub-tabs inside the editor
  return (
    <div className="wf" style={{ padding: 16, overflow:'auto' }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="icn sm dim">←</span>
          <span className="av md acc">K</span>
          <span className="h h2">Koda</span>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn ghost" style={{ fontSize:14, padding:'4px 10px' }}>cancel</button>
          <button className="btn primary" style={{ fontSize:14, padding:'4px 12px' }}>save</button>
        </div>
      </div>

      {/* 3 sub-tabs */}
      <div className="row" style={{ gap: 4, borderBottom:'1.5px solid var(--line-dim)', paddingBottom: 6 }}>
        <div className={`tab ${tab==='profile'?'active':''}`}>profile</div>
        <div className={`tab ${tab==='context'?'active':''}`}>context</div>
        <div className={`tab ${tab==='skills'?'active':''}`}>skills</div>
      </div>

      <div style={{ marginTop: 14 }}>
        {tab === 'profile' && <ProfileBlock />}
        {tab === 'context' && <ContextBlock />}
        {tab === 'skills'  && <SkillsBlock />}
      </div>
    </div>
  );
}

function PersonaEditorC() { // Inline collapsibles
  return (
    <div className="wf" style={{ padding: 16, overflow:'auto' }}>
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="icn sm dim">←</span>
          <span className="av md acc">K</span>
          <span className="h h2">Koda</span>
        </div>
        <button className="btn primary" style={{ fontSize:14, padding:'4px 12px' }}>save</button>
      </div>

      <div className="col" style={{ gap: 10 }}>
        {/* collapsed profile */}
        <div className="box" style={{ padding:'8px 10px' }}>
          <div className="between">
            <div className="col" style={{ gap:1 }}>
              <span className="h h3">Profile</span>
              <span className="tiny dim">Koda · code coach · alloy · web ✓ (12 domains)</span>
            </div>
            <span className="dim">▸</span>
          </div>
        </div>

        {/* context expanded */}
        <div className="box fill" style={{ padding:'10px 12px' }}>
          <div className="between" style={{ marginBottom: 8 }}>
            <span className="h h3">Context · 4.1% used</span>
            <span className="dim">▾</span>
          </div>
          <ContextBlock />
        </div>

        {/* collapsed skills */}
        <div className="box" style={{ padding:'8px 10px' }}>
          <div className="between">
            <div className="col" style={{ gap:1 }}>
              <span className="h h3">Skills · 4 of 6 + 2 cmds</span>
              <span className="tiny dim">vault, repo, web, /review, /notes…</span>
            </div>
            <span className="dim">▸</span>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { PersonaEditorA, PersonaEditorB, PersonaEditorC });
