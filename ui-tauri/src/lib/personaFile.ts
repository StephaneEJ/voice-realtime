// personaFile.ts — read/write persona MD files in the vault via Tauri fs.
//
// Personas live in $HOME/OBSIDIAN/2ND_CERVEAU/_System/voice-personas/<slug>.md.
// The MD has YAML frontmatter (matched by voice_realtime/persona.py) + a body
// that is the system prompt. We serialize a strict subset of fields the UI
// editor exposes; advanced fields (obsidian_skills/notes/tools/avatar) are
// preserved on edit by round-tripping the raw frontmatter map.

import { exists, readDir, readTextFile, remove, writeTextFile } from "@tauri-apps/plugin-fs";
import { homeDir, join } from "@tauri-apps/api/path";
import type { Persona } from "./models";

/** Sprint 3 custom command entry — phrase trigger → tool/action recipe. */
export interface PersonaCustomCommand {
  trigger: string;
  action: string;
}

export interface PersonaFile {
  slug: string;
  name: string;
  description: string;
  provider: "gemini" | "openai" | "";
  model: string;
  voice: string;
  vad: "reactive" | "balanced" | "patient" | "very-patient" | "";
  greetingMode: "persona" | "user";
  greetingText: string;
  systemPrompt: string;
  // Sprint 3 — Vault filter (now first-class instead of extraFrontmatter)
  obsidianSkills: string[];
  obsidianNotes: string[];
  // Sprint 3 — Tools allowlist (drives which functions the model may call)
  tools: string[];
  // Sprint 3 — Context preset
  project: string;
  cliContext: boolean;
  rollingRecap: boolean;
  rollingTerminal: boolean;
  // Sprint 3 — Web search allowlist
  webAllowlist: string[];
  // Sprint 3 — Safety gate
  askBeforeActing: boolean;
  // Sprint 3 — Custom command recipes
  customCommands: PersonaCustomCommand[];
  /** Round-tripped extra frontmatter fields the form doesn't edit. */
  extraFrontmatter: Record<string, unknown>;
}

const VAULT_REL = "OBSIDIAN/2ND_CERVEAU/_System/voice-personas";

async function personaPath(slug: string): Promise<string> {
  const home = await homeDir();
  return await join(home, VAULT_REL, `${slug}.md`);
}

export async function personaExists(slug: string): Promise<boolean> {
  const path = await personaPath(slug);
  return await exists(path);
}

export async function deletePersonaFile(slug: string): Promise<void> {
  const path = await personaPath(slug);
  await remove(path);
}

/** List all persona .md files in the vault — fs-driven so the UI can show
 *  the welcome list even when the CLI control_server isn't running.
 *  Returns Persona records shaped to match the WS payload, so the UI can
 *  treat both sources interchangeably. Errors on individual files are
 *  swallowed (one bad file shouldn't hide the rest), matching the Python
 *  list_personas behaviour. */
