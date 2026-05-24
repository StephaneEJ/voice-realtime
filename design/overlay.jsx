/* global React, VuBars, VuWave, VuRadial, Sparkline */
// Vue 2 — Split-screen overlay sidebar (vertical, ~280px width, full height)
// Frame shows ghostty terminal at 80% on left + sidebar at 20% right.
// 4 variantes : EQ bars, waveform horiz, radial spectrum, ultra-compact.

// Shared terminal context (left 80%) — fake Ghostty content for context
function TermShade({ accent }) {
  return (
    <div className="shade-term" style={{
      flex: '0 0 70%',
      borderRight: '1.5px dashed var(--line-dim)',
      padding: '12px 14px',
      fontFamily: 'var(--mono)',
      fontSize: 10,
      color: 'var(--fg-mute)',
      lineHeight: 1.6,
      position: 'relative',
      overflow: 'hidden',
    }}>
      <div className="row tiny mute" style={{ gap: 6, marginBottom: 8 }}>
        <span>● ● ●</span>
        <span style={{ marginLeft: 6 }}>~/voice-rt — zsh</span>
      </div>
      <div>$ python -m voice.server --port 7711</div>
      <div>{'[server] websocket listening on 127.0.0.1:7711'}</div>
      <div>{'[session] persona=koda model=gpt-realtime-2'}</div>
      <div>{'[turn]    user 0:14 → model 0:18  · ttfa 280ms'}</div>
      <div>{'[turn]    user 0:34 → model 0:37  · ttfa 240ms'}</div>
      <div>{'[skill]   repo.search("rate limit middleware") → 3 files'}</div>
      <div style={{ marginTop: 14 }}>$ <span className="acc">_</span></div>

      <div style={{ position:'absolute', bottom: 14, left: 14, right: 14 }}>
        <div className="callout">
          <span className="num">A</span>
          <span>ghostty (or any term) — 70% width, untouched</span>
        </div>
      </div>
    </div>
  );
}

// Frame wrapper — sized as a tall artboard
function OverlayFrame({ children }) {
  return (
    <div className="wf" style={{ display:'flex', borderRadius: 0 }}>
      <TermShade />
      <div style={{
        flex: '1 1 0',
        padding: '14px 12px',
        borderLeft: '1.5px solid var(--line)',
        position: 'relative',
        display:'flex', flexDirection:'column', gap: 10,
      }}>
        {children}
      </div>
    </div>
  );
}

function OverlayA() { // EQ bars classic (brief default)
  return (
    <OverlayFrame>
      {/* header strip */}
      <div className="between">
        <span className="tiny mono mute">voice · session</span>
        <div className="row" style={{ gap:5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ alignItems:'center', gap:6 }}>
        <span className="av xxl acc">K</span>
        <div className="h h2">Koda</div>
        <span className="lbl dim" style={{ textAlign:'center' }}>code coach<br/>repos · docs · stack</span>
      </div>

      <div className="divider" />

      {/* VU spectrum — 2 layers */}
      <div className="col" style={{ gap: 6 }}>
        <div className="between tiny">
          <span className="lbl">you</span>
          <span className="mono mute">-12 dB</span>
        </div>
        <VuBars.layer id="ov-a-u" kind="user" n={32} />
        <div className="between tiny">
          <span className="lbl">koda</span>
          <span className="mono mute">-9 dB</span>
        </div>
        <VuBars.layer id="ov-a-m" kind="model" n={32} />
      </div>

      <div className="divider" />

      {/* metrics */}
      <div className="col" style={{ gap: 5, fontFamily:'var(--mono)', fontSize:11 }}>
        <div className="between"><span className="mute">TTFA</span><span className="acc">280 ms</span></div>
        <div className="between"><span className="mute">TTFI</span><span className="acc">140 ms</span></div>
        <div className="between"><span className="mute">dur</span><span>04:18</span></div>
        <div className="between"><span className="mute">cost</span><span>$0.12</span></div>
      </div>

      <div style={{ flex:1 }} />

      {/* controls */}
      <div className="row" style={{ justifyContent:'center', gap: 12 }}>
        <button className="icn lg dim" title="mute mic">🎤</button>
        <button className="talk sm stop" title="kill session">⏹</button>
      </div>

      <div className="col" style={{ gap: 2 }}>
        <div className="between tiny">
          <span className="lbl">cost · 30d</span>
          <span className="mono dim">$8.40</span>
        </div>
        <Sparkline id="ov-a-spark" />
      </div>
    </OverlayFrame>
  );
}

