// Active session view — full live session UX:
//   - persona avatar with radial spectrum (VU-driven bars)
//   - rolling transcript bubbles (user right, model left)
//   - control trio (mute / stop / expand)
//   - metrics strip (mm:ss · $cost · TTFA · TTFI)
//
// Keyboard shortcuts: ⌘M mute, ⌘. stop.

import { useEffect, useMemo, useRef } from "react";
import { Avatar } from "../components/Avatar";
import { Bubble } from "../components/Bubble";
import { ControlTrio } from "../components/ControlTrio";
import { MetricsStrip } from "../components/MetricsStrip";
import { RadialSpectrum } from "../components/RadialSpectrum";
import { StatusChip } from "../components/StatusChip";
import {
  formatDuration,
  SessionMetrics,
  TranscriptTurn,
  VULevels,
} from "../lib/models";

export interface LiveSession {
  sessionId: string;
  personaId: string;
  model: string;
  provider: string;
  voice: string;
}

export interface ActiveSessionViewProps {
  session: LiveSession;
  turns: TranscriptTurn[];
  metrics: SessionMetrics;
  vu: VULevels;
  muted: boolean;
  onMute: (next: boolean) => void;
  onStop: () => void;
}

export function ActiveSessionView({
  session,
  turns,
  metrics,
  vu,
  muted,
  onMute,
  onStop,
}: ActiveSessionViewProps) {
  // Auto-scroll transcript to the bottom on new turns.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [turns.length, turns[turns.length - 1]?.text]);

  // Keyboard shortcuts.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey && e.key === "m") {
        e.preventDefault();
        onMute(!muted);
      } else if (e.metaKey && e.key === ".") {
        e.preventDefault();
        onStop();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [muted, onMute, onStop]);

  // The radial spectrum uses both user + model RMS interleaved, so the bars
  // animate from both sides simultaneously. The merge avoids needing two
  // spectrums stacked on top of each other.
  const mergedVU = useMemo(() => {
    const out = new Array(48).fill(0);
    for (let i = 0; i < 48; i += 1) {
      const u = vu.user[i % vu.user.length] ?? 0;
      const m = vu.model[i % vu.model.length] ?? 0;
      out[i] = Math.max(u, m);
    }
    return out;
  }, [vu]);

  const radialColor = muted ? "var(--mf-warn)" : "var(--mf-acc)";

  return (
    <div className="mf" style={{ display: "flex", flexDirection: "column", height: "100%", padding: 0 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 12px 6px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Avatar personaId={session.personaId} size="sm" live />
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            <span className="mf-title" style={{ fontSize: 13 }}>
              {session.personaId}
            </span>
            <span className="mf-cap mf-mono mf-dim">{session.model}</span>
          </div>
        </div>
        <StatusChip variant={muted ? "warn" : "live"}>
          {muted ? "muted" : formatDuration(metrics.durationSeconds)}
        </StatusChip>
      </header>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 4,
          paddingTop: 12,
          paddingBottom: 6,
        }}
      >
        <div style={{ width: 168, height: 168, position: "relative" }}>
          <RadialSpectrum size={168} innerRadius={56} count={48} values={mergedVU} color={radialColor} />
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Avatar personaId={session.personaId} size="xxl" live={!muted} />
          </div>
        </div>
        <span className="mf-display" style={{ fontSize: 18, marginTop: 4 }}>
          {session.personaId}
        </span>
        <span className="mf-cap mf-dim">{session.provider} · {session.voice}</span>
      </div>

      <div
        ref={scrollRef}
        className="mf-scroll"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          minHeight: 100,
        }}
      >
        {turns.length === 0 ? (
          <p className="mf-dim mf-body" style={{ textAlign: "center", margin: "auto" }}>
            En attente du premier tour…
          </p>
        ) : (
          turns.map((t) => <Bubble key={t.id} role={t.role} text={t.text} partial={t.partial} />)
        )}
      </div>

      <ControlTrio muted={muted} onMute={onMute} onStop={onStop} />
      <MetricsStrip
        durationSeconds={metrics.durationSeconds}
        costUsd={metrics.costUsd}
        ttfaMs={metrics.ttfaMs}
        ttfiMs={metrics.ttfiMs}
        tokensTotal={metrics.tokensTotal}
        tokensCapModel={metrics.tokensCapModel}
      />
    </div>
  );
}
