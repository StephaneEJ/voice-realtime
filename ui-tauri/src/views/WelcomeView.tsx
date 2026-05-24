// Welcome popover — shown when no session is attached. Lists personas with
// ⌘1-9 shortcuts. Selected persona is highlighted. Bottom CTA shows the
// terminal command the user runs to start a session with the selected persona.
//
// Once Phase I (spawn-CLI-from-UI) ships, the CTA will actually launch the
// CLI as a hidden subprocess instead of asking the user to copy the command.

import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState } from "react";
import { Avatar } from "../components/Avatar";
import { Kbd } from "../components/Kbd";
import { StatusChip } from "../components/StatusChip";
import type { Persona } from "../lib/models";

export interface WelcomeViewProps {
  personas: Persona[];
  closeReason: string | null;
  onSettings: () => void;
}

export function WelcomeView({ personas, closeReason, onSettings }: WelcomeViewProps) {
  // Auto-select the first persona by default; arrow keys + ⌘N (number) cycle.
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    if (selectedIdx >= personas.length && personas.length > 0) {
      setSelectedIdx(0);
    }
  }, [personas.length, selectedIdx]);

  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const launchSession = useCallback(async (personaId: string) => {
    setLaunching(true);
    setLaunchError(null);
    try {
      await invoke("spawn_cli_session", { persona: personaId });
      // Server.session.opened will be broadcast within ~3s when the CLI
      // connects to its provider; the parent App.tsx flips to ActiveSession
      // automatically on that event. Keep the spinner briefly so the user
      // sees feedback.
      window.setTimeout(() => setLaunching(false), 4000);
    } catch (err) {
      setLaunchError(String(err));
      setLaunching(false);
    }
  }, []);

  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (personas.length === 0) return;
      // ⌘↵ → launch selected
      if (e.metaKey && e.key === "Enter") {
        e.preventDefault();
        if (personas[selectedIdx]) {
          void launchSession(personas[selectedIdx].id);
        }
        return;
      }
      // ⌘1 - ⌘9 to jump to a persona — use e.code (physical key) instead
      // of e.key (logical), so AZERTY/QWERTZ users hit Digit1 even though
      // the typed character would be & or ! without Shift.
      if (e.metaKey && e.code.startsWith("Digit")) {
        const digit = parseInt(e.code.slice(5), 10);
        if (digit >= 1 && digit <= 9) {
          const idx = digit - 1;
          if (idx < personas.length) {
            e.preventDefault();
            setSelectedIdx(idx);
          }
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIdx((i) => Math.min(personas.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIdx((i) => Math.max(0, i - 1));
      }
    },
    [personas, selectedIdx, launchSession],
  );

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  const selected = personas[selectedIdx];

  return (
    <div className="mf" style={{ display: "flex", flexDirection: "column", height: "100%", padding: 0 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 14px 6px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="mf-display" style={{ fontSize: 15 }}>
            Personas
          </span>
          <StatusChip variant="idle">idle</StatusChip>
        </div>
        <button
          type="button"
          onClick={onSettings}
          title="Settings (⌘,)"
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            background: "var(--mf-panel-3)",
            border: "1px solid var(--mf-border-2)",
            color: "var(--mf-dim)",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
          }}
        >
          ⚙
        </button>
      </header>

      {closeReason ? (
        <div
          className="mf-card"
          style={{
            margin: "0 12px 8px",
            padding: "8px 10px",
            borderColor: closeReason.startsWith("kill_") ? "var(--mf-warn)" : undefined,
          }}
        >
          <span className="mf-cap mf-dim">Dernière session</span>
          <p className="mf-body" style={{ margin: 0 }}>
            Fermée — <span className="mf-mono">{closeReason}</span>
          </p>
        </div>
      ) : null}

      <div
        className="mf-scroll"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "4px 8px 96px",
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        {personas.length === 0 ? (
          <p className="mf-dim mf-body" style={{ padding: 12 }}>
            Aucune persona — vérifie <code>_System/voice-personas/</code> dans le vault.
          </p>
        ) : (
          personas.map((p, i) => {
            const sel = i === selectedIdx;
            return (
              <button
                type="button"
                key={p.id}
                onClick={() => setSelectedIdx(i)}
                style={{
                  background: sel ? "var(--mf-acc-soft)" : "transparent",
                  border: sel ? "1px solid var(--mf-acc)" : "1px solid transparent",
                  borderRadius: 9,
                  padding: "8px 10px",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  cursor: "pointer",
                  textAlign: "left",
                  color: "inherit",
                  font: "inherit",
                  transition: "background 120ms, border-color 120ms",
                }}
              >
                <Avatar personaId={p.id} size="md" />
                <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
                  <span className="mf-title" style={{ fontSize: 14 }}>
                    {p.name}
                  </span>
                  <span
                    className="mf-cap mf-dim"
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {p.description || p.provider || "—"}
                  </span>
                </div>
                {i < 9 ? <Kbd>⌘{i + 1}</Kbd> : null}
              </button>
            );
          })
        )}
      </div>

      {selected ? (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: 12,
            background: "linear-gradient(180deg, transparent 0%, var(--mf-bg) 30%)",
            borderTop: "1px solid var(--mf-border)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 9,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <span className="mf-title" style={{ fontSize: 13.5 }}>
                {selected.name} {selected.description ? `· ${selected.description.slice(0, 30)}` : ""}
              </span>
              <span className="mf-cap mf-mono mf-dim">
                {selected.provider ?? "default provider"} · {selected.model ?? "default model"}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void launchSession(selected.id)}
            disabled={launching}
            style={{
              width: "100%",
              background: launching ? "var(--mf-panel-3)" : "var(--mf-acc)",
              color: launching ? "var(--mf-dim)" : "rgba(0,0,0,0.85)",
              border: "none",
              borderRadius: 8,
              padding: "10px 12px",
              cursor: launching ? "wait" : "pointer",
              font: "inherit",
              fontWeight: 600,
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
              transition: "background 160ms",
            }}
            title="⌘↵ to start"
          >
            <span style={{ fontSize: 11 }}>{launching ? "⏳" : "▶"}</span>
            {launching ? "Launching CLI…" : `Start with ${selected.name}`}
            <span style={{ marginLeft: "auto", display: "flex", gap: 3 }}>
              <Kbd>⌘</Kbd>
              <Kbd>↵</Kbd>
            </span>
          </button>
          {launchError ? (
            <p
              className="mf-cap"
              style={{ color: "var(--mf-danger)", marginTop: 6, marginBottom: 0, fontSize: 11 }}
            >
              {launchError}
            </p>
          ) : null}
          <details style={{ marginTop: 6 }}>
            <summary className="mf-cap mf-dim" style={{ cursor: "pointer", fontSize: 10 }}>
              or run manually in terminal
            </summary>
            <CopyableCommand persona={selected.id} />
          </details>
        </div>
      ) : null}
    </div>
  );
}

function CopyableCommand({ persona }: { persona: string }) {
  const cmd = `voice-realtime talk --ui --persona ${persona}`;
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch (err) {
      console.warn("clipboard write failed", err);
    }
  }, [cmd]);

  return (
    <button
      type="button"
      onClick={copy}
      style={{
        width: "100%",
        background: copied ? "var(--mf-ok-soft)" : "var(--mf-panel-2)",
        border: `1px solid ${copied ? "var(--mf-ok)" : "var(--mf-border-2)"}`,
        borderRadius: 8,
        padding: "10px 12px",
        cursor: "pointer",
        color: "var(--mf-fg)",
        textAlign: "left",
        font: "inherit",
        display: "flex",
        alignItems: "center",
        gap: 10,
        transition: "background 160ms, border-color 160ms",
      }}
      title="Click to copy"
    >
      <span className="mf-mono mf-acc" style={{ fontSize: 11, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        $ {cmd}
      </span>
      <span className="mf-cap mf-dim" style={{ fontSize: 10 }}>
        {copied ? "copied ✓" : "click to copy"}
      </span>
    </button>
  );
}
