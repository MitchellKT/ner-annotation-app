import { useMemo, useState } from "react";
import { useStore } from "../store";
import type { DocStatus } from "../types";

export function DocNavigator() {
  const summaries = useStore((s) => s.summaries);
  const docId = useStore((s) => s.docId);
  const loadDoc = useStore((s) => s.loadDoc);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | DocStatus | "predicted">("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return summaries.filter((d) => {
      if (filter === "predicted" ? !d.has_prediction : filter !== "all" && d.status !== filter) return false;
      return q === "" || d.doc_id.toLowerCase().includes(q);
    });
  }, [summaries, query, filter]);

  return (
    <>
      <div className="nav-tools">
        <input placeholder="Search doc_id…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
          <option value="all">All documents</option>
          <option value="unreviewed">Unreviewed</option>
          <option value="in_progress">In progress</option>
          <option value="done">Done</option>
          <option value="predicted">Has prediction</option>
        </select>
      </div>
      <div className="nav-list">
        {filtered.map((d) => (
          <div
            key={d.doc_id}
            className={"nav-item" + (d.doc_id === docId ? " active" : "")}
            onClick={() => loadDoc(d.doc_id)}
            title={d.doc_id}
          >
            <span className={"dot " + d.status} />
            <span className="nid">{d.doc_id}</span>
            {d.has_prediction && <span className="pred-flag" title="has model prediction">◆</span>}
            <span className="ncount">{d.n_entities}</span>
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: 16, color: "var(--muted)", fontSize: 13 }}>No matches.</div>
        )}
      </div>
    </>
  );
}
