// TagListInput — reusable list editor for short string entries.
//
// Used by PersonaEditorModal for:
//   - tools allowlist (one tool slug per row)
//   - web allowlist (one domain per row)
//   - obsidian_skills (one skill slug per row)
//   - obsidian_notes (one path pattern per row)
//
// Renders a list of removable chips + a single input that adds on Enter or
// blur. Empty values are dropped. Optional dedupe so the same entry can't
// be added twice. Validation is the caller's responsibility — the component
// just edits strings.

import { CSSProperties, KeyboardEvent, useState } from "react";

export interface TagListInputProps {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  /** Drop duplicate entries on add (case-insensitive). Default true. */
  dedupe?: boolean;
  /** Show a hint below the input — e.g. "ex. github.com, claude.ai". */
  hint?: string;
}

const ROW: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
  alignItems: "center",
  padding: 6,
  background: "var(--mf-panel-3)",
  borderRadius: 6,
  border: "1px solid var(--mf-border)",
  minHeight: 32,
};

const CHIP: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "2px 6px",
  background: "var(--mf-panel-2)",
  border: "1px solid var(--mf-border-2)",
  borderRadius: 12,
  fontSize: 12,
  color: "var(--mf-fg)",
  fontFamily: "var(--mf-mono)",
};

const CHIP_X: CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--mf-dim)",
  cursor: "pointer",
  padding: 0,
  fontSize: 14,
  lineHeight: 1,
};

const INPUT: CSSProperties = {
  flex: 1,
  minWidth: 80,
  border: "none",
  outline: "none",
  background: "transparent",
  color: "var(--mf-fg)",
  fontSize: 12,
  fontFamily: "var(--mf-mono)",
  padding: 2,
};

const HINT: CSSProperties = {
  marginTop: 4,
  fontSize: 11,
  color: "var(--mf-dim)",
};

export function TagListInput({
  values,
  onChange,
  placeholder = "Ajouter…",
  dedupe = true,
  hint,
}: TagListInputProps) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const v = draft.trim();
    if (!v) {
      setDraft("");
      return;
    }
    if (dedupe && values.some((x) => x.toLowerCase() === v.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  };

  const remove = (idx: number) => {
    const next = values.slice();
    next.splice(idx, 1);
    onChange(next);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
      // Backspace on empty input pops the last chip.
      remove(values.length - 1);
    }
  };

  return (
    <div>
      <div style={ROW}>
        {values.map((v, idx) => (
          <span key={`${v}-${idx}`} style={CHIP}>
            {v}
            <button
              type="button"
              aria-label={`Supprimer ${v}`}
              style={CHIP_X}
              onClick={() => remove(idx)}
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={commit}
          style={INPUT}
        />
      </div>
      {hint ? <div style={HINT}>{hint}</div> : null}
    </div>
  );
}
