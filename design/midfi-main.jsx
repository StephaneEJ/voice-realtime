/* global React, MfAvatar, MfPERSONAS, MfKbd, MfHeader,
   MfVuBars, MfVuWave, MfRadial, MfSpark, MfSwitch, MfRowToggle, MfMenubar */

// ════════════════════════════════════════════════════════════
// VUE 1a · Welcome (popup inactif, layout C — list ⌘1-6)
// ════════════════════════════════════════════════════════════
function MfWelcome() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <div className="mf-row" style={{ gap: 8 }}>
          <span className="mf-display" style={{ fontSize: 15 }}>Personas</span>
          <span className="mf-chip outline" style={{ height: 18, fontSize: 10 }}>idle</span>
        </div>
        <div className="mf-row" style={{ gap: 2 }}>
          <button className="mf-icn sm" title="Settings ⌘,">⚙</button>
        </div>
      </div>

      <div style={{ padding: 8 }}>
        <div className="mf-col" style={{ gap: 2 }}>
          {MfPERSONAS.slice(0,5).map((p, i) => {
            const sel = i === 1; // Koda preselected
            return (
              <div key={p.id}
                   className={`mf-card hover ${sel ? 'selected' : ''}`}
                   style={{
                     padding: '8px 10px',
                     background: sel ? 'var(--mf-acc-soft)' : 'transparent',
                     border: sel ? '1px solid var(--mf-acc)' : '1px solid transparent',
                     display: 'flex', alignItems: 'center', gap: 10,
                     borderRadius: 9,
                   }}>
                <MfAvatar persona={p.id} size="md" />
                <div className="mf-col" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                  <span className="mf-title" style={{ fontSize: 14 }}>{p.name}</span>
                  <span className="mf-cap" style={{
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  }}>{p.role} · {p.tag}</span>
                </div>
                <MfKbd>⌘{i+1}</MfKbd>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        padding: 12,
        background: 'linear-gradient(180deg, transparent 0%, var(--mf-bg) 30%)',
        borderTop: '1px solid var(--mf-border)',
      }}>
        <div className="mf-between" style={{ marginBottom: 9 }}>
          <div className="mf-col" style={{ gap: 1 }}>
            <span className="mf-title" style={{ fontSize: 13.5 }}>Koda · code coach</span>
            <span className="mf-cap mf-mono">~$0.42 / hour · gpt-realtime-2</span>
          </div>
        </div>
        <button className="mf-btn primary block lg">
          <span style={{ fontSize: 11 }}>▶</span>
          Start with Koda
          <span style={{ marginLeft: 'auto', display:'flex', gap: 3 }}>
            <MfKbd>⌘</MfKbd><MfKbd>↵</MfKbd>
          </span>
        </button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// VUE 1b · Active session (popup, layout E — bubbles + radial + trio)
// ════════════════════════════════════════════════════════════
function MfActive() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <MfHeader
        persona="mira"
        status={<span className="mf-chip live ok">01:48</span>}
        right={<button className="mf-icn sm">⚙</button>}
      />

      {/* big avatar + radial halo */}
      <div style={{
        display:'flex', flexDirection:'column', alignItems:'center',
        gap: 4, paddingTop: 14, paddingBottom: 6,
      }}>
        <div className="mf-radial" style={{ width: 168, height: 168 }}>
          <svg viewBox="-84 -84 168 168" style={{ position:'absolute', inset: 0 }}>
            {/* inline (avoid extra component) — single layer */}
          </svg>
          <MfRadial id="active-mira" radius={54} count={42} size={168} />
          <MfAvatar persona="mira" size="xxl" live />
        </div>
        <span className="mf-display" style={{ fontSize: 18, marginTop: 4 }}>Mira</span>
        <span className="mf-cap">writing · drafts · refs</span>
      </div>

      {/* transcript bubbles */}
      <div style={{
        flex: 1, overflow: 'hidden',
        padding: '10px 12px',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        <div className="mf-bub user">cut the second paragraph?</div>
        <div className="mf-bub model">yes — the dialogue does the same job and it feels lived-in.</div>
        <div className="mf-bub user">and the ending?</div>
        <div className="mf-bub model partial">depends what you're after. if it's a moment of…</div>
      </div>

      {/* trio: mute · stop · expand */}
      <div style={{
        padding: '10px 12px 14px',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18,
        borderTop: '1px solid var(--mf-border)',
        background: 'rgba(255,255,255,0.015)',
      }}>
        <button className="mf-icn lg" title="mute (⌘M)">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <rect x="6" y="2" width="4" height="8" rx="2"/>
            <path d="M3 7v1a5 5 0 0 0 10 0V7" />
            <path d="M8 13v2"/>
          </svg>
        </button>
        <button className="mf-talk stop" title="stop (⌘.)">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="currentColor">
            <rect x="6" y="6" width="10" height="10" rx="1.5"/>
          </svg>
        </button>
        <button className="mf-icn lg" title="expand (⌘⇧E)">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <path d="M3 9v4h4M13 7V3H9M3 13l4-4M13 3l-4 4"/>
          </svg>
        </button>
      </div>

      {/* metrics strip */}
      <div style={{
        padding: '6px 12px 10px',
        display: 'flex', justifyContent: 'center', gap: 14,
        fontFamily: 'var(--mf-mono)', fontSize: 10.5, color: 'var(--mf-dim)',
      }}>
        <span>01:48</span>
        <span style={{ color: 'var(--mf-mute)' }}>·</span>
        <span>$0.05</span>
        <span style={{ color: 'var(--mf-mute)' }}>·</span>
        <span className="mf-acc">TTFI 140ms</span>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// VUE 2 · Split overlay sidebar (layout C — radial spectrum)
// ════════════════════════════════════════════════════════════
function MfTerm() {
  return (
    <div className="mf-term" style={{ flex: '0 0 70%', borderRight: '1px solid var(--mf-border)' }}>
      <div style={{ display:'flex', gap: 6, marginBottom: 8, fontSize: 10.5, opacity: 0.6 }}>
        <span>●</span><span>●</span><span>●</span>
        <span style={{ marginLeft: 8 }}>~/voice-rt — zsh</span>
      </div>
      <div><span className="ln-prompt">$</span> python -m voice.server --port 7711</div>
      <div className="ln-out">[server] websocket listening on 127.0.0.1:7711</div>
      <div className="ln-out">[session] persona=koda model=gpt-realtime-2</div>
      <div className="ln-evt">[turn]    user 0:14 → model 0:18  · ttfa 280ms</div>
      <div className="ln-evt">[turn]    user 0:34 → model 0:37  · ttfa 240ms</div>
      <div className="ln-out">[skill]   repo.search("rate limit") → 3 files</div>
      <div className="ln-evt">[turn]    user 0:54 → model 0:57  · ttfa 260ms</div>
      <div className="ln-out">[skill]   vault.read(architecture.md) → 4.2k tokens</div>
      <div style={{ marginTop: 10 }}>
        <span className="ln-prompt">$</span> <span style={{
          display:'inline-block', width: 7, height: 14, background: 'var(--mf-acc)',
          verticalAlign: 'middle', animation: 'mf-blink 1s steps(2) infinite',
        }} />
      </div>
    </div>
  );
}

function MfOverlay() {
  return (
    <div className="mf" style={{ display:'flex', borderRadius: 0, border: 'none' }}>
      <MfTerm />
      <div style={{
        flex: 1, borderLeft: '1px solid var(--mf-border)',
        background: 'var(--mf-panel)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* header */}
        <div className="mf-header" style={{ padding: '10px 12px' }}>
          <span className="mf-mono" style={{ color:'var(--mf-mute)' }}>voice · overlay</span>
          <div className="mf-row" style={{ gap: 2 }}>
            <button className="mf-icn sm" title="collapse to popover">⤺</button>
            <button className="mf-icn sm" title="settings">⚙</button>
          </div>
        </div>

        {/* persona + radial */}
        <div style={{
          padding: '18px 12px 10px',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
        }}>
          <div className="mf-radial" style={{ width: 168, height: 168 }}>
            <MfRadial id="ov-koda" radius={56} count={48} size={168} />
            <MfAvatar persona="koda" size="xxl" live />
          </div>
          <span className="mf-display" style={{ fontSize: 17 }}>Koda</span>
          <span className="mf-cap">code coach</span>
        </div>

        <div className="mf-divider" style={{ margin: '4px 12px' }} />

        {/* metrics */}
        <div style={{ padding: '8px 14px', display:'flex', flexDirection:'column', gap: 6, fontFamily:'var(--mf-mono)', fontSize: 11.5 }}>
          {[
            ['TTFA',  '280 ms', 'mf-acc'],
            ['TTFI',  '140 ms', 'mf-acc'],
            ['Session', '04:18', ''],
            ['Cost',    '$0.12', ''],
            ['Tokens',  '12.4k in · 9.1k out', 'mf-dim'],
          ].map(([k, v, c]) => (
            <div key={k} className="mf-between">
              <span className="mf-dim" style={{ letterSpacing: '0.02em' }}>{k}</span>
              <span className={c}>{v}</span>
            </div>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        {/* controls */}
        <div style={{
          padding: '12px 14px',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
          borderTop: '1px solid var(--mf-border)',
          background: 'rgba(255,255,255,0.015)',
        }}>
          <button className="mf-icn lg" title="mute (⌘M)">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="6" y="2" width="4" height="8" rx="2"/>
              <path d="M3 7v1a5 5 0 0 0 10 0V7"/>
              <path d="M8 13v2"/>
            </svg>
          </button>
          <button className="mf-talk sm stop" title="stop (⌘.)">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <rect x="4" y="4" width="8" height="8" rx="1.5"/>
            </svg>
          </button>
        </div>

        {/* budget footer */}
        <div style={{ padding: '8px 14px 12px' }}>
          <div className="mf-between mf-cap" style={{ marginBottom: 4 }}>
            <span>Budget · march</span>
            <span className="mf-mono mf-fg-2" style={{ color: 'var(--mf-fg-2)' }}>$20.40 / $30</span>
          </div>
          <div className="mf-bar"><i style={{ width: '68%' }} /></div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MfWelcome, MfActive, MfOverlay });