export async function listPersonaFilesFromVault(): Promise<Persona[]> {
  const home = await homeDir();
  const dir = await join(home, VAULT_REL);
  if (!(await exists(dir))) return [];
  let entries;
  try {
    entries = await readDir(dir);
  } catch {
    return [];
  }
  const out: Persona[] = [];
  for (const entry of entries) {
    if (!entry.isFile || !entry.name?.endsWith(".md") || entry.name.startsWith("_")) continue;
    const slug = entry.name.slice(0, -3);
    try {
      const file = await readPersonaFile(slug);
      out.push({
        id: file.slug,
        name: file.name,
        description: file.description,
        voice: file.voice || null,
        model: file.model || null,
        provider: file.provider || null,
        vad: file.vad || null,
        avatar: null,
        hasObsidianFilter:
          Array.isArray(file.extraFrontmatter.obsidian_skills) &&
          (file.extraFrontmatter.obsidian_skills as unknown[]).length > 0,
      });
    } catch {
      // skip malformed file
    }
  }
  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

/** Tiny YAML serializer for our schema. Quotes strings; lists become flow
 *  arrays. Doesn't pretend to handle every YAML edge case — works for the
 *  subset we emit. */
function serializeYaml(map: Record<string, unknown>): string {
  const lines: string[] = [];
  for (const [key, value] of Object.entries(map)) {
    if (value === null || value === undefined) continue;
    lines.push(`${key}: ${serializeValue(value)}`);
  }
  return lines.join("\n");
}

function serializeValue(value: unknown): string {
  if (typeof value === "string") {
    // Quote if contains special chars, otherwise leave bare for readability.
    if (/^[A-Za-z0-9_\-./]+$/.test(value) && value.length > 0) return value;
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return "[" + value.map(serializeValue).join(", ") + "]";
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Naive YAML frontmatter parser for the schema we emit. Handles scalars,
 *  quoted strings, `[...]` flow arrays, and JSON-style flow arrays of flow
 *  maps (custom_commands). Hand-edited block-style content lands as-is in
 *  `extraFrontmatter` — the UI editor will rewrite it in flow style on next
 *  save, so authoring stays Python-side authoritative until then. */
function parseYaml(text: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const rawLine of text.split("\n")) {
    const line = rawLine.replace(/#.*$/, "").trimEnd();
    if (!line.trim()) continue;
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    let valueStr = line.slice(idx + 1).trim();
    if (!valueStr) {
      out[key] = "";
      continue;
    }
    // Flow array — try JSON.parse first (handles `[{trigger:"x",...}, ...]`).
    if (valueStr.startsWith("[") && valueStr.endsWith("]")) {
      try {
        // Trust valid JSON shape we emit ourselves.
        out[key] = JSON.parse(valueStr);
      } catch {
        // Fallback for human-edited scalar arrays: split-by-comma + unquote.
        const inner = valueStr.slice(1, -1).trim();
        out[key] = inner ? inner.split(",").map((s) => unquote(s.trim())) : [];
      }
      continue;
    }
    out[key] = unquote(valueStr);
  }
  return out;
}

function unquote(s: string): string {
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  }
  return s;
}

/** Coerce a frontmatter value to bool — `true`/`false` may arrive as YAML
 *  native bool (already JS bool), as string ("true"/"yes"/"1"), or be absent.
 *  Mirrors Python's `_coerce_bool` so round-trips don't drift. */
function coerceBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const s = value.trim().toLowerCase();
    return s === "true" || s === "yes" || s === "1" || s === "on";
  }
  return fallback;
}

function coerceStringList(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.map((x) => String(x));
  return [];
}

function coerceCommandList(value: unknown): PersonaCustomCommand[] {
  if (!Array.isArray(value)) return [];
  const out: PersonaCustomCommand[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const obj = item as Record<string, unknown>;
    const trigger = String(obj.trigger ?? "").trim();
    const action = String(obj.action ?? "").trim();
    if (trigger && action) out.push({ trigger, action });
  }
  return out;
}

const KNOWN_KEYS = new Set([
  "type", "slug", "name", "description", "provider", "model", "voice", "vad",
  "greeting_mode", "greeting_text", "system_prompt",
  // Sprint 3 first-class fields
  "obsidian_skills", "obsidian_notes", "tools",
  "project", "cli_context", "rolling_recap", "rolling_terminal",
  "web_allowlist", "ask_before_acting", "custom_commands",
]);

