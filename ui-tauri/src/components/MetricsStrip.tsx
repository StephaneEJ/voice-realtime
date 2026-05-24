// Compact monospace strip showing live session numbers.
// Mirrors the layout in design/midfi-main.jsx MfActive metrics row.

import { formatCost, formatDuration } from "../lib/models";

export function MetricsStrip({
  durationSeconds,
  costUsd,
  ttfaMs,
  ttfiMs,
}: {
  durationSeconds: number;
  costUsd: number;
  ttfaMs: number | null;
  ttfiMs: number | null;
}) {
  const dot = <span style={{ color: "var(--mf-mute)" }}>·</span>;
  return (
    <div
      style={{
        padding: "6px 12px 10px",
        display: "flex",
        justifyContent: "center",
        gap: 14,
        fontFamily: "var(--mf-mono)",
        fontSize: 10.5,
        color: "var(--mf-dim)",
      }}
    >
      <span>{formatDuration(durationSeconds)}</span>
      {dot}
      <span>{formatCost(costUsd)}</span>
      {dot}
      <span style={{ color: ttfaMs ? "var(--mf-acc)" : "var(--mf-mute)" }}>
        TTFA {ttfaMs ? `${Math.round(ttfaMs)}ms` : "—"}
      </span>
      {dot}
      <span style={{ color: ttfiMs ? "var(--mf-acc)" : "var(--mf-mute)" }}>
        TTFI {ttfiMs ? `${Math.round(ttfiMs)}ms` : "—"}
      </span>
    </div>
  );
}
