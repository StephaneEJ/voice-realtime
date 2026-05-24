// App.tsx — orchestrator. Holds the WS client + the entire UI state,
// routes to the Welcome view (no live session) or ActiveSession (live).
// All persistence-free state — the UI is a viewer over the CLI's authoritative
// state.

import { useCallback, useEffect, useRef, useState } from "react";
import { StatusBanner } from "./views/StatusBanner";
import { WelcomeView } from "./views/WelcomeView";
import { ActiveSessionView, LiveSession } from "./views/ActiveSessionView";
import { SettingsModal } from "./views/SettingsModal";
import { EdgeStateBanners } from "./views/EdgeStateBanners";
import {
  ConnectionState,
  createVoiceRTClient,
  VoiceRTClient,
} from "./lib/ws-client";
import {
  emptyVULevels,
  Persona,
  pushVULevel,
  SessionMetrics,
  SettingsSnapshot,
  TranscriptTurn,
  VULevels,
  WSEvent,
} from "./lib/models";
import { listPersonaFilesFromVault } from "./lib/personaFile";

import "./styles/midfi.css";
import "./styles/animations.css";

const EMPTY_METRICS: SessionMetrics = {
  durationSeconds: 0,
  costUsd: 0,
  ttfaMs: null,
  ttfiMs: null,
  tokensIn: 0,
  tokensOut: 0,
};

