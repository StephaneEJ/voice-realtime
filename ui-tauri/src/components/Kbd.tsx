// Keyboard shortcut chip — small monospace badge for shortcut hints.

import { CSSProperties } from "react";

const STYLE: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  minWidth: 16,
  height: 16,
  padding: "0 4px",
  borderRadius: 4,
  background: "var(--mf-panel-3)",
  border: "1px solid var(--mf-border-2)",
  color: "var(--mf-fg-2)",
  fontFamily: "var(--mf-mono)",
  fontSize: 10,
  letterSpacing: 0,
};

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd style={STYLE}>{children}</kbd>;
}
