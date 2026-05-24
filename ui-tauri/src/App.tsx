// ─────────────────────────────────────────────────────────────────────────
// App.tsx — voice-realtime UI shell (MVP)
//
// Connects to the CLI's control_server on ws://127.0.0.1:7711 and renders
// three states:
//   - disconnected/reconnecting → status banner with retry indicator
//   - connected (no session)    → personas list (informational)
//   - connected + session live  → live transcript + mute/stop controls
//
// The CLI keeps full ownership of audio I/O. This UI never captures the mic
// or plays audio — it just observes events and sends commands.
// ─────────────────────────────────────────────────────────────────────────

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ConnectionState,
  createVoiceRTClient,
  VoiceRTClient,
} from "./lib/ws-client";
import {
  formatCost,
  formatDuration,
  Persona,
  SessionMetrics,
  TranscriptTurn,
  WSEvent,
} from "./lib/models";
import "./styles/midfi.css";

interface LiveSession {
  sessionId: string;
  personaId: string;
  model: string;
  provider: string;
  voice: string;
}

function App() {
  const clientRef = useRef<VoiceRTClient | null>(null);
  const [connState, setConnState] = useState<ConnectionState>("disconnected");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [session, setSession] = useState<LiveSession | null>(null);
  const [closeReason, setCloseReason] = useState<string | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [metrics, setMetrics] = useState<SessionMetrics>({
    durationSeconds: 0,
    costUsd: 0,
    ttfaMs: null,
    ttfiMs: null,
    tokensIn: 0,
    tokensOut: 0,
  });
  const [muted, setMuted] = useState(false);
  const [userRms, setUserRms] = useState(0);
  const [modelRms, setModelRms] = useState(0);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.ev) {
      case "personas.list":
        setPersonas(event.personas);
        break;
      case "session.opened":
        setSession({
          sessionId: event.sessionId,
          personaId: event.personaId,
          model: event.model,
          provider: event.provider,
          voice: event.voice,
        });
        setCloseReason(null);
        setTurns([]);
        setMetrics({
          durationSeconds: 0,
          costUsd: 0,
          ttfaMs: null,
          ttfiMs: null,
          tokensIn: 0,
          tokensOut: 0,
        });
        setMuted(false);
        break;
      case "session.closed":
        setSession(null);
        setCloseReason(event.reason);
        break;
      case "transcript.delta":
        setTurns((prev) => {
          // Update the last turn if it matches role + is still partial; else append.
          const last = prev[prev.length - 1];
          if (last && last.partial && last.role === event.role) {
            const updated: TranscriptTurn = { ...last, text: last.text + event.text };
            return [...prev.slice(0, -1), updated];
          }
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: event.role,
              text: event.text,
              partial: true,
              createdAt: Date.now(),
            },
          ];
        });
        break;
      case "transcript.final":
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.partial && last.role === event.role) {
            const finalized: TranscriptTurn = { ...last, text: event.text, partial: false };
            return [...prev.slice(0, -1), finalized];
          }
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: event.role,
              text: event.text,
              partial: false,
              createdAt: Date.now(),
            },
          ];
        });
        break;
      case "audio.user.frame":
        setUserRms(event.rms);
        break;
      case "audio.model.frame":
        setModelRms(event.rms);
        break;
      case "ttfa":
        setMetrics((m) => ({ ...m, ttfaMs: event.ms }));
        break;
      case "ttfi":
        setMetrics((m) => ({ ...m, ttfiMs: event.ms }));
        break;
      case "cost.tick":
        setMetrics((m) => ({
          ...m,
          costUsd: event.total,
          durationSeconds: event.elapsed,
        }));
        break;
      case "mute.state":
        setMuted(event.on);
        break;
      case "model.interrupted":
        // Just a metric signal; ttfi event follows with the actual number.
        break;
      case "error":
        console.error("[server error]", event.code, event.msg);
        break;
    }
  }, []);

  useEffect(() => {
    const client = createVoiceRTClient();
    clientRef.current = client;
    const offEvent = client.onEvent(handleEvent);
    const offState = client.onState((next, attempt) => {
      setConnState(next);
      setReconnectAttempt(attempt);
      if (next === "connected") {
        client.send({ op: "personas.list" });
      }
    });
    client.connect();
    return () => {
      offEvent();
      offState();
      client.disconnect();
    };
  }, [handleEvent]);

  const requestMute = useCallback((on: boolean) => {
    clientRef.current?.send({ op: "mute", on });
  }, []);

  const requestStop = useCallback(() => {
    clientRef.current?.send({ op: "session.stop" });
  }, []);

  const banner = useMemo(() => {
    if (connState === "connected") return null;
    const labelByState: Record<ConnectionState, string> = {
      disconnected: "Disconnected from CLI",
      connecting: "Connecting to CLI…",
      connected: "Connected",
      reconnecting: `Reconnecting (attempt ${reconnectAttempt})…`,
      failed: "Failed to connect — start `voice-realtime talk --ui` first.",
    };
    return (
      <div className="mf-card" style={{ borderColor: connState === "failed" ? "var(--mf-danger)" : undefined }}>
        <span className="mf-label">Status</span>
        <p className="mf-body">{labelByState[connState]}</p>
      </div>
    );
  }, [connState, reconnectAttempt]);

  return (
    <div className="mf" style={{ height: "100vh", padding: 12, overflow: "auto" }}>
      <div className="mf-header">
        <div className="mf-row">
          <div className="mf-display">voice-realtime</div>
        </div>
        <div className="mf-row">
          <span className={`mf-chip ${connState === "connected" ? "live" : ""}`}>
            {connState === "connected" ? <span className="mf-dot" /> : null}
            {connState}
          </span>
        </div>
      </div>

      {banner}

      {session ? (
        <ActiveSessionView
          session={session}
          turns={turns}
          metrics={metrics}
          muted={muted}
          userRms={userRms}
          modelRms={modelRms}
          onMute={requestMute}
          onStop={requestStop}
        />
      ) : (
        <PersonasListView personas={personas} closeReason={closeReason} />
      )}
    </div>
  );
}