function OverlayB() { // Waveform horizontal — dense data, fewer chrome
  return (
    <OverlayFrame>
      <div className="between">
        <div className="row" style={{ gap:6 }}>
          <span className="av sm acc">N</span>
          <span className="lbl">noor</span>
        </div>
        <div className="row" style={{ gap:5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ alignItems:'center', gap: 4, marginTop: 6 }}>
        <span className="av xl acc">N</span>
        <div className="h h3">Noor · research</div>
      </div>

      <div className="col" style={{ gap: 6, marginTop: 4 }}>
        <span className="tiny dim">you · noor (overlay)</span>
        <VuWave id="ov-b-wave" />
        <div className="between tiny mono mute">
          <span>-3s</span><span>now</span>
        </div>
      </div>

      {/* metric tiles 2x2 */}
      <div style={{
        display:'grid', gridTemplateColumns:'1fr 1fr', gap: 6,
      }}>
        {[
          ['TTFA', '320 ms', 'acc'],
          ['TTFI', '180 ms', 'acc'],
          ['dur',  '07:42', ''],
          ['cost', '$0.21', ''],
        ].map(([k,v,c]) => (
          <div key={k} className="box" style={{ padding:'6px 8px' }}>
            <div className="tiny dim mono">{k}</div>
            <div className={`mono ${c}`} style={{ fontSize: 14 }}>{v}</div>
          </div>
        ))}
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 4 }}>
        <span className="tiny mute">last skill calls</span>
        <div className="tx-line model" style={{ fontSize:10 }}>
          <span className="pfx">↳</span>vault.search("rate limit")
        </div>
        <div className="tx-line model" style={{ fontSize:10 }}>
          <span className="pfx">↳</span>arxiv.fetch(2401.13074)
        </div>
        <div className="tx-line model" style={{ fontSize:10 }}>
          <span className="pfx">↳</span>web.read(fastapi.docs/rate)
        </div>
      </div>

      <div style={{ flex:1 }} />

      <div className="row" style={{ justifyContent:'space-around' }}>
        <button className="icn lg dim">🔇</button>
        <button className="talk sm stop">⏹</button>
        <button className="icn lg dim">⊟</button>
      </div>
    </OverlayFrame>
  );
}

function OverlayC() { // Radial spectrum AROUND the avatar — most striking
  return (
    <OverlayFrame>
      <div className="between">
        <span className="tiny mono mute">voice · overlay</span>
        <div className="row" style={{ gap:5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ alignItems:'center', gap: 8, marginTop: 6, position:'relative' }}>
        <div style={{ position:'relative', width: 180, height: 180,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          <VuRadial id="ov-c" radius={56} count={42} />
          <span className="av xl acc" style={{ zIndex: 2 }}>F</span>
        </div>
        <div className="h h2">Fox</div>
        <span className="lbl dim">brainstorm</span>
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 5, fontFamily:'var(--mono)', fontSize:11 }}>
        <div className="between"><span className="mute">latency 1st</span><span className="acc">260 ms</span></div>
        <div className="between"><span className="mute">interrupt</span><span className="acc">95 ms</span></div>
        <div className="between"><span className="mute">session</span><span>11:04</span></div>
        <div className="between"><span className="mute">spent</span><span>$0.34</span></div>
      </div>

      <div style={{ flex:1 }} />

      <div className="col" style={{ gap: 2 }}>
        <span className="tiny dim">budget · march</span>
        <div className="bar"><i style={{ width:'68%'}}/></div>
        <div className="between tiny mono mute"><span>$20.40</span><span>$30</span></div>
      </div>

      <div className="row" style={{ justifyContent:'center', gap: 10, marginTop:4 }}>
        <button className="icn lg dim">🎤</button>
        <button className="talk sm stop">⏹</button>
      </div>
    </OverlayFrame>
  );
}

