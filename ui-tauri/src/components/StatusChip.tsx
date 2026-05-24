// Pill-shaped status chip — variants: live (green dot), warn, idle.

import { CSSProperties } from "react";

const BASE: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  height: 22,
  padding: "0 8px",
  borderRadius: 11,
  fontSize: 11,
  fontWeight: 500,
  fontFamily: "var(--mf-mono)",
};

export type ChipVariant = "live" | "idle" | "warn" | "error";

const VARIANT: Record<ChipVariant, CSSProperties> = {
  live: {
    background: "var(--mf-ok-soft)",
    color: "var(--mf-ok)",
    border: "1px solid rgba(128,226,126,0.3)",
  },
  idle: {
    background: "var(--mf-panel-3)",
    color: "var(--mf-dim)",
    border: "1px solid var(--mf-border-2)",
  },
  warn: {
    background: "var(--mf-warn-soft)",
    color: "var(--mf-warn)",
    border: "1px solid rgba(255,183,77,0.3)",
  },
  error: {
    background: "var(--mf-danger-soft)",
    color: "var(--mf-danger)",
    border: "1px solid rgba(255,118,118,0.3)",
  },
};

export function StatusChip({
  variant = "idle",
  children,
}: {
  variant?: ChipVariant;
  children: React.ReactNode;
}) {
  const showDot = variant === "live";
  return (
    <span style={{ ...BASE, ...VARIANT[variant] }}>
      {showDot ? (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "var(--mf-ok)",
            boxShadow: "0 0 4px var(--mf-ok)",
            animation: "mf-blink 1.4s ease-in-out infinite",
          }}
        />
      ) : null}
      {children}
    </span>
  );
}