function PersonasListView({
  personas,
  closeReason,
}: {
  personas: Persona[];
  closeReason: string | null;
}) {
  return (
    <section className="mf-col" style={{ gap: 12, marginTop: 12 }}>
      <div className="mf-row mf-between">
        <span className="mf-label">Personas disponibles</span>
        <span className="mf-cap">{personas.length}</span>
      </div>
      {closeReason ? (
        <div className="mf-card">
          <span className="mf-label">Dernière session</span>
          <p className="mf-body">Fermée — raison : {closeReason}</p>
        </div>
      ) : null}
      {personas.length === 0 ? (
        <p className="mf-dim">Aucune persona — vérifie <code>_System/voice-personas/</code> dans le vault.</p>
      ) : (
        <ul className="mf-col" style={{ listStyle: "none", padding: 0, gap: 8 }}>
          {personas.map((p) => (
            <li key={p.id} className="mf-card">
              <div className="mf-row mf-between">
                <span className="mf-title">{p.name}</span>
                <span className="mf-cap">{p.provider ?? "default"}</span>
              </div>
              {p.description ? <p className="mf-body">{p.description}</p> : null}
              <div className="mf-row" style={{ gap: 6, marginTop: 4 }}>
                {p.voice ? <span className="mf-chip">voice: {p.voice}</span> : null}
                {p.vad ? <span className="mf-chip">vad: {p.vad}</span> : null}
                {p.hasObsidianFilter ? <span className="mf-chip">vault filter</span> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mf-cap mf-dim">
        Lance <code>voice-realtime talk --ui --persona &lt;slug&gt;</code> dans un terminal pour démarrer.
      </p>
    </section>
  );
}

function ActiveSessionView({
  session,
  turns,
  metrics,
  muted,
  userRms,
  modelRms,
  onMute,
  onStop,
}: {
  session: LiveSession;
  turns: TranscriptTurn[];
  metrics: SessionMetrics;
  muted: boolean;
  userRms: number;
  modelRms: number;
  onMute: (on: boolean) => void;
  onStop: () => void;
}) {
  return (
    <section className="mf-col" style={{ gap: 12, marginTop: 12 }}>
      <div className="mf-card">
        <div className="mf-row mf-between">
          <span className="mf-title">{session.personaId}</span>
          <span className="mf-cap">{session.model}</span>
        </div>
        <div className="mf-row" style={{ gap: 6, marginTop: 4 }}>
          <span className="mf-chip live">
            <span className="mf-dot" />
            {session.provider}
          </span>
          <span className="mf-chip">voice: {session.voice}</span>
        </div>
      </div>

      <div className="mf-card">
        <span className="mf-label">Métriques</span>
        <p className="mf-mono-12" style={{ margin: "4px 0" }}>
          {formatDuration(metrics.durationSeconds)} · {formatCost(metrics.costUsd)} · TTFA{" "}
          {metrics.ttfaMs ? `${Math.round(metrics.ttfaMs)}ms` : "—"} · TTFI{" "}
          {metrics.ttfiMs ? `${Math.round(metrics.ttfiMs)}ms` : "—"}
        </p>
        <div className="mf-row" style={{ gap: 8 }}>
          <VUBar label="Toi" rms={userRms} color="var(--mf-acc)" />
          <VUBar label="IA" rms={modelRms} color="var(--mf-warn)" />
        </div>
      </div>

      <div className="mf-card" style={{ minHeight: 200 }}>
        <span className="mf-label">Transcript</span>
        {turns.length === 0 ? (
          <p className="mf-dim mf-body">En attente du premier tour…</p>
        ) : (
          <div className="mf-col" style={{ gap: 6, marginTop: 6 }}>
            {turns.slice(-12).map((t) => (
              <p
                key={t.id}
                className="mf-body"
                style={{
                  margin: 0,
                  color: t.role === "user" ? "var(--mf-acc)" : "var(--mf-fg)",
                  opacity: t.partial ? 0.6 : 1,
                }}
              >
                <span className="mf-mono mf-dim">{t.role === "user" ? ">>>" : "<<<"}</span>{" "}
                {t.text}
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="mf-row" style={{ gap: 8 }}>
        <button
          className="mf-btn"
          onClick={() => onMute(!muted)}
          style={muted ? { background: "var(--mf-warn-soft)", color: "var(--mf-warn)" } : undefined}
        >
          {muted ? "Unmute" : "Mute"}
        </button>
        <button
          className="mf-btn"
          onClick={onStop}
          style={{ background: "var(--mf-danger-soft)", color: "var(--mf-danger)" }}
        >
          Stop session
        </button>
      </div>
    </section>
  );
}

function VUBar({ label, rms, color }: { label: string; rms: number; color: string }) {
  const pct = Math.min(100, Math.round(rms * 450));  // amplify speech RMS (0.05-0.2 → 22-90%)
  return (
    <div className="mf-col mf-grow" style={{ gap: 2 }}>
      <span className="mf-label">{label}</span>
      <div
        style={{
          height: 6,
          background: "var(--mf-panel-3)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            transition: "width 80ms linear",
          }}
        />
      </div>
    </div>
  );
}

export default App;