function OverlayD() { // Ultra-compact — everything tight, no decoration
  return (
    <OverlayFrame>
      <div className="between">
        <div className="row" style={{ gap:6 }}>
          <span className="av sm acc">M</span>
          <span className="lbl">mira</span>
          <span className="chip ok">● 02:14</span>
        </div>
        <span className="icn sm dim">×</span>
      </div>

      {/* tiny avatar + name */}
      <div className="row" style={{ gap: 8, alignItems:'center' }}>
        <span className="av lg acc">M</span>
        <div className="col" style={{ gap:0 }}>
          <span className="h h3">Mira</span>
          <span className="tiny dim">writing · drafts · refs</span>
        </div>
      </div>

      {/* compact 2-layer EQ */}
      <div className="col" style={{ gap: 3 }}>
        <div style={{ height: 28 }}><VuBars.layer id="ov-d-u" kind="user" n={28} /></div>
        <div style={{ height: 28 }}><VuBars.layer id="ov-d-m" kind="model" n={28} /></div>
      </div>

      {/* metrics as 1-line table */}
      <div className="box" style={{ padding:'6px 8px', fontFamily:'var(--mono)', fontSize:10.5 }}>
        <div className="between"><span className="mute">ttfa·ttfi</span><span className="acc">280 / 140</span></div>
        <div className="between"><span className="mute">dur·$$</span><span>02:14 · $0.07</span></div>
        <div className="between"><span className="mute">model</span><span>gpt-rt-2</span></div>
        <div className="between"><span className="mute">tokens</span><span>12.4k in / 9.1k out</span></div>
      </div>

      {/* last partial turn */}
      <div className="col" style={{ gap: 3 }}>
        <div className="tx-line user" style={{ fontSize:10 }}>
          <span className="pfx">{'>'}</span>cut the second paragraph?
        </div>
        <div className="tx-line model partial" style={{ fontSize:10, fontStyle:'italic' }}>
          <span className="pfx">{'<'}</span>yes, the dialogue does that…
        </div>
      </div>

      <div style={{ flex:1 }} />

      <div className="row" style={{ justifyContent:'space-between', gap: 6 }}>
        <button className="btn ghost" style={{ flex:1 }}>mute</button>
        <button className="btn danger" style={{ flex:1 }}>stop</button>
      </div>

      <Sparkline id="ov-d-spark" />
      <span className="tiny mute mono">30d · $8.40 (-12%)</span>
    </OverlayFrame>
  );
}

