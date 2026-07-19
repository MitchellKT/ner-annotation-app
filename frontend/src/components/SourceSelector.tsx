import { useMemo, useState } from "react";
import { useStore, hasSelection } from "../store";
import type { Selection } from "../types";

/**
 * After login: choose which sources to label under each document type. The
 * selection is saved per-user and filters the documents shown while annotating.
 *
 * Built to stay usable with many sources per type: the source lists flow into
 * as many columns as fit, type headers stick while scrolling, and a filter box
 * narrows long lists (with "select all" then acting on just the matches).
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

  const [filter, setFilter] = useState("");

  // Local editable selection as sets keyed by type. A first-time annotator
  // starts with everything selected; a returning one gets their saved picks.
  const [picked, setPicked] = useState<Record<string, Set<string>>>(() => {
    const sourcesByType = meta?.sourcesByType ?? {};
    const saved = hasSelection(meta?.selection);
    const init: Record<string, Set<string>> = {};
    for (const [t, sources] of Object.entries(sourcesByType)) {
      init[t] = new Set(saved ? meta?.selection?.[t] ?? [] : sources);
    }
    return init;
  });

  const needle = filter.trim().toLowerCase();

  /** Sources of a type matching the current filter, in display order. */
  const visibleSources = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const [t, sources] of Object.entries(meta?.sourcesByType ?? {})) {
      out[t] = needle
        ? sources.filter((s) => s.toLowerCase().includes(needle))
        : sources;
    }
    return out;
  }, [meta, needle]);

  const totalSources = useMemo(
    () => Object.values(meta?.sourcesByType ?? {}).reduce((n, s) => n + s.length, 0),
    [meta]
  );
  const totalVisible = useMemo(
    () => Object.values(visibleSources).reduce((n, s) => n + s.length, 0),
    [visibleSources]
  );

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
      for (const s of sources) n += meta?.counts[t]?.[s] ?? 0;
    }
    return n;
  }, [selection, meta]);

  const selectedSources = useMemo(
    () => Object.values(picked).reduce((n, set) => n + set.size, 0),
    [picked]
  );

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

  /** Turn the currently visible (filtered) sources of a type on or off. */
  function toggleType(type: string, on: boolean) {
    setPicked((prev) => {
      const next = new Set(prev[type]);
      for (const s of visibleSources[type] ?? []) {
        if (on) next.add(s);
        else next.delete(s);
      }
      return { ...prev, [type]: next };
    });
  }

  /** Turn every visible source, across all types, on or off. */
  function toggleAll(on: boolean) {
    setPicked((prev) => {
      const next: Record<string, Set<string>> = {};
      for (const [t, set] of Object.entries(prev)) {
        const copy = new Set(set);
        for (const s of visibleSources[t] ?? []) {
          if (on) copy.add(s);
          else copy.delete(s);
        }
        next[t] = copy;
      }
      return next;
    });
  }

  const anySelected = selectedDocs > 0;
  const alreadyHadSelection = hasSelection(meta.selection);
  const allVisibleOn =
    totalVisible > 0 &&
    types.every((t) => (visibleSources[t] ?? []).every((s) => picked[t]?.has(s)));

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

        {totalSources > 8 && (
          <div className="select-tools">
            <input
              className="select-filter"
              value={filter}
              placeholder={`Filter ${totalSources} sources…`}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button onClick={() => toggleAll(!allVisibleOn)} disabled={totalVisible === 0}>
              {allVisibleOn ? "Clear" : "Select"} {needle ? "matches" : "all"}
            </button>
            <span className="select-tally">
              {selectedSources} / {totalSources} selected
            </span>
          </div>
        )}

        <div className="select-body">
          {types.length === 0 && <div className="gate-sub">No documents were loaded.</div>}
          {needle && totalVisible === 0 && (
            <div className="gate-sub">No sources match “{filter.trim()}”.</div>
          )}
          {types.map((type) => {
            const sources = visibleSources[type] ?? [];
            if (needle && sources.length === 0) return null;
            const set = picked[type] ?? new Set<string>();
            const allOn = sources.length > 0 && sources.every((s) => set.has(s));
            const total = meta.sourcesByType[type].length;
            return (
              <div key={type} className="select-group">
                <div className="select-group-head">
                  <span className="select-type">{type}</span>
                  <span className="select-type-count">
                    {set.size} / {total} selected
                    {needle && ` · ${sources.length} shown`}
                  </span>
                  <button className="select-all-btn" onClick={() => toggleType(type, !allOn)}>
                    {allOn ? "Clear" : "Select all"}
                  </button>
                </div>
                <div className="select-sources">
                  {sources.map((source) => (
                    <label
                      key={source}
                      className="select-source"
                      title={`${source} — ${countFor(type, source)} document(s)`}
                    >
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
