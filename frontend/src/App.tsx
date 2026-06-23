import { useEffect, useState } from "react";
import { useStore } from "./store";
import { useKeyboard } from "./hooks/useKeyboard";
import { TopBar } from "./components/TopBar";
import { DocNavigator } from "./components/DocNavigator";
import { TextPanel } from "./components/TextPanel";
import { EntityPanel } from "./components/EntityPanel";
import { KeyboardHelp } from "./components/KeyboardHelp";
import { cpSlice } from "./lib/offsets";

export default function App() {
  const init = useStore((s) => s.init);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const docId = useStore((s) => s.docId);
  const warnings = useStore((s) => s.config?.warnings ?? []);
  const snap = useStore((s) => s.snap);
  const setSnap = useStore((s) => s.setSnap);
  const selectionSpan = useStore((s) => s.selectionSpan);
  const cps = useStore((s) => s.cps);
  const activeEntityId = useStore((s) => s.activeEntityId);
  const entities = useStore((s) => s.entities);

  const [showHelp, setShowHelp] = useState(false);
  useKeyboard(() => setShowHelp((v) => !v));

  useEffect(() => {
    void init();
  }, [init]);

  const activeIdx = entities.findIndex((e) => e.id === activeEntityId);
  const selPreview = selectionSpan ? cpSlice(cps, selectionSpan.start, selectionSpan.end) : "";

  return (
    <div className="app">
      <TopBar onHelp={() => setShowHelp(true)} />
      {warnings.length > 0 && (
        <div className="banner">
          ⚠ {warnings.length} load warning(s): {warnings.slice(0, 3).join("; ")}
          {warnings.length > 3 ? " …" : ""}
        </div>
      )}
      <div className="main">
        <div className="col-nav">
          <DocNavigator />
        </div>

        <div className="col-text">
          <div className="text-toolbar">
            <label>
              <input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} />
              snap to words
            </label>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {selPreview ? (
                <>selection: <strong>“<bdi>{selPreview.slice(0, 40)}</bdi>”</strong> — press <kbd>P L O T</kbd>, <kbd>1-9</kbd>, or click an entity</>
              ) : (
                "select text to annotate"
              )}
            </span>
            <span className="spacer" style={{ flex: 1 }} />
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              active entity: {activeIdx >= 0 ? `#${activeIdx + 1} (${entities[activeIdx].type})` : "none"}
            </span>
          </div>
          {loading && <div className="center-msg">Loading…</div>}
          {error && <div className="center-msg" style={{ color: "var(--danger)" }}>{error}</div>}
          {!loading && !error && !docId && <div className="center-msg">No documents.</div>}
          {!loading && docId && <TextPanel />}
        </div>

        <div className="col-entities">
          <EntityPanel />
        </div>
      </div>

      {showHelp && <KeyboardHelp onClose={() => setShowHelp(false)} />}
    </div>
  );
}
