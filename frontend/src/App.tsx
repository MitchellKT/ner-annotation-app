import { useEffect, useState } from "react";
import { useStore } from "./store";
import { useSession } from "./session";
import { useKeyboard } from "./hooks/useKeyboard";
import { TopBar } from "./components/TopBar";
import { DocNavigator } from "./components/DocNavigator";
import { TextPanel } from "./components/TextPanel";
import { EntityPanel } from "./components/EntityPanel";
import { KeyboardHelp } from "./components/KeyboardHelp";
import { UidPrompt } from "./components/UidPrompt";
import { NameScreen } from "./components/NameScreen";
import { UploadScreen } from "./components/UploadScreen";
import { cpSlice } from "./lib/offsets";
import { colorForType } from "./colors";

export default function App() {
  const phase = useSession((s) => s.phase);
  const bootstrap = useSession((s) => s.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  if (phase === "booting") return <div className="gate"><div className="center-msg">Loading…</div></div>;
  if (phase === "name") return <NameScreen />;
  if (phase === "upload") return <UploadScreen />;
  return <Annotator />;
}

function Annotator() {
  const init = useStore((s) => s.init);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const docId = useStore((s) => s.docId);
  const warnings = useStore((s) => s.config?.warnings ?? []);
  const autoMatch = useStore((s) => s.autoMatch);
  const setAutoMatch = useStore((s) => s.setAutoMatch);
  const selectionSpan = useStore((s) => s.selectionSpan);
  const cps = useStore((s) => s.cps);
  const activeEntityId = useStore((s) => s.activeEntityId);
  const entities = useStore((s) => s.entities);
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);

  const uidPromptEntityId = useStore((s) => s.uidPromptEntityId);

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
            <label title="when you annotate a mention, automatically annotate every identical (case-sensitive, Ctrl+F style) occurrence in the document too — remove unwanted ones as usual">
              <input
                type="checkbox"
                checked={autoMatch}
                onChange={(e) => setAutoMatch(e.target.checked)}
              />
              auto-annotate repeats
            </label>
            <span className="type-legend" title="press a number to create an entity of that type from the selection">
              {types.slice(0, 9).map((t, i) => (
                <span key={t} className="type-legend-item">
                  <kbd>{i + 1}</kbd>
                  <span className="type-chip" style={{ background: colorForType(t) }}>{t}</span>
                </span>
              ))}
            </span>
            <span className="spacer" style={{ flex: 1 }} />
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {selPreview ? (
                <>selection: <strong>“<bdi>{selPreview.slice(0, 40)}</bdi>”</strong> — press a number, or click an entity to add</>
              ) : (
                `active entity: ${activeIdx >= 0 ? `#${activeIdx + 1} (${entities[activeIdx].type})` : "none"}`
              )}
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

      {/* keyed so the input state resets when the prompt targets a new entity */}
      {uidPromptEntityId && <UidPrompt key={uidPromptEntityId} />}
      {showHelp && <KeyboardHelp onClose={() => setShowHelp(false)} />}
    </div>
  );
}
