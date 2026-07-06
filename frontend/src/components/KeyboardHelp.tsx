import { Fragment } from "react";
import { useStore } from "../store";

export function KeyboardHelp({ onClose }: { onClose: () => void }) {
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);

  // Show which digit creates which type (only the first nine are reachable).
  const digitLegend = types
    .slice(0, 9)
    .map((t, i) => `${i + 1}=${t}`)
    .join("  ");

  const rows: [string, string][] = [
    ["1 – 9", `New entity from the selected text (${digitLegend || "by type"}) — with “auto-annotate repeats” on, identical text elsewhere is annotated too`],
    ["1 – 9 (no selection)", "Change the active entity's type"],
    ["click entity (text selected)", "Add the selection to that entity (the only way to extend an entity)"],
    ["Enter / Esc (id prompt)", "Save / skip the optional unique identifier asked after creating an entity"],
    ["x", "Extend a mention with the selection (non-continuous mention: hovered mention, else the active entity's last)"],
    ["click mention chip (text selected)", "Add the selection as a fragment of that mention"],
    ["n", "New empty entity"],
    ["Tab / Shift+Tab", "Cycle the active entity"],
    ["click highlight", "Make that entity active"],
    ["Del / Backspace", "Delete the hovered mention"],
    ["r", "Confirm / unconfirm the active entity"],
    ["A", "Accept all (confirm every entity)"],
    ["m", "Merge: press m, then click another entity (or drag card onto card)"],
    ["s", "Split the hovered mention into its own entity"],
    ["drag chip → card", "Reassign a mention to another entity"],
    ["drag chip → empty space", "Split that mention out into a new entity"],
    ["Esc", "Cancel a pending merge / clear selection"],
    ["Ctrl+Z / Ctrl+Shift+Z", "Undo / redo"],
    ["d", "Mark document done & go to next unreviewed"],
    ["← / →", "Previous / next document"],
    ["?", "Toggle this help"],
  ];

  return (
    <div className="overlay" onClick={onClose}>
      <div className="help-card" onClick={(e) => e.stopPropagation()}>
        <h2>Keyboard shortcuts</h2>
        <p style={{ color: "var(--muted)", marginTop: -8 }}>
          Select text, then assign it to an entity. Set an entity “active” to add several mentions to it quickly.
        </p>
        <div className="help-grid">
          {rows.map(([k, d]) => (
            <Fragment key={k}>
              <kbd className="k">{k}</kbd>
              <span>{d}</span>
            </Fragment>
          ))}
        </div>
        <div style={{ textAlign: "right", marginTop: 18 }}>
          <button className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
