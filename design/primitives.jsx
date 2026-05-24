/* global React */
// Shared sketchy primitives for the wireframes.

const { useMemo } = React;

// Seeded pseudo-random so VU bars / waveforms render identically per id.
function rng(seed) {
  let s = 0;
  for (let i = 0; i < seed.length; i++) s = (s * 31 + seed.charCodeAt(i)) >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

// Vertical EQ bars — 2 stacked layers (user + model)
function VuBars({ id = 'vu', n = 28, heights, dim = false }) {
  const rand = useMemo(() => rng(id), [id]);
  const hs = heights || Array.from({ length: n }, () => 0.25 + rand() * 0.75);
  return (
    <div className="vu-bars" style={dim ? { opacity: 0.55 } : null}>
      {hs.map((h, i) => (
        <i key={i} style={{ height: `${Math.round(h * 100)}%` }} />
      ))}
    </div>
  );
}
VuBars.layer = function VuBarsLayer({ id = 'vu', n = 28, kind = 'user' }) {
  const rand = useMemo(() => rng(id + kind), [id, kind]);
  const hs = Array.from({ length: n }, () => 0.15 + rand() * 0.85);
  return (
    <div className={`vu-bars ${kind}`}>
      {hs.map((h, i) => (
        <i key={i} style={{ height: `${Math.round(h * 100)}%` }} />
      ))}
    </div>
  );
};

// 2-layer waveform (user on top, model below)
function VuWave({ id = 'w' }) {
  const rand = useMemo(() => rng(id), [id]);
  const W = 200, H = 44, segs = 60;
  const path = (off, amp) => {
    let d = `M 0 ${H/2}`;
    for (let i = 1; i <= segs; i++) {
      const x = (i / segs) * W;
      const y = H/2 + Math.sin(i*0.45 + off) * (rand() * amp + 4);
      d += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
    }
    return d;
  };
  return (
    <div className="vu-wave">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <path className="u" d={path(0.3, 10)} />
        <path className="m" d={path(1.4, 6)} />
      </svg>
    </div>
  );
}

// Radial bars around an avatar (absolute overlay)
function VuRadial({ id = 'r', radius = 64, count = 36 }) {
  const rand = useMemo(() => rng(id), [id]);
  const lines = Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2;
    const len = 6 + rand() * 22;
    const kind = i % 2 === 0 ? 'u' : 'm';
    const x1 = Math.cos(a) * radius;
    const y1 = Math.sin(a) * radius;
    const x2 = Math.cos(a) * (radius + len);
    const y2 = Math.sin(a) * (radius + len);
    return { x1, y1, x2, y2, kind };
  });
  const size = (radius + 30) * 2;
  return (
    <div className="vu-radial">
      <svg width={size} height={size} viewBox={`${-size/2} ${-size/2} ${size} ${size}`}>
        {lines.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
                className={l.kind === 'm' ? 'm' : ''} />
        ))}
      </svg>
    </div>
  );
}

// Sparkline (30-day cost trend)
function Sparkline({ id = 's', height = 30 }) {
  const rand = useMemo(() => rng(id), [id]);
  const N = 30, W = 200;
  const pts = Array.from({ length: N }, (_, i) => {
    const y = height - (0.15 + rand() * 0.8) * (height - 4) - 2;
    const x = (i / (N - 1)) * W;
    return [x, y];
  });
  const line = 'M ' + pts.map(p => p.map(v => v.toFixed(1)).join(' ')).join(' L ');
  const area = line + ` L ${W} ${height} L 0 ${height} Z`;
  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
      <path className="fill" d={area} />
      <path d={line} />
    </svg>
  );
}

// Tiny menubar context strip (above popover variants)
function Menubar({ active = true }) {
  return (
    <div className="menubar">
      <span>🔋 87%</span>
      <span>14:32</span>
      <span className={active ? 'acc' : 'dim'}>● voice</span>
      <span className="ico" />
      <span style={{ opacity: 0.6 }}>⌘ ⌥ ⇧</span>
    </div>
  );
}

// Persona record (label, emoji-glyph placeholder, accent role color)
const PERSONAS = [
  { id: 'aria',   name: 'Aria',   role: 'Daily ops',     mono: 'A', tag: 'inbox · cal · notes' },
  { id: 'koda',   name: 'Koda',   role: 'Code coach',    mono: 'K', tag: 'repos · docs · stack' },
  { id: 'mira',   name: 'Mira',   role: 'Writing',       mono: 'M', tag: 'drafts · style · refs' },
  { id: 'noor',   name: 'Noor',   role: 'Research',      mono: 'N', tag: 'arxiv · vault · web' },
  { id: 'zen',    name: 'Zen',    role: 'Reflexion',     mono: 'Z', tag: 'journal · habits' },
  { id: 'fox',    name: 'Fox',    role: 'Brainstorm',    mono: 'F', tag: 'ideas · sparks' },
];

// Callout — circled number + label
function Callout({ n, children, style }) {
  return (
    <span className="callout" style={style}>
      <span className="num">{n}</span>
      <span>{children}</span>
    </span>
  );
}

// Keyboard combo
function Kbd({ children }) {
  return <span className="kbd">{children}</span>;
}

Object.assign(window, {
  VuBars, VuWave, VuRadial, Sparkline, Menubar, PERSONAS, Callout, Kbd,
});
