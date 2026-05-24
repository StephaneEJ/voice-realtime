/* global React, MfAvatar */
// midfi-anim.jsx — animation specs doc, one artboard per key animation.
// Each block has: name, trigger, target, duration, curve, visual demo + notes.

const { useEffect: mfaUseEffect, useState: mfaUseState, useMemo: mfaUseMemo, useRef: mfaUseRef } = React;

// Inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('mfa-keyframes')) {
  const s = document.createElement('style');
  s.id = 'mfa-keyframes';
  s.textContent = `
    @keyframes mfa-pulse-ring {
      0%   { transform: scale(1);    opacity: 0.55; }
      60%  { transform: scale(1.32); opacity: 0;    }
      100% { transform: scale(1.32); opacity: 0;    }
    }
    @keyframes mfa-pulse-av {
      0%, 100% { transform: scale(1);    }
      50%      { transform: scale(1.035); }
    }
    @keyframes mfa-spin-dash {
      to { stroke-dashoffset: -120; }
    }
    @keyframes mfa-popover-in {
      0%   { transform: translateY(-6px) scale(0.94); opacity: 0; }
      60%  { transform: translateY(0)     scale(1.01); opacity: 1; }
      100% { transform: translateY(0)     scale(1);    opacity: 1; }
    }
    @keyframes mfa-vu-flicker {
      0%, 100% { transform: scaleY(0.3); }
      25%      { transform: scaleY(0.85); }
      50%      { transform: scaleY(0.55); }
      75%      { transform: scaleY(1);    }
    }
    @keyframes mfa-overlay-slide {
      0%   { transform: translateX(100%); }
      100% { transform: translateX(0); }
    }
  `;
  document.head.appendChild(s);
}

// ── Spec card layout ──────────────────────────────────────
function MfaSpec({ index, name, sub, demo, rows }) {
  return (
    <div className="mf" style={{ padding: 18, height: '100%', display:'flex', flexDirection:'column' }}>
      <div className="mf-between" style={{ marginBottom: 12 }}>
        <div className="mf-col" style={{ gap: 2 }}>
          <span className="mf-cap mf-mono" style={{ color: 'var(--mf-mute)' }}>animation · {index}/5</span>
          <span className="mf-display" style={{ fontSize: 19 }}>{name}</span>
          {sub && <span className="mf-cap">{sub}</span>}
        </div>
      </div>

      <div className="mf-card" style={{
        flex: 1, display:'flex', alignItems:'center', justifyContent:'center',
        background: 'var(--mf-bg)',
        padding: 24,
      }}>
        {demo}
      </div>

      <div className="mf-col" style={{ gap: 0, marginTop: 12 }}>
        {rows.map(([k, v, mono]) => (
          <div key={k} className="mf-between" style={{
            padding: '7px 0',
            borderTop: '1px solid var(--mf-border)',
          }}>
            <span className="mf-cap" style={{ textTransform:'uppercase', letterSpacing:'0.05em' }}>{k}</span>
            <span className={mono ? 'mf-mono-12' : ''} style={{ color:'var(--mf-fg)', fontSize: 12.5 }}>
              {v}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 1. Avatar pulse (model speaking) ──────────────────────
function MfaPulse() {
  return (
    <MfaSpec
      index="1"
      name="Avatar pulse"
      sub="Visual indicator that the model is generating audio."
      demo={
        <div style={{ position:'relative', width: 130, height: 130, display:'flex', alignItems:'center', justifyContent:'center' }}>
          {/* expanding ring */}
          <div style={{
            position:'absolute', inset: 0,
            borderRadius: '50%',
            border: '2px solid var(--pa-koda)',
            animation: 'mfa-pulse-ring 1.6s cubic-bezier(0.16, 1, 0.3, 1) infinite',
          }} />
          {/* avatar with subtle scale */}
          <div style={{ animation: 'mfa-pulse-av 1.6s ease-in-out infinite' }}>
            <MfAvatar persona="koda" size="xl" />
          </div>
        </div>
      }
      rows={[
        ['Trigger',  <span>WS event <span className="mf-mono mf-acc">audio.model.frame</span></span>, false],
        ['Layers',   '(a) avatar scale 1.000 → 1.035 ↻  ·  (b) ring scale 1.00 → 1.32 + fade', false],
        ['Duration', '1600ms loop (avatar)  ·  1600ms each ring iteration', true],
        ['Curve',    'avatar: ease-in-out  ·  ring: cubic-bezier(0.16, 1, 0.3, 1)', true],
        ['Stops on', <span>last frame received + <span className="mf-mono">tail = 200ms</span></span>, false],
        ['Reduced motion', 'Ring fades to static 8% glow ring. Scale disabled.', false],
      ]}
    />
  );
}

// ── 2. Talk button states ─────────────────────────────────
function MfaTalk() {
  // Quick auto-cycling demo of the 3 states
  const states = ['idle', 'connecting', 'live'];
  const [si, setSi] = mfaUseState(0);
  mfaUseEffect(() => {
    const t = setInterval(() => setSi(s => (s+1) % 3), 1700);
    return () => clearInterval(t);
  }, []);
  const state = states[si];

  return (
    <MfaSpec
      index="2"
      name="Talk button transitions"
      sub="Idle → Connecting → Live → Stop, four discrete states."
      demo={
        <div style={{ display:'flex', alignItems:'center', gap: 28 }}>
          {/* idle */}
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap: 6, opacity: state==='idle'?1:0.35, transition:'opacity 0.3s' }}>
            <button className="mf-talk sm">▶</button>
            <span className="mf-cap">idle</span>
          </div>
          <span className="mf-mute">→</span>
          {/* connecting */}
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap: 6, opacity: state==='connecting'?1:0.35, transition:'opacity 0.3s' }}>
            <button className="mf-talk sm connecting" style={{ position:'relative' }}>
              <svg width="56" height="56" viewBox="0 0 56 56" style={{ position:'absolute', inset: 0 }}>
                <circle cx="28" cy="28" r="22" fill="none"
                        stroke="rgba(0,0,0,0.3)" strokeWidth="3"
                        strokeDasharray="30 90"
                        style={{ animation: 'mfa-spin-dash 0.9s linear infinite' }}
                        transform="rotate(-90 28 28)" />
              </svg>
              ⏳
            </button>
            <span className="mf-cap">connecting</span>
          </div>
          <span className="mf-mute">→</span>
          {/* live (stop) */}
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap: 6, opacity: state==='live'?1:0.35, transition:'opacity 0.3s' }}>
            <button className="mf-talk sm stop">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="4" y="4" width="8" height="8" rx="1.5"/>
              </svg>
            </button>
            <span className="mf-cap">live · stop</span>
          </div>
        </div>
      }
      rows={[
        ['Color tween', 'idle bg: acc#4fc3f7 → connecting: warn#ffb74d → live: transparent + danger#ff7676 stroke', false],
        ['Bg duration', '180ms ease-in-out (color + box-shadow)', true],
        ['Glyph swap',  'play ▶ → spinner → ⏹ : cross-fade 120ms', false],
        ['Spinner',     'svg arc 30/90 dasharray, rotate 360° in 900ms linear infinite', true],
        ['Connecting timeout', '4000ms → revert to idle with banner "couldn\'t connect"', true],
        ['Press feedback', 'transform: scale(0.96) on :active, 80ms', true],
      ]}
    />
  );
}

