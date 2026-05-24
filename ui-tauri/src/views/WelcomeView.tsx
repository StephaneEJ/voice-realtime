// Welcome popover — shown when no session is attached. Lists personas with
// ⌘1-9 shortcuts. Selected persona is highlighted. Bottom CTA shows the
// terminal command the user runs to start a session with the selected persona.
//
// Once Phase I (spawn-CLI-from-UI) ships, the CTA will actually launch the
// CLI as a hidden subprocess instead of asking the user to copy the command.

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

  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (personas.length === 0) return;
      // ⌘1 - ⌘9 to jump to a persona
      if (e.metaKey && e.key >= "1" && e.key <= "9") {
        const idx = parseInt(e.key, 10) - 1;
        if (idx < personas.length) {
          e.preventDefault();
          setSelectedIdx(idx);
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
    [personas.length],
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
          <CopyableCommand persona={selected.id} />
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
