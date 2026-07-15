import { useMemo, useState } from "react";
import { useStore, hasSelection } from "../store";
import type { Selection } from "../types";

/**
 * After login: choose which sources to label under each document type. The
 * selection is saved per-user and filters the documents shown while annotating.
 */
export function SourceSelector() {
  const meta = useStore((s) => s.meta);
  const username = useStore((s) => s.username);
  const loading = useStore((s) => s.loading);
  const saveSelection = useStore((s) => s.saveSelection);
  const setPhase = useStore.setState;

  const types = useMemo(
    () => Object.keys(meta?.sourcesByType ?? {}).sort(),
    [meta]
  );

  // Local editable selection as sets keyed by type.
  const [picked, setPicked] = useState<Record<string, Set<string>>>(() => {
    const init: Record<string, Set<string>> = {};
    for (const t of Object.keys(meta?.sourcesByType ?? {})) {
      init[t] = new Set(meta?.selection?.[t] ?? []);
    }
    return init;
  });

  if (!meta) return null;

  const countFor = (t: string, s: string) => meta.counts[t]?.[s] ?? 0;

  function toggle(type: string, source: string) {
    setPicked((prev) => {
      const next = new Set(prev[type]);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return { ...prev, [type]: next };
    });
  }

  function toggleType(type: string, on: boolean) {
    setPicked((prev) => ({
      ...prev,
      [type]: on ? new Set(meta!.sourcesByType[type]) : new Set(),
    }));
  }

  const selection: Selection = useMemo(() => {
    const out: Selection = {};
    for (const [t, set] of Object.entries(picked)) {
      if (set.size > 0) out[t] = [...set];
    }
    return out;
  }, [picked]);

  const selectedDocs = useMemo(() => {
    let n = 0;
    for (const [t, sources] of Object.entries(selection)) {
      for (const s of sources) n += countFor(t, s);
    }
    return n;
  }, [selection, meta]);

  const anySelected = selectedDocs > 0;
  const alreadyHadSelection = hasSelection(meta.selection);

  return (
    <div className="gate gate-wide">
      <div className="gate-card select-card">
        <div className="select-head">
          <div>
            <h1 className="gate-title">Choose sources to annotate</h1>
            <p className="gate-sub">
              Signed in as <strong>{username}</strong>. Pick the sources you want to label under
              each text type.
            </p>
          </div>
          {alreadyHadSelection && (
            <button
              onClick={() => setPhase({ phase: "annotate" })}
              title="keep the current selection and go back"
            >
              ← Back
            </button>
          )}
        </div>

        <div className="select-body">
          {types.length === 0 && <div className="gate-sub">No documents were loaded.</div>}
          {types.map((type) => {
            const sources = meta.sourcesByType[type];
            const set = picked[type] ?? new Set<string>();
            const allOn = set.size === sources.length;
            return (
              <div key={type} className="select-group">
                <div className="select-group-head">
                  <span className="select-type">{type}</span>
                  <span className="select-type-count">{sources.length} source(s)</span>
                  <button
                    className="select-all-btn"
                    onClick={() => toggleType(type, !allOn)}
                  >
                    {allOn ? "Clear" : "Select all"}
                  </button>
                </div>
                <div className="select-sources">
                  {sources.map((source) => (
                    <label key={source} className="select-source">
                      <input
                        type="checkbox"
                        checked={set.has(source)}
                        onChange={() => toggle(type, source)}
                      />
                      <span className="select-source-name">{source}</span>
                      <span className="select-source-count">{countFor(type, source)}</span>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="select-footer">
          <span className="gate-sub" style={{ margin: 0 }}>
            {anySelected ? `${selectedDocs} document(s) selected` : "No sources selected yet"}
          </span>
          <button
            className="primary"
            disabled={!anySelected || loading}
            onClick={() => void saveSelection(selection)}
          >
            {loading ? "Loading…" : "Start annotating"}
          </button>
        </div>
      </div>
    </div>
  );
}