function App() {
  const clientRef = useRef<VoiceRTClient | null>(null);
  const [connState, setConnState] = useState<ConnectionState>("disconnected");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [session, setSession] = useState<LiveSession | null>(null);
  const [closeReason, setCloseReason] = useState<string | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [metrics, setMetrics] = useState<SessionMetrics>(EMPTY_METRICS);
  const [vu, setVU] = useState<VULevels>(emptyVULevels);
  const [muted, setMuted] = useState(false);
  const [settings, setSettings] = useState<SettingsSnapshot | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.ev) {
      case "personas.list":
        setPersonas(event.personas);
        break;
      case "settings.get":
        // Destructure to drop the `ev` discriminator before storing.
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { ev: _ev, ...snapshot } = event;
        setSettings(snapshot);
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
        setMetrics(EMPTY_METRICS);
        setVU(emptyVULevels());
        setMuted(false);
        break;
      case "session.closed":
        setSession(null);
        setCloseReason(event.reason);
        // Keep transcript + metrics displayed briefly via the close reason
        // banner; they're cleared on the next session.opened.
        break;
      case "transcript.delta": {
        const { role, text } = event;
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.partial && last.role === role) {
            return [...prev.slice(0, -1), { ...last, text: last.text + text }];
          }
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role,
              text,
              partial: true,
              createdAt: Date.now(),
            },
          ];
        });
        break;
      }
      case "transcript.final": {
        const { role, text } = event;
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.partial && last.role === role) {
            return [...prev.slice(0, -1), { ...last, text, partial: false }];
          }
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role,
              text,
              partial: false,
              createdAt: Date.now(),
            },
          ];
        });
        break;
      }
      case "audio.user.frame":
        setVU((prev) => ({ ...prev, user: pushVULevel(prev.user, event.rms) }));
        break;
      case "audio.model.frame":
        setVU((prev) => ({ ...prev, model: pushVULevel(prev.model, event.rms) }));
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
        // ttfi event follows with the actual value; just a signal here.
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
        client.send({ op: "settings.get" });
      }
    });
    client.connect();
    return () => {
      offEvent();
      offState();
      client.disconnect();
    };
  }, [handleEvent]);

  // If the WS connection drops while a session was attached, the CLI was
  // probably killed brutally (no session.closed event arrived). Drop the
  // session state after a short grace period so the UI bounces back to
  // the Welcome view instead of pretending the session is still live.
  // 4s grace lets a quick reconnect (e.g. CLI restart) recover without
  // flicker; longer absences clear the UI cleanly.
  useEffect(() => {
    if (connState === "connected") return;
    if (session === null) return;
    const t = window.setTimeout(() => {
      setSession((s) => {
        if (s === null) return s;
        setCloseReason("disconnect");
        return null;
      });
    }, 4000);
    return () => window.clearTimeout(t);
  }, [connState, session]);

  const requestMute = useCallback((on: boolean) => {
    clientRef.current?.send({ op: "mute", on });
  }, []);

  const requestStop = useCallback(() => {
    const wsState = clientRef.current?.getState();
    if (wsState === "connected") {
      clientRef.current?.send({ op: "session.stop" });
      // CLI will reply with session.closed → handleEvent clears `session`.
    } else {
      // WS not live — CLI is probably dead. Skip the command and clear the
      // session state locally so the user can get back to the Welcome view.
      setSession(null);
      setCloseReason("local_stop_ws_down");
    }
  }, []);

  const refreshSettings = useCallback(() => {
    clientRef.current?.send({ op: "settings.get" });
    // Also re-list personas in case the user just edited / created one in
    // Obsidian via the Personas tab links.
    clientRef.current?.send({ op: "personas.list" });
  }, []);

  // Refetch personas when the window regains focus — covers the round-trip
  // from "+ New persona" → user creates+saves in Obsidian → comes back here.
  // Also re-reads from the vault filesystem directly, so the list stays
  // accurate even when no CLI/WS session is running.
  const refreshPersonas = useCallback(() => {
    clientRef.current?.send({ op: "personas.list" });
    void listPersonaFilesFromVault().then((p) => {
      // Only adopt the fs result if WS hasn't supplied a list yet (avoid
      // flickering when both fire near-simultaneously). If WS later comes
      // back with its own list, the WS payload wins (handled in handleEvent).
      setPersonas((prev) => (prev.length === 0 ? p : prev));
    });
  }, []);

  useEffect(() => {
    refreshPersonas();
    window.addEventListener("focus", refreshPersonas);
    return () => window.removeEventListener("focus", refreshPersonas);
  }, [refreshPersonas]);

  const openSettings = useCallback(() => setSettingsOpen(true), []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  // Keyboard shortcut for opening settings — ⌘, is the macOS convention.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey && e.key === ",") {
        e.preventDefault();
        setSettingsOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Track muted in a ref so the global-shortcut callback (registered once)
  // always sees the latest value without re-registering on every render.
  const mutedRef = useRef(muted);
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  // Global mute toggle shortcut — fires even when the app is not focused.
  // Useful in the menubar mode where the popover is rarely the active window.
  // Uses CmdOrCtrl+Shift+M (won't clash with system ⌘M = minimize).
  useEffect(() => {
    let registered = false;
    const accelerator = "CmdOrCtrl+Shift+M";
    (async () => {
      try {
        const { register, unregister, isRegistered } = await import("@tauri-apps/plugin-global-shortcut");
        if (await isRegistered(accelerator)) {
          await unregister(accelerator);
        }
        await register(accelerator, (e) => {
          // Only fire on key down to avoid double-toggling on key up.
          if (e.state === "Pressed") {
            clientRef.current?.send({ op: "mute", on: !mutedRef.current });
          }
        });
        registered = true;
      } catch (err) {
        // Not running inside Tauri (e.g. plain web preview) — skip silently.
        console.info("global-shortcut unavailable:", err);
      }
    })();
    return () => {
      if (!registered) return;
      void import("@tauri-apps/plugin-global-shortcut").then(({ unregister }) =>
        unregister(accelerator).catch(() => {}),
      );
    };
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "var(--mf-bg)",
        color: "var(--mf-fg)",
        fontFamily: "var(--mf-sans)",
        fontSize: 13,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <StatusBanner state={connState} attempt={reconnectAttempt} />
      <EdgeStateBanners settings={settings} closeReason={closeReason} onOpenSettings={openSettings} />
      {session ? (
        <ActiveSessionView
          session={session}
          turns={turns}
          metrics={metrics}
          vu={vu}
          muted={muted}
          onMute={requestMute}
          onStop={requestStop}
        />
      ) : (
        <WelcomeView personas={personas} closeReason={closeReason} onSettings={openSettings} />
      )}
      <SettingsModal
        open={settingsOpen}
        onClose={closeSettings}
        settings={settings}
        personas={personas}
        onRefresh={refreshSettings}
        onPersonasRefresh={refreshPersonas}
      />
    </div>
  );
}

export default App;
