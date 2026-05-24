// EdgeStateBanners — top-of-app warnings for non-runtime conditions:
//   - No API key configured (both providers missing)
//   - Budget approaching/over the monthly cap
//   - Last session closed by a kill switch (mic/cost/error)
//
// Live runtime states (WS down, reconnecting, failed) are surfaced by
// StatusBanner. These banners are config/usage-driven and pulled from the
// settings.get snapshot + the last session.closed reason.

import type { SettingsSnapshot } from "../lib/models";

const BANNER_BASE: React.CSSProperties = {
  margin: "8px 12px 0",
  padding: "8px 10px",
  borderRadius: 8,
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12,
  animation: "mf-slide-up 200ms ease-out",
};

export interface EdgeStateBannersProps {
  settings: SettingsSnapshot | null;
  /** Last session.closed reason or null. */
  closeReason: string | null;
  onOpenSettings: () => void;
}

export function EdgeStateBanners({ settings, closeReason, onOpenSettings }: EdgeStateBannersProps) {
  const noKey =
    settings !== null && settings.openaiKey === "absent" && settings.geminiKey === "absent";

  const monthlyPct = settings?.monthlyProgressPct ?? 0;
  const budgetOver = monthlyPct >= 100;
  const budgetWarn = !budgetOver && monthlyPct >= 80;

  const killReason = closeReason && closeReason.startsWith("kill_") ? closeReason : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {noKey ? (
        <button
          type="button"
          onClick={onOpenSettings}
          style={{
            ...BANNER_BASE,
            background: "var(--mf-danger-soft)",
            color: "var(--mf-danger)",
            border: "1px solid var(--mf-danger)",
            cursor: "pointer",
            textAlign: "left",
            font: "inherit",
          }}
          title="Open Settings → API Keys"
        >
          <Dot color="var(--mf-danger)" />
          <span style={{ flex: 1 }}>
            Aucune clé API configurée — Settings → API Keys
          </span>
          <span style={{ color: "var(--mf-danger)", opacity: 0.6 }}>↗</span>
        </button>
      ) : null}

      {budgetOver ? (
        <button
          type="button"
          onClick={onOpenSettings}
          style={{
            ...BANNER_BASE,
            background: "var(--mf-danger-soft)",
            color: "var(--mf-danger)",
            border: "1px solid var(--mf-danger)",
            cursor: "pointer",
            textAlign: "left",
            font: "inherit",
          }}
          title="Open Settings → Budget"
        >
          <Dot color="var(--mf-danger)" />
          <span style={{ flex: 1 }}>
            Budget mensuel dépassé : ${settings?.monthlyTotalUsd.toFixed(2)} / ${settings?.budgetCapUsd.toFixed(2)}
          </span>
          <span style={{ color: "var(--mf-danger)", opacity: 0.6 }}>↗</span>
        </button>
      ) : budgetWarn ? (
        <button
          type="button"
          onClick={onOpenSettings}
          style={{
            ...BANNER_BASE,
            background: "var(--mf-warn-soft)",
            color: "var(--mf-warn)",
            border: "1px solid rgba(255,183,77,0.4)",
            cursor: "pointer",
            textAlign: "left",
            font: "inherit",
          }}
          title="Open Settings → Budget"
        >
          <Dot color="var(--mf-warn)" />
          <span style={{ flex: 1 }}>
            {monthlyPct.toFixed(0)}% du budget utilisé ce mois (${settings?.monthlyTotalUsd.toFixed(2)})
          </span>
          <span style={{ color: "var(--mf-warn)", opacity: 0.6 }}>↗</span>
        </button>
      ) : null}

      {killReason ? (
        <div
          style={{
            ...BANNER_BASE,
            background: "var(--mf-warn-soft)",
            color: "var(--mf-warn)",
            border: "1px solid rgba(255,183,77,0.4)",
          }}
        >
          <Dot color="var(--mf-warn)" />
          <span style={{ flex: 1 }}>
            Dernière session arrêtée par kill switch :{" "}
            <code className="mf-mono" style={{ fontSize: 11 }}>{killReason}</code>
          </span>
        </div>
      ) : null}
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: color,
        boxShadow: `0 0 4px ${color}`,
        flexShrink: 0,
      }}
    />
  );
}
