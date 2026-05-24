/* global React, VuBars, VuWave, Menubar, Kbd */
// Vue 1b — Active session (popup en cours, ~400x600)
// 4 variantes : Columns split, Terminal stream, Bubbles, Compact

function ActiveA() { // 2-column user/model split (brief original)
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret center" />

      <div className="between" style={{ marginBottom: 8 }}>
        <div className="row" style={{ gap:7 }}>
          <span className="av sm acc">K</span>
          <span className="lbl">koda  ▾</span>
          <span className="chip ok">live · 02:14</span>
        </div>
        <span className="icn sm dim">⚙</span>
      </div>

      {/* 2-column transcript */}
      <div style={{
        display:'grid', gridTemplateColumns:'1fr 1fr', gap: 6,
        border:'1.5px solid var(--line-dim)', borderRadius:10,
        padding:'7px 6px', height: 360, position:'relative',
      }}>
        <div className="lbl tiny dim" style={{ gridColumn:'1' }}>you</div>
        <div className="lbl tiny dim" style={{ gridColumn:'2' }}>koda</div>

        <div className="col" style={{ gap: 6, fontSize:12, color:'var(--accent)' }}>
          <div className="box" style={{ padding:'4px 7px', borderColor:'var(--accent)' }}>
            ok so the rate limiter — should it be per route or global?
          </div>
          <div className="box" style={{ padding:'4px 7px', borderColor:'var(--accent)' }}>
            yeah let's do per route. start with 60 / min.
          </div>
          <div className="box dash" style={{ padding:'4px 7px', fontStyle:'italic' }}>
            and what about the …
          </div>
        </div>

        <div className="col" style={{ gap: 6, fontSize:12 }}>
          <div className="box" style={{ padding:'4px 7px' }}>
            depends. global is simpler; per-route lets you tune auth vs public.
          </div>
          <div className="box" style={{ padding:'4px 7px' }}>
            good call. middleware sits before the router so we tag the route key first.
          </div>
        </div>
      </div>

      {/* footer controls */}
      <div className="col" style={{ alignItems:'center', gap:6, marginTop: 12 }}>
        <button className="talk stop">stop</button>
        <div className="row tiny mono mute" style={{ gap: 10 }}>
          <span>02:14</span><span>·</span>
          <span>$0.07</span><span>·</span>
          <span className="acc">TTFA 280ms</span>
        </div>
      </div>
    </div>
  );
}

function ActiveB() { // Terminal-stream: > user / < model lines
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret left" />

      <div className="between" style={{ marginBottom: 8 }}>
        <div className="row" style={{ gap:7 }}>
          <span className="av sm">A</span>
          <span className="lbl">aria</span>
          <span className="chip ok">● rec</span>
        </div>
        <div className="row" style={{ gap:6 }}>
          <span className="icn sm dim">⏏</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="box" style={{
        height: 360, padding:'8px 10px', overflow:'hidden',
        background:'var(--paper-hi)',
      }}>
        <div className="tx-line user"><span className="pfx">{'> 14:32'}</span>quick — what's on my calendar after 3?</div>
        <div className="tx-line model"><span className="pfx">{'< aria '}</span>two things. design review with marc at 3:15, dentist 5pm.</div>
        <div className="tx-line user"><span className="pfx">{'> 14:32'}</span>can we push the dentist?</div>
        <div className="tx-line model"><span className="pfx">{'< aria '}</span>checking. earliest open slot is thursday 6pm. should i book?</div>
        <div className="tx-line user"><span className="pfx">{'> 14:33'}</span>yes please.</div>
        <div className="tx-line model"><span className="pfx">{'< aria '}</span>done — confirmation in your inbox. anything else before the 3:15?</div>
        <div className="tx-line user partial" style={{ opacity:0.5, fontStyle:'italic' }}>
          <span className="pfx">{'> ····'}</span>actually one more thing—
        </div>
      </div>

      <div className="between" style={{ marginTop: 10 }}>
        <div className="row" style={{ gap: 6 }}>
          <button className="icn lg dim">🎤</button>
          <button className="btn ghost">mute</button>
        </div>
        <button className="talk sm stop">stop</button>
        <div className="col tiny mono" style={{ alignItems:'flex-end', gap:1 }}>
          <span className="mute">04:18 · $0.12</span>
          <span className="acc">320ms</span>
        </div>
      </div>
    </div>
  );
}

