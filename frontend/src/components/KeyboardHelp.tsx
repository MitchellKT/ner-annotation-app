import { Fragment } from "react";

const ROWS: [string, string][] = [
  ["P / L / O / T", "New entity (PER/LOC/ORG/TIME) from the selected text"],
  ["1 – 9", "Add selection to entity N (and make it active)"],
  ["click entity (text selected)", "Add the selection to that entity — works for any entity, incl. beyond 9"],
  ["a", "Add selection to the active entity"],
  ["n", "New empty entity"],
  ["Tab / Shift+Tab", "Cycle the active entity"],
  ["click highlight", "Make that entity active"],
  ["Del / Backspace", "Delete the hovered mention"],
  ["r", "Confirm / unconfirm the active entity"],
  ["A", "Accept all (confirm every entity)"],
  ["m", "Merge: press m, then click another entity (or drag card onto card)"],
  ["s", "Split the hovered mention into its own entity"],
  ["drag chip → card", "Reassign a mention to another entity"],
  ["Esc", "Cancel a pending merge / clear selection"],
  ["Ctrl+Z / Ctrl+Shift+Z", "Undo / redo"],
  ["d", "Mark document done & go to next unreviewed"],
  ["← / →", "Previous / next document"],
  ["?", "Toggle this help"],
];

export function KeyboardHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="help-card" onClick={(e) => e.stopPropagation()}>
        <h2>Keyboard shortcuts</h2>
        <p style={{ color: "var(--muted)", marginTop: -8 }}>
          Select text, then assign it to an entity. Set an entity “active” to add several mentions to it quickly.
        </p>
        <div className="help-grid">
          {ROWS.map(([k, d]) => (
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
