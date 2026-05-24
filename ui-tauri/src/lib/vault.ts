// vault.ts — helpers to build Obsidian Advanced URI links from persona slugs.
//
// Convention from CLAUDE.md (vault 2ND_CERVEAU): personas live in
// `_System/voice-personas/<slug>.md`. The Advanced URI plugin must be
// installed in Obsidian for these links to work (Stéphane already has it).
//
// Format:
//   obsidian://advanced-uri?vault=<VAULT>&filepath=<encoded-path>&openmode=tab

import { openUrl } from "@tauri-apps/plugin-opener";

const VAULT_NAME = "2ND_CERVEAU";

export function personaVaultPath(slug: string): string {
  return `_System/voice-personas/${slug}.md`;
}

export function personaObsidianURI(slug: string): string {
  const path = encodeURIComponent(personaVaultPath(slug));
  return `obsidian://advanced-uri?vault=${VAULT_NAME}&filepath=${path}&openmode=tab`;
}

export function personasFolderObsidianURI(): string {
  const path = encodeURIComponent("_System/voice-personas/");
  return `obsidian://advanced-uri?vault=${VAULT_NAME}&filepath=${path}&openmode=tab`;
}

/** Markdown template for a new persona file. Mirrors all the fields that
 *  `voice_realtime/persona.py::load_persona_file` reads from frontmatter,
 *  with sensible defaults and TODO placeholders for the user to fill. */
export function personaTemplate(slug: string, name: string): string {
  const safeName = name.trim() || slug;
  return `---
type: voice-persona
slug: ${slug}
name: ${safeName}
description: "TODO — 1 phrase qui décrit qui est ${safeName}"
provider: gemini
model: gemini-2.5-flash-native-audio-latest
voice: Charon
vad: balanced
greeting_mode: persona
greeting_text: "Salut Stéphane, je suis ${safeName}, je t'écoute."
avatar: ""
obsidian_skills: []
obsidian_notes: []
tools: []
---

# System prompt

Décris ici la personnalité, le ton, les contraintes, le style de réponse.

Exemple à remplacer :
- **Rôle** : (coach / partenaire de brainstorm / interviewer / etc.)
- **Ton** : direct, sans flagornerie, challenge quand utile
- **Approche** : (méthodes utilisées, frameworks de questionnement)
- **Format réponse** : court, oral-friendly, pas de listes interminables
- **Interdits** : (sujets ou comportements à éviter)

## Contexte vault (optionnel)

Liste de notes/skills à injecter dans le prompt système quand l'agent
démarre. Renseigner \`obsidian_skills\` ou \`obsidian_notes\` ci-dessus
si tu veux que la persona ait accès au vault.
`;
}

/** Opens Obsidian to a new persona file pre-filled with the template.
 *  Uses Advanced URI's `mode=new` + `data` parameter. */
export function newPersonaObsidianURI(slug: string, name: string): string {
  const path = encodeURIComponent(personaVaultPath(slug));
  const data = encodeURIComponent(personaTemplate(slug, name));
  return `obsidian://advanced-uri?vault=${VAULT_NAME}&filepath=${path}&data=${data}&mode=new&openmode=tab`;
}

export async function createNewPersonaInObsidian(slug: string, name: string): Promise<void> {
  return safeOpen(newPersonaObsidianURI(slug, name), `new persona:${slug}`);
}

async function safeOpen(url: string, label: string): Promise<void> {
  try {
    await openUrl(url);
  } catch (err) {
    console.error(`[vault] openUrl(${label}) failed:`, err);
  }
}

export async function openPersonaInObsidian(slug: string): Promise<void> {
  return safeOpen(personaObsidianURI(slug), `persona:${slug}`);
}

export async function openPersonasFolderInObsidian(): Promise<void> {
  return safeOpen(personasFolderObsidianURI(), "personas folder");
}

export async function openSecretsFile(path: string): Promise<void> {
  // File:// URI is OS-default-app safe via the opener plugin. macOS opens
  // .env files in TextEdit unless the user has set a different default.
  return safeOpen(`file://${path}`, "secrets file");
}
