// ControlTrio — mute / stop / expand round button cluster on the active
// session view. Matches the SVG icons used in design/midfi-main.jsx MfActive.

import { CSSProperties } from "react";

const BTN_LG: CSSProperties = {
  width: 36,
  height: 36,
  borderRadius: "50%",
  background: "var(--mf-panel-3)",
  color: "var(--mf-fg-2)",
  border: "1px solid var(--mf-border-2)",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  transition: "background 120ms, color 120ms, border-color 120ms",
};

const STOP_BTN: CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: "50%",
  background: "var(--mf-danger-soft)",
  color: "var(--mf-danger)",
  border: "1px solid var(--mf-danger)",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  boxShadow: "0 0 0 4px rgba(255,118,118,0.08)",
};

export function ControlTrio({
  muted,
  onMute,
  onStop,
  onExpand,
}: {
  muted: boolean;
  onMute: (next: boolean) => void;
  onStop: () => void;
  onExpand?: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        padding: "10px 12px 14px",
        borderTop: "1px solid var(--mf-border)",
        background: "rgba(255,255,255,0.015)",
      }}
    >
      <button
        type="button"
        title={muted ? "Unmute (⌘M)" : "Mute (⌘M)"}
        onClick={() => onMute(!muted)}
        style={{
          ...BTN_LG,
          ...(muted
            ? {
                background: "var(--mf-warn-soft)",
                color: "var(--mf-warn)",
                borderColor: "var(--mf-warn)",
              }
            : null),
        }}
      >
        {muted ? (
          // Mic with slash
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <rect x="6" y="2" width="4" height="6" rx="2" />
            <path d="M3 7v1a5 5 0 0 0 5 5M13 7v1a5 5 0 0 1-.6 2.4" />
            <line x1="2" y1="14" x2="14" y2="2" strokeWidth="1.6" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <rect x="6" y="2" width="4" height="8" rx="2" />
            <path d="M3 7v1a5 5 0 0 0 10 0V7" />
            <path d="M8 13v2" />
          </svg>
        )}
      </button>

      <button type="button" title="Stop (⌘.)" onClick={onStop} style={STOP_BTN}>
        <svg width="22" height="22" viewBox="0 0 22 22" fill="currentColor">
          <rect x="6" y="6" width="10" height="10" rx="1.5" />
        </svg>
      </button>

      <button
        type="button"
        title="Expand (⌘⇧E)"
        onClick={onExpand}
        style={{ ...BTN_LG, opacity: onExpand ? 1 : 0.4, cursor: onExpand ? "pointer" : "not-allowed" }}
        disabled={!onExpand}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
          <path d="M3 9v4h4M13 7V3H9M3 13l4-4M13 3l-4 4" />
        </svg>
      </button>
    </div>
  );
}
