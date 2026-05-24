/* global React */
// midfi-primitives.jsx — shared mid-fidelity components.
// All components prefix CSS classes with mf-* so they coexist with the wireframe set.

const { useMemo: mfUseMemo } = React;

// ── Seeded random for stable VU heights ───────────────────
function mfRng(seed) {
  let s = 0;
  for (let i = 0; i < seed.length; i++) s = (s * 31 + seed.charCodeAt(i)) >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 0xffffffff; };
}

// ── Avatar ─────────────────────────────────────────────────
function MfAvatar({ persona = 'koda', size = 'md', live = false, mono }) {
  const letter = (mono || persona[0]).toUpperCase();
  return (
    <span className={`mf-av ${size} ${persona} ${live ? 'live' : ''}`}>
      {letter}
    </span>
  );
}

// ── Persona roster (mid-fi version) ────────────────────────
const MfPERSONAS = [
  { id:'aria', name:'Aria', role:'Daily ops',  tag:'inbox · cal · notes',  voice:'shimmer' },
  { id:'koda', name:'Koda', role:'Code coach', tag:'repos · docs · stack', voice:'alloy'   },
  { id:'mira', name:'Mira', role:'Writing',    tag:'drafts · style · refs',voice:'sage'    },
  { id:'noor', name:'Noor', role:'Research',   tag:'arxiv · vault · web',  voice:'verse'   },
  { id:'zen',  name:'Zen',  role:'Reflexion',  tag:'journal · habits',     voice:'echo'    },
  { id:'fox',  name:'Fox',  role:'Brainstorm', tag:'ideas · sparks',       voice:'ash'     },
];

// ── Kbd ────────────────────────────────────────────────────
function MfKbd({ children }) { return <span className="mf-kbd">{children}</span>; }

// ── Header (popover top) ───────────────────────────────────
function MfHeader({ persona, right, status }) {
  const p = MfPERSONAS.find(x => x.id === persona) || MfPERSONAS[0];
  return (
    <div className="mf-header">
      <div className="mf-row" style={{ gap: 8 }}>
        <div className="mf-switcher">
          <MfAvatar persona={p.id} size="sm" />
          <span className="mf-title" style={{ fontSize: 14 }}>{p.name}</span>
          <span className="mf-chev">▾</span>
        </div>
        {status}
      </div>
      <div className="mf-row" style={{ gap: 2 }}>
        {right}
      </div>
    </div>
  );
}

// ── VU bars (vertical EQ) ──────────────────────────────────
function MfVuBars({ id = 'v', n = 32, kind = 'user', size = 'md' }) {
  const rand = mfUseMemo(() => mfRng(id + kind), [id, kind]);
  const hs = mfUseMemo(() => Array.from({ length: n }, () => 0.18 + rand() * 0.82), [n]);
  return (
    <div className={`mf-vu-bars ${kind} ${size}`}>
      {hs.map((h, i) => <i key={i} style={{ height: `${(h*100).toFixed(0)}%` }} />)}
    </div>
  );
}

// ── Waveform (2 layers: user + model) ──────────────────────
function MfVuWave({ id = 'w', height = 36 }) {
  const rand = mfUseMemo(() => mfRng(id), [id]);
  const W = 240, segs = 90;
  const path = (off, amp) => {
    const mid = height / 2;
    let d = `M 0 ${mid}`;
    for (let i = 1; i <= segs; i++) {
      const x = (i / segs) * W;
      const y = mid + Math.sin(i * 0.32 + off) * (rand() * amp + 3);
      d += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
    }
    return d;
  };
  return (
    <div className="mf-vu-wave" style={{ height }}>
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
        <path className="u" d={path(0.3, height * 0.32)} />
        <path className="m" d={path(1.4, height * 0.20)} />
      </svg>
    </div>
  );
}

// ── Radial spectrum around an avatar ───────────────────────
function MfRadial({ id = 'r', radius = 60, count = 44, size = 220 }) {
  const rand = mfUseMemo(() => mfRng(id), [id]);
  const lines = mfUseMemo(() => Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2;
    const len = 8 + rand() * 26;
    const x1 = Math.cos(a) * radius;
    const y1 = Math.sin(a) * radius;
    const x2 = Math.cos(a) * (radius + len);
    const y2 = Math.sin(a) * (radius + len);
    return { x1, y1, x2, y2, m: i % 3 === 0 };
  }), [count, radius]);
  return (
    <svg width={size} height={size}
         viewBox={`${-size/2} ${-size/2} ${size} ${size}`}>
      {lines.map((l, i) => (
        <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} className={l.m ? 'm' : ''} />
      ))}
    </svg>
  );
}

// ── Sparkline ──────────────────────────────────────────────
function MfSpark({ id = 's', height = 26 }) {
  const rand = mfUseMemo(() => mfRng(id), [id]);
  const N = 30, W = 220;
  const pts = Array.from({ length: N }, (_, i) => {
    const y = height - (0.15 + rand() * 0.8) * (height - 4) - 2;
    const x = (i / (N - 1)) * W;
    return [x, y];
  });
  const line = 'M ' + pts.map(p => p.map(v => v.toFixed(1)).join(' ')).join(' L ');
  const area = line + ` L ${W} ${height} L 0 ${height} Z`;
  return (
    <svg className="mf-spark" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
      <path className="fill" d={area} />
      <path className="stroke" d={line} />
    </svg>
  );
}

// ── Switch (toggle) ────────────────────────────────────────
function MfSwitch({ on }) {
  return <span className={`mf-switch ${on ? 'on' : ''}`} />;
}

// ── Row toggle ─────────────────────────────────────────────
function MfRowToggle({ label, sub, on, ico }) {
  return (
    <div className="mf-between" style={{ alignItems:'flex-start', padding:'4px 0' }}>
      <div className="mf-col" style={{ gap: 1, flex:1 }}>
        <div className="mf-row" style={{ gap: 6 }}>
          {ico && <span className="mf-dim" style={{ fontSize: 13 }}>{ico}</span>}
          <span className="mf-title" style={{ fontSize: 13, fontWeight: 500 }}>{label}</span>
        </div>
        {sub && <span className="mf-cap">{sub}</span>}
      </div>
      <MfSwitch on={on} />
    </div>
  );
}

// ── Menubar context (above popover) ────────────────────────
function MfMenubar({ active = true }) {
  return (
    <div style={{
      position: 'absolute', top: -22, left: '50%', transform: 'translateX(-50%)',
      display: 'flex', gap: 12, alignItems: 'center',
      fontFamily: 'var(--mf-mono)', fontSize: 10, color: 'var(--mf-mute)',
      whiteSpace: 'nowrap',
    }}>
      <span>14:32</span>
      <span>🔋 87%</span>
      <span style={{
        width: 14, height: 14, borderRadius: 3,
        background: active ? 'var(--mf-acc)' : 'transparent',
        border: `1px solid ${active ? 'var(--mf-acc)' : 'var(--mf-mute)'}`,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        color: '#04131c', fontSize: 9, fontWeight: 700,
      }}>{active ? '●' : ''}</span>
    </div>
  );
}

Object.assign(window, {
  MfAvatar, MfPERSONAS, MfKbd, MfHeader,
  MfVuBars, MfVuWave, MfRadial, MfSpark,
  MfSwitch, MfRowToggle, MfMenubar, mfRng,
});
