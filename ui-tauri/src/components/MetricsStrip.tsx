// Compact monospace strip showing live session numbers.
// Mirrors the layout in design/midfi-main.jsx MfActive metrics row.

import { formatCost, formatDuration } from "../lib/models";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function MetricsStrip({
  durationSeconds,
  costUsd,
  ttfaMs,
  ttfiMs,
  tokensTotal,
  tokensCapModel,
}: {
  durationSeconds: number;
  costUsd: number;
  ttfaMs: number | null;
  ttfiMs: number | null;
  tokensTotal?: number;
  tokensCapModel?: number;
}) {
  const dot = <span style={{ color: "var(--mf-mute)" }}>·</span>;
  // Sprint 4 token budget viz — values are PROXY estimates (elapsed × rate),
  // not real provider counters yet. Colour ramps amber > 70%, red > 90%.
  let tokensNode: React.ReactNode = null;
  if (tokensTotal != null && tokensCapModel != null && tokensCapModel > 0) {
    const pct = (tokensTotal / tokensCapModel) * 100;
    const colour =
      pct >= 90 ? "var(--mf-danger)" :
      pct >= 70 ? "var(--mf-warn)" :
      "var(--mf-dim)";
    tokensNode = (
      <>
        {dot}
        <span style={{ color: colour }} title={`${tokensTotal.toLocaleString()} / ${tokensCapModel.toLocaleString()}`}>
          {formatTokens(tokensTotal)}/{formatTokens(tokensCapModel)} ({pct.toFixed(1)}%)
        </span>
      </>
    );
  }
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
      {tokensNode}
    </div>
  );
}
