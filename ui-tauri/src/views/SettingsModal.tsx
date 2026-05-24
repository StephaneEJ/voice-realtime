// Settings modal — read-mostly snapshot of config + usage + personas list.
// 4 tabs: Keys / Models / Budget / Personas. Writes are deferred to a future
// phase (file rewriting via Tauri fs plugin) — for now the modal shows the
// secrets file path and asks the user to edit manually.

import { useEffect, useState } from "react";
import { Avatar } from "../components/Avatar";
import { StatusChip } from "../components/StatusChip";
import type { Persona, SettingsSnapshot } from "../lib/models";

export type SettingsTab = "keys" | "models" | "budget" | "personas";

export interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  settings: SettingsSnapshot | null;
  personas: Persona[];
  /** Triggered when the modal opens — parent should send WSCommand settings.get. */
  onRefresh: () => void;
}

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "keys", label: "API Keys" },
  { id: "models", label: "Models" },
  { id: "budget", label: "Budget" },
  { id: "personas", label: "Personas" },
];

export function SettingsModal({ open, onClose, settings, personas, onRefresh }: SettingsModalProps) {
  const [tab, setTab] = useState<SettingsTab>("keys");

  useEffect(() => {
    if (!open) return;
    onRefresh();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, onRefresh]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
        animation: "mf-spring-in 180ms ease-out",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(460px, 92vw)",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          background: "var(--mf-panel)",
          border: "1px solid var(--mf-border-2)",
          borderRadius: 14,
          overflow: "hidden",
          boxShadow: "0 16px 50px rgba(0,0,0,0.55), 0 0 0 1px rgba(0,0,0,0.5)",
        }}
      >
        <header
          style={{
            padding: "12px 14px 8px",
            borderBottom: "1px solid var(--mf-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span className="mf-display" style={{ fontSize: 15 }}>
            Settings
          </span>
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            style={{
              width: 24,
              height: 24,
              borderRadius: 6,
              background: "transparent",
              border: "1px solid var(--mf-border-2)",
              color: "var(--mf-dim)",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 14,
            }}
          >
            ✕
          </button>
        </header>

        <div
          style={{
            display: "flex",
            gap: 2,
            padding: "8px 8px 0",
            borderBottom: "1px solid var(--mf-border)",
          }}
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              style={{
                padding: "8px 12px",
                background: tab === t.id ? "var(--mf-panel-2)" : "transparent",
                color: tab === t.id ? "var(--mf-fg)" : "var(--mf-dim)",
                border: "none",
                borderTopLeftRadius: 6,
                borderTopRightRadius: 6,
                borderBottom: tab === t.id ? "1px solid var(--mf-acc)" : "1px solid transparent",
                fontFamily: "var(--mf-sans)",
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
                transition: "background 120ms, color 120ms, border-color 120ms",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div
          className="mf-scroll"
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 14,
          }}
        >
          {settings === null ? (
            <p className="mf-dim mf-body">Chargement…</p>
          ) : tab === "keys" ? (
            <KeysTab settings={settings} />
          ) : tab === "models" ? (
            <ModelsTab settings={settings} />
          ) : tab === "budget" ? (
            <BudgetTab settings={settings} />
          ) : (
            <PersonasTab personas={personas} />
          )}
        </div>
      </div>
    </div>
  );
}

function KeysTab({ settings }: { settings: SettingsSnapshot }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <KeyRow label="OpenAI Realtime" present={settings.openaiKey === "present"} />
      <KeyRow label="Gemini Live" present={settings.geminiKey === "present"} />
      <div className="mf-card" style={{ padding: 10 }}>
        <span className="mf-label">Edit file</span>
        <code className="mf-mono mf-acc" style={{ fontSize: 11, display: "block", marginTop: 4, wordBreak: "break-all" }}>
          {settings.secretsPath}
        </code>
        <p className="mf-cap mf-dim" style={{ marginTop: 6 }}>
          Write OPENAI_API_KEY=… and GEMINI_API_KEY=… one per line. Restart the CLI
          to pick up changes.
        </p>
      </div>
    </div>
  );
}

