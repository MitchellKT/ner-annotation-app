import { useState } from "react";
import { useSession } from "../session";

export function NameScreen() {
  const identify = useSession((s) => s.identify);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);
  const [name, setName] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim() && !busy) void identify(name.trim());
  };

  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <h1>NER Entity Annotator</h1>
        <p className="gate-sub">Enter your name to begin. Your annotations are saved under this name.</p>
        <input
          className="gate-input"
          autoFocus
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="primary gate-btn" type="submit" disabled={!name.trim() || busy}>
          {busy ? "…" : "Continue"}
        </button>
        {error && <div className="gate-error">{error}</div>}
      </form>
    </div>
  );
}
