import { useStore } from "../store";

const SAVE_LABEL: Record<string, string> = {
  idle: "",
  saving: "Saving…",
  saved: "Saved ✓",
  error: "Save failed",
};

export function TopBar({ onHelp }: { onHelp: () => void }) {
  const summaries = useStore((s) => s.summaries);
  const docId = useStore((s) => s.docId);
  const status = useStore((s) => s.status);
  const saveState = useStore((s) => s.saveState);
  const prev = useStore((s) => s.prev);
  const next = useStore((s) => s.next);
  const markDone = useStore((s) => s.markDone);

  const done = summaries.filter((d) => d.status === "done").length;
  const total = summaries.length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const idx = summaries.findIndex((d) => d.doc_id === docId);

  return (
    <div className="topbar">
      <span className="title">NER Entity Annotator</span>
      <span className="docid">{docId ?? "—"}</span>
      {idx >= 0 && <span style={{ color: "var(--muted)", fontSize: 12 }}>#{idx + 1}/{total}</span>}
      <span className={"status-chip " + status}>{status.replace("_", " ")}</span>

      <span className="spacer" />

      <div className="progress-wrap">
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{done}/{total} done</span>
        <div className="progress-bar"><div style={{ width: `${pct}%` }} /></div>
      </div>

      <span className={"save-pill " + saveState}>{SAVE_LABEL[saveState]}</span>

      <button onClick={prev} title="previous (←)">←</button>
      <button onClick={next} title="next (→)">→</button>
      <button className="primary" onClick={markDone} title="mark done & go to next unreviewed (d)">
        Done &amp; next
      </button>
      <button onClick={onHelp} title="keyboard shortcuts (?)">?</button>
    </div>
  );
}
