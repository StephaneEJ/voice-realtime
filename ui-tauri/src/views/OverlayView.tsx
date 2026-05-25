// OverlayView — secondary always-on-top window that mirrors the live session
// at a glance. Companion to the main app's ActiveSessionView.
//
// Rendered when the Tauri entry point detects `?overlay=1` in window.location
// (see main.tsx). Connects to the same control_server WS as the main App,
// reads the live session events, and renders:
//
//   - Avatar XXL (current persona)
//   - RadialSpectrum centred on the model's VU level
//   - Minimal MetricsStrip (duration, cost, tokens)
//   - Tiny 30-day cost sparkline (placeholder until cost.history WS event)
//
// The overlay holds NO controls (mute/stop) — that's the main window's job.
// It's a pure status surface, anchored on-screen so the user can keep an eye
// on the session while working in another window.

import { useCallback, useEffect, useRef, useState } from "react";
import { Avatar } from "../components/Avatar";
import { RadialSpectrum } from "../components/RadialSpectrum";
import {
  Persona,
  SessionMetrics,
  VULevels,
  WSEvent,
  emptyVULevels,
  formatCost,
  formatDuration,
  pushVULevel,
} from "../lib/models";
import { createVoiceRTClient, VoiceRTClient } from "../lib/ws-client";

const EMPTY_METRICS: SessionMetrics = {
  durationSeconds: 0,
  costUsd: 0,
  ttfaMs: null,
  ttfiMs: null,
  tokensIn: 0,
  tokensOut: 0,
  tokensTotal: 0,
  tokensCapModel: 0,
};

export function OverlayView() {
  const clientRef = useRef<VoiceRTClient | null>(null);
  const [personaList, setPersonaList] = useState<Persona[]>([]);
  const [sessionPersonaId, setSessionPersonaId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SessionMetrics>(EMPTY_METRICS);
  const [vu, setVU] = useState<VULevels>(emptyVULevels);
  const [muted, setMuted] = useState(false);
  const [live, setLive] = useState(false);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.ev) {
      case "personas.list":
        setPersonaList(event.personas);
        break;
      case "session.opened":
        setLive(true);
        setSessionPersonaId(event.personaId);
        clientRef.current?.send({ op: "personas.list" });
        break;
      case "session.closed":
        setLive(false);
        setMetrics(EMPTY_METRICS);
        break;
      case "audio.model.frame":
        setVU((prev) => ({ ...prev, model: pushVULevel(prev.model, event.rms) }));
        break;
      case "audio.user.frame":
        setVU((prev) => ({ ...prev, user: pushVULevel(prev.user, event.rms) }));
        break;
      case "cost.tick":
        setMetrics((m) => ({
          ...m,
          costUsd: event.total,
          durationSeconds: event.elapsed,
          tokensIn: event.tokensIn ?? m.tokensIn,
          tokensOut: event.tokensOut ?? m.tokensOut,
          tokensTotal: event.tokensTotal ?? m.tokensTotal,
          tokensCapModel: event.tokensCapModel ?? m.tokensCapModel,
        }));
        break;
      case "mute.state":
        setMuted(event.on);
        break;
    }
  }, []);

  const persona = personaList.find((p) => p.id === sessionPersonaId) ?? null;

  useEffect(() => {
    const client = createVoiceRTClient();
    clientRef.current = client;
    const off = client.onEvent(handleEvent);
    client.connect();
    return () => {
      off();
      client.disconnect();
    };
  }, [handleEvent]);

  const tokensPct = metrics.tokensCapModel > 0
    ? (metrics.tokensTotal / metrics.tokensCapModel) * 100
    : 0;

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "rgba(20, 22, 27, 0.85)",
        color: "var(--mf-fg)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: 24,
        userSelect: "none",
        // Drag the borderless window by grabbing the background.
        // (data-tauri-drag-region propagates click drags to the OS).
      }}
      data-tauri-drag-region
    >
      <div style={{ position: "relative", width: 200, height: 200 }}>
        <RadialSpectrum
          size={200}
          innerRadius={56}
          values={vu.model}
          color="var(--mf-acc)"
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Avatar personaId={persona?.id ?? "jarvis"} size="xxl" live={live} />
        </div>
      </div>

      <div style={{
        fontFamily: "var(--mf-mono)",
        fontSize: 12,
        color: live ? "var(--mf-acc)" : "var(--mf-dim)",
        letterSpacing: 0.4,
      }}>
        {live ? (muted ? "muted" : "live") : "idle"}
      </div>

      <div style={{
        display: "flex",
        gap: 12,
        fontFamily: "var(--mf-mono)",
        fontSize: 11,
        color: "var(--mf-dim)",
      }}>
        <span>{formatDuration(metrics.durationSeconds)}</span>
        <span>·</span>
        <span>{formatCost(metrics.costUsd)}</span>
        {metrics.tokensCapModel > 0 ? (
          <>
            <span>·</span>
            <span style={{
              color: tokensPct >= 90 ? "var(--mf-danger)" :
                     tokensPct >= 70 ? "var(--mf-warn)" :
                     "var(--mf-dim)",
            }}>
              {tokensPct.toFixed(0)}%
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}