function OverlayE() { // C-evolution: radial halo + dedicated horizontal "you" waveform
  return (
    <OverlayFrame>
      <div className="between">
        <span className="tiny mono mute">voice · overlay</span>
        <div className="row" style={{ gap:5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ alignItems:'center', gap: 6, marginTop: 2 }}>
        <div style={{ position:'relative', width: 180, height: 180,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          <VuRadial id="ov-e-r" radius={56} count={44} />
          <span className="av xl acc" style={{ zIndex: 2 }}>F</span>
        </div>
        <div className="h h2">Fox</div>
        <span className="lbl dim">brainstorm</span>
      </div>

      <div className="divider" />

      {/* dedicated "you" horizontal waveform — like B */}
      <div className="col" style={{ gap: 4 }}>
        <div className="between tiny">
          <span className="lbl acc">you</span>
          <span className="mono mute">-12 dB · live</span>
        </div>
        <VuWave id="ov-e-wave" />
      </div>

      <div className="divider" />

      <div className="col" style={{ gap: 5, fontFamily:'var(--mono)', fontSize:11 }}>
        <div className="between"><span className="mute">TTFA</span><span className="acc">260 ms</span></div>
        <div className="between"><span className="mute">TTFI</span><span className="acc">95 ms</span></div>
        <div className="between"><span className="mute">dur</span><span>11:04</span></div>
        <div className="between"><span className="mute">spent</span><span>$0.34</span></div>
      </div>

      <div style={{ flex:1 }} />

      <div className="row" style={{ justifyContent:'center', gap: 12 }}>
        <button className="icn lg dim">🎤</button>
        <button className="talk sm stop">⏹</button>
      </div>
    </OverlayFrame>
  );
}

function OverlayF() { // F — radial smaller; user waveform gets primary real estate
  return (
    <OverlayFrame>
      <div className="between">
        <div className="row" style={{ gap: 6 }}>
          <span className="av sm acc">K</span>
          <span className="lbl">koda</span>
        </div>
        <div className="row" style={{ gap: 5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      {/* compact radial badge on the right, name+stats on left */}
      <div className="row" style={{ gap: 10, alignItems:'center', marginTop: 4 }}>
        <div className="col" style={{ flex: 1, gap: 2 }}>
          <div className="h h2">Koda</div>
          <span className="tiny dim">code coach</span>
          <span className="chip ok" style={{ marginTop:4 }}>● 04:18</span>
        </div>
        <div style={{ position:'relative', width: 100, height: 100,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          <VuRadial id="ov-f-r" radius={30} count={28} />
          <span className="av md acc" style={{ zIndex: 2 }}>K</span>
        </div>
      </div>

      <div className="divider" />

      {/* user spectrum gets vertical room — waveform on top, EQ bars below */}
      <div className="col" style={{ gap: 4 }}>
        <span className="lbl acc">you · live</span>
        <VuWave id="ov-f-wave" />
        <div style={{ height: 36, marginTop: 2 }}>
          <VuBars.layer id="ov-f-u" kind="user" n={36} />
        </div>
      </div>

      <div className="divider" />

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap: 6 }}>
        {[
          ['TTFA', '280 ms', 'acc'],
          ['TTFI', '140 ms', 'acc'],
          ['dur',  '04:18', ''],
          ['cost', '$0.12', ''],
        ].map(([k,v,c]) => (
          <div key={k} className="box" style={{ padding:'5px 8px' }}>
            <div className="tiny dim mono">{k}</div>
            <div className={`mono ${c}`} style={{ fontSize: 13 }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ flex:1 }} />

      <div className="row" style={{ justifyContent:'center', gap: 12 }}>
        <button className="icn lg dim">🎤</button>
        <button className="talk sm stop">⏹</button>
      </div>
    </OverlayFrame>
  );
}

function OverlayG() { // G — radial as background halo, user wave dominant
  return (
    <OverlayFrame>
      <div className="between">
        <span className="tiny mono mute">voice · session</span>
        <div className="row" style={{ gap: 5 }}>
          <span className="icn sm dim">⤡</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      {/* large radial backdrop centered, small avatar inside */}
      <div className="col" style={{ alignItems:'center', gap: 4, marginTop: 6 }}>
        <div style={{ position:'relative', width: 200, height: 140,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          <VuRadial id="ov-g-r" radius={42} count={52} />
          <span className="av lg acc" style={{ zIndex: 2 }}>N</span>
        </div>
        <div className="h h3">Noor · research</div>
      </div>

      {/* user spectrum — both waveform AND tall EQ for richness */}
      <div className="col" style={{ gap: 5 }}>
        <div className="between tiny">
          <span className="lbl acc">you</span>
          <span className="mono mute">scroll ←</span>
        </div>
        <VuWave id="ov-g-wave" />
        <div style={{ height: 44, marginTop: 4 }}>
          <VuBars.layer id="ov-g-u" kind="user" n={42} />
        </div>
      </div>

      {/* metrics inline tight */}
      <div className="box" style={{ padding:'6px 8px', fontFamily:'var(--mono)', fontSize:10.5 }}>
        <div className="between"><span className="mute">ttfa · ttfi</span><span className="acc">320 / 180</span></div>
        <div className="between"><span className="mute">dur · $$</span><span>07:42 · $0.21</span></div>
      </div>

      <div style={{ flex:1 }} />

      <div className="row" style={{ justifyContent:'space-around' }}>
        <button className="icn lg dim">🎤</button>
        <button className="talk sm stop">⏹</button>
        <button className="icn lg dim">⊟</button>
      </div>

      <Sparkline id="ov-g-spark" />
    </OverlayFrame>
  );
}

Object.assign(window, { OverlayA, OverlayB, OverlayC, OverlayD, OverlayE, OverlayF, OverlayG });
