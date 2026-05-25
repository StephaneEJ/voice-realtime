// ─────────────────────────────────────────────────────────────────────────
// models.ts — voice-realtime UI data models (TypeScript)
//
// Port of design/tokens-draft/Models.swift (now obsolete with the pivot to
// Tauri). These types are the wire contracts between the CLI's
// control_server.py and the Tauri UI. Keep field names in sync with the
// payloads emitted by voice_realtime/control_server.py.
//
// DRAFT: not yet inside the Tauri project. Will move to
//   ui-tauri/src/lib/models.ts
// once `cargo create-tauri-app` has produced the scaffold.
// ─────────────────────────────────────────────────────────────────────────

// ─── Persona ──────────────────────────────────────────────────────────────
// Echoes the `personas.list` WS event payload. The Python source of truth is
// voice_realtime/control_server.py::_persona_to_dict. Keep field names aligned.

export type ProviderName = "gemini" | "openai";
export type VADPreset = "reactive" | "balanced" | "patient" | "very-patient";

export interface Persona {
  id: string;                  // slug, primary key
  name: string;
  description: string;
  voice: string | null;
  model: string | null;
  provider: ProviderName | null;
  vad: VADPreset | null;
  avatar: string | null;
  hasObsidianFilter: boolean;
}

// ─── Session state machine ────────────────────────────────────────────────
// Drives top-level UI routing (welcome popover vs active session vs error).
// Transitions are documented in design/README.md state diagram.

export type SessionState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "live" }
  | { kind: "muted" }
  | { kind: "stopping" }
  | { kind: "reconnecting"; attempt: number }
  | { kind: "error"; code: string; message: string };

// ─── Metrics ──────────────────────────────────────────────────────────────
// Live numbers shown in the active session strip + overlay sidebar.

export interface SessionMetrics {
  durationSeconds: number;
  costUsd: number;
  ttfaMs: number | null;       // time-to-first-audio
  ttfiMs: number | null;       // time-to-first-interrupt
  // Sprint 4 — proxy estimates emitted by backend cost.tick. Not real
  // provider usage counters yet (see voice_realtime/cost_tracker.py).
  tokensIn: number;
  tokensOut: number;
  tokensTotal: number;
  tokensCapModel: number;      // provider context window (1M Gemini, 128k OpenAI)
}

export function formatDuration(seconds: number): string {
  const total = Math.min(Math.floor(seconds), 99 * 60 + 59);
  const m = Math.floor(total / 60).toString().padStart(2, "0");
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

// ─── Transcript ───────────────────────────────────────────────────────────

export type TranscriptRole = "user" | "model";

export interface TranscriptTurn {
  id: string;                  // generated client-side (crypto.randomUUID)
  role: TranscriptRole;
  text: string;
  partial: boolean;            // true while server is still streaming this turn
  createdAt: number;           // Date.now() ms epoch
}

// ─── VU levels ────────────────────────────────────────────────────────────
// Rolling buffer of the last N RMS values per side. Drives the radial
// spectrum animation in the ActiveSession view.

export const VU_BUFFER_SIZE = 32;

export interface VULevels {
  user: number[];              // length VU_BUFFER_SIZE, values [0..1]
  model: number[];             // length VU_BUFFER_SIZE, values [0..1]
}

export function emptyVULevels(): VULevels {
  return {
    user: new Array(VU_BUFFER_SIZE).fill(0),
    model: new Array(VU_BUFFER_SIZE).fill(0),
  };
}

export function pushVULevel(buffer: number[], rms: number): number[] {
  const clamped = Math.max(0, Math.min(1, rms));
  return [...buffer.slice(1), clamped];
}

// ─── Settings persisted to disk via Tauri store ───────────────────────────

export interface AppSettings {
  defaultModel: string;
  budgetCapUsd: number;
  alertAt80Percent: boolean;
  activePersonaId: string;
}

export const DEFAULT_SETTINGS: AppSettings = {
  defaultModel: "gemini-2.5-flash-native-audio-latest",
  budgetCapUsd: 22.0,
  alertAt80Percent: true,
  activePersonaId: "jarvis",
};

// ─── Settings snapshot (read-only) ────────────────────────────────────────
// Mirrors _build_settings_payload in voice_realtime/control_server.py.

export interface SettingsSnapshot {
  secretsPath: string;
  openaiKey: "present" | "absent";
  geminiKey: "present" | "absent";
  defaultModelOpenai: string;
  defaultModelGemini: string;
  budgetCapUsd: number;
  monthlyTotalUsd: number;
  dailyTotalUsd: number;
  monthlyProgressPct: number;
}

// ─── WS wire types (events received from control_server) ──────────────────
// These are the exact shapes emitted by voice_realtime/control_server.py.
// Discriminated union on `ev` makes the client code exhaustive-checkable.

export type WSEvent =
  | { ev: "personas.list"; personas: Persona[] }
  | ({ ev: "settings.get" } & SettingsSnapshot)
  | {
      ev: "session.opened";
      sessionId: string;
      personaId: string;
      model: string;
      provider: ProviderName;
      voice: string;
      vad: string;
    }
  | { ev: "session.closed"; reason: string }
  | { ev: "audio.user.frame"; rms: number; ts: number }
  | { ev: "audio.model.frame"; rms: number; ts: number }
  | {
      ev: "transcript.delta";
      role: TranscriptRole;
      text: string;
      final: false;
    }
  | { ev: "transcript.final"; role: TranscriptRole; text: string }
  | { ev: "ttfa"; ms: number }
  | { ev: "ttfi"; ms: number }
  | { ev: "model.interrupted" }
  | {
      ev: "cost.tick";
      delta: number;
      total: number;
      elapsed: number;
      // Sprint 4 — proxy token estimates (not real provider counters yet).
      tokensIn?: number;
      tokensOut?: number;
      tokensTotal?: number;
      tokensCapModel?: number;
    }
  | { ev: "mute.state"; on: boolean }
  // Sprint 1 — tool call lifecycle.
  | { ev: "tool.call"; callId: string; name: string; args: Record<string, unknown>; ts: number }
  | { ev: "tool.result"; callId: string; name: string; ok: boolean; summary: string; durationMs: number }
  // Sprint 4 — ask-before-acting gate. UI must reply with tool.confirm_reply.
  | { ev: "tool.confirm_request"; callId: string; name: string; args: Record<string, unknown>; ts: number }
  | { ev: "error"; code: string; msg: string };

// ─── WS wire types (commands sent to control_server) ──────────────────────

export type WSCommand =
  | { op: "personas.list" }
  | { op: "settings.get" }
  | { op: "mute"; on: boolean }
  | { op: "session.stop" }
  // Sprint 4 — reply to tool.confirm_request, drives ask-before-acting flow.
  | { op: "tool.confirm_reply"; callId: string; approve: boolean };
