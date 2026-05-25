// FileTreePicker — recursive vault tree with checkboxes.
//
// Used by PersonaEditorModal "Vault filter" section to let the user pick
// which notes/folders the persona should "know" (lands in obsidian_notes).
//
// Behaviour:
//   - Lazy load: top-level entries on mount, children on folder expand.
//   - Selection model: leaves OR folder roots stored verbatim in `selected`.
//     A folder selection implies its entire subtree. Children of a selected
//     folder appear as "covered" (greyed) — no need to also tick them.
//   - Folder checkbox states:
//       checked       — this folder path is in `selected`
//       indeterminate — some descendant is in `selected`
//       unchecked     — nothing in subtree
//   - Toggling a folder swaps between {selected, unselected} (clears any
//     descendant selections to avoid redundancy).
//
// Errors on individual readDir calls are swallowed (one bad folder shouldn't
// hide the tree). Performance bound: only loads as the user expands.

import { readDir } from "@tauri-apps/plugin-fs";
import { useCallback, useEffect, useState } from "react";

export interface FileTreePickerProps {
  /** Absolute root path under which to display the tree. */
  rootPath: string;
  /** Currently selected paths (folder or file, vault-relative if you want). */
  selected: string[];
  onChange: (next: string[]) => void;
  /** Filter visible filenames (default: hide dotfiles + leading underscore). */
  hideEntry?: (name: string) => boolean;
}

interface TreeNode {
  name: string;
  path: string;             // absolute
  isDirectory: boolean;
  children?: TreeNode[];    // undefined = not loaded yet
}

const defaultHide = (name: string) =>
  name.startsWith(".") || name.startsWith("_") || name === "node_modules";

export function FileTreePicker({
  rootPath,
  selected,
  onChange,
  hideEntry = defaultHide,
}: FileTreePickerProps) {
  const [root, setRoot] = useState<TreeNode | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const loadDir = useCallback(async (absPath: string): Promise<TreeNode[]> => {
    try {
      const entries = await readDir(absPath);
      const sorted = entries
        .filter((e) => e.name && !hideEntry(e.name))
        .sort((a, b) => {
          // Folders first, then alphabetic
          if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
          return (a.name || "").localeCompare(b.name || "");
        });
      return sorted.map((e) => ({
        name: e.name!,
        path: `${absPath}/${e.name}`,
        isDirectory: !!e.isDirectory,
        children: undefined,
      }));
    } catch (exc) {
      return [];
    }
  }, [hideEntry]);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const children = await loadDir(rootPath);
        if (!cancel) {
          setRoot({ name: "", path: rootPath, isDirectory: true, children });
          setError(null);
        }
      } catch (exc) {
        if (!cancel) setError(String(exc));
      }
    })();
    return () => {
      cancel = true;
    };
  }, [rootPath, loadDir]);

  const toggleExpand = async (node: TreeNode) => {
    const isOpen = expanded.has(node.path);
    if (isOpen) {
      const next = new Set(expanded);
      next.delete(node.path);
      setExpanded(next);
      return;
    }
    // Open + load children if not yet loaded
    if (node.children === undefined) {
      const kids = await loadDir(node.path);
      node.children = kids;
      // Force re-render: rebuild root reference
      setRoot((r) => (r ? { ...r } : r));
    }
    setExpanded(new Set(expanded).add(node.path));
  };

  const checkboxState = (path: string): "checked" | "indeterminate" | "unchecked" => {
    if (selected.includes(path)) return "checked";
    // Indeterminate if any selected entry is a descendant
    const prefix = path.endsWith("/") ? path : path + "/";
    if (selected.some((s) => s.startsWith(prefix))) return "indeterminate";
    return "unchecked";
  };

  const isCoveredByAncestor = (path: string): boolean => {
    return selected.some((s) => path !== s && path.startsWith(s.endsWith("/") ? s : s + "/"));
  };

  const toggle = (path: string) => {
    const state = checkboxState(path);
    if (state === "checked") {
      // Remove this exact entry
      onChange(selected.filter((s) => s !== path));
    } else {
      // Add this, drop any descendants (redundant once parent is selected)
      const prefix = path.endsWith("/") ? path : path + "/";
      onChange([...selected.filter((s) => !s.startsWith(prefix)), path]);
    }
  };

  if (error) return <div style={{ color: "var(--mf-danger)" }}>Erreur tree : {error}</div>;
  if (!root) return <div style={{ color: "var(--mf-dim)", padding: 8 }}>Chargement…</div>;

  return (
    <div style={{
      maxHeight: 280,
      overflowY: "auto",
      border: "1px solid var(--mf-border)",
      borderRadius: 6,
      background: "var(--mf-panel-3)",
      padding: 4,
    }}>
      {(root.children || []).map((child) => (
        <TreeRow
          key={child.path}
          node={child}
          depth={0}
          expanded={expanded}
          toggleExpand={toggleExpand}
          checkboxState={checkboxState}
          isCovered={isCoveredByAncestor}
          onToggle={toggle}
        />
      ))}
    </div>
  );
}

interface RowProps {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  toggleExpand: (n: TreeNode) => void;
  checkboxState: (path: string) => "checked" | "indeterminate" | "unchecked";
  isCovered: (path: string) => boolean;
  onToggle: (path: string) => void;
}

function TreeRow({ node, depth, expanded, toggleExpand, checkboxState, isCovered, onToggle }: RowProps) {
  const isOpen = expanded.has(node.path);
  const state = checkboxState(node.path);
  const covered = isCovered(node.path);
  return (
    <>
      <div style={{
        display: "flex", alignItems: "center", gap: 4, padding: "2px 4px",
        paddingLeft: 4 + depth * 14, fontSize: 12,
        opacity: covered ? 0.45 : 1,
      }}>
        {node.isDirectory ? (
          <button
            type="button"
            aria-label={isOpen ? "Replier" : "Déplier"}
            onClick={() => toggleExpand(node)}
            style={{
              background: "transparent", border: "none", padding: 0,
              cursor: "pointer", color: "var(--mf-dim)", width: 14,
              fontFamily: "var(--mf-mono)",
            }}
          >
            {isOpen ? "▾" : "▸"}
          </button>
        ) : (
          <span style={{ width: 14 }} />
        )}
        <input
          type="checkbox"
          checked={state === "checked"}
          ref={(el) => {
            if (el) el.indeterminate = state === "indeterminate";
          }}
          disabled={covered}
          onChange={() => onToggle(node.path)}
          style={{ accentColor: "var(--mf-acc)" }}
        />
        <span style={{
          color: node.isDirectory ? "var(--mf-fg)" : "var(--mf-fg-2)",
          fontFamily: node.isDirectory ? "var(--mf-display)" : "var(--mf-mono)",
        }}>
          {node.name}
          {node.isDirectory ? "/" : ""}
        </span>
      </div>
      {isOpen && node.children
        ? node.children.map((c) => (
            <TreeRow
              key={c.path}
              node={c}
              depth={depth + 1}
              expanded={expanded}
              toggleExpand={toggleExpand}
              checkboxState={checkboxState}
              isCovered={isCovered}
              onToggle={onToggle}
            />
          ))
        : null}
    </>
  );
}
