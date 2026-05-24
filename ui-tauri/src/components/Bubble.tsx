// Transcript bubble — user (right-aligned, accent) or model (left, panel).
// Adds a soft fade-in when a new bubble appears.

import { CSSProperties } from "react";
import type { TranscriptRole } from "../lib/models";

const BASE: CSSProperties = {
  maxWidth: "82%",
  padding: "7px 11px",
  borderRadius: 12,
  fontSize: 13,
  lineHeight: 1.4,
  wordBreak: "break-word",
  animation: "mf-bubble-in 180ms ease-out",
};

export function Bubble({
  role,
  text,
  partial,
}: {
  role: TranscriptRole;
  text: string;
  partial: boolean;
}) {
  const userStyle: CSSProperties = {
    ...BASE,
    alignSelf: "flex-end",
    background: "var(--mf-acc-soft)",
    color: "var(--mf-acc)",
    borderTopRightRadius: 4,
  };
  const modelStyle: CSSProperties = {
    ...BASE,
    alignSelf: "flex-start",
    background: "var(--mf-panel-2)",
    color: "var(--mf-fg)",
    borderTopLeftRadius: 4,
    opacity: partial ? 0.7 : 1,
  };
  return (
    <div style={role === "user" ? userStyle : modelStyle}>
      {text}
      {partial && role === "model" ? (
        <span style={{ marginLeft: 4, opacity: 0.5, animation: "mf-blink 1.4s ease-in-out infinite" }}>▌</span>
      ) : null}
    </div>
  );
}
