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

export async function openPersonaInObsidian(slug: string): Promise<void> {
  await openUrl(personaObsidianURI(slug));
}

export async function openPersonasFolderInObsidian(): Promise<void> {
  await openUrl(personasFolderObsidianURI());
}

export async function openSecretsFile(path: string): Promise<void> {
  // File:// URI is OS-default-app safe via the opener plugin. macOS opens
  // .env files in TextEdit unless the user has set a different default.
  await openUrl(`file://${path}`);
}
