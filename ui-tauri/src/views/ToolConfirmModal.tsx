// ToolConfirmModal — gate WRITE_USER_SCOPE+ tool calls behind explicit approval.
//
// Fires when the backend emits `tool.confirm_request` AND the active persona
// has `ask_before_acting: true`. The modal shows the tool name + args dump.
// User clicks Approve → CLI runs the tool; Reject → CLI sends an error
// response and the model continues without the result.
//
// The 60s server-side timeout is the safety net — if the user ignores the
// modal, the CLI auto-rejects so the model doesn't sit waiting forever.

import { useEffect } from "react";

export interface ToolConfirmRequest {
  callId: string;
  name: string;
  args: Record<string, unknown>;
  ts: number;
}

export interface ToolConfirmModalProps {
  request: ToolConfirmRequest | null;
  onDecide: (callId: string, approve: boolean) => void;
}

export function ToolConfirmModal({ request, onDecide }: ToolConfirmModalProps) {
  useEffect(() => {
    if (!request) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onDecide(request!.callId, false);
      } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        // ⌘↵ approves — keeps single keypress for the common (deny) path.
        e.preventDefault();
        onDecide(request!.callId, true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [request, onDecide]);

  if (!request) return null;

  const argsPreview = JSON.stringify(request.args, null, 2);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 300,
      }}
      onClick={() => onDecide(request.callId, false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(480px, 92vw)",
          background: "var(--mf-panel)",
          border: "1px solid var(--mf-warn)",
          borderRadius: 12,
          padding: 16,
          boxShadow: "0 12px 36px rgba(0,0,0,0.55)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>⚠</span>
          <span className="mf-display" style={{ fontSize: 14 }}>
            Confirmer l'action de l'outil
          </span>
        </div>

        <div>
          <span className="mf-label">Outil</span>
          <div
            style={{
              fontFamily: "var(--mf-mono)",
              fontSize: 13,
              background: "var(--mf-panel-2)",
              border: "1px solid var(--mf-border-2)",
              borderRadius: 6,
              padding: "6px 10px",
              color: "var(--mf-acc)",
            }}
          >
            {request.name}()
          </div>
        </div>

        <div>
          <span className="mf-label">Arguments</span>
          <pre
            style={{
              fontFamily: "var(--mf-mono)",
              fontSize: 11,
              background: "var(--mf-panel-2)",
              border: "1px solid var(--mf-border-2)",
              borderRadius: 6,
              padding: "8px 10px",
              color: "var(--mf-fg-2)",
              maxHeight: 200,
              overflow: "auto",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {argsPreview}
          </pre>
        </div>

        <p className="mf-cap mf-dim" style={{ margin: 0 }}>
          Le modèle attend ta décision. Sans réponse sous 60s, l'appel est refusé automatiquement.
          <br />
          <kbd>Esc</kbd> = refuser, <kbd>⌘↵</kbd> = approuver.
        </p>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => onDecide(request.callId, false)}
            style={{
              background: "var(--mf-panel-3)",
              color: "var(--mf-fg-2)",
              border: "1px solid var(--mf-border-2)",
              borderRadius: 6,
              padding: "8px 14px",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Refuser
          </button>
          <button
            type="button"
            onClick={() => onDecide(request.callId, true)}
            style={{
              background: "var(--mf-warn)",
              color: "rgba(0,0,0,0.85)",
              border: "none",
              borderRadius: 6,
              padding: "8px 14px",
              fontWeight: 600,
              fontSize: 12,
              cursor: "pointer",
            }}
            autoFocus
          >
            Approuver
          </button>
        </div>
      </div>
    </div>
  );
}