export async function readPersonaFile(slug: string): Promise<PersonaFile> {
  const path = await personaPath(slug);
  const text = await readTextFile(path);
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
  if (!match) {
    throw new Error(`No YAML frontmatter in ${slug}.md`);
  }
  const fm = parseYaml(match[1]);
  const body = match[2].trim();
  const extra: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(fm)) {
    if (!KNOWN_KEYS.has(k)) extra[k] = v;
  }
  return {
    slug: String(fm.slug || slug),
    name: String(fm.name || slug),
    description: String(fm.description || ""),
    provider: (fm.provider as PersonaFile["provider"]) || "",
    model: String(fm.model || ""),
    voice: String(fm.voice || ""),
    vad: (fm.vad as PersonaFile["vad"]) || "",
    greetingMode: (fm.greeting_mode as PersonaFile["greetingMode"]) || "persona",
    greetingText: String(fm.greeting_text || ""),
    systemPrompt: body,
    obsidianSkills: coerceStringList(fm.obsidian_skills),
    obsidianNotes: coerceStringList(fm.obsidian_notes),
    tools: coerceStringList(fm.tools),
    project: String(fm.project || ""),
    cliContext: coerceBool(fm.cli_context, false),
    rollingRecap: coerceBool(fm.rolling_recap, true),
    rollingTerminal: coerceBool(fm.rolling_terminal, false),
    webAllowlist: coerceStringList(fm.web_allowlist),
    askBeforeActing: coerceBool(fm.ask_before_acting, false),
    customCommands: coerceCommandList(fm.custom_commands),
    extraFrontmatter: extra,
  };
}

export async function writePersonaFile(p: PersonaFile): Promise<void> {
  const path = await personaPath(p.slug);
  const map: Record<string, unknown> = {
    type: "voice-persona",
    slug: p.slug,
    name: p.name,
    description: p.description,
  };
  if (p.provider) map.provider = p.provider;
  if (p.model) map.model = p.model;
  if (p.voice) map.voice = p.voice;
  if (p.vad) map.vad = p.vad;
  map.greeting_mode = p.greetingMode;
  if (p.greetingText) map.greeting_text = p.greetingText;
  // Sprint 3 — emit only when non-default so existing personas don't grow
  // a wall of frontmatter on first re-save.
  if (p.obsidianSkills.length) map.obsidian_skills = p.obsidianSkills;
  if (p.obsidianNotes.length) map.obsidian_notes = p.obsidianNotes;
  if (p.tools.length) map.tools = p.tools;
  if (p.project) map.project = p.project;
  if (p.cliContext) map.cli_context = true;
  if (!p.rollingRecap) map.rolling_recap = false; // default is true → omit when true
  if (p.rollingTerminal) map.rolling_terminal = true;
  if (p.webAllowlist.length) map.web_allowlist = p.webAllowlist;
  if (p.askBeforeActing) map.ask_before_acting = true;
  if (p.customCommands.length) map.custom_commands = p.customCommands;
  // Round-trip anything else we don't model explicitly (avatar, creativity, …).
  Object.assign(map, p.extraFrontmatter);

  const content =
    "---\n" +
    serializeYaml(map) +
    "\n---\n\n" +
    p.systemPrompt.trim() +
    "\n";
  await writeTextFile(path, content);
}

export function emptyPersonaFile(slug: string, name: string): PersonaFile {
  return {
    slug,
    name: name.trim() || slug,
    description: "",
    provider: "gemini",
    model: "gemini-2.5-flash-native-audio-latest",
    voice: "Charon",
    vad: "balanced",
    greetingMode: "persona",
    greetingText: `Salut Stéphane, je suis ${name.trim() || slug}, je t'écoute.`,
    systemPrompt:
      `Tu es ${name.trim() || slug} — décris ici la personnalité, le ton, les contraintes.\n` +
      `\n` +
      `- Rôle : (coach / partenaire / interviewer / etc.)\n` +
      `- Ton : direct, sans flagornerie, challenge utile\n` +
      `- Format réponse : court, oral-friendly\n` +
      `- Interdits : (sujets ou comportements à éviter)\n`,
    obsidianSkills: [],
    obsidianNotes: [],
    tools: [],
    project: "",
    cliContext: false,
    rollingRecap: true,
    rollingTerminal: false,
    webAllowlist: [],
    askBeforeActing: false,
    customCommands: [],
    extraFrontmatter: {},
  };
}
