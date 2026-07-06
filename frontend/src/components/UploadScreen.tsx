import { useState } from "react";
import { useSession } from "../session";

const DEFAULT_TYPES = "PER,LOC,ORG,TIME";

export function UploadScreen() {
  const session = useSession((s) => s.session);
  const workspace = useSession((s) => s.workspace);
  const upload = useSession((s) => s.upload);
  const signOut = useSession((s) => s.signOut);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);

  const [file, setFile] = useState<File | null>(null);
  const [types, setTypes] = useState(workspace?.types?.join(",") ?? DEFAULT_TYPES);
  const [dragOver, setDragOver] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (file && !busy) void upload(file, types.trim() || DEFAULT_TYPES);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  return (
    <div className="gate">
      <form className="gate-card wide" onSubmit={submit}>
        <div className="gate-top">
          <h1>Upload a file to annotate</h1>
          <span className="gate-who">
            {session?.name} · <button type="button" className="linkish" onClick={() => void signOut()}>switch user</button>
          </span>
        </div>
        <p className="gate-sub">
          A <code>.jsonl</code> file, one record per line:{" "}
          <code>{`{"doc_id": "...", "text": "...", "entities": [...]}`}</code>. Only <code>doc_id</code> and{" "}
          <code>text</code> are required.
        </p>

        <label
          className={"dropzone" + (dragOver ? " over" : "")}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <input
            type="file"
            accept=".jsonl,.json,.ndjson,application/json,application/x-ndjson,text/plain"
            style={{ display: "none" }}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <span>
              <strong>{file.name}</strong> ({Math.ceil(file.size / 1024)} KB)
            </span>
          ) : (
            <span>Click to choose a file, or drag it here</span>
          )}
        </label>

        <label className="gate-field">
          <span>Entity types (comma-separated, first 9 map to keys 1–9)</span>
          <input
            className="gate-input"
            value={types}
            onChange={(e) => setTypes(e.target.value)}
            placeholder={DEFAULT_TYPES}
          />
        </label>

        <button className="primary gate-btn" type="submit" disabled={!file || busy}>
          {busy ? "Uploading…" : "Start annotating"}
        </button>
        {workspace && (
          <div className="gate-note">
            Replacing your current file (<strong>{workspace.filename}</strong>,{" "}
            {workspace.n_done}/{workspace.n_docs} done) archives it — nothing is lost.
          </div>
        )}
        {error && <div className="gate-error">{error}</div>}
      </form>
    </div>
  );
}
