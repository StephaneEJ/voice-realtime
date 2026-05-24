// ─────────────────────────────────────────────────────────────────────────
// ws-client.ts — typed WebSocket client for voice-realtime control_server.
//
// Talks to ws://127.0.0.1:7711 (spawned by `voice-realtime talk --ui`). Sends
// commands as { op: ... }, receives events as { ev: ... }. The discriminated
// union types live in models.ts.
//
// Reconnect strategy: exponential backoff up to 8 tries (matches the state
// diagram in design/README.md). After 8 failed attempts the client gives up
// and surfaces an error event to listeners.
// ─────────────────────────────────────────────────────────────────────────

import type { WSCommand, WSEvent } from "./models";

// macOS App Transport Security blocks ws:// to 127.0.0.1 by default but
// whitelists "localhost". Both resolve to the same loopback interface but
// only the hostname form is exempt from ATS. Stick to "localhost" here.
// macOS App Transport Security blocks ws:// to 127.0.0.1 from WebKit
// contexts but exempts "localhost". Both resolve to the same loopback
// interface but only the hostname form is exempt from ATS.
const DEFAULT_URL = "ws://localhost:7711";
const BASE_BACKOFF_MS = 500;       // attempt 1 waits 500ms
const MAX_BACKOFF_MS = 8000;       // cap interval at 8s — keep retrying forever

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "failed";

export type EventListener = (event: WSEvent) => void;
export type StateListener = (state: ConnectionState, attempt: number) => void;

export interface VoiceRTClient {
  connect: () => void;
  disconnect: () => void;
  send: (cmd: WSCommand) => void;
  onEvent: (listener: EventListener) => () => void;
  onState: (listener: StateListener) => () => void;
  getState: () => ConnectionState;
}

export function createVoiceRTClient(url: string = DEFAULT_URL): VoiceRTClient {
  let ws: WebSocket | null = null;
  let state: ConnectionState = "disconnected";
  let attempts = 0;
  let reconnectTimer: number | null = null;
  let shouldReconnect = true;

  const eventListeners = new Set<EventListener>();
  const stateListeners = new Set<StateListener>();

  function setState(next: ConnectionState): void {
    state = next;
    for (const listener of stateListeners) {
      try {
        listener(next, attempts);
      } catch (err) {
        console.error("[ws-client] state listener threw:", err);
      }
    }
  }

  function backoffDelay(attempt: number): number {
    // Exponential: 500ms, 1s, 2s, 4s, 8s, then capped at 8s forever
    return Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
  }

  function scheduleReconnect(): void {
    if (!shouldReconnect) return;
    setState("reconnecting");
    // Backoff up to MAX_BACKOFF_MS but never give up — the CLI is local,
    // privacy isn't an issue, and the user expects the UI to reattach as
    // soon as they launch the CLI again. The `attempt` counter just feeds
    // the backoff curve.
    const delay = backoffDelay(attempts);
    attempts += 1;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      openSocket();
    }, delay);
  }

  function openSocket(): void {
    console.log(`[ws-client] connecting to ${url} (attempt ${attempts + 1})`);
    setState("connecting");
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error("[ws-client] WebSocket construction failed:", err);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.log("[ws-client] socket OPEN");
      attempts = 0;
      setState("connected");
    };

    ws.onmessage = (msg) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(typeof msg.data === "string" ? msg.data : "");
      } catch (err) {
        console.error("[ws-client] bad JSON from server:", msg.data, err);
        return;
      }
      // Minimal shape check before fan-out. We don't validate exhaustively
      // because the discriminated union below is checked at use sites.
      if (typeof parsed !== "object" || parsed === null || !("ev" in parsed)) {
        console.warn("[ws-client] message missing 'ev' field:", parsed);
        return;
      }
      const event = parsed as WSEvent;
      for (const listener of eventListeners) {
        try {
          listener(event);
        } catch (err) {
          console.error("[ws-client] event listener threw:", err);
        }
      }
    };

    ws.onerror = (err) => {
      console.warn("[ws-client] socket ERROR:", err);
    };

    ws.onclose = (e) => {
      console.log(`[ws-client] socket CLOSE code=${e.code} reason=${e.reason} clean=${e.wasClean}`);
      ws = null;
      if (shouldReconnect) {
        scheduleReconnect();
      } else {
        setState("disconnected");
      }
    };
  }

  return {
    connect() {
      shouldReconnect = true;
      if (state === "connected" || state === "connecting") return;
      attempts = 0;
      openSocket();
    },

    disconnect() {
      shouldReconnect = false;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (ws !== null) {
        ws.close();
        ws = null;
      }
      setState("disconnected");
    },

    send(cmd: WSCommand) {
      if (ws === null || ws.readyState !== WebSocket.OPEN) {
        console.warn("[ws-client] dropped command, socket not open:", cmd);
        return;
      }
      ws.send(JSON.stringify(cmd));
    },

    onEvent(listener: EventListener) {
      eventListeners.add(listener);
      return () => eventListeners.delete(listener);
    },

    onState(listener: StateListener) {
      stateListeners.add(listener);
      return () => stateListeners.delete(listener);
    },

    getState() {
      return state;
    },
  };
}