function ActiveC() { // Bubbles iMessage-like + central pulse
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret center" />

      <div className="between" style={{ marginBottom: 8 }}>
        <div className="row" style={{ gap: 7 }}>
          <span className="av sm acc">M</span>
          <div className="col" style={{ gap:0 }}>
            <span style={{ fontSize:14 }}>mira</span>
            <span className="tiny dim">writing · gpt-realtime-2</span>
          </div>
        </div>
        <div className="row" style={{ gap:5 }}>
          <span className="chip ok">01:48</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ gap:8, height: 290, overflow:'hidden' }}>
        <div className="bub model">opening with the conflict works better here.
          you established stakes in 2 lines instead of 6.</div>
        <div className="bub user">should I keep the second paragraph?</div>
        <div className="bub model">cut it. the dialogue does the same job and feels lived-in.</div>
        <div className="bub user">ok — and the ending?</div>
        <div className="bub model partial">depends what you're after. if it's…</div>
      </div>

      {/* live audio strip + talk */}
      <div className="col" style={{ alignItems:'center', gap:6, marginTop: 8 }}>
        <div style={{ width:'100%', height: 36 }}>
          <VuBars.layer id="active-c" n={42} kind="model" />
        </div>
        <button className="talk stop">stop</button>
        <div className="row tiny mono mute" style={{ gap: 8 }}>
          <span>01:48</span>·<span>$0.05</span>·<span className="acc">TTFI 140ms</span>
        </div>
      </div>
    </div>
  );
}

function ActiveD() { // Compact: small transcript, big visualizer & metrics
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret right" />

      <div className="between" style={{ marginBottom: 6 }}>
        <div className="row" style={{ gap: 6 }}>
          <span className="av sm acc">Z</span>
          <span className="lbl">zen</span>
        </div>
        <div className="row" style={{ gap: 5 }}>
          <span className="chip ok">● 00:42</span>
          <span className="icn sm dim">⚙</span>
        </div>
      </div>

      <div className="col" style={{ alignItems:'center', gap: 10, marginTop: 8 }}>
        <span className="av xxl acc">Z</span>
        <span className="h h3 dim">zen is listening…</span>

        <div style={{ width:'100%', display:'flex', flexDirection:'column', gap:4 }}>
          <span className="tiny dim">you</span>
          <VuBars.layer id="active-d-u" n={48} kind="user" />
          <span className="tiny dim">zen</span>
          <VuBars.layer id="active-d-m" n={48} kind="model" />
        </div>

        {/* last 2 lines only */}
        <div className="col" style={{ width:'100%', gap:3 }}>
          <div className="tx-line user"><span className="pfx">{'>'}</span>my week felt heavy. mostly mondays.</div>
          <div className="tx-line model"><span className="pfx">{'<'}</span>tell me about monday. what made it heavy?</div>
        </div>

        <div className="row" style={{ gap: 12, marginTop: 4 }}>
          <button className="icn lg dim" title="mute">🎤</button>
          <button className="talk sm stop">⏹</button>
          <button className="icn lg dim" title="expand">⤢</button>
        </div>

        <div className="row tiny mono mute" style={{ gap: 8 }}>
          <span>00:42</span>·<span>$0.02</span>·<span className="acc">220ms</span>
        </div>
      </div>
    </div>
  );
}

// E — merged: bubbles (C) + big avatar (D) + radial spectrum + 3-button row (D)
function ActiveE() {
  return (
    <div className="wf popover">
      <Menubar />
      <div className="caret center" />

      <div className="between" style={{ marginBottom: 6 }}>
        <div className="row" style={{ gap: 6 }}>
          <span className="av sm acc">M</span>
          <span className="lbl">mira  ▾</span>
          <span className="chip ok">● 01:48</span>
        </div>
        <span className="icn sm dim">⚙</span>
      </div>

      {/* big avatar + radial spectrum halo */}
      <div className="col" style={{ alignItems:'center', gap: 2, marginTop: 4 }}>
        <div style={{ position:'relative', width: 160, height: 160,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          <VuRadial id="active-e" radius={52} count={40} />
          <span className="av xxl acc" style={{ zIndex: 2, width: 110, height: 110, fontSize: 32 }}>M</span>
        </div>
        <div className="h h2" style={{ marginTop: 2 }}>Mira</div>
        <span className="tiny dim">writing · drafts · refs</span>
      </div>

      {/* bubbles transcript — last 3 turns */}
      <div className="col" style={{ gap: 6, marginTop: 10, height: 168, overflow:'hidden' }}>
        <div className="bub user" style={{ fontSize:13 }}>should I keep the second paragraph?</div>
        <div className="bub model" style={{ fontSize:13 }}>cut it. the dialogue does the same job and feels lived-in.</div>
        <div className="bub user" style={{ fontSize:13 }}>ok — and the ending?</div>
        <div className="bub model partial" style={{ fontSize:13 }}>depends what you're after. if it's…</div>
      </div>

      {/* 3-button row (from D) */}
      <div className="row" style={{ justifyContent:'center', gap: 16, marginTop: 8 }}>
        <button className="icn lg dim" title="mute">🎤</button>
        <button className="talk sm stop" title="stop">⏹</button>
        <button className="icn lg dim" title="expand to overlay">⤢</button>
      </div>

      <div className="row tiny mono mute" style={{ gap: 8, justifyContent:'center', marginTop: 6 }}>
        <span>01:48</span>·<span>$0.05</span>·<span className="acc">TTFI 140ms</span>
      </div>
    </div>
  );
}

Object.assign(window, { ActiveA, ActiveB, ActiveC, ActiveD, ActiveE });
