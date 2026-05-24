// Banner shown when the WS client is not in `connected` state. Helps user
// understand whether the CLI is reachable, retrying, or has given up.

import type { ConnectionState } from "../lib/ws-client";

export function StatusBanner({
  state,
  attempt,
}: {
  state: ConnectionState;
  attempt: number;
}) {
  if (state === "connected") return null;

  const labels: Record<ConnectionState, string> = {
    disconnected: "Déconnecté de la CLI",
    connecting: "Connexion à la CLI…",
    connected: "Connecté",
    reconnecting: `Reconnexion (essai ${attempt})…`,
    failed: "Connexion impossible — lance d'abord `voice-realtime talk --ui` dans un terminal.",
  };

  const isError = state === "failed";

  return (
    <div
      className="mf-card"
      style={{
        margin: "12px 12px 0",
        padding: "10px 12px",
        borderColor: isError ? "var(--mf-danger)" : "var(--mf-warn)",
        background: isError ? "var(--mf-danger-soft)" : "var(--mf-warn-soft)",
        animation: "mf-slide-up 200ms ease-out",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: isError ? "var(--mf-danger)" : "var(--mf-warn)",
            animation: state === "reconnecting" ? "mf-blink 1.4s ease-in-out infinite" : undefined,
            flexShrink: 0,
          }}
        />
        <span className="mf-body" style={{ color: isError ? "var(--mf-danger)" : "var(--mf-warn)" }}>
          {labels[state]}
        </span>
      </div>
    </div>
  );
}
