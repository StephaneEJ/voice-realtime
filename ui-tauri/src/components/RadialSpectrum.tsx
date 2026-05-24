// RadialSpectrum — SVG of `count` radial bars around a center, lengths driven
// by a rolling VU level buffer. Animates user+model audio concentrically.

export interface RadialSpectrumProps {
  /** Outer pixel size of the square SVG. */
  size?: number;
  /** Inner radius (avatar lives inside). */
  innerRadius?: number;
  /** Number of bars around the circle. */
  count?: number;
  /** RMS values [0..1] used to compute bar length. Length must equal `count`
   *  or be cycled. Pass a rolling buffer for spectrum-like behavior. */
  values: number[];
  /** Hex/CSS color of the bars. */
  color?: string;
}

export function RadialSpectrum({
  size = 168,
  innerRadius = 56,
  count = 48,
  values,
  color = "var(--mf-acc)",
}: RadialSpectrumProps) {
  const half = size / 2;
  const maxBarLength = half - innerRadius - 4;
  const bars = [];
  for (let i = 0; i < count; i += 1) {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    const rms = values[i % values.length] ?? 0;
    // Amplify speech RMS: 0.03-0.2 → 0.15-1.0 bar length
    const len = Math.max(2, Math.min(maxBarLength, rms * 4.5 * maxBarLength));
    const x1 = Math.cos(angle) * innerRadius;
    const y1 = Math.sin(angle) * innerRadius;
    const x2 = Math.cos(angle) * (innerRadius + len);
    const y2 = Math.sin(angle) * (innerRadius + len);
    bars.push(
      <line
        key={i}
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        opacity={0.65}
      />,
    );
  }
  return (
    <svg
      viewBox={`${-half} ${-half} ${size} ${size}`}
      width={size}
      height={size}
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      {bars}
    </svg>
  );
}