function KeyRow({ label, present }: { label: string; present: boolean }) {
  return (
    <div className="mf-card" style={{ padding: 10, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <span className="mf-title" style={{ fontSize: 13 }}>{label}</span>
      <StatusChip variant={present ? "live" : "warn"}>{present ? "configured" : "missing"}</StatusChip>
    </div>
  );
}

function ModelsTab({ settings }: { settings: SettingsSnapshot }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <ModelCard provider="OpenAI Realtime" model={settings.defaultModelOpenai} accent="var(--mf-acc)" />
      <ModelCard provider="Gemini Live" model={settings.defaultModelGemini} accent="#c084fc" />
      <p className="mf-cap mf-dim">
        Override per-session with <code>--model</code>. Set per-persona defaults in the persona's
        frontmatter (model: field).
      </p>
    </div>
  );
}

function ModelCard({ provider, model, accent }: { provider: string; model: string; accent: string }) {
  return (
    <div className="mf-card" style={{ padding: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span className="mf-title" style={{ fontSize: 13 }}>{provider}</span>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: accent }} />
      </div>
      <code className="mf-mono" style={{ fontSize: 11, color: "var(--mf-fg-2)", display: "block", marginTop: 4 }}>
        {model}
      </code>
    </div>
  );
}

function BudgetTab({ settings }: { settings: SettingsSnapshot }) {
  const pct = settings.monthlyProgressPct;
  const danger = pct >= 100;
  const warn = pct >= 80 && pct < 100;
  const barColor = danger ? "var(--mf-danger)" : warn ? "var(--mf-warn)" : "var(--mf-acc)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="mf-card" style={{ padding: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <span className="mf-label">This month</span>
          <span className="mf-mono" style={{ fontSize: 15, color: barColor }}>
            ${settings.monthlyTotalUsd.toFixed(2)} / ${settings.budgetCapUsd.toFixed(2)}
          </span>
        </div>
        <div
          style={{
            marginTop: 8,
            height: 6,
            background: "var(--mf-panel-3)",
            borderRadius: 3,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${Math.min(100, pct)}%`,
              height: "100%",
              background: barColor,
              transition: "width 240ms",
            }}
          />
        </div>
        <p className="mf-cap mf-dim" style={{ marginTop: 6 }}>
          {pct.toFixed(1)}% of cap used
        </p>
      </div>

      <div className="mf-card" style={{ padding: 12 }}>
        <span className="mf-label">Today</span>
        <p className="mf-mono" style={{ fontSize: 15, color: "var(--mf-fg)" }}>
          ${settings.dailyTotalUsd.toFixed(2)}
        </p>
      </div>

      <p className="mf-cap mf-dim">
        Edit <code>VOICE_REALTIME_MONTHLY_BUDGET_USD</code> in <code>{settings.secretsPath.split("/").slice(-2).join("/")}</code>
        {" "}to change the cap.
      </p>
    </div>
  );
}

function PersonasTab({ personas }: { personas: Persona[] }) {
  if (personas.length === 0) {
    return <p className="mf-dim mf-body">Aucune persona — vérifie <code>_System/voice-personas/</code> dans le vault.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {personas.map((p) => (
        <div key={p.id} className="mf-card" style={{ padding: 10, display: "flex", alignItems: "center", gap: 10 }}>
          <Avatar personaId={p.id} size="md" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="mf-title" style={{ fontSize: 13 }}>{p.name}</span>
              {p.hasObsidianFilter ? <StatusChip variant="idle">vault</StatusChip> : null}
            </div>
            <span
              className="mf-cap mf-dim"
              style={{
                display: "block",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {p.description || p.provider || "—"}
            </span>
          </div>
          <span className="mf-cap mf-mono mf-dim" style={{ fontSize: 10 }}>{p.id}</span>
        </div>
      ))}
      <p className="mf-cap mf-dim">
        Edit personas in <code>_System/voice-personas/&lt;slug&gt;.md</code>. Per-file frontmatter
        controls voice, model, vad, obsidian filter.
      </p>
    </div>
  );
}
