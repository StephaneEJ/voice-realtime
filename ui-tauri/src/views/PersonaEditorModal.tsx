// PersonaEditorModal — inline form to create or edit a persona file in the
// vault. Replaces the Obsidian-redirect flow with direct fs writes via the
// Tauri fs plugin (scoped to _System/voice-personas/ in capabilities).

import { useEffect, useState } from "react";
import {
  PersonaFile,
  deletePersonaFile,
  emptyPersonaFile,
  personaExists,
  readPersonaFile,
  writePersonaFile,
} from "../lib/personaFile";

export interface PersonaEditorModalProps {
  /** Slug to edit. If undefined → create mode (form starts empty). */
  editingSlug: string | undefined;
  /** When create mode, slugs already in use — blocks duplicate creation. */
  existingSlugs: Set<string>;
  open: boolean;
  onClose: () => void;
  /** Called after a successful save so the parent can refresh personas.list. */
  onSaved: () => void;
}

const VAD_OPTIONS: PersonaFile["vad"][] = ["reactive", "balanced", "patient", "very-patient"];
const PROVIDER_OPTIONS: PersonaFile["provider"][] = ["gemini", "openai"];
const VOICE_BY_PROVIDER: Record<string, string[]> = {
  gemini: ["Charon", "Aoede", "Fenrir", "Kore", "Puck"],
  openai: ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"],
  "": [],
};