// ── 3. Popover open/close ─────────────────────────────────
function MfaPopover() {
  const [open, setOpen] = mfaUseState(true);
  mfaUseEffect(() => {
    const t = setInterval(() => setOpen(o => !o), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <MfaSpec
      index="3"
      name="Popover spring"
      sub="NSPopover-like overshoot when opening from menubar icon."
      demo={
        <div style={{ position:'relative', width: 240, height: 160, display:'flex', flexDirection:'column', alignItems:'center' }}>
          {/* menubar icon */}
          <div style={{
            width: 18, height: 18, borderRadius: 4,
            background: 'var(--mf-acc)',
            display:'flex', alignItems:'center', justifyContent:'center',
            color: '#04131c', fontSize: 11, fontWeight: 700, position:'relative',
          }}>●</div>

          {open && (
            <div key={String(open)} style={{
              marginTop: 12,
              width: 180, height: 100,
              background: 'var(--mf-panel)',
              border: '1px solid var(--mf-border-2)',
              borderRadius: 10,
              boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
              position: 'relative',
              animation: 'mfa-popover-in 240ms cubic-bezier(0.34, 1.56, 0.64, 1)',
              display:'flex', alignItems:'center', justifyContent:'center',
              fontSize: 11, color: 'var(--mf-fg-2)',
            }}>
              {/* caret */}
              <div style={{
                position:'absolute', top: -5, left: '50%', transform:'translateX(-50%) rotate(45deg)',
                width: 10, height: 10,
                background: 'var(--mf-panel)',
                borderTop: '1px solid var(--mf-border-2)',
                borderLeft: '1px solid var(--mf-border-2)',
              }} />
              popover content
            </div>
          )}
        </div>
      }
      rows={[
        ['Trigger',   'Click menubar icon  ·  ⌘⌥V global hotkey', true],
        ['Duration',  '240ms in  ·  140ms out', true],
        ['Curve in',  'cubic-bezier(0.34, 1.56, 0.64, 1) — gentle overshoot', true],
        ['Curve out', 'cubic-bezier(0.4, 0, 1, 1) — quick fade', true],
        ['Transform', 'translateY(-6px) scale(0.94) → translateY(0) scale(1)', true],
        ['Opacity',   '0 → 1, locked to transform progress', true],
        ['Anchor',    'caret tracks menubar icon center; popover left edge clamped to screen', false],
      ]}
    />
  );
}

// ── 4. VU bars (RMS-driven) ──────────────────────────────
function MfaVU() {
  const ref = mfaUseRef(null);
  // Render 22 bars with staggered flicker for a "real-looking" demo
  return (
    <MfaSpec
      index="4"
      name="VU bars (RMS smoothing)"
      sub="Driven by audio RMS, smoothed with exponential decay."
      demo={
        <div className="mf-vu-bars lg" ref={ref} style={{ width: 280 }}>
          {Array.from({ length: 32 }).map((_, i) => (
            <i key={i} style={{
              transformOrigin: 'bottom',
              animation: `mfa-vu-flicker ${500 + (i * 37) % 400}ms ease-in-out infinite`,
              animationDelay: `${(i * 53) % 700}ms`,
              height: '100%',
              background: i < 16 ? 'var(--mf-acc)' : 'var(--mf-fg-2)',
            }} />
          ))}
        </div>
      }
      rows={[
        ['Driver',     'WS audio frames (Int16 PCM, 24kHz, ~50Hz frame rate)', true],
        ['Compute',    'RMS over 20ms window → log-scale → 32 bands (FFT only for radial spectrum)', false],
        ['Smoothing',  'h(t) = max(rms, h(t-1) · 0.78)  ·  decay 22% per frame', true],
        ['Frame rate', '50Hz visual (matches audio frames; no interpolation)', true],
        ['Floor',      'min-height 3px so bars stay visible during silence', false],
        ['Layers',     'user (accent) and model (fg-2) stack vertically when both visible', false],
        ['Reduced motion', 'static bars at 60% height, no animation', false],
      ]}
    />
  );
}

// ── 5. Overlay slide-in/out ──────────────────────────────
function MfaOverlay() {
  const [on, setOn] = mfaUseState(true);
  mfaUseEffect(() => {
    const t = setInterval(() => setOn(o => !o), 2400);
    return () => clearInterval(t);
  }, []);
  return (
    <MfaSpec
      index="5"
      name="Overlay slide-in"
      sub="Popover collapses; sidebar slides in from the right edge of the screen."
      demo={
        <div style={{
          width: 320, height: 180,
          borderRadius: 10, border: '1px solid var(--mf-border-2)',
          background: '#0c0e12',
          display: 'flex',
          overflow: 'hidden',
          position: 'relative',
        }}>
          {/* terminal "ghostty" left */}
          <div className="mf-term" style={{ flex: 1, padding: 10, fontSize: 9 }}>
            <div className="ln-out">$ python -m voice.server</div>
            <div className="ln-out">[server] listening :7711</div>
            <div className="ln-evt">[turn] user → model · 280ms</div>
            <div className="ln-out">[skill] vault.search()</div>
          </div>
          {/* sidebar slides in */}
          {on && (
            <div key={String(on)} style={{
              width: 90,
              borderLeft: '1px solid var(--mf-border)',
              background: 'var(--mf-panel)',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              animation: 'mfa-overlay-slide 320ms cubic-bezier(0.32, 0.72, 0, 1)',
            }}>
              <MfAvatar persona="koda" size="lg" live />
              <span className="mf-mono" style={{ fontSize: 10 }}>Koda</span>
              <div className="mf-bar" style={{ width: 70 }}><i style={{ width: '68%' }} /></div>
            </div>
          )}
        </div>
      }
      rows={[
        ['Trigger',      'click ⤡ in popover  ·  ⌘⇧E', true],
        ['Sequence',     '(1) popover closes 140ms  ·  (2) sidebar slides in 320ms — 80ms overlap OK', true],
        ['Duration',     '320ms in  ·  220ms out', true],
        ['Curve',        'cubic-bezier(0.32, 0.72, 0, 1) — fast start, gentle land', true],
        ['Transform',    'translateX(100%) → translateX(0)  ·  opacity stays 1', true],
        ['Terminal',     'no transform — sidebar simply docks beside it (NSWindow.collectionBehavior = .moveToActiveSpace)', false],
        ['Menubar icon', 'switches to hollow ring during overlay; click closes overlay back to popover', false],
        ['Reverse',      'slide-out 220ms then popover-in 240ms (chained)', true],
      ]}
    />
  );
}

Object.assign(window, { MfaPulse, MfaTalk, MfaPopover, MfaVU, MfaOverlay });