function slugify(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function PersonaEditorModal({
  editingSlug,
  existingSlugs,
  open,
  onClose,
  onSaved,
}: PersonaEditorModalProps) {
  const [persona, setPersona] = useState<PersonaFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touchedSlug, setTouchedSlug] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setConfirmDelete(false);
    setSaving(false);
    setDeleting(false);
    if (editingSlug === undefined) {
      // create mode
      setPersona(emptyPersonaFile("", ""));
      setTouchedSlug(false);
    } else {
      setLoading(true);
      readPersonaFile(editingSlug)
        .then((p) => setPersona(p))
        .catch((err) => setError(String(err)))
        .finally(() => setLoading(false));
      setTouchedSlug(true);
    }
  }, [open, editingSlug]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const isCreate = editingSlug === undefined;
  const effectiveSlug = isCreate && !touchedSlug && persona ? slugify(persona.name) : persona?.slug ?? "";
  const slugClash = isCreate && effectiveSlug.length > 0 && existingSlugs.has(effectiveSlug);
  const canSave =
    persona !== null &&
    persona.name.trim().length > 0 &&
    effectiveSlug.length > 0 &&
    !slugClash &&
    !saving;

  const update = <K extends keyof PersonaFile>(key: K, value: PersonaFile[K]) => {
    setPersona((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const save = async () => {
    if (!persona || !canSave) {
      console.warn("[persona-editor] save() called but canSave=false", {
        persona,
        canSave,
        name: persona?.name,
        effectiveSlug,
        slugClash,
        saving,
      });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const finalSlug = isCreate ? effectiveSlug : persona.slug;
      if (isCreate && (await personaExists(finalSlug))) {
        setError(`« ${finalSlug}.md » existe déjà sur disque.`);
        setSaving(false);
        return;
      }
      console.log("[persona-editor] writing persona", finalSlug);
      await writePersonaFile({ ...persona, slug: finalSlug });
      console.log("[persona-editor] write OK");
      onSaved();
      onClose();
    } catch (err) {
      console.error("[persona-editor] save failed:", err);
      setError(`Save failed: ${err}`);
      setSaving(false);
    }
  };

  const performDelete = async () => {
    if (!persona || isCreate) return;
    setDeleting(true);
    setError(null);
    try {
      console.log("[persona-editor] deleting persona", persona.slug);
      await deletePersonaFile(persona.slug);
      console.log("[persona-editor] delete OK");
      onSaved();
      onClose();
    } catch (err) {
      console.error("[persona-editor] delete failed:", err);
      setError(`Delete failed: ${err}`);
      setDeleting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        backdropFilter: "blur(3px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
        animation: "mf-spring-in 180ms ease-out",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(520px, 94vw)",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          background: "var(--mf-panel)",
          border: "1px solid var(--mf-border-2)",
          borderRadius: 14,
          overflow: "hidden",
          boxShadow: "0 16px 50px rgba(0,0,0,0.55)",
        }}
      >
        <header
          style={{
            padding: "12px 14px",
            borderBottom: "1px solid var(--mf-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span className="mf-display" style={{ fontSize: 15 }}>
            {isCreate ? "New persona" : `Edit ${editingSlug}`}
          </span>
          <button type="button" onClick={onClose} title="Close (Esc)" style={CLOSE_BTN}>
            ✕
          </button>
        </header>

        <div className="mf-scroll" style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {loading ? (
            <p className="mf-dim mf-body">Chargement…</p>
          ) : persona === null ? (
            <p className="mf-danger mf-body">{error || "État inattendu"}</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Row label="Name">
                <input
                  type="text"
                  value={persona.name}
                  onChange={(e) => update("name", e.target.value)}
                  placeholder="Jarvis"
                  style={INPUT}
                  autoFocus
                />
              </Row>

              <Row label="Slug (.md basename)">
                <input
                  type="text"
                  value={touchedSlug || !isCreate ? persona.slug : slugify(persona.name)}
                  onChange={(e) => {
                    setTouchedSlug(true);
                    update("slug", e.target.value);
                  }}
                  placeholder="jarvis"
                  style={{
                    ...INPUT,
                    borderColor: slugClash ? "var(--mf-warn)" : "var(--mf-border-2)",
                  }}
                  disabled={!isCreate}
                />
                {slugClash ? (
                  <span className="mf-cap" style={{ color: "var(--mf-warn)", marginTop: 4 }}>
                    « {effectiveSlug}.md » existe déjà
                  </span>
                ) : null}
              </Row>

              <Row label="Description">
                <input
                  type="text"
                  value={persona.description}
                  onChange={(e) => update("description", e.target.value)}
                  placeholder="1 phrase qui résume la persona"
                  style={INPUT}
                />
              </Row>

              <div style={{ display: "flex", gap: 10 }}>
                <Row label="Provider" flex>
                  <select
                    value={persona.provider}
                    onChange={(e) => update("provider", e.target.value as PersonaFile["provider"])}
                    style={INPUT}
                  >
                    <option value="">— default —</option>
                    {PROVIDER_OPTIONS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </Row>
                <Row label="Voice" flex>
                  <select
                    value={persona.voice}
                    onChange={(e) => update("voice", e.target.value)}
                    style={INPUT}
                  >
                    <option value="">— default —</option>
                    {(VOICE_BY_PROVIDER[persona.provider] || []).map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </Row>
              </div>

              <div style={{ display: "flex", gap: 10 }}>
                <Row label="Model" flex>
                  <input
                    type="text"
                    value={persona.model}
                    onChange={(e) => update("model", e.target.value)}
                    placeholder="gemini-2.5-flash-native-audio-latest"
                    style={{ ...INPUT, fontFamily: "var(--mf-mono)", fontSize: 11 }}
                  />
                </Row>
                <Row label="VAD preset" flex>
                  <select
                    value={persona.vad}
                    onChange={(e) => update("vad", e.target.value as PersonaFile["vad"])}
                    style={INPUT}
                  >
                    <option value="">— default —</option>
                    {VAD_OPTIONS.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </Row>
              </div>

              <Row label="Greeting mode">
                <div style={{ display: "flex", gap: 8 }}>
                  {(["persona", "user"] as const).map((m) => (
                    <button
                      type="button"
                      key={m}
                      onClick={() => update("greetingMode", m)}
                      style={{
                        ...CHIP_BTN,
                        background: persona.greetingMode === m ? "var(--mf-acc-soft)" : "var(--mf-panel-3)",
                        color: persona.greetingMode === m ? "var(--mf-acc)" : "var(--mf-dim)",
                        borderColor: persona.greetingMode === m ? "var(--mf-acc)" : "var(--mf-border-2)",
                      }}
                    >
                      {m === "persona" ? "persona speaks first" : "user speaks first"}
                    </button>
                  ))}
                </div>
              </Row>

              {persona.greetingMode === "persona" ? (
                <Row label="Greeting text">
                  <input
                    type="text"
                    value={persona.greetingText}
                    onChange={(e) => update("greetingText", e.target.value)}
                    placeholder="Salut Stéphane, je suis Jarvis, je t'écoute."
                    style={INPUT}
                  />
                </Row>
              ) : null}

              <Row label="System prompt">
                <textarea
                  value={persona.systemPrompt}
                  onChange={(e) => update("systemPrompt", e.target.value)}
                  rows={10}
                  style={{
                    ...INPUT,
                    fontFamily: "var(--mf-mono)",
                    fontSize: 12,
                    lineHeight: 1.4,
                    resize: "vertical",
                    minHeight: 140,
                  }}
                />
                <span className="mf-cap mf-dim" style={{ marginTop: 4 }}>
                  Décris la personnalité, ton, contraintes, format de réponse. Cette section
                  pilote la session entière.
                </span>
              </Row>

              {Object.keys(persona.extraFrontmatter).length > 0 ? (
                <div className="mf-card" style={{ padding: 8 }}>
                  <span className="mf-label">Preserved extra fields</span>
                  <code className="mf-mono mf-dim" style={{ fontSize: 10, display: "block", marginTop: 4 }}>
                    {Object.keys(persona.extraFrontmatter).join(", ")}
                  </code>
                  <span className="mf-cap mf-dim">
                    Édite ces champs dans Obsidian si nécessaire — ils sont conservés tels quels.
                  </span>
                </div>
              ) : null}

              {error ? (
                <p className="mf-body" style={{ color: "var(--mf-danger)" }}>
                  {error}
                </p>
              ) : null}
            </div>
          )}
        </div>

        <footer
          style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--mf-border)",
            display: "flex",
            gap: 8,
            alignItems: "center",
            background: "var(--mf-panel)",
          }}
        >
          {confirmDelete ? (
            // Delete confirmation takes over the entire footer — hide Save +
            // modal Cancel to avoid the duplicate "Cancel" buttons issue.
            <>
              <span className="mf-cap" style={{ color: "var(--mf-warn)" }}>
                Supprimer « {persona?.slug} » ?
              </span>
              <span style={{ flex: 1 }} />
              <button type="button" onClick={() => setConfirmDelete(false)} style={SECONDARY_BTN}>
                Annuler
              </button>
              <button
                type="button"
                onClick={() => void performDelete()}
                disabled={deleting}
                style={{
                  ...PRIMARY_BTN,
                  background: "var(--mf-danger)",
                  color: "rgba(0,0,0,0.85)",
                  opacity: deleting ? 0.6 : 1,
                  cursor: deleting ? "not-allowed" : "pointer",
                }}
              >
                {deleting ? "Suppression…" : "Confirmer suppression"}
              </button>
            </>
          ) : (
            <>
              {!isCreate ? (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  style={{
                    ...SECONDARY_BTN,
                    color: "var(--mf-danger)",
                    borderColor: "var(--mf-border-2)",
                  }}
                >
                  Delete
                </button>
              ) : null}
              <span style={{ flex: 1 }} />
              <button type="button" onClick={onClose} style={SECONDARY_BTN}>
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={!canSave}
                style={{
                  ...PRIMARY_BTN,
                  opacity: canSave ? 1 : 0.5,
                  cursor: canSave ? "pointer" : "not-allowed",
                }}
                title={
                  !canSave
                    ? `Cannot save — name=${persona?.name?.trim() ? "ok" : "empty"} slug=${effectiveSlug || "empty"} clash=${slugClash}`
                    : undefined
                }
              >
                {saving ? "Saving…" : isCreate ? "Create" : "Save"}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}

function Row({
  label,
  flex,
  children,
}: {
  label: string;
  flex?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        flex: flex ? 1 : "initial",
        minWidth: 0,
      }}
    >
      <span className="mf-label">{label}</span>
      {children}
    </label>
  );
}

const INPUT: React.CSSProperties = {
  background: "var(--mf-panel-2)",
  border: "1px solid var(--mf-border-2)",
  borderRadius: 6,
  padding: "6px 8px",
  color: "var(--mf-fg)",
  font: "inherit",
  fontSize: 12,
  outline: "none",
};

const CHIP_BTN: React.CSSProperties = {
  padding: "6px 10px",
  border: "1px solid var(--mf-border-2)",
  borderRadius: 16,
  font: "inherit",
  fontSize: 11,
  cursor: "pointer",
};

const CLOSE_BTN: React.CSSProperties = {
  width: 24,
  height: 24,
  borderRadius: 6,
  background: "transparent",
  border: "1px solid var(--mf-border-2)",
  color: "var(--mf-dim)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 14,
};

const PRIMARY_BTN: React.CSSProperties = {
  background: "var(--mf-acc)",
  color: "rgba(0,0,0,0.85)",
  border: "none",
  borderRadius: 6,
  padding: "8px 14px",
  fontWeight: 600,
  fontSize: 12,
  cursor: "pointer",
};

const SECONDARY_BTN: React.CSSProperties = {
  background: "var(--mf-panel-3)",
  color: "var(--mf-fg-2)",
  border: "1px solid var(--mf-border-2)",
  borderRadius: 6,
  padding: "8px 14px",
  fontSize: 12,
  cursor: "pointer",
};
